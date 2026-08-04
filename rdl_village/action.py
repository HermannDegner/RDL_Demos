"""関係作用・移動計画・物理ゲート。

参照:
  RDL_簡易村シミュレーター §7（関係作用システム）, §8（移動決定）
  RDL_NPC行動決定システム §5.1（物理制約層）, §5.6（関係的行動統合器）

移動は最短経路処理ではない（村§19-4）。
移動候補の評価は、物理世界の真値ではなく知覚Fと個体予測場から作る（村§8.2 末尾, §19-1）。
"""

import math
from dataclasses import dataclass, field

from .core import clamp, distance, normalized
from .perception import cell_of

TAU = math.pi * 2
DIRECTIONS = [(0.0, 0.0, "stay")] + [
    (math.cos(index / 12 * TAU), math.sin(index / 12 * TAU), f"dir{index}") for index in range(12)
]

# 関係作用のチャネル（村§7）
CHANNELS = ("movement", "dialogue", "transfer", "cooperation", "interference", "observation")


@dataclass
class RelationalAction:
    """すべての対人的行動を共通構造で保持する（村§7）。"""

    actor: str
    action_type: str
    channel: str = "movement"
    target: str | None = None
    object: str | None = None
    place: str | None = None
    intent: str = ""
    expected_effect: str = ""
    physical_cost: float = 0.0
    social_cost: float = 0.0
    visibility: float = 1.0

    def as_record(self):
        record = {"actor": self.actor, "action": self.action_type, "channel": self.channel}
        for key in ("target", "object", "place"):
            value = getattr(self, key)
            if value is not None:
                record[key] = value
        return record


@dataclass
class ActionCandidate:
    """NPC§5.6 の ActionCandidate。除外理由まで追跡できるようにする。"""

    action_type: str
    source_layers: tuple = ()
    target: str | None = None
    target_pos: tuple | None = None
    node_id: str | None = None
    place_id: str | None = None
    expected_outcome: dict = field(default_factory=dict)
    score_components: dict = field(default_factory=dict)
    viability: float = 1.0
    uncertainty: float = 0.3
    novelty: float = 0.0
    reason: str = ""

    @property
    def key(self):
        return self.action_type, self.target or self.node_id or self.place_id

    def total(self):
        return sum(self.score_components.values())

    def brief(self):
        return {
            "action": self.action_type,
            "target": self.target or self.node_id or self.place_id,
            "score": round(self.total(), 2),
            "layers": list(self.source_layers),
        }


