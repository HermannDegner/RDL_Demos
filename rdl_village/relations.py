"""方向つき個体間関係と、状況・行動・結果のW_ij。

参照:
  RDL_簡易村シミュレーター §4.3（村内関係場）, §5.3（関係状態）, §11（関係更新）
  RDL_NPC行動決定システム §3.4（W_ij）, §5.3（関係記憶・整合慣性システム）, §8（学習規則）

好感度一軸で対人行動を決めない（村§19-3）。
関係は方向つきで保持する： RelationState[A][B] ≠ RelationState[B][A]。
"""

from collections import defaultdict
from dataclasses import dataclass, field

from .core import Phase, clamp

CORE_AXES = ("familiarity", "trust", "affinity", "fear", "irritation", "obligation")


@dataclass
class RelationState:
    """相手ごとの多軸関係（村§5.3）。"""

    other: str
    familiarity: float = 0.0
    trust: float = 0.0
    affinity: float = 0.0
    fear: float = 0.0
    irritation: float = 0.0
    obligation: float = 0.0
    predictability: float = 0.5
    dependency: float = 0.0
    territoriality: float = 0.0
    last_contact: int = 0
    # 処理されなかった熱が固着したもの。熱ではなく構造なので、
    # 接触がなくても薄れにくく、再会したときに熱へ戻る。
    residue: float = 0.0
    shared_history: list = field(default_factory=list)

    def nudge(self, axis, delta, low=-1.0, high=1.0):
        setattr(self, axis, clamp(getattr(self, axis) + delta, low, high))

    def touch(self, t):
        self.last_contact = t

    def approach_gradient(self):
        """接近方向の正味勾配。単一の好感度ではなく複数軸の合成。"""
        return (
            self.affinity * 0.9
            + self.familiarity * 0.35
            + self.trust * 0.4
            + self.obligation * 0.25
            - self.fear * 1.1
            - self.irritation * 0.7
            - self.territoriality * 0.3
        )

    def talk_gradient(self):
        return (
            self.affinity * 0.7
            + self.familiarity * 0.5
            + self.trust * 0.3
            - self.fear * 0.9
            - self.irritation * 0.8
        )

    def snapshot(self):
        return {axis: round(getattr(self, axis), 2) for axis in CORE_AXES}


@dataclass
class ActionPattern:
    """W_ij：状況・行動・結果の接続（NPC§5.3）。"""

    key: tuple
    weight: float = 0.2
    confidence: float = 0.3
    ttl: int = 200
    phase: Phase = Phase.LAT
    positive_count: int = 0
    negative_count: int = 0
    last_used: int = 0

    def reinforce(self, error, t, cost=0.0, fixation=1.0):
        """成功回数ではなく、予測と結果の差で更新する（NPC§5.3 学習原則）。

        fixation は D3（再現性確認・反復固定ループ）の強さ。
        """
        gain = clamp(0.14 * (1.0 - error) * fixation - cost * 0.05, -0.12, 0.16)
        self.weight = clamp(self.weight + gain, -0.9, 1.2)
        self.confidence = clamp(self.confidence + (0.06 if error < 0.4 else -0.05), 0.02, 0.98)
        if error < 0.4:
            self.positive_count += 1
        else:
            self.negative_count += 1
        self.last_used = t
        self.ttl = 200
        if self.confidence >= 0.55 and self.phase is Phase.LAT:
            self.phase = Phase.ACT


class ActionMemory:
    """行動経路のW_ijを保持する。

    容量超過時に最弱パターンを直ちに消さず、まず潜在化させる（NPC§12-7）。
    """

    def __init__(self, capacity=180):
        self.patterns = {}
        self.capacity = capacity

    def pattern(self, key):
        if key not in self.patterns:
            self.patterns[key] = ActionPattern(key)
        return self.patterns[key]

    def weight(self, key):
        found = self.patterns.get(key)
        return found.weight if found and found.phase is not Phase.LAT else 0.0

    def usage(self, key):
        found = self.patterns.get(key)
        return 0 if found is None else found.positive_count + found.negative_count

    def metabolize(self, t):
        for pattern in list(self.patterns.values()):
            pattern.ttl -= 1
            if pattern.ttl <= 0 and pattern.phase is Phase.ACT:
                pattern.phase = Phase.LAT
                pattern.ttl = 60
        if len(self.patterns) <= self.capacity:
            return
        latent = sorted(
            (item for item in self.patterns.values() if item.phase is Phase.LAT),
            key=lambda item: (item.confidence, item.last_used),
        )
        for pattern in latent[: len(self.patterns) - self.capacity]:
            del self.patterns[pattern.key]


