"""個体知覚と個体予測場。

参照:
  RDL_簡易村シミュレーター §3.2（物理世界と予測場の分離）, §3.3（連続移動・離散記憶）,
                          §4.2（個体予測場）, §6.2（場所の個体的意味）

NPCは PhysicalWorld を直接読まない。ここで生成されたFだけを予測場へ統合する。
"""

from collections import defaultdict
from dataclasses import dataclass, field

from .core import Phase, clamp, distance

CELL = 4.0


def cell_of(pos):
    """連続座標 → 粗いセル（村§3.3）。記憶は離散で持つ。"""
    return int(pos[0] // CELL), int(pos[1] // CELL)


def route_cells(start, goal):
    return cell_of(start), cell_of(goal)


@dataclass
class ResourceObservation:
    node_id: str
    kind: str
    place_id: str
    pos: tuple
    amount: float
    state: str


@dataclass
class AgentObservation:
    name: str
    pos: tuple
    place_id: str | None
    last_action: str | None


@dataclass
class Perception:
    """F：NPC向けに解釈された入力（NPC§3.2）。"""

    t: int = 0
    band: str = "morning"
    weather: str = "sunny"
    is_night: bool = False
    light: float = 1.0
    dark_ahead: int = 0
    pos: tuple = (0.0, 0.0)
    place_id: str | None = None
    vision_radius: float = 7.0
    visible_places: list = field(default_factory=list)
    visible_resources: list = field(default_factory=list)
    visible_agents: list = field(default_factory=list)
    visible_obstacles: list = field(default_factory=list)
    # いまいる場所に置かれている物（村§6.1 Place.objects）。見えるから分かる。
    stored_here: dict = field(default_factory=dict)
    audible_agents: list = field(default_factory=list)
    crowding: float = 0.0
    discomfort: float = 0.0

    def resource_here(self, kind):
        return [
            item
            for item in self.visible_resources
            if item.kind == kind and distance(self.pos, item.pos) <= 1.2
        ]

    def agent_named(self, name):
        return next((item for item in self.visible_agents if item.name == name), None)


class PerceptionSystem:
    """物理環境から各NPC固有の視覚・音・接触Fを生成する（村§16）。"""

    def __init__(self, base_radius=7.0):
        self.base_radius = base_radius

    def radius_for(self, npc, world):
        # 視界は光量に連続的に従う。夜になった瞬間に半分になるのではない。
        radius = self.base_radius * (0.45 + 0.55 * world.clock.light)
        if world.weather == "rainy":
            radius *= 0.8
        # 衰弱すれば視野も狭くなる。疲労だけでなく空腹・渇きも効く。
        return radius * (0.72 + 0.28 * npc.body.condition())

    def perceive(self, npc, world, agents):
        radius = self.radius_for(npc, world)
        place = world.places.place_at(npc.pos)
        perception = Perception(
            t=world.clock.t,
            band=world.clock.band,
            weather=world.weather,
            is_night=world.clock.is_night,
            light=world.clock.light,
            dark_ahead=world.clock.ticks_until_light(),
            pos=npc.pos,
            place_id=place.id if place else None,
            vision_radius=radius,
        )

        for candidate in world.places.all_places():
            gap = distance(npc.pos, candidate.center) - candidate.radius
            if gap <= radius * candidate.visibility + 1.5:
                # 場所の広さは見れば分かる。移動評価が一律の半径を仮定しないよう渡す。
                perception.visible_places.append(
                    (candidate.id, candidate.kind, candidate.center, candidate.radius, max(0.0, gap))
                )

        for node in world.resources.all_nodes():
            if distance(npc.pos, node.pos) > radius:
                continue
            if world.line_blocked(npc.pos, node.pos):
                continue
            perception.visible_resources.append(
                ResourceObservation(node.id, node.kind, node.place_id, node.pos, node.amount, node.state)
            )

        if place is not None:
            perception.stored_here = {
                kind: amount for kind, amount in place.objects.items() if amount > 0.05
            }

        for obstacle in world.obstacles:
            gap = distance(npc.pos, obstacle) - obstacle[2]
            if gap <= radius:
                perception.visible_obstacles.append(obstacle)

        occupancy = defaultdict(int)
        for other in agents:
            if other is npc or not other.alive:
                continue
            gap = distance(npc.pos, other.pos)
            other_place = world.places.place_at(other.pos)
            if other_place:
                occupancy[other_place.id] += 1
            if gap <= radius and not world.line_blocked(npc.pos, other.pos):
                perception.visible_agents.append(
                    AgentObservation(
                        other.name,
                        other.pos,
                        other_place.id if other_place else None,
                        other.last_action_name,
                    )
                )
            elif gap <= radius * 1.4:
                perception.audible_agents.append(other.name)

        if place:
            # 自分も収容の一部である。除くと定員2の場所に二人いても混雑率0.5になる。
            perception.crowding = place.occupancy_ratio(occupancy.get(place.id, 0) + 1)

        discomfort = 0.0
        sheltered = bool(place) and bool({"rest", "sleep"} & set(place.affordances))
        if world.weather == "rainy":
            discomfort += 0.35 if not sheltered else 0.05
        # 暗さの不快も連続。屋根の下なら効かない。
        discomfort += (1.0 - world.clock.light) * (0.0 if sheltered else 0.32)
        perception.discomfort = clamp(discomfort, 0.0, 1.0)
        return perception


@dataclass
class PlaceMeaning:
    """場所ラベルは共有されても、意味は共有されない（村§6.2）。"""

    place_id: str
    kind: str | None = None
    center: tuple | None = None
    radius: float = 3.0
    familiarity: float = 0.0
    comfort: float = 0.0
    social_expectation: float = 0.0
    resource_expectation: float = 0.0
    danger_expectation: float = 0.0
    ownership_claim: float = 0.0
    visits: int = 0
    last_seen: int = 0
    memorable_events: list = field(default_factory=list)

    # 思考的探索が内生した仮説。外的観測に当たるまで M_lat のまま置く。
    hypothesis: float | None = None
    hypothesis_t: int = 0

    def visit(self):
        self.visits += 1
        self.familiarity = clamp(self.familiarity + 0.05, 0.0, 1.0)

    def suppose(self, expected_resource, t):
        self.hypothesis = clamp(expected_resource, 0.0, 1.0)
        self.hypothesis_t = t


@dataclass
class ResourceBelief:
    """資源についての個体的な仮説。世界の真値とはずれうる。"""

    node_id: str
    kind: str
    place_id: str
    pos: tuple
    expected_amount: float
    confidence: float = 0.5
    existence_prob: float = 0.6
    last_seen: int = 0
    last_decay_t: int = 0
    phase: Phase = Phase.LAT
    # 思考的探索が内生した見込み。確認できるまで M_lat のまま置く。
    supposed: float | None = None

    def suppose(self, amount):
        self.supposed = clamp(amount, 0.0, 200.0)
        self.expected_amount = self.supposed
        self.phase = Phase.LAT

    def reinforce(self, amount, t, align_rate):
        self.expected_amount += (amount - self.expected_amount) * 0.55
        self.confidence = clamp(self.confidence + align_rate, 0.0, 0.98)
        self.existence_prob = clamp(self.existence_prob + align_rate * 1.4, 0.0, 1.0)
        self.last_seen = t
        self.phase = Phase.ACT

    def weaken(self, t, rate=0.22):
        self.expected_amount *= 1.0 - rate
        self.confidence = clamp(self.confidence - rate * 0.5, 0.05, 0.98)
        self.existence_prob = clamp(self.existence_prob - rate * 0.6, 0.0, 1.0)
        self.last_seen = t
        if self.confidence < 0.25:
            self.phase = Phase.LAT

    def reliability(self):
        return self.existence_prob * 0.6 + self.confidence * 0.4


class PredictionField:
    """場所・資源・他者・危険・移動の個体記憶（村§4.2）。"""

    def __init__(self, node_coeffs):
        self.coeffs = node_coeffs
        self.places = {}
        self.resources = {}
        self.motion_memory = defaultdict(lambda: 0.7)
        self.danger_memory = defaultdict(float)
        self.event_memory = []
        self.tested_hypotheses = []
        self.last_discoveries = 0

    # --- 場所 ---

    def meaning(self, place_id):
        if place_id not in self.places:
            self.places[place_id] = PlaceMeaning(place_id)
            self.last_discoveries += 1
        return self.places[place_id]

    def known_places(self):
        return list(self.places.values())

    # --- 資源 ---

    def belief(self, node_id):
        return self.resources.get(node_id)

    def beliefs_of_kind(self, kind, minimum_reliability=0.2):
        return [
            belief
            for belief in self.resources.values()
            if belief.kind == kind and belief.reliability() >= minimum_reliability
        ]

    def integrate(self, perception, t):
        """観測を予測場へ統合し、期待と実測のずれを返す。

        戻り値は資源チャネルの予測差。休眠中の資源を「あるはず」と覚えていた場合、
        ここで大きな誤差が立つ（村§6.3 の狙い）。

        誤差は既に信念を持っていたノードの平均を取る。max だと1件の意外が
        チャネル全体を天井へ張り付かせ、Leapが飽和する。
        """
        # 今回のtickで新しく知ったものの数。統合後の総数と比べても発見は測れない。
        self.last_discoveries = 0
        errors = []
        for observation in perception.visible_resources:
            belief = self.resources.get(observation.node_id)
            observed_amount = observation.amount if observation.state == "available" else 0.0
            if belief is None:
                self.resources[observation.node_id] = ResourceBelief(
                    observation.node_id,
                    observation.kind,
                    observation.place_id,
                    observation.pos,
                    observed_amount,
                    confidence=self.coeffs.reliability * 0.8,
                    existence_prob=0.75 if observed_amount > 0 else 0.3,
                    last_seen=t,
                    phase=Phase.ACT,
                )
                self.event_memory.append((t, "discover_resource", observation.node_id))
                self.last_discoveries += 1
                continue
            scale = max(1.0, belief.expected_amount, observed_amount)
            errors.append(abs(observed_amount - belief.expected_amount) / scale)
            if belief.supposed is not None:
                self.tested_hypotheses.append(
                    (observation.node_id, belief.supposed / scale, observed_amount / scale)
                )
                belief.supposed = None
            if observed_amount > 0.05:
                belief.reinforce(observed_amount, t, self.coeffs.align_rate)
            else:
                belief.weaken(t)

        hypothesis_error = 0.0
        for place_id, kind, center, radius, gap in perception.visible_places:
            meaning = self.meaning(place_id)
            meaning.center = center
            meaning.kind = kind
            meaning.radius = radius
            meaning.last_seen = t
            if gap <= 0.0:
                meaning.visit()
                if meaning.hypothesis is not None:
                    # 内生した仮説が外的観測に当たる瞬間。ここで初めて誤差が立つ。
                    usable = sum(
                        1
                        for item in perception.visible_resources
                        if item.place_id == place_id and item.state == "available"
                    )
                    observed = clamp(usable / 3.0, 0.0, 1.0)
                    hypothesis_error = max(hypothesis_error, abs(meaning.hypothesis - observed))
                    self.tested_hypotheses.append((place_id, meaning.hypothesis, observed))
                    meaning.hypothesis = None
            else:
                meaning.familiarity = clamp(meaning.familiarity + 0.004, 0.0, 1.0)

        if perception.place_id:
            meaning = self.meaning(perception.place_id)
            meaning.social_expectation = clamp(
                meaning.social_expectation * 0.96 + len(perception.visible_agents) * 0.03, 0.0, 1.0
            )
            meaning.comfort = clamp(
                meaning.comfort * 0.97 + (0.04 if perception.discomfort < 0.15 else -0.03), -1.0, 1.0
            )
            usable = sum(1 for item in perception.visible_resources if item.state == "available")
            meaning.resource_expectation = clamp(
                meaning.resource_expectation * 0.95 + usable * 0.04, 0.0, 1.0
            )
        return {
            "resource": sum(errors) / len(errors) if errors else 0.0,
            "hypothesis": hypothesis_error,
        }

    def decay(self, t):
        """毎tick呼ばれる。前回減衰時からの差分だけを進める。

        最終観測からの全経過を毎tick累乗すると、20tickで 0.995^210 相当まで落ちる。
        減衰は経過時間に対して指数であって、tickごとに再累乗するものではない。
        """
        for belief in self.resources.values():
            elapsed = max(0, t - max(belief.last_seen, belief.last_decay_t))
            belief.last_decay_t = t
            if elapsed <= 0:
                continue
            belief.confidence = clamp(belief.confidence * (0.995 ** elapsed), 0.05, 0.98)
            belief.existence_prob = clamp(
                belief.existence_prob * (0.997 ** elapsed) + 0.5 * (1 - 0.997 ** elapsed), 0.0, 1.0
            )
            if belief.confidence < 0.25:
                belief.phase = Phase.LAT

    # --- 移動 ---

    def traversability(self, start, goal):
        """通行可能性の個体的見積り。世界の真値ではない。"""
        return self.motion_memory[route_cells(start, goal)]

    def update_traversability(self, start, goal, achieved):
        key = route_cells(start, goal)
        self.motion_memory[key] += (achieved - self.motion_memory[key]) * 0.28
        self.motion_memory[key] = clamp(self.motion_memory[key], 0.03, 1.0)

    def penalize_route(self, start, goal, amount=0.3):
        key = route_cells(start, goal)
        self.motion_memory[key] = clamp(self.motion_memory[key] - amount, 0.03, 1.0)

    def danger_at(self, place_id):
        return self.danger_memory[place_id]