class MovementPlanner:
    """停止を含む13方向の局所候補を、関係勾配で比較する（村§8.1, §8.2）。"""

    def __init__(self, rng):
        self.rng = rng

    def plan(self, npc, perception, target_pos, xi_pressure):
        weights = npc.move_weights
        relations = npc.relations
        field_memory = npc.prediction_field
        speed = npc.body.speed()

        goal_direction = (0.0, 0.0)
        if target_pos is not None:
            goal_direction = normalized(target_pos[0] - npc.pos[0], target_pos[1] - npc.pos[1])
        previous = normalized(npc.vx, npc.vy)

        best = None
        for ax, ay, name in DIRECTIONS:
            step = (npc.pos[0] + ax * speed, npc.pos[1] + ay * speed)
            components = {}

            if target_pos is not None:
                components["goal"] = weights["goal"] * (
                    (ax * goal_direction[0] + ay * goal_direction[1])
                    + (distance(npc.pos, target_pos) - distance(step, target_pos)) * 0.5
                )
            else:
                components["goal"] = 0.0

            meaning = self._meaning_at(field_memory, perception, step)
            if meaning is not None:
                components["resource"] = weights["resource"] * meaning.resource_expectation
                components["comfort"] = weights["comfort"] * meaning.comfort
                components["familiarity"] = weights["familiarity"] * meaning.familiarity
                components["fear"] = -weights["fear"] * meaning.danger_expectation
            else:
                components["exploration"] = weights["exploration"] * (0.4 if name != "stay" else 0.0)

            affiliation = 0.0
            fear = 0.0
            intrusion = 0.0
            for observation in perception.visible_agents:
                state = relations.state(observation.name)
                gap_now = distance(npc.pos, observation.pos)
                gap_next = distance(step, observation.pos)
                closing = gap_now - gap_next
                gradient = state.approach_gradient()
                if gradient > 0:
                    affiliation += closing * gradient
                else:
                    fear += max(0.0, closing) * (state.fear + state.irritation)
                if gap_next < 1.1 and observation.last_action in {"work", "rest", "forage"}:
                    intrusion += (1.1 - gap_next)
            components["affiliation"] = weights["affiliation"] * affiliation
            components["fear"] = components.get("fear", 0.0) - weights["fear"] * fear
            components["intrusion"] = -weights["intrusion"] * intrusion

            if npc.coordination_partner:
                partner = perception.agent_named(npc.coordination_partner)
                if partner:
                    closing = distance(npc.pos, partner.pos) - distance(step, partner.pos)
                    components["coordination"] = weights["coordination"] * closing

            components["crowding"] = -weights["crowding"] * perception.crowding * (
                0.0 if name == "stay" else 0.4
            )

            blocked = 0.0
            for obstacle in perception.visible_obstacles:
                clearance = distance(step, obstacle) - obstacle[2] - npc.body_radius
                if clearance < 0.0:
                    blocked += 1.2
                elif clearance < 0.6:
                    blocked += 0.35 * (0.6 - clearance)
            traversability = field_memory.traversability(npc.pos, step)
            components["motion"] = -weights["motion"] * (
                blocked + (1.0 - traversability) * 0.6 + (0.3 if name == "stay" else 0.0)
            )
            components["continuity"] = 0.12 * (ax * previous[0] + ay * previous[1])
            components["xi"] = self.rng.uniform(-0.05, 0.05) + xi_pressure * self.rng.uniform(0.0, 0.22)

            total = sum(components.values())
            if best is None or total > best[0]:
                best = (total, ax, ay, name, components, traversability)

        _, ax, ay, name, components, traversability = best
        expected_progress = speed * traversability * (0.0 if name == "stay" else 1.0)
        return {
            "vx": ax * speed,
            "vy": ay * speed,
            "direction": name,
            "components": {key: round(value, 3) for key, value in components.items() if value},
            "expected_progress": expected_progress,
            "expected_motion": traversability if name != "stay" else 0.0,
        }

    def _meaning_at(self, field_memory, perception, step):
        """踏み込もうとしている地点が、どの場所の内側かを判定する。

        一律の半径を仮定すると、半径2.2の家を実際より広く、
        半径6.0の林を狭く解釈する。見えている広さをそのまま使う。
        """
        for place_id, _kind, center, radius, _gap in perception.visible_places:
            if distance(step, center) <= radius:
                return field_memory.meaning(place_id)
        return None


class PhysicalConstraintLayer:
    """実行可能性のハードゲート（NPC§5.1）。

    「物理が行動を命令する」のではなく、通常候補の大半が実行不能になり、
    緊急候補だけが残る状態として扱う。
    """

    TALK_RANGE = 2.2
    # 候補生成は TALK_RANGE で行うので、ゲートが狭すぎると毎回除外される。
    TRANSFER_RANGE = 2.0
    USE_RANGE = 1.3

    def gate(self, candidates, npc, perception):
        viable, removed = [], []
        for candidate in candidates:
            reason = self._rejection(candidate, npc, perception)
            if reason:
                removed.append((candidate, reason))
            else:
                viable.append(candidate)
        emergency = [item for item in viable if "emergency" in item.source_layers]
        normal = [item for item in viable if "emergency" not in item.source_layers]
        return normal, emergency, removed

    def _rejection(self, candidate, npc, perception):
        action = candidate.action_type
        if action == "court" and npc.mate:
            return "already_bonded"
        if action in {"talk", "give", "help", "court"}:
            observation = perception.agent_named(candidate.target)
            if observation is None:
                return "target_not_visible"
            gap = distance(npc.pos, observation.pos)
            limit = self.TALK_RANGE if action in {"talk", "court"} else self.TRANSFER_RANGE
            if gap > limit:
                return "target_out_of_range"
            if action == "give" and not npc.inventory:
                return "nothing_to_give"
        if action == "use_resource":
            belief = npc.prediction_field.belief(candidate.node_id)
            if belief is None:
                return "unknown_resource"
            if distance(npc.pos, belief.pos) > self.USE_RANGE:
                return "resource_out_of_range"
            if belief.existence_prob < 0.12:
                return "belief_too_weak"
        if action == "rest":
            if candidate.place_id != perception.place_id:
                return "not_at_place"
        if action == "go_resource":
            belief = npc.prediction_field.belief(candidate.node_id)
            if belief is None:
                return "unknown_resource"
            if belief.existence_prob < 0.08:
                return "belief_too_weak"
        return None