class RelationMemorySystem:
    """一人のNPCから見た、他者への方向つき関係を保持・更新する。"""

    def __init__(self, owner_name):
        self.owner = owner_name
        self.states = {}
        self.pending_predictions = {}
        self.reputation_hints = defaultdict(list)
        self.reactivated = []

    def state(self, name):
        if name not in self.states:
            self.states[name] = RelationState(name)
        return self.states[name]

    def known(self):
        return list(self.states.values())

    # --- 予測と誤差（村§11.1 / H_relation） ---

    def predict_response(self, name):
        """相手が応じてくれる度合いの予測。0=離れる 0.5=変わらず 1=応じる。"""
        state = self.state(name)
        base = 0.5 + state.affinity * 0.3 + state.trust * 0.2 + state.familiarity * 0.15
        base -= state.irritation * 0.25 + state.fear * 0.2
        return clamp(base, 0.02, 0.98)

    def register_prediction(self, name, predicted, context):
        self.pending_predictions[name] = {"predicted": predicted, "context": context}

    def evaluate_response(self, name, observed):
        """予測差を返し、predictability を更新する（村§11.1）。"""
        pending = self.pending_predictions.pop(name, None)
        if pending is None:
            return None
        state = self.state(name)
        error = abs(observed - pending["predicted"])
        state.predictability = clamp(state.predictability + 0.12 * ((1.0 - error) - state.predictability), 0.05, 0.98)
        if error > 0.45:
            state.nudge("irritation", 0.05 * error)
            state.nudge("affinity", -0.03 * error)
            # 大きく外した分は、その場で処理しきれずに固着する。
            state.residue = clamp(state.residue + error * 0.30, 0.0, 1.5)
        else:
            state.nudge("affinity", 0.02)
            # 予測が当たれば、固着していた分も一緒に解ける。
            state.residue = max(0.0, state.residue - 0.12)
        return error

    def drop_prediction(self, name):
        self.pending_predictions.pop(name, None)

    # --- 直接作用 ---

    # これ以上間が空いてから再会すると、固着した熱が戻る。
    REACTIVATION_ABSENCE = 40

    def on_proximity(self, name, t, ticks=1):
        state = self.state(name)
        absence = t - state.last_contact
        if absence >= self.REACTIVATION_ABSENCE and state.residue > 0.05:
            # 構造として固着していたものが、再会で熱へ戻る。
            self.reactivated.append((name, state.residue))
            state.residue *= 0.35
        state.nudge("familiarity", 0.006 * ticks, 0.0, 1.0)
        state.touch(t)

    def take_reactivated(self):
        """再会によって熱へ戻った分を取り出す。"""
        total = sum(value for _, value in self.reactivated)
        events = list(self.reactivated)
        self.reactivated.clear()
        return total, events

    def on_dialogue(self, name, speech_act, accepted, t):
        state = self.state(name)
        state.nudge("familiarity", 0.03, 0.0, 1.0)
        if accepted:
            state.nudge("trust", 0.035)
            state.nudge("affinity", 0.03)
            state.nudge("irritation", -0.02, 0.0, 1.0)
        else:
            state.nudge("irritation", 0.05, 0.0, 1.0)
            state.nudge("affinity", -0.02)
        if speech_act == "thank":
            state.nudge("obligation", -0.12, 0.0, 1.0)
        elif speech_act == "apologize":
            state.nudge("irritation", -0.14, 0.0, 1.0)
        state.shared_history.append((t, "dialogue", speech_act, accepted))
        del state.shared_history[:-12]
        state.touch(t)

    def on_received_gift(self, name, value, t):
        """AがBへ渡す → B.obligation[A]上昇, B.trust[A]微増（村§11.2）。"""
        state = self.state(name)
        state.nudge("obligation", clamp(value / 20.0, 0.02, 0.45), 0.0, 1.0)
        state.nudge("trust", 0.05)
        state.nudge("affinity", 0.04)
        state.shared_history.append((t, "received", round(value, 1)))
        del state.shared_history[:-12]
        state.touch(t)

    def on_gave_gift(self, name, value, accepted, t):
        state = self.state(name)
        if accepted:
            state.nudge("affinity", 0.05)
            state.nudge("familiarity", 0.02, 0.0, 1.0)
        else:
            state.nudge("irritation", 0.06, 0.0, 1.0)
        state.shared_history.append((t, "gave", round(value, 1), accepted))
        del state.shared_history[:-12]
        state.touch(t)

    def on_courted(self, name, accepted, t):
        """求愛の結果。受容と拒否で関係の動く向きが分かれる。

        これまで関係は接触によって単調増加するだけだった。
        拒否がある行為を入れて初めて、下向きの経路が供給される。
        """
        state = self.state(name)
        if accepted:
            state.nudge("affinity", 0.12)
            state.nudge("familiarity", 0.04, 0.0, 1.0)
            state.nudge("trust", 0.05)
        else:
            state.nudge("affinity", -0.02)
            state.nudge("irritation", 0.04, 0.0, 1.0)
            state.nudge("predictability", -0.05, 0.05, 0.98)
        state.shared_history.append((t, "court", accepted))
        del state.shared_history[:-12]
        state.touch(t)

    def on_cooperation(self, name, success, t):
        state = self.state(name)
        state.nudge("trust", 0.06 if success else -0.03)
        state.nudge("affinity", 0.05 if success else -0.02)
        state.nudge("dependency", 0.03 if success else 0.0, 0.0, 1.0)
        state.shared_history.append((t, "cooperate", success))
        del state.shared_history[:-12]
        state.touch(t)

    def on_contested_resource(self, name, lost, t):
        state = self.state(name)
        state.nudge("territoriality", 0.08 if lost else 0.03, 0.0, 1.0)
        if lost:
            state.nudge("irritation", 0.07, 0.0, 1.0)
        state.shared_history.append((t, "contest", lost))
        del state.shared_history[:-12]
        state.touch(t)

    # --- 観察作用（村§7.5 / §11.3） ---

    def on_witnessed(self, actor, target, action_type, result, confidence, t):
        """全NPCへ自動的に評判を配布しない。目撃した者だけが更新する。"""
        if actor == self.owner:
            return
        state = self.state(actor)
        if action_type in {"give", "help"}:
            state.nudge("trust", 0.03 * confidence)
            state.nudge("affinity", 0.02 * confidence)
        elif action_type in {"block", "contest"}:
            state.nudge("trust", -0.03 * confidence)
            state.nudge("fear", 0.02 * confidence, 0.0, 1.0)
        self.reputation_hints[actor].append((t, action_type, result, round(confidence, 2)))
        del self.reputation_hints[actor][:-8]

    def decay(self, t):
        """去る者は日々に疎し。

        減衰を駆動するのは時間そのものではなく、最後の接触からの経過である。
        毎日会う相手は薄れないが、離れた相手は日ごとに疎くなる。

        predictability は 0 ではなく 0.5（不定）へ戻す。
        忘れるのは「どういう相手か」であって、「悪い相手だ」になるのではない。
        再会したときに予測が外れるのは、この戻りによる。
        """
        for state in self.states.values():
            absence = max(0, t - state.last_contact)
            fade = 1.0 + clamp(absence / 120.0, 0.0, 3.0)
            state.familiarity = clamp(state.familiarity * (1 - 0.0010 * fade), 0.0, 1.0)
            state.trust = clamp(state.trust * (1 - 0.0007 * fade), -1.0, 1.0)
            state.affinity = clamp(state.affinity * (1 - 0.0009 * fade), -1.0, 1.0)
            state.dependency = clamp(state.dependency * (1 - 0.0012 * fade), 0.0, 1.0)
            state.predictability += (0.5 - state.predictability) * 0.003 * fade
            # 固着は構造なので、熱よりはるかに緩やかにしか薄れない。
            # ここを速くすると「放置すれば全部なかったことになる」に戻る。
            state.residue *= 0.9993
            # 以下は接触の有無に関わらず薄れる
            state.irritation = clamp(state.irritation * 0.985, 0.0, 1.0)
            state.fear = clamp(state.fear * 0.99, 0.0, 1.0)
            state.obligation = clamp(state.obligation * 0.995, 0.0, 1.0)
            state.territoriality = clamp(state.territoriality * 0.99, 0.0, 1.0)

    def strongest(self, count=2):
        return sorted(
            self.states.values(), key=lambda item: item.approach_gradient(), reverse=True
        )[:count]
