"""簡易関係対話：語彙ノードと構造化発話イベント。

参照:
  RDL_NPC行動決定システム §5.5（簡易関係対話システム）
  RDL_簡易村シミュレーター §9（簡易対話）

NPC同士は表示文を再解析しない（NPC§12-8）。
surface_text は表示用で、意味は DialogueEvent が構造として運ぶ。
LLMは必須構成に含めない。
"""

from collections import defaultdict
from dataclasses import dataclass, field

from .core import Phase, clamp

SPEECH_ACTS = ("greet", "ask", "tell", "invite", "agree", "refuse", "thank", "apologize", "end_talk")

# H_dialogue の内訳（NPC§5.5）
DIALOGUE_H_KEYS = ("no_match", "rejection", "repetition", "topic_failure", "relation")


@dataclass
class DialogueIntent:
    speech_act: str
    topic: str
    target: str
    stance: str
    desired_effect: str


@dataclass
class DialogueEvent:
    """受信側は surface_text を解析しない。構造をFとして受け取る（NPC§5.5）。"""

    speaker: str
    listener: str
    speech_act: str
    topic: str
    stance: str
    desired_effect: str
    referenced_entities: tuple = ()
    expected_response_types: tuple = ()
    surface_text: str = ""

    def as_record(self):
        return {
            "speaker": self.speaker,
            "listener": self.listener,
            "speech_act": self.speech_act,
            "topic": self.topic,
            "stance": self.stance,
            "text": self.surface_text,
        }


@dataclass
class DialogueNode:
    """語彙ノード。関係記憶と同様に代謝する（NPC§5.5）。"""

    id: str
    speech_act: str
    dialogue_type: str
    topic_tags: tuple
    templates: tuple
    relations: tuple = ()
    confidence: float = 0.45
    ttl: int = 240
    usage_count: int = 0
    phase: Phase = Phase.LAT
    status: str = "active"

    def usable(self):
        return self.status == "active"

    def foreground(self):
        """潜在相は前景化していない（NPC§3.7）。

        除外はしない。初期語彙はすべて M_lat から始まるため、
        排除すると会話が成立しなくなる。選ばれにくくすることで接続する。
        """
        return 1.0 if self.phase is Phase.ACT else 0.55


def build_vocabulary():
    """v0.1の最小語彙。表現の豊かさではなく、交換される関係作用を保持する。"""
    return [
        DialogueNode("greet_morning", "greet", "関係性開始", ("plan", "weather"),
                     ("おはよう。今日は早いね", "おはよう"), ("ask_plan", "invite_place")),
        DialogueNode("greet_plain", "greet", "関係性開始", ("person",),
                     ("やあ", "こんにちは"), ("ask_state", "invite_place")),
        DialogueNode("greet_night", "greet", "関係性開始", ("weather",),
                     ("こんばんは", "まだ起きてたんだ"), ("ask_state", "end_bye")),
        DialogueNode("ask_plan", "ask", "境界打診", ("plan",),
                     ("これからどこ行くの？",), ("tell_plan", "refuse_tired")),
        DialogueNode("ask_state", "ask", "境界打診", ("feeling",),
                     ("調子はどう？",), ("tell_state", "refuse_tired")),
        DialogueNode("ask_resource", "ask", "境界打診", ("food",),
                     ("{place}に何かあった？",), ("tell_resource", "refuse_tired")),
        DialogueNode("tell_plan", "tell", "報告", ("plan",),
                     ("{place}に行くところ",), ("invite_place", "agree_plain")),
        DialogueNode("tell_state", "tell", "報告", ("feeling",),
                     ("少し疲れたよ", "悪くないよ"), ("agree_plain", "end_bye")),
        DialogueNode("tell_resource", "tell", "報告", ("food", "place"),
                     ("{place}なら少しあったよ", "{place}は空だった"), ("thank_plain", "agree_plain")),
        DialogueNode("invite_place", "invite", "関係性開始", ("place", "plan"),
                     ("{place}まで一緒に行かない？",), ("agree_plain", "refuse_tired")),
        DialogueNode("agree_plain", "agree", "同意", ("plan",),
                     ("いいよ", "そうしよう"), ("end_bye",)),
        DialogueNode("refuse_tired", "refuse", "拒否", ("feeling",),
                     ("ごめん。今は少し休みたい",), ("apologize_plain", "end_bye")),
        DialogueNode("refuse_busy", "refuse", "拒否", ("plan",),
                     ("今はちょっと無理かな",), ("apologize_plain", "end_bye")),
        DialogueNode("thank_plain", "thank", "修復", ("person",),
                     ("ありがとう", "助かったよ"), ("end_bye",)),
        DialogueNode("apologize_plain", "apologize", "修復", ("person",),
                     ("ごめん",), ("end_bye",)),
        DialogueNode("end_bye", "end_talk", "閉鎖", ("person",),
                     ("またね", "じゃあ"), ()),
    ]


