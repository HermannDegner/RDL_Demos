"""物理環境場・時計・場所・資源循環。

参照:
  RDL_簡易村シミュレーター §4.1（物理環境場）, §6（場所と資源）, §10（日課）

このモジュールが持つのは「実際に存在する状態」だけである。
場所の意味や危険性をNPCへ直接与えない（村§4.1）。
NPCはここを直接参照せず、PerceptionSystem を通してのみFを得る（村§3.2 / §19-1）。
"""

import math
from dataclasses import dataclass, field, replace

from .core import clamp, distance, normalized, point_to_segment_distance  # noqa: F401

TAU = math.pi * 2

BANDS = ("morning", "noon", "evening", "night")
TICKS_PER_BAND = 16
TICKS_PER_DAY = TICKS_PER_BAND * len(BANDS)


class VillageClock:
    """時刻・日・時間帯・予定窓の管理（村§16）。"""

    def __init__(self):
        self.t = 0

    def advance(self):
        self.t += 1

    @property
    def decision_tick(self):
        """このtickの意思決定が属する時刻。

        時計は step 冒頭で進むため、最初の決定は t=1 に記録される。
        日・時間帯・光量・評価側の日区切りを、すべてこの値から計算して
        定義を一本にする。t と decision_tick の二重定義が、
        世界時計の day と評価側の day を1日ずらしていた。
        """
        return max(0, self.t - 1)

    @property
    def day(self):
        return self.decision_tick // TICKS_PER_DAY

    @property
    def tick_of_day(self):
        return self.decision_tick % TICKS_PER_DAY

    @property
    def band(self):
        return BANDS[self.tick_of_day // TICKS_PER_BAND]

    @property
    def is_night(self):
        return self.band == "night"

    @property
    def light(self):
        """光量。0が最も暗く1が最も明るい。

        時間帯は4段の離散だが、明るさは連続で落ちる。
        「薄暗くなれば戻ろうとする」は夜になってからでは遅く、
        夕方に入った時点から勾配が要る。
        """
        phase = (self.tick_of_day - TICKS_PER_BAND * 1.5) / TICKS_PER_DAY
        return clamp(0.5 + 0.5 * math.cos(phase * math.pi * 2), 0.0, 1.0)

    def ticks_until_light(self, threshold=0.55):
        """明るさが閾値まで戻るまでの残りtick。

        既に明るければ0。暗い時間の長さを個体が見積もるために使う。
        時計そのものは個体が読めるものとして扱う（日の傾きは知覚できる）。
        """
        if self.light >= threshold:
            return 0
        for ahead in range(1, TICKS_PER_DAY + 1):
            future = (self.tick_of_day + ahead) % TICKS_PER_DAY
            phase = (future - TICKS_PER_BAND * 1.5) / TICKS_PER_DAY
            if clamp(0.5 + 0.5 * math.cos(phase * math.pi * 2), 0.0, 1.0) >= threshold:
                return ahead
        return TICKS_PER_DAY

    def label(self):
        return f"D{self.day}/{self.band}"


@dataclass
class Place:
    """場所は座標範囲だけでなく、利用可能な行動を接続するSILN（村§6.1）。

    ここに持つのは物理的事実だけで、「意味」は各NPCの PlaceMeaning 側に置く。
    """

    id: str
    kind: str
    center: tuple
    radius: float
    affordances: tuple
    capacity: int = 4
    noise_level: float = 0.3
    visibility: float = 0.8
    owner: str | None = None
    # 置かれた物（村§6.1 の Place.objects）。
    # 村§7.3 の「置く」「取る」が成立するには、場所に残る場が要る。
    objects: dict = field(default_factory=dict)

    def store(self, kind, amount):
        self.objects[kind] = self.objects.get(kind, 0.0) + amount

    def take_stored(self, kind, amount):
        available = self.objects.get(kind, 0.0)
        taken = min(available, amount)
        if taken > 0.0:
            self.objects[kind] = available - taken
        return taken

    def stored(self, kind):
        return self.objects.get(kind, 0.0)

    def contains(self, pos):
        return distance(pos, self.center) <= self.radius

    def occupancy_ratio(self, count):
        return clamp(count / max(1, self.capacity), 0.0, 2.0)


@dataclass
class ResourceNode:
    """資源は即時に無限復活させない（村§6.3, §19-8）。

        利用 → 残量低下 → 枯渇 → 休眠 → 再生

    休眠期間があることで、NPCの古い記憶と現在の状態が食い違い、
    探索・再学習・H_resource が生まれる。
    """

    id: str
    kind: str
    place_id: str
    pos: tuple
    capacity: float
    amount: float
    regen_rate: float = 0.06
    dormant_ticks: int = 30
    state: str = "available"
    timer: int = 0

    @property
    def usable(self):
        return self.state == "available" and self.amount > 0.05

    def take(self, requested):
        if not self.usable:
            return 0.0
        given = min(requested, self.amount)
        self.amount -= given
        if self.amount <= 0.05:
            self.amount = 0.0
            self.state = "dormant"
            self.timer = self.dormant_ticks
        return given

    def tick(self):
        if self.state == "dormant":
            self.timer -= 1
            if self.timer <= 0:
                self.state = "regenerating"
        elif self.state == "regenerating":
            self.amount = min(self.capacity, self.amount + self.capacity * self.regen_rate)
            if self.amount >= self.capacity * 0.55:
                self.state = "available"


class ResourceCycleSystem:
    """消費・枯渇・休眠・再生（村§16）。"""

    def __init__(self, nodes):
        self.nodes = {node.id: node for node in nodes}

    def tick(self):
        events = []
        for node in self.nodes.values():
            before = node.state
            node.tick()
            if node.state != before:
                events.append({"kind": "resource_state", "node": node.id, "state": node.state})
        return events

    def at(self, node_id):
        return self.nodes.get(node_id)

    def nodes_in_place(self, place_id):
        return [node for node in self.nodes.values() if node.place_id == place_id]

    def all_nodes(self):
        return list(self.nodes.values())


class PlaceSystem:
    """場所範囲・収容・利用可能行動（村§16）。"""

    def __init__(self, places):
        self.places = {place.id: place for place in places}

    def get(self, place_id):
        return self.places.get(place_id)

    def place_at(self, pos):
        for place in self.places.values():
            if place.contains(pos):
                return place
        return None

    def all_places(self):
        return list(self.places.values())

    def of_kind(self, kind):
        return [place for place in self.places.values() if place.kind == kind]


def default_layout():
    """固定レイアウト。seedを変えても場所の同一性が保たれるようにする。"""
    places = [
        Place("plaza", "広場", (20.0, 20.0), 4.2, ("talk", "gather", "rest"), capacity=6, noise_level=0.7),
        Place("well", "水場", (10.0, 14.0), 2.6, ("drink", "talk"), capacity=3, noise_level=0.4),
        Place("stream", "水場", (30.0, 23.0), 2.4, ("drink", "talk"), capacity=3, noise_level=0.4),
        Place("field", "畑", (28.0, 12.0), 5.0, ("forage", "work"), capacity=4, noise_level=0.3),
        Place("garden", "畑", (13.0, 19.0), 3.4, ("forage", "work"), capacity=3, noise_level=0.3),
        Place("shop", "店", (24.0, 27.0), 3.0, ("trade", "talk"), capacity=3, noise_level=0.5),
        Place("grove", "林", (10.0, 30.0), 6.0, ("forage", "gather", "explore"), capacity=4, noise_level=0.2),
        Place("home_a", "家", (8.0, 8.0), 2.2, ("rest", "sleep"), capacity=2, noise_level=0.1, visibility=0.4),
        Place("home_b", "家", (32.0, 32.0), 2.2, ("rest", "sleep"), capacity=2, noise_level=0.1, visibility=0.4),
        Place("home_c", "家", (33.0, 7.0), 2.2, ("rest", "sleep"), capacity=2, noise_level=0.1, visibility=0.4),
    ]
    obstacles = [
        (16.0, 10.0, 2.0),
        (14.0, 24.0, 2.2),
        (26.0, 20.0, 1.8),
        (20.0, 32.0, 2.0),
        (5.0, 20.0, 1.6),
        (31.0, 18.0, 1.7),
    ]
    nodes = [
        ResourceNode("water_1", "water", "well", (9.2, 13.4), 70.0, 70.0, regen_rate=0.22, dormant_ticks=8),
        ResourceNode("water_2", "water", "well", (11.0, 15.0), 70.0, 70.0, regen_rate=0.22, dormant_ticks=8),
        ResourceNode("water_3", "water", "stream", (29.4, 22.4), 70.0, 70.0, regen_rate=0.22, dormant_ticks=8),
        ResourceNode("water_4", "water", "stream", (30.8, 23.8), 70.0, 70.0, regen_rate=0.22, dormant_ticks=8),
        ResourceNode("food_field_1", "food", "field", (26.5, 10.8), 44.0, 44.0, regen_rate=0.08, dormant_ticks=24),
        ResourceNode("food_field_2", "food", "field", (29.4, 13.2), 44.0, 44.0, regen_rate=0.08, dormant_ticks=24),
        ResourceNode("food_field_3", "food", "field", (28.2, 9.6), 36.0, 36.0, regen_rate=0.07, dormant_ticks=30),
        ResourceNode("food_garden_1", "food", "garden", (12.4, 18.4), 40.0, 40.0, regen_rate=0.08, dormant_ticks=26),
        ResourceNode("food_garden_2", "food", "garden", (14.0, 19.8), 40.0, 40.0, regen_rate=0.08, dormant_ticks=26),
        ResourceNode("food_grove_1", "food", "grove", (8.4, 28.6), 34.0, 34.0, regen_rate=0.06, dormant_ticks=34),
        ResourceNode("food_grove_2", "food", "grove", (12.2, 32.4), 34.0, 34.0, regen_rate=0.06, dormant_ticks=34),
        ResourceNode("material_1", "material", "grove", (7.6, 32.0), 18.0, 18.0, regen_rate=0.03, dormant_ticks=52),
        ResourceNode("material_2", "material", "grove", (12.8, 28.2), 18.0, 18.0, regen_rate=0.03, dormant_ticks=52),
        # 林だけだと村の東側から到達できず、素材が誰の手にも渡らない。
        ResourceNode("material_3", "material", "field", (29.2, 10.4), 16.0, 16.0, regen_rate=0.03, dormant_ticks=52),
        ResourceNode("material_4", "material", "plaza", (19.2, 18.6), 14.0, 14.0, regen_rate=0.04, dormant_ticks=46),
        ResourceNode("rest_plaza", "rest", "plaza", (20.6, 21.2), 90.0, 90.0, regen_rate=0.22, dormant_ticks=6),
        ResourceNode("rest_field", "rest", "field", (27.4, 13.6), 50.0, 50.0, regen_rate=0.18, dormant_ticks=10),
        ResourceNode("rest_grove", "rest", "grove", (10.6, 30.4), 50.0, 50.0, regen_rate=0.18, dormant_ticks=10),
        ResourceNode("rest_shop", "rest", "shop", (23.4, 27.6), 50.0, 50.0, regen_rate=0.18, dormant_ticks=10),
        ResourceNode("rest_home_a", "rest", "home_a", (8.0, 8.0), 90.0, 90.0, regen_rate=0.26, dormant_ticks=4),
        ResourceNode("rest_home_b", "rest", "home_b", (32.0, 32.0), 90.0, 90.0, regen_rate=0.26, dormant_ticks=4),
        ResourceNode("rest_home_c", "rest", "home_c", (33.0, 7.0), 90.0, 90.0, regen_rate=0.26, dormant_ticks=4),
    ]
    return places, obstacles, nodes


class PhysicalWorld:
    """連続座標・地形・建物・障害物・天候（村§16）。

    ここに公開されている移動・遮蔽の判定は、シミュレーション側が「実行」に使うためのものであり、
    NPCの意思決定が先読みに使ってはならない（村§19-1, §19-11）。
    NPCが持つ通行可能性の見積りは PredictionField.motion_memory 側にある。
    """

    def __init__(self, rng, size=40.0, scale=1.0):
        """scale は村の絶対的な広さを変える。

        配置の相対関係は保ったまま距離だけが伸びるので、
        「個体が一日で踏破できる範囲に対して村がどれだけ大きいか」が変わる。
        知覚半径は据え置きなので、広げるほど世界に対する視野は相対的に狭くなる。
        """
        self.rng = rng
        self.scale = scale
        self.size = size * scale
        places, obstacles, nodes = default_layout()
        if scale != 1.0:
            places = [
                replace(
                    place,
                    center=(place.center[0] * scale, place.center[1] * scale),
                    radius=place.radius * scale,
                )
                for place in places
            ]
            obstacles = [(x * scale, y * scale, r * scale) for x, y, r in obstacles]
            for node in nodes:
                node.pos = (node.pos[0] * scale, node.pos[1] * scale)
        self.places = PlaceSystem(places)
        self.obstacles = obstacles
        self.resources = ResourceCycleSystem(nodes)
        self.clock = VillageClock()
        self.weather = "sunny"
        self._weather_timer = 0

    def advance_environment(self):
        self.clock.advance()
        self._weather_timer += 1
        events = []
        if self._weather_timer >= TICKS_PER_BAND:
            self._weather_timer = 0
            previous = self.weather
            roll = self.rng.random()
            self.weather = "rainy" if roll < (0.22 if previous == "sunny" else 0.55) else "sunny"
            if self.weather != previous:
                events.append({"kind": "weather", "weather": self.weather})
        events.extend(self.resources.tick())
        return events

    # --- 幾何（実行時にのみ使用） ---

    def is_position_open(self, pos, radius=0.0):
        if not (0.0 <= pos[0] <= self.size and 0.0 <= pos[1] <= self.size):
            return False
        return all(distance(pos, obstacle) >= obstacle[2] + radius for obstacle in self.obstacles)

    def line_blocked(self, start, end):
        return any(
            point_to_segment_distance(obstacle, start, end) < obstacle[2]
            for obstacle in self.obstacles
        )

    def move_with_collisions(self, start, vx, vy, body_radius=0.4):
        desired = (
            clamp(start[0] + vx, 0.3, self.size - 0.3),
            clamp(start[1] + vy, 0.3, self.size - 0.3),
        )
        hit = next(
            (o for o in self.obstacles if distance(desired, o) < o[2] + body_radius), None
        )
        if hit is None:
            return desired, False

        normal = normalized(desired[0] - hit[0], desired[1] - hit[1])
        if normal == (0.0, 0.0):
            normal = normalized(start[0] - hit[0], start[1] - hit[1]) or (1.0, 0.0)
        dot = vx * normal[0] + vy * normal[1]
        slide = (
            clamp(start[0] + vx - dot * normal[0], 0.3, self.size - 0.3),
            clamp(start[1] + vy - dot * normal[1], 0.3, self.size - 0.3),
        )
        if distance(slide, hit) >= hit[2] + body_radius:
            return slide, True

        tangent = (-normal[1], normal[0])
        step = math.hypot(vx, vy) * 0.7
        for sign in (1, -1):
            candidate = (
                clamp(start[0] + tangent[0] * sign * step + normal[0] * 0.1, 0.3, self.size - 0.3),
                clamp(start[1] + tangent[1] * sign * step + normal[1] * 0.1, 0.3, self.size - 0.3),
            )
            if self.is_position_open(candidate, body_radius):
                return candidate, True
        return start, True

    def nearest_open_point(self, origin, body_radius=0.4):
        if self.is_position_open(origin, body_radius):
            return origin
        for radius in (0.8, 1.4, 2.2, 3.2, 4.6):
            for index in range(16):
                angle = (index / 16) * TAU
                candidate = (
                    clamp(origin[0] + math.cos(angle) * radius, 0.5, self.size - 0.5),
                    clamp(origin[1] + math.sin(angle) * radius, 0.5, self.size - 0.5),
                )
                if self.is_position_open(candidate, body_radius):
                    return candidate
        return self.size / 2, self.size / 2