class RelationalDialogueSystem:
    """発話意図・話題・語彙ノードを短文へ変換し、構造化イベントを交換する。"""

    def __init__(self, coeffs, rng):
        self.coeffs = coeffs
        self.rng = rng
        self.nodes = {node.id: node for node in build_vocabulary()}
        self.h_dialogue = {key: 0.0 for key in DIALOGUE_H_KEYS}
        self.turns = defaultdict(int)
        self.recent = defaultdict(list)
        self.last_talk_t = defaultdict(lambda: -999)
        self.xi_pool = []

    def _refresh(self, partner, t):
        """間が空けば会話は仕切り直しになる。ターン上限は1回の会話に対する制限。"""
        if t - self.last_talk_t[partner] > 12:
            self.turns[partner] = 0
            self.recent[partner] = []
        self.last_talk_t[partner] = t

    # --- 選択 ---

    def _candidates(self, speech_acts, topic_hint=None):
        found = [
            node
            for node in self.nodes.values()
            if node.usable() and node.speech_act in speech_acts
        ]
        if topic_hint:
            preferred = [node for node in found if topic_hint in node.topic_tags]
            if preferred:
                return preferred
        return found

    def _pick(self, candidates, partner):
        if not candidates:
            self.h_dialogue["no_match"] = clamp(self.h_dialogue["no_match"] + 0.3, 0.0, 2.0)
            return None
        history = self.recent[partner]
        scored = []
        for node in candidates:
            score = (node.confidence + node.usage_count * 0.004) * node.foreground()
            # 反復しすぎた表現には新規性ペナルティ（NPC§5.5）
            score -= history.count(node.id) * self.coeffs.repetition_penalty
            score += self.rng.uniform(-0.05, 0.05)
            scored.append((node, score))
        return max(scored, key=lambda item: item[1])[0]

    def open(self, npc, partner, relation, perception):
        """会話の開始発話を作る。終了条件に達していれば None。"""
        self._refresh(partner, perception.t)
        if self.turns[partner] >= self.coeffs.max_turns:
            return None
        if perception.band == "night":
            acts, topic = ("greet",), "weather"
        elif perception.band == "morning":
            acts, topic = ("greet",), "plan"
        elif relation.familiarity > 0.35:
            acts, topic = ("ask", "invite"), "plan"
        else:
            acts, topic = ("greet",), "person"
        if relation.obligation > 0.35:
            acts, topic = ("thank",), "person"
        elif relation.irritation > 0.45:
            acts, topic = ("apologize",), "person"
        elif npc.body.crisis() > 0.5 and relation.familiarity > 0.2:
            # 身体的な不足があり、相手を多少知っていれば資源を尋ねる。
            acts, topic = ("ask",), "food"
        node = self._pick(self._candidates(acts, topic), partner)
        if node is None:
            return None
        return self._realize(node, npc, partner, relation, perception)

    def reply(self, event, npc, relation, perception):
        """受信した DialogueEvent へ応答する。surface_text は解析しない。"""
        partner = event.speaker
        self._refresh(partner, perception.t)
        self.turns[partner] += 1
        if self.turns[partner] >= self.coeffs.max_turns:
            node = self.nodes["end_bye"]
            return self._realize(node, npc, partner, relation, perception), False

        expected = event.expected_response_types or ("agree", "refuse")
        tired = npc.body.fatigue_ratio() > 0.7 or npc.body.hunger_ratio() > 0.75
        willing = relation.talk_gradient() + (0.3 if not tired else -0.45)
        willing += self.rng.uniform(-0.12, 0.12)

        if event.speech_act == "end_talk":
            return self._realize(self.nodes["end_bye"], npc, partner, relation, perception), True
        if event.speech_act == "thank":
            return self._realize(self.nodes["agree_plain"], npc, partner, relation, perception), True
        if event.speech_act == "apologize":
            accepted = willing > -0.2
            node = self.nodes["agree_plain"] if accepted else self.nodes["refuse_busy"]
            return self._realize(node, npc, partner, relation, perception), accepted

        accepted = willing > 0.05
        if accepted:
            acts = tuple(act for act in expected if act in {"agree", "tell", "thank"}) or ("agree",)
        else:
            acts = ("refuse",)
        node = self._pick(self._candidates(acts, event.topic), partner)
        if node is None:
            self.xi_pool.append((event.speech_act, event.topic))
            node = self.nodes["end_bye"]
            accepted = False
        return self._realize(node, npc, partner, relation, perception), accepted

    def _realize(self, node, npc, partner, relation, perception):
        template = node.templates[self.rng.randrange(len(node.templates))]
        place_label = npc.intended_place_label or perception.place_id or "広場"
        surface = template.format(place=place_label, other=partner)
        stance = "好意" if relation.talk_gradient() > 0.3 else "警戒" if relation.fear > 0.25 else "中立"
        node.usage_count += 1
        node.confidence = clamp(node.confidence + self.coeffs.confidence_gain * 0.35, 0.02, 0.98)
        node.ttl = self.coeffs.node_ttl
        if node.confidence >= self.coeffs.activation_threshold:
            node.phase = Phase.ACT
        history = self.recent[partner]
        history.append(node.id)
        del history[:-6]
        return DialogueEvent(
            speaker=npc.name,
            listener=partner,
            speech_act=node.speech_act,
            topic=node.topic_tags[0] if node.topic_tags else "person",
            stance=stance,
            desired_effect=node.dialogue_type,
            referenced_entities=(place_label,),
            expected_response_types=tuple(
                self.nodes[next_id].speech_act for next_id in node.relations if next_id in self.nodes
            ),
            surface_text=surface,
        )

    # --- 結果とH ---

    def register_outcome(self, partner, event, accepted, relation_error=None):
        node_id = self.recent[partner][-1] if self.recent[partner] else None
        node = self.nodes.get(node_id)
        if node is None:
            return
        if accepted:
            node.confidence = clamp(node.confidence + self.coeffs.confidence_gain, 0.02, 0.98)
            for key in DIALOGUE_H_KEYS:
                self.h_dialogue[key] *= 0.88
        else:
            node.confidence = clamp(node.confidence - self.coeffs.confidence_loss, 0.02, 0.98)
            self.h_dialogue["rejection"] = clamp(self.h_dialogue["rejection"] + 0.25, 0.0, 2.0)
            if node.confidence <= 0.08:
                node.status = "quarantined"
        history = self.recent[partner]
        if len(history) >= 3 and history[-1] == history[-2] == history[-3]:
            self.h_dialogue["repetition"] = clamp(self.h_dialogue["repetition"] + 0.3, 0.0, 2.0)
        if relation_error is not None:
            self.h_dialogue["relation"] = clamp(
                self.h_dialogue["relation"] * 0.8 + relation_error * 0.5, 0.0, 2.0
            )

    def pressure(self):
        return max(self.h_dialogue.values()) if self.h_dialogue else 0.0

    def close(self, partner):
        self.turns[partner] = 0

    def metabolize(self):
        for node in self.nodes.values():
            node.ttl -= 1
            if node.confidence < self.coeffs.activation_threshold:
                node.phase = Phase.LAT
            if node.ttl <= 0:
                node.phase = Phase.LAT
                node.confidence = clamp(node.confidence - 0.02, 0.02, 0.98)
                node.ttl = self.coeffs.ttl_recovery
        for key in self.h_dialogue:
            self.h_dialogue[key] *= 0.96

    def on_leap(self):
        """H_dialogue Leap：話題変更 / 会話終了 / 語彙ノード再接続（村§12.3）。"""
        actions = []
        for partner in list(self.turns):
            self.turns[partner] = 0
            self.recent[partner] = []
        actions.append("会話をリセット")
        quarantined = [node for node in self.nodes.values() if node.status == "quarantined"]
        for node in quarantined[:2]:
            node.status = "active"
            node.confidence = 0.3
            node.phase = Phase.LAT
            actions.append(f"{node.id}を再接続")
        for key in self.h_dialogue:
            self.h_dialogue[key] *= 0.28
        return actions
