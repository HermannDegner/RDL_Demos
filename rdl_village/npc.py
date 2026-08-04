"""VillageNPC と意思決定サイクル。

参照:
  RDL_NPC行動決定システム §4（四層）, §5（各モジュール）, §7（統合実行フロー）, §9（ログ）
  RDL_簡易村シミュレーター §5（NPCの最小構造）, §10（日課・予定・偶発）, §12（H_vec・ξ・Leap）
"""

import math
from collections import defaultdict, deque
from dataclasses import dataclass

from .action import TAU, ActionCandidate, MovementPlanner, PhysicalConstraintLayer
from .core import (
    BasalHeat,
    Boundary,
    ErrorLedger,
    HVec,
    LeapEngine,
    Phase,
    XiPool,
    clamp,
    distance,
    weighted_choice,
)
from .profiles import profile_for
from .dialogue import RelationalDialogueSystem
from .perception import PredictionField
from .relations import ActionMemory, RelationMemorySystem

# NPC§5.2 の5欲求に PAIRING を加える。
# 階層構造§1 の定義では基層構造は「進化的選択圧によって形成された」層であり、
# 繁殖動機はその選択圧そのものなので、他の欲求の隣ではなく下に位置する。
# 神経力学§1 のオキシトシン（自己拡張的重み付け）はこの動機の派生として扱う。
DRIVES = ("COMFORT", "SOCIAL", "EXPLORATION", "CREATION", "RECOGNITION", "PAIRING")

# 一回の利用で取り込める上限。simulation 側の要求量と同一の定義を使う。
# 期待値に残量をそのまま入れると、満量ノードでは完全に成功しても誤差が残り、
# H_body と行動記憶の失敗学習を汚染する。
INTAKE_LIMIT = {"food": 34.0, "water": 45.0, "rest": 55.0, "material": 8.0}

# 備蓄（村§6.1 Place.objects, §7.3 置く／取る）。
# 備蓄がないと、その日に食べる分をその日に採り続けるしかない。
# 薄暮に安心できる場所へ戻る余裕は、蓄えがあって初めて生まれる。
CARRY_LIMIT = {"food": 60.0, "water": 60.0, "material": 24.0}
STORABLE = ("food", "water")

# 待機一回で回復する疲労。期待値と実測値が同じ語彙を指すようにする。
WAIT_RELIEF = 1.6

# 繁殖「動機」のみを実装し、繁殖「機構」（出産・継承・世代選択）は入れない。
# 村§15.3 は世代選択の同時導入が因果の判別を困難にすると警告している。
PAIRING_CYCLE = 96.0

DEFAULT_MOVE_WEIGHTS = {
    "goal": 1.0,
    "resource": 0.55,
    "comfort": 0.4,
    "affiliation": 0.5,
    "coordination": 0.6,
    "familiarity": 0.3,
    "exploration": 0.45,
    "fear": 0.9,
    "irritation": 0.5,
    "intrusion": 0.6,
    "crowding": 0.4,
    "motion": 1.0,
}


@dataclass
class BodyState:
    """身体状態（村§5.1）。"""

    hunger: float = 20.0
    thirst: float = 15.0
    fatigue: float = 15.0
    arousal: float = 0.6
    safety: float = 0.8
    base_speed: float = 0.85
    carrying: float = 0.0

    LIMITS = {"hunger": 190.0, "thirst": 165.0, "fatigue": 205.0}

    def tick(self, band, sheltered=False, light=1.0):
        self.hunger += 0.26
        self.thirst += 0.30
        if sheltered:
            # 休息可能な場所に居れば回復する。暗いほどよく休まる（村§10）。
            self.fatigue = max(0.0, self.fatigue - (0.30 + 0.55 * (1.0 - light)))
        else:
            self.fatigue += 0.22 + 0.18 * (1.0 - light)
        # 覚醒は光量と疲労で決まる。暗く、疲れているほど落ちる。
        self.arousal = clamp(
            (0.35 + 0.65 * light) * (1.0 - self.fatigue / 260.0), 0.05, 1.0
        )

    def condition(self):
        """身体の効き。0.35で最も衰弱、1.0で健常。

        空腹と渇きには、これまで限界に達するまで何の影響もなかった。
        189で健常、190で即死という段差は、余裕を保つ理由を個体から奪う。
        衰えが先に来て、死はその果てに来る。
        """
        strain = max(self.hunger_ratio(), self.thirst_ratio(), self.fatigue_ratio())
        return clamp(1.0 - max(0.0, strain - 0.45) * 0.85, 0.35, 1.0)

    def speed(self):
        return self.base_speed * self.condition() * clamp(1.0 - self.carrying / 160.0, 0.6, 1.0)

    # 各変数が1tickあたり増える量（休息可能な場所以外での既定値）。
    RATES = {"hunger": 0.26, "thirst": 0.30, "fatigue": 0.22}

    def fatal(self):
        for key, limit in self.LIMITS.items():
            if getattr(self, key) >= limit:
                return key
        return None

    def ticks_to_fatal(self):
        """今の速度で、最も逼迫している変数が限界へ達するまでの残りtick。"""
        return min(
            (self.LIMITS[key] - getattr(self, key)) / rate
            for key, rate in self.RATES.items()
        )

    def hunger_ratio(self):
        return clamp(self.hunger / 120.0, 0.0, 1.5)

    def thirst_ratio(self):
        return clamp(self.thirst / 100.0, 0.0, 1.5)

    def fatigue_ratio(self):
        return clamp(self.fatigue / 110.0, 0.0, 1.5)

    def crisis(self):
        return max(self.hunger_ratio(), self.thirst_ratio(), self.fatigue_ratio())

    def snapshot(self):
        return {
            "hunger": round(self.hunger, 1),
            "thirst": round(self.thirst, 1),
            "fatigue": round(self.fatigue, 1),
        }


class BasalDynamicsSystem:
    """基層欲求から行動勾配を生成する（NPC§5.2）。

    性格プリセットは完成された人格ではなく初期条件であり、運用中にドリフトする。
    """

    def __init__(self, preset):
        self.sensitivity = dict(preset)
        self.activation = {drive: 0.2 for drive in DRIVES}
        self.satisfaction = {drive: 0.5 for drive in DRIVES}
        self.phase = {drive: Phase.LAT for drive in DRIVES}

    def update(self, body, perception, ticks_since_dialogue, unknown_ratio, materials, pairing=0.0):
        raw = {
            "COMFORT": body.fatigue_ratio() * 0.7 + perception.discomfort * 0.6,
            "SOCIAL": clamp(ticks_since_dialogue / 40.0, 0.0, 1.2)
            + len(perception.visible_agents) * 0.06,
            "EXPLORATION": unknown_ratio,
            # 所持量で駆動すると「素材を集めるには素材が必要」という循環になる。
            # 駆動するのは充足の不足であり、所持は実行を後押しするだけ。
            "CREATION": clamp(0.55 - self.satisfaction["CREATION"], 0.0, 1.0) * 0.9
            + clamp(materials / 6.0, 0.0, 0.35),
            "RECOGNITION": clamp(0.35 - self.satisfaction["RECOGNITION"], 0.0, 1.0),
            "PAIRING": pairing,
        }
        for drive in DRIVES:
            value = raw[drive] * self.sensitivity[drive]
            self.activation[drive] = clamp(self.activation[drive] * 0.72 + value * 0.4, 0.0, 1.6)
            self.phase[drive] = Phase.ACT if self.activation[drive] > 0.45 else Phase.LAT

    def satisfy(self, drive, amount):
        self.satisfaction[drive] = clamp(self.satisfaction[drive] + amount, 0.0, 1.0)
        self.activation[drive] = clamp(self.activation[drive] - amount * 0.8, 0.0, 1.6)

    def drift(self, drive, amount):
        """経験による感度のドリフト（NPC§5.2, §12-1）。"""
        self.sensitivity[drive] = clamp(self.sensitivity[drive] + amount, 0.15, 1.6)

    def snapshot(self):
        return {drive: round(value, 2) for drive, value in self.activation.items() if value > 0.05}


@dataclass
class ScheduleBlock:
    """予定は脚本ではなく、上層候補へ重みを与えるM_B（村§10）。"""

    band: str
    place_id: str
    action_type: str
    flexibility: float = 0.5


class UpperContextSystem:
    """予定・役割・約束を行動候補へ接続する（NPC§5.4）。"""

    def __init__(self, role, blocks):
        self.role = role
        self.blocks = {block.band: block for block in blocks}
        self.promises = []
        self.active_goal = None
        self.adherence = 0.6

    def block_for(self, band):
        return self.blocks.get(band)

    def add_promise(self, partner, place_id, band):
        self.promises.append({"partner": partner, "place": place_id, "band": band, "kept": None})
        del self.promises[:-4]

    def pending_promise(self, band):
        return next((item for item in self.promises if item["band"] == band and item["kept"] is None), None)

    def resolve_promise(self, promise, kept):
        promise["kept"] = kept
        self.adherence = clamp(self.adherence + (0.05 if kept else -0.08), 0.1, 0.95)

    def loosen(self):
        """H_goal Leap：予定の柔軟性を上げる（村§12.3）。"""
        for block in self.blocks.values():
            block.flexibility = clamp(block.flexibility + 0.18, 0.0, 0.95)


class VillageNPC:
    """RDL_NPC行動決定システムを持つ個体（村§5）。"""

    # 思考的探索の有無を切り替える。A/B測定用。
    REFLECTION_ENABLED = True
    # 繁殖動機の有無を切り替える。A/B測定用。
    PAIRING_ENABLED = True
    # 競合とみなす期間。同一tickの重なりでは競合はほぼ発生しない。
    RIVAL_WINDOW = 80
    # この危機度を越えたら通常候補を捨てて緊急候補だけで決める。
    EMERGENCY_CRISIS = 0.78

    def __init__(self, name, role, preset, home_id, schedule, pos, profile, rng, neuro):
        self.name = name
        self.role = role
        self.home_id = home_id
        # 基層パラメータを係数へ反映した、この個体固有のプロファイル。
        self.neuro = neuro
        self.profile = profile_for(profile, neuro)
        profile = self.profile
        self.rng = rng

        self.x, self.y = float(pos[0]), float(pos[1])
        self.vx = self.vy = 0.0
        self.body_radius = 0.4
        self.alive = True

        self.body = BodyState()
        self.basal = BasalDynamicsSystem(preset)
        self.upper = UpperContextSystem(role, schedule)
        self.prediction_field = PredictionField(profile.node)
        self.relations = RelationMemorySystem(name)
        self.action_memory = ActionMemory()
        self.dialogue = RelationalDialogueSystem(profile.dialogue, rng)

        self.boundary = Boundary(profile.boundary)
        self.h_vec = HVec(profile.h)
        self.xi = XiPool(profile.node)
        self.leap_engine = LeapEngine(profile.leap, self.boundary)
        self.basal_heat = BasalHeat(neuro)
        self.phase = Phase.ACT

        self.planner = MovementPlanner(rng)
        self.gate = PhysicalConstraintLayer()
        self.move_weights = dict(DEFAULT_MOVE_WEIGHTS)
        # オキシトシン＝自己拡張的重み付け。B_self が広いほど他者への接近勾配が強い。
        self.move_weights["affiliation"] *= 0.6 + neuro.oxytocin
        self.move_weights["fear"] *= 0.7 + neuro.noradrenaline * 0.5

        self.inventory = []
        # 携行している蓄え。村§7.3 の「取る／置く」の主体側。
        self.stock = {}
        self.pending = None
        self.last_action_name = None
        self.intended_place_label = None
        self.coordination_partner = None
        self.ticks_since_dialogue = 0
        self.goal_stall = 0
        self.visited_this_band = set()
        self.promise_break = 0.0
        self.explore_boost = 0.0
        self.outward_ticks = 0
        self.reflections = 0
        self.hypotheses_made = 0
        self.reunions = 0
        self.pending_reactivation = 0.0

        # 繁殖動機。個体ごとに周期の位相をずらす。
        self.pairing_phase = rng.random()
        self.mate = None
        self.courtship = defaultdict(float)
        self.courtship_attempts = 0
        self.rejections = 0
        self.rivals = defaultdict(int)
        # 誰にいつ言い寄られたか。競合は同一tickではなく期間で成立する。
        self.courted_by = deque(maxlen=12)

        self.leap_log = deque(maxlen=12)
        self.recent_events = deque(maxlen=16)
        self.explore_targets = deque(maxlen=6)

    def recent_rival(self, exclude, t):
        """自分に言い寄った相手のうち、直近で受け入れられた者を競合相手とみなす。"""
        for name, when, accepted in reversed(self.courted_by):
            if accepted and name != exclude and t - when <= self.RIVAL_WINDOW:
                return name
        return None

    @property
    def pos(self):
        return self.x, self.y

    # ------------------------------------------------------------------
    # 1-2. 観測とB更新
    # ------------------------------------------------------------------

    def update_boundary(self, perception):
        known = len(self.prediction_field.places)
        unknown_ratio = clamp(1.0 - known / 12.0, 0.0, 1.0)
        self.explore_boost *= 0.94
        if self.outward_ticks > 0:
            self.outward_ticks -= 1
        materials = sum(item["amount"] for item in self.inventory if item["kind"] == "material")
        self.basal.update(
            self.body,
            perception,
            self.ticks_since_dialogue,
            unknown_ratio,
            materials,
            self.pairing_pressure(perception.t),
        )
        self.boundary.summary = {
            "place": perception.place_id,
            "band": perception.band,
            "visible_agents": len(perception.visible_agents),
            "crisis": round(self.body.crisis(), 2),
            "theta": round(self.boundary.theta_effective(self.xi.value), 3),
        }

    # ------------------------------------------------------------------
    # 4. 予測差の評価 → H_vec → Leap
    # ------------------------------------------------------------------

    def evaluate_prediction(self, perception, field_errors, t):
        ledger = ErrorLedger()
        pending = self.pending
        leap = None

        if pending:
            moved = distance(pending["pos"], self.pos)
            expected_progress = pending.get("expected_progress", 0.0)
            if expected_progress > 0.01:
                achieved = clamp(moved / expected_progress, 0.0, 1.3)
                ledger.record("motion", pending["expected_motion"], achieved * pending["expected_motion"])
                self.prediction_field.update_traversability(pending["pos"], self.pos, clamp(achieved, 0.0, 1.0))
                newly_seen = [
                    obstacle
                    for obstacle in perception.visible_obstacles
                    if distance(pending["pos"], obstacle) - obstacle[2] > perception.vision_radius * 0.9
                ]
                if newly_seen:
                    ledger.explain("motion", "unseen_obstacle", 0.35)
            if pending.get("expected_relief") is not None:
                observed = pending["relief_before"] - self._relief_metric(pending["relief_kind"])
                # 他チャネルは 0〜1 に正規化されている。生の資源量のまま入れると
                # body だけ二桁の誤差になり、観測頻度が低くても一撃で天井に届く。
                expected = pending["expected_relief"]
                scale = max(1.0, expected, observed)
                ledger.record_raw("body", abs(expected - observed) / scale)
            if pending.get("relation_target"):
                observed = self._observed_response(pending, perception)
                if observed is not None:
                    error = self.relations.evaluate_response(pending["relation_target"], observed)
                    if error is not None:
                        ledger.record_raw("relation", error)
                else:
                    predicted = self.relations.pending_predictions.get(
                        pending["relation_target"], {}
                    ).get("predicted", 0.5)
                    self.relations.drop_prediction(pending["relation_target"])
                    self.xi.hold(
                        {
                            "kind": "relation",
                            "target": pending["relation_target"],
                            "predicted": predicted,
                            "held_at": t,
                        },
                        t,
                    )
            if pending.get("goal_pos") is not None:
                gap_now = distance(self.pos, pending["goal_pos"])
                if perception.place_id == pending["goal_place"]:
                    self.goal_stall = 0
                    ledger.record_raw("goal", 0.0)
                elif pending.get("goal_pursued"):
                    # 予定地へ向かったのに詰められなかった分が予測差になる。
                    closed = pending["goal_gap"] - gap_now
                    expected = max(0.05, pending.get("expected_progress", 0.0))
                    ledger.record_raw("goal", clamp(1.0 - clamp(closed / expected, 0.0, 1.0), 0.0, 1.0))
                    self.goal_stall = self.goal_stall + 1 if closed < expected * 0.3 else 0
                else:
                    # 予定より優先度の高い行動を選んだ場合の滞留は説明がつく（村§10）。
                    self.goal_stall += 1
                    ledger.record_raw("goal", clamp(self.goal_stall / 20.0, 0.0, 1.0))
                    ledger.explain("goal", "priority_override", 0.55)

        # 固着していた熱が再会で戻る（階層構造§1：中核構造への沈降と再前景化）。
        # H は派生量であり、処理されないまま熱として在り続けることはない。
        # 処理されなかった分は M_lat として構造に沈み、再び合ったときに熱へ戻る。
        reactivated, events = self.relations.take_reactivated()
        if reactivated > 0.0:
            # 誤差としても記録する（ログとξへの反映のため）。
            ledger.record_raw("relation", clamp(reactivated, 0.0, 1.0))
            self.pending_reactivation = reactivated
            self.recent_events.append((t, "reunion", [name for name, _ in events]))
            self.reunions += len(events)

        if self.promise_break:
            # 約束の不成立は H_goal と H_relation の両方へ効く（村§13.2）。
            ledger.record_raw("goal", self.promise_break)
            ledger.record_raw("relation", self.promise_break * 0.6)
            self.promise_break = 0.0

        ledger.record_raw("resource", field_errors["resource"])
        if field_errors["hypothesis"]:
            # 思考的探索が内生した予測が外れた分。誤差の出所としては内的だが、
            # 突き合わせたのは外的観測なので説明はつけない。
            ledger.record_raw("resource", field_errors["hypothesis"])
        for belief_id in self._dormant_expectations(perception):
            ledger.explain("resource", f"known_dormant:{belief_id}", 0.3)

        ledger.record_raw("dialogue", self.dialogue.pressure())
        ledger.record_raw("environment", perception.discomfort)
        if perception.weather == "rainy":
            ledger.explain("environment", "rain_is_known", 0.22)
        if perception.is_night:
            ledger.explain("environment", "night_is_known", 0.2)

        # Hは生の予測差Eを受け取る（村§12.1）。
        # ξへ流れるのは、説明のつかない残差だけ（NPC§3.6）。
        self.h_vec.observe(ledger.errors)

        # 戻ってきた熱はゲインで平滑化しない。
        # これは新しい予測差ではなく、既に蓄積されていた熱の再前景化である。
        # 通常の誤差経路へ流すと、観測頻度の低いチャネルは何度再会しても
        # θへ届かず、固着させた意味がなくなる。
        if self.pending_reactivation:
            self.h_vec.values["relation"] = clamp(
                self.h_vec.values["relation"] + self.pending_reactivation,
                0.0,
                self.profile.h.ceiling,
            )
            self.pending_reactivation = 0.0

        # 誤差が少ない状態が続けば、誤差とは別の熱源が立つ（階層構造§2 / D4）。
        observed_errors = list(ledger.errors.values())
        mean_error = sum(observed_errors) / len(observed_errors) if observed_errors else 0.0
        boredom = self.basal_heat.update(mean_error, self.exploration_margin())
        self.h_vec.set_direct("boredom", boredom)

        residual = ledger.largest_residual()
        self.xi.accumulate(residual)
        # 退屈は「既存の最有力候補以外を試す余地」としてもξへ効く（NPC§3.6）。
        self.xi.accumulate(boredom * 0.25)
        self.xi.decay()

        leap_event = self.leap_engine.check(self.h_vec, self.xi, t, exclude=self.h_vec.direct)
        if leap_event is None:
            leap_event = self.leap_engine.check_basal(self.h_vec, self.xi, t)
        if leap_event:
            leap = self._apply_leap(leap_event)
        self.pending = None
        return ledger, leap

    # ------------------------------------------------------------------
    # 繁殖動機：既存の絆では満たされない、特定の他者への接近圧
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 備蓄：携行と保管
    # ------------------------------------------------------------------

    def carried(self, kind):
        return self.stock.get(kind, 0.0)

    def store_surplus(self, kind, amount):
        """使い切れなかった分を携行する。重さは移動速度へ効く。"""
        if kind not in CARRY_LIMIT or amount <= 0.0:
            return 0.0
        room = CARRY_LIMIT[kind] - self.stock.get(kind, 0.0)
        kept = clamp(amount, 0.0, max(0.0, room))
        if kept > 0.0:
            self.stock[kind] = self.stock.get(kind, 0.0) + kept
            self._sync_carrying()
        return kept

    def consume_carried(self, kind, amount):
        held = self.stock.get(kind, 0.0)
        taken = min(held, amount)
        if taken > 0.0:
            self.stock[kind] = held - taken
            self._sync_carrying()
        return taken

    def _sync_carrying(self):
        self.body.carrying = sum(self.stock.values())

    def provision_shortfall(self, perception):
        """暗い間を持たせられるかの予測。

        退避も備蓄も、現在の光量や空腹への反射ではなく、
        「明るくなるまでに何がどれだけ足りなくなるか」の見積りから来る。

        この予測は外れうる。少なく見積もって夜明けに飢えていれば、
        それは body チャネルの予測差として立つ。反射ではなく予測にすることで、
        機構がRDLのループの内側に入る。
        """
        ahead = perception.dark_ahead
        if ahead <= 0:
            return {}, 0.0
        shortfall = {}
        # 基準は致死限界ではなく、行動を起こす水準。
        # 限界で測ると「夜の間に死にはしない」ので不足が立たず、
        # 予測が常に「備え不要」を返す。
        comfort = {"food": 120.0 * 0.55, "water": 100.0 * 0.55}
        for kind, current, rate in (
            ("food", self.body.hunger, BodyState.RATES["hunger"]),
            ("water", self.body.thirst, BodyState.RATES["thirst"]),
        ):
            projected = current + rate * ahead
            need = max(0.0, projected - comfort[kind])
            shortfall[kind] = max(0.0, need - self.stock.get(kind, 0.0))
        worst = max(
            (value / max(1.0, CARRY_LIMIT[kind]) for kind, value in shortfall.items()),
            default=0.0,
        )
        return shortfall, clamp(worst, 0.0, 1.0)

    def _gather_candidates(self, perception):
        """後で使うために採る（村§7.3「取る」）。

        空腹になってから採りに行くと、採った分はその場で消える。
        余剰が出るのは「食べ残し」であって備蓄ではない。
        備蓄は、**まだ困っていないうちに**、これから困る見込みに備えて採る行動である。

        暗くなる見込みが備蓄の動機になる。薄暮に安心できる場所へ戻れるのは、
        戻っても食べる物があるからで、蓄えのない個体に退避の余裕はない。
        """
        found = []
        shortfall, _ = self.provision_shortfall(perception)
        if not shortfall:
            return found
        for kind in STORABLE:
            missing = shortfall.get(kind, 0.0)
            if missing < 4.0:
                continue
            room = CARRY_LIMIT[kind] - self.stock.get(kind, 0.0)
            if room < 4.0:
                continue
            ratio = self.body.hunger_ratio() if kind == "food" else self.body.thirst_ratio()
            # 逼迫していれば採るより食べる。備蓄は余裕のある個体の行動である。
            if ratio > 0.62:
                continue
            for belief in self.prediction_field.beliefs_of_kind(kind):
                if distance(self.pos, belief.pos) > PhysicalConstraintLayer.USE_RANGE:
                    continue
                want = min(room, missing, INTAKE_LIMIT[kind])
                found.append(
                    ActionCandidate(
                        "gather",
                        ("basal", "upper"),
                        node_id=belief.node_id,
                        place_id=belief.place_id,
                        target_pos=belief.pos,
                        score_components={
                            # 足りない見込みの量そのものが動機になる。
                            "provision": clamp(missing / CARRY_LIMIT[kind], 0.0, 1.0)
                            * 2.2
                            * belief.reliability()
                        },
                        expected_outcome={"relief": kind, "amount": want},
                        uncertainty=1.0 - belief.confidence,
                        reason=f"provision_{kind}",
                    )
                )
        return found

    def _deficit(self, kind):
        """その資源で埋めるべき身体の不足量。"""
        return {"food": self.body.hunger, "water": self.body.thirst, "rest": self.body.fatigue}.get(kind, 0.0)

    def _deposit_candidates(self, perception):
        """安心できる場所へ蓄えを置く（村§7.3「置く」, §6.1 Place.objects）。

        携行は速度を落とす。置いておけるなら置いたほうがよいが、
        置いた先は自分だけのものではない。
        """
        place_id = perception.place_id
        if not place_id:
            return []
        meaning = self.prediction_field.places.get(place_id)
        if meaning is None or meaning.comfort < 0.15:
            return []
        found = []
        for kind in STORABLE:
            held = self.stock.get(kind, 0.0)
            if held < 8.0:
                continue
            found.append(
                ActionCandidate(
                    "deposit",
                    ("upper",),
                    node_id=kind,
                    place_id=place_id,
                    score_components={
                        "unburden": clamp(self.body.carrying / 80.0, 0.0, 1.0)
                        * (0.4 + meaning.comfort)
                    },
                    expected_outcome={"stored": kind},
                    reason=f"deposit_{kind}",
                )
            )
        return found

    def _stock_candidates(self, perception):
        """蓄えから食べる／飲む。移動を伴わないので、暗い時間帯の支えになる。

        携行している分と、いまいる場所に置かれている分の双方を見る（村§7.3「取る」）。
        """
        found = []
        for kind, ratio in (("food", self.body.hunger_ratio()), ("water", self.body.thirst_ratio())):
            stored = perception.stored_here.get(kind, 0.0)
            if stored >= 4.0 and ratio >= 0.28:
                found.append(
                    ActionCandidate(
                        "take_stored",
                        ("physical", "basal"),
                        node_id=kind,
                        place_id=perception.place_id,
                        score_components={"stored": self._urgency(ratio) * 0.95},
                        expected_outcome={
                            "relief": kind,
                            "amount": min(stored, INTAKE_LIMIT[kind], self._deficit(kind)),
                        },
                        uncertainty=0.05,
                        reason=f"stored_at_{perception.place_id}",
                    )
                )
            held = self.stock.get(kind, 0.0)
            if held < 2.0 or ratio < 0.28:
                continue
            found.append(
                ActionCandidate(
                    "use_stock",
                    ("physical", "basal"),
                    node_id=kind,
                    score_components={"stock": self._urgency(ratio) * 0.9},
                    expected_outcome={
                        "relief": kind,
                        "amount": min(held, INTAKE_LIMIT[kind], self._deficit(kind)),
                    },
                    uncertainty=0.05,
                    reason=f"stocked_{kind}",
                )
            )
        return found

    def exploration_margin(self):
        """探索に出せる余裕。

        現在の危機度で測るのは遅すぎる。退屈で遠くへ出た時点ではまだ余裕があり、
        危機に気づいたときには既に遠い。効いてくるコストは往路ではなく復路である。

        測るのは「今いる場所から、知っている最寄りの資源へ戻れるか」。
        自分の予測場だけを使うので、全知にはならない。
        """
        remaining = self.body.ticks_to_fatal()
        if remaining <= 0.0:
            return 0.0
        speed = max(0.05, self.body.speed())
        worst = 0.0
        for kind in ("water", "food"):
            beliefs = self.prediction_field.beliefs_of_kind(kind)
            if not beliefs:
                # 行き先を知らないなら、余裕があるとは言えない。
                worst = 1.0
                continue
            nearest = min(distance(self.pos, belief.pos) for belief in beliefs)
            worst = max(worst, (nearest / speed) / remaining)
        return clamp(1.0 - worst, 0.0, 1.0)

    def pairing_pressure(self, t):
        """周期的に立ち上がる。身体が逼迫していれば抑制される。

        つがい成立後も完全には消えない（絆の維持側へ回る）が、
        新規の求愛を駆動する水準ではなくなる。
        """
        cycle = 0.5 + 0.5 * math.sin(TAU * (t / PAIRING_CYCLE + self.pairing_phase))
        pressure = cycle * clamp(1.0 - self.body.crisis() * 1.2, 0.0, 1.0)
        if self.mate:
            pressure *= 0.25
        return clamp(pressure, 0.0, 1.0)

    def _attractiveness(self, name):
        """相手の見込み。全知ではなく、自分が観測・記憶した範囲から作る。

        目撃記録（村§11.3）をここで初めて読む。溜めた観察に意味を与えるのは、
        評価が必要になった時点である。
        """
        state = self.relations.state(name)
        hints = self.relations.reputation_hints.get(name, ())
        seen_good = sum(confidence for _, act, _, confidence in hints if act in {"give", "help"})
        seen_bad = sum(confidence for _, act, _, confidence in hints if act in {"block", "contest"})
        return (
            state.trust * 0.9
            + state.predictability * 0.6
            + state.familiarity * 0.3
            + seen_good * 0.25
            - seen_bad * 0.3
            - state.fear * 0.8
            - state.irritation * 0.7
        )

    def _courtship_candidates(self, perception):
        """つがい相手への選択的接近。

        SOCIAL と違い、誰と話しても満たされない。特定の相手を要求する。
        相手が既につがいかどうかは直接は分からない。拒否されて初めて分かる。
        """
        pressure = self.basal.activation["PAIRING"]
        # 身体が逼迫しているときに求愛して死んでは元も子もない。
        if not self.PAIRING_ENABLED or self.mate or pressure < 0.42 or self.body.crisis() > 0.62:
            return []
        found = []
        for observation in perception.visible_agents:
            state = self.relations.state(observation.name)
            appeal = self._attractiveness(observation.name)
            if appeal < 0.15:
                continue
            progress = self.courtship[observation.name]
            persistence = self.neuro.oxytocin * 0.6 + self.neuro.d1 * 0.3
            gap = distance(self.pos, observation.pos)
            score = pressure * (0.8 + appeal) * persistence + progress * 0.5
            if gap <= PhysicalConstraintLayer.TALK_RANGE:
                found.append(
                    ActionCandidate(
                        "court",
                        ("basal",),
                        target=observation.name,
                        target_pos=observation.pos,
                        score_components={"pairing": score},
                        expected_outcome={"response": clamp(0.35 + appeal * 0.3 + progress * 0.3, 0.05, 0.95)},
                        uncertainty=1.0 - state.predictability,
                        reason="pairing",
                    )
                )
            else:
                found.append(
                    ActionCandidate(
                        "approach",
                        ("basal",),
                        target=observation.name,
                        target_pos=observation.pos,
                        score_components={"pairing": score * 0.75},
                        expected_outcome={"response": self.relations.predict_response(observation.name)},
                        uncertainty=1.0 - state.predictability,
                        reason="pairing_approach",
                    )
                )
        return found

    def bond_with(self, name, t):
        self.mate = name
        self.coordination_partner = name
        state = self.relations.state(name)
        state.nudge("affinity", 0.35)
        state.nudge("trust", 0.2)
        state.nudge("dependency", 0.3, 0.0, 1.0)
        self.basal.satisfy("PAIRING", 1.0)
        # B_self の拡張がつがいへ集中する（神経力学§1）。
        self.move_weights["coordination"] = clamp(
            self.move_weights["coordination"] + self.neuro.oxytocin * 0.5, 0.2, 1.8
        )
        self.recent_events.append((t, "bond", name))

    def on_rejected_by(self, name, rival, t):
        """拒否は求愛の意欲を削るが、友人関係そのものは壊さない。

        affinity を大きく下げると、村の関係網ごと崩れる。
        減衰させるのは courtship（その相手への求愛の見込み）の側にする。
        """
        self.rejections += 1
        self.courtship[name] = max(0.0, self.courtship[name] - 0.35)
        state = self.relations.state(name)
        state.nudge("affinity", -0.015)
        if rival:
            self.rivals[rival] += 1
            rival_state = self.relations.state(rival)
            rival_state.nudge("territoriality", 0.18, 0.0, 1.0)
            rival_state.nudge("irritation", 0.14, 0.0, 1.0)
            rival_state.nudge("trust", -0.05)
        self.recent_events.append((t, "rejected", name))

    # ------------------------------------------------------------------
    # 思考的探索：身体を動かさずに構造の中を探索する
    # ------------------------------------------------------------------

    def reflect(self, perception, t):
        """内的探索。外的な未踏が尽きても、構造の中の未接続は尽きない。

        参照:
          RDL_階層構造モジュール §1（上層構造＝新たな構造の生成場）, §2（基層構造的跳躍）
          RDL_NPC行動決定システム §6.1（ξ探索の「新規接続候補」）, §8.3（未確定の保持）

        産物は必ず M_lat として仮置きし、外的観測に当たるまで M_act へ昇格させない。
        内生した仮説を内生した確信で裏付けると閉じたループ（反芻）になる。
        NPC§5.5 が LLM 出力に課しているのと同じ制約をここにも適用する。
        """
        operations = [
            (self._recombine_places, 0.9 + self.neuro.d4 * 0.5),
            (self._revisit_unresolved, 0.7),
            (self._replay_failure, 0.5 + self.neuro.d3 * 0.4),
            (self._consolidate_patterns, 0.4 + self.neuro.d3 * 0.3),
        ]
        total = sum(weight for _, weight in operations)
        pick = self.rng.random() * total
        upto = 0.0
        for operation, weight in operations:
            upto += weight
            if upto >= pick:
                record = operation(perception, t)
                break
        else:
            record = operation(perception, t)

        self.basal_heat.discharge(0.72)
        self.reflections += 1
        self.recent_events.append((t, "reflect", record.get("op")))
        return record

    def _recombine_places(self, perception, t):
        """いま見えていない場所の現在の状態を、既存の構造から推定する。

        二つの経路がある。
          未訪問 : 同種の既知の場所から類推する（空間的な未接続を繋ぐ）
          疎遠   : 最後に見てからの経過時間から、資源の回復を見込む（時間的な外挿）

        どちらも移動せずに立つ予測であり、行けば必ず外れうる。
        そこが誤差源になる。
        """
        pool = [
            meaning
            for meaning in self.prediction_field.known_places()
            if meaning.center is not None
            and meaning.hypothesis is None
            and meaning.place_id != perception.place_id
        ]
        if not pool:
            return {"op": "recombine", "result": "no_gap"}

        # 場所が見えていることと、そこの資源の状態を知っていることは別である。
        # 林は遠くから見えても、実が戻ったかは近づかないと分からない。
        stale_beliefs = [
            belief
            for belief in self.prediction_field.resources.values()
            if belief.supposed is None and t - belief.last_seen >= 20
        ]
        if stale_beliefs:
            belief = max(stale_beliefs, key=lambda item: t - item.last_seen)
            elapsed = t - belief.last_seen
            peers = [
                item.expected_amount
                for item in self.prediction_field.resources.values()
                if item.kind == belief.kind and item.node_id != belief.node_id
            ]
            ceiling = max(peers) if peers else max(20.0, belief.expected_amount)
            # 離れている間に休眠が明けて回復しているはず、という時間的外挿。
            belief.suppose(min(ceiling, belief.expected_amount + ceiling * elapsed / 220.0))
            self.hypotheses_made += 1
            return {
                "op": "recombine",
                "result": "supposed",
                "basis": "regrowth",
                "node": belief.node_id,
                "elapsed": elapsed,
                "expected": round(belief.expected_amount, 1),
            }

        target = max(pool, key=lambda item: (0.0 if item.visits else 40.0) + (t - item.last_seen))
        staleness = t - target.last_seen
        if target.visits == 0:
            siblings = [
                meaning
                for meaning in self.prediction_field.known_places()
                if meaning.kind == target.kind and meaning.visits > 0
            ]
            if not siblings:
                return {"op": "recombine", "result": "no_analogue"}
            expected = sum(item.resource_expectation for item in siblings) / len(siblings)
            basis = "analogy"
            source = [item.place_id for item in siblings]
        else:
            if staleness < 12:
                return {"op": "recombine", "result": "too_fresh"}
            # 離れている間に休眠が明けているはず、という外挿。
            expected = clamp(target.resource_expectation + staleness / 260.0, 0.0, 1.0)
            basis = "regrowth"
            source = [f"stale:{staleness}"]

        target.suppose(expected, t)
        self.hypotheses_made += 1
        return {
            "op": "recombine",
            "result": "supposed",
            "basis": basis,
            "place": target.place_id,
            "from": source,
            "expected": round(expected, 2),
        }

    def _revisit_unresolved(self, perception, t):
        """ξ_poolに残した未確定を、現在の構造に照らして評価し直す（NPC§8.3）。

        キューを消費する経路は `_reevaluate_unresolved` 一本に限定する。
        独自に take_due すると、そこで扱えない型のレコードが黙って消え、
        「未確定を保持して後で再評価する」という定義が別経路から破れる。
        """
        pending = len(self.xi.unresolved)
        resolved = self._reevaluate_unresolved(t)
        if not pending:
            return {"op": "revisit", "result": "empty"}
        return {"op": "revisit", "result": "resolved", "count": resolved, "due": pending}

    def _replay_failure(self, perception, t):
        """過去の失敗を現在のW_ijで再生する。行動せずに評価だけ更新する。"""
        failures = [
            pattern
            for pattern in self.action_memory.patterns.values()
            if pattern.negative_count > pattern.positive_count and pattern.weight < 0.1
        ]
        if not failures:
            return {"op": "replay", "result": "no_failure"}
        pattern = min(failures, key=lambda item: item.weight)
        context, action_type, target = pattern.key
        changed = False
        if target and target in self.relations.states:
            # 相手との関係が当時と変わっていれば、同じ行動の見込みも変わる。
            gradient = self.relations.state(target).approach_gradient()
            if gradient > 0.4:
                pattern.weight = clamp(pattern.weight + 0.18, -0.9, 1.2)
                changed = True
        elif context[0] != perception.band:
            # 時間帯が変われば同じ場所の意味も変わる。潜在相へ戻して再試行余地を残す。
            pattern.phase = Phase.LAT
            pattern.weight = clamp(pattern.weight + 0.10, -0.9, 1.2)
            changed = True
        return {
            "op": "replay",
            "result": "revised" if changed else "unchanged",
            "target": f"{action_type}:{target}",
        }

    def _consolidate_patterns(self, perception, t):
        """潜在相のパターンを統合する。

        NPC§5.3 は容量超過時に「潜在化・圧縮・統合を先に試す」と定めているが、
        通常の代謝で行っているのは潜在化までである。統合はここで行う。
        """
        latent = defaultdict(list)
        for pattern in self.action_memory.patterns.values():
            if pattern.phase is Phase.LAT:
                latent[(pattern.key[1], pattern.key[2])].append(pattern)
        merged = 0
        for (action_type, target), group in latent.items():
            if len(group) < 2:
                continue
            keep = max(group, key=lambda item: item.confidence)
            for other in group:
                if other is keep:
                    continue
                keep.weight = clamp((keep.weight + other.weight) / 2, -0.9, 1.2)
                keep.positive_count += other.positive_count
                keep.negative_count += other.negative_count
                del self.action_memory.patterns[other.key]
                merged += 1
            if merged:
                break
        return {"op": "consolidate", "result": "merged" if merged else "nothing", "count": merged}

    def _relief_metric(self, kind):
        return {"food": self.body.hunger, "water": self.body.thirst, "rest": self.body.fatigue}[kind]

    def _observed_response(self, pending, perception):
        """行為ごとに観測量を分ける。

        talk / give は受容そのものが観測値であり、その場に居続けたかではない。
        距離変化を全行為の観測値にすると、H_relation は社会的な受容・拒否ではなく
        事後の空間移動を測ることになる。
        """
        action = pending.get("relation_action")
        if action in {"talk", "court"}:
            accepted = pending.get("relation_accepted")
            return None if accepted is None else (1.0 if accepted else 0.0)
        if action == "give":
            accepted = pending.get("relation_accepted")
            return None if accepted is None else (1.0 if accepted else 0.0)

        name = pending["relation_target"]
        observation = perception.agent_named(name)
        if observation is None:
            return None
        before = pending.get("relation_gap")
        if before is None:
            return None
        now = distance(self.pos, observation.pos)
        if before - now > 0.25:
            return 1.0
        if now - before > 0.25:
            return 0.0
        return 0.5

    def _dormant_expectations(self, perception):
        dormant = []
        for observation in perception.visible_resources:
            if observation.state != "available":
                belief = self.prediction_field.belief(observation.node_id)
                if belief and belief.expected_amount < 1.0:
                    dormant.append(observation.node_id)
        return dormant

    def _apply_leap(self, event):
        """再編対象を最大Hのチャネルへ局所化する（NPC§6.2, 村§12.3）。"""
        self.phase = Phase.DELTA
        channel = event.channel
        actions = []

        if channel == "motion":
            worst = sorted(
                self.prediction_field.motion_memory.items(), key=lambda item: item[1]
            )[:3]
            for key, _ in worst:
                self.prediction_field.motion_memory[key] = 0.55
            self.move_weights["exploration"] = clamp(self.move_weights["exploration"] + 0.15, 0.1, 1.2)
            self.move_weights["motion"] = clamp(self.move_weights["motion"] - 0.08, 0.4, 1.6)
            actions.append("停滞セルのコストを再設定し別経路を探索")
        elif channel == "relation":
            for state in self.relations.known():
                state.predictability = clamp(state.predictability * 0.7, 0.05, 0.98)
            self.move_weights["intrusion"] = clamp(self.move_weights["intrusion"] + 0.12, 0.2, 1.4)
            actions.append("相手予測と接近距離のモデルを更新")
        elif channel == "dialogue":
            actions.extend(self.dialogue.on_leap())
        elif channel == "goal":
            self.upper.loosen()
            self.upper.active_goal = None
            actions.append("予定の柔軟性を引き上げ目標を再編")
        elif channel == "resource":
            weakened = 0
            for belief in self.prediction_field.resources.values():
                if belief.reliability() < 0.5:
                    belief.confidence = clamp(belief.confidence * 0.55, 0.05, 0.98)
                    belief.phase = Phase.LAT
                    weakened += 1
            self.basal.drift("EXPLORATION", 0.12)
            actions.append(f"古い資源記憶を{weakened}件弱化し探索範囲を拡張")
        elif channel == "boredom":
            # 誤差ではなく予測性の高さが熱源。再編の向きは M_B の拡張になる（階層構造§2）。
            # 既知の場所を選び直しても拡張にならない。既知圏の外側へ向ける。
            self.move_weights["exploration"] = clamp(self.move_weights["exploration"] + 0.25, 0.1, 1.4)
            self.move_weights["familiarity"] = clamp(self.move_weights["familiarity"] - 0.12, 0.05, 1.0)
            self.upper.loosen()
            self.explore_boost = 1.0
            self.outward_ticks = 40
            actions.append("既知圏の外側へ探索を向ける")
            distant = sorted(self.relations.known(), key=lambda item: item.familiarity)
            if distant:
                self.relations.state(distant[0].other).nudge("affinity", 0.12)
                actions.append(f"関係の薄い{distant[0].other}へ接近余地を作る")
            self.basal.drift("EXPLORATION", 0.02)
            self.basal_heat.discharge(self.profile.h.residual_after_leap)
            actions.append("退屈由来の仮想熱を放出")
        elif channel == "body":
            self.basal.drift("COMFORT", 0.1)
            actions.append("休息優先度を引き上げ")
        else:
            self.move_weights["comfort"] = clamp(self.move_weights["comfort"] + 0.12, 0.1, 1.2)
            actions.append("環境コストの見積りを更新")

        # 再編対象は最大Hのチャネルに局所化する（NPC§6.2）。
        # 全チャネルを放出すると、高頻度チャネルの跳躍が他チャネルの熱まで
        # 定期的に消し、破断位置の競合そのものを歪める。
        self.h_vec.retain_after_leap(channel)
        event.actions = actions
        self.leap_log.append(event.as_record())
        self.phase = Phase.REFORMED
        return event

    # ------------------------------------------------------------------
    # 5. 行動候補生成（四層）
    # ------------------------------------------------------------------

    def generate_candidates(self, perception):
        candidates = []
        candidates.extend(self._emergency_candidates(perception))
        candidates.extend(self._basal_candidates(perception))
        candidates.extend(self._memory_candidates(perception))
        candidates.extend(self._upper_candidates(perception))
        candidates.extend(self._social_candidates(perception))
        candidates.extend(self._courtship_candidates(perception))
        candidates.extend(self._stock_candidates(perception))
        candidates.extend(self._gather_candidates(perception))
        candidates.extend(self._deposit_candidates(perception))
        candidates.append(
            ActionCandidate(
                "wait",
                ("basal",),
                score_components={"idle": 0.12 + self.body.fatigue_ratio() * 0.2},
                # 資源種と身体変数の語彙を揃える。"fatigue" は身体変数名であり
                # INTAKE_LIMIT の資源種ではないため、期待量の既定値10が使われていた。
                expected_outcome={"relief": "rest", "amount": WAIT_RELIEF},
                reason="low_energy",
            )
        )
        return self._merge(candidates)

    # 同一種の資源から出す移動候補の上限。
    # 信念の件数がそのまま候補本数になると、weighted_choice の上位枠を同族が
    # 占有し、層の重みではなく候補の本数が選択を支配する（NPC§5.6 との乖離）。
    GO_CANDIDATE_LIMIT = 1

    def _resource_candidates(self, kind, perception, layer, urgency, emergency=False):
        found = []
        travel = []
        for belief in self.prediction_field.beliefs_of_kind(kind):
            gap = distance(self.pos, belief.pos)
            proximity = 1.0 / (1.0 + gap * 0.35)
            # 到着時点での逼迫で測る。遠い先ほど早く出る必要がある。
            arrival = self._urgency(self.projected_ratio(kind, belief.pos)) if kind in self.NEED_SCALE else urgency
            score = belief.reliability() * 0.8 + proximity + max(urgency, arrival)
            layers = (layer, "emergency") if emergency else (layer,)
            if gap <= PhysicalConstraintLayer.USE_RANGE:
                found.append(
                    ActionCandidate(
                        "use_resource",
                        layers,
                        node_id=belief.node_id,
                        place_id=belief.place_id,
                        target_pos=belief.pos,
                        score_components={"reliability": score + 0.5},
                        expected_outcome={
                            "relief": kind,
                            "amount": min(belief.expected_amount, INTAKE_LIMIT.get(kind, 12.0)),
                        },
                        uncertainty=1.0 - belief.confidence,
                        reason=f"{kind}_at_hand",
                    )
                )
            else:
                travel.append(
                    ActionCandidate(
                        "go_resource",
                        layers,
                        node_id=belief.node_id,
                        place_id=belief.place_id,
                        target_pos=belief.pos,
                        score_components={"reliability": score},
                        expected_outcome={"approach": belief.node_id},
                        uncertainty=1.0 - belief.confidence,
                        reason=f"seek_{kind}",
                    )
                )
        travel.sort(key=lambda item: item.total(), reverse=True)
        found.extend(travel[: self.GO_CANDIDATE_LIMIT])
        return found

    @staticmethod
    def _urgency(ratio):
        """身体圧は非線形に効かせる。線形だと平常時の予定・探索に埋もれる。"""
        return clamp(ratio, 0.0, 1.3) ** 2 * 3.0

    # 空腹の予測に使う基準量（hunger_ratio / thirst_ratio の分母と揃える）
    NEED_SCALE = {"food": 120.0, "water": 100.0, "rest": 110.0}

    def projected_ratio(self, kind, target_pos):
        """そこへ着いた時点で、どれだけ逼迫しているかの見積り。

        空腹になってから動くのでは、道中でさらに空腹になって到着する。
        遠い資源ほど早く出なければならない、という当たり前のことが、
        現在値で駆動している限り表現できない。

        近さは「今すぐ行けるか」ではなく「間に合うか」の問題になる。
        """
        current, rate = {
            "food": (self.body.hunger, BodyState.RATES["hunger"]),
            "water": (self.body.thirst, BodyState.RATES["thirst"]),
            "rest": (self.body.fatigue, BodyState.RATES["fatigue"]),
        }.get(kind, (0.0, 0.0))
        travel = distance(self.pos, target_pos) / max(0.05, self.body.speed())
        return clamp((current + rate * travel) / self.NEED_SCALE.get(kind, 120.0), 0.0, 1.6)

    def _foreseen(self, perception, kind):
        """知っている最寄りの資源へ着いた時点での逼迫の見込み。

        知らなければ現在値で判断するしかない。
        """
        beliefs = self.prediction_field.beliefs_of_kind(kind)
        current = {
            "food": self.body.hunger_ratio(),
            "water": self.body.thirst_ratio(),
            "rest": self.body.fatigue_ratio(),
        }.get(kind, 0.0)
        if not beliefs:
            return current
        nearest = min(beliefs, key=lambda item: distance(self.pos, item.pos))
        return max(current, self.projected_ratio(kind, nearest.pos))

    def _emergency_candidates(self, perception):
        found = []
        # ノルアドレナリン＝危険検知・優先度増幅、5-HT3＝強制割り込み。
        # 高いほど早い段階で通常処理を中断し、緊急候補へ切り替わる。
        trip = clamp(0.62 / max(0.5, self.neuro.noradrenaline * 0.6 + self.neuro.ht3 * 0.4), 0.45, 0.70)
        if self.body.thirst_ratio() > trip:
            found.extend(self._resource_candidates("water", perception, "physical", 2.4, emergency=True))
        if self.body.hunger_ratio() > trip:
            found.extend(self._resource_candidates("food", perception, "physical", 2.2, emergency=True))
        if self.body.fatigue_ratio() > trip + 0.18:
            found.extend(self._resource_candidates("rest", perception, "physical", 1.8, emergency=True))
        return found

    def _basal_candidates(self, perception):
        found = []
        activation = self.basal.activation
        # 到着時点で閾値を越える見込みなら、まだ空いていなくても動く。
        # 実際に空腹になってから行動できるのは、食料が常に手元にある個体だけである。
        if self._foreseen(perception, "water") > 0.3:
            found.extend(self._resource_candidates("water", perception, "basal", self._urgency(self.body.thirst_ratio())))
        if self._foreseen(perception, "food") > 0.32:
            found.extend(self._resource_candidates("food", perception, "basal", self._urgency(self.body.hunger_ratio())))
        if activation["COMFORT"] > 0.3:
            found.extend(self._resource_candidates("rest", perception, "basal", activation["COMFORT"] * 0.9))
        if activation["CREATION"] > 0.3:
            found.extend(self._resource_candidates("material", perception, "basal", activation["CREATION"] * 0.6))
        # 思考的探索。ノルアドレナリン＝危険検知は通常処理を中断させる層なので、
        # 身体圧や不快が高いほど抑制される（神経力学§1）。
        load = max(self.body.crisis(), perception.discomfort) * self.neuro.noradrenaline
        if self.REFLECTION_ENABLED and self.basal_heat.value > 0.12 and load < 0.62:
            found.append(
                ActionCandidate(
                    "reflect",
                    ("basal", "upper"),
                    score_components={
                        "boredom": self.basal_heat.value * 1.15,
                        "load": -load * 0.9,
                    },
                    expected_outcome={"internal": True},
                    novelty=0.8,
                    reason="reflective_search",
                )
            )
        # 内生した仮説を外へ確かめに行く候補。M_lat のまま、低い重みで持つ。
        for meaning in self.prediction_field.known_places():
            if meaning.hypothesis is None or meaning.center is None:
                continue
            found.append(
                ActionCandidate(
                    "go_place",
                    ("upper",),
                    place_id=meaning.place_id,
                    score_components={"hypothesis": 0.55 + meaning.hypothesis * 1.15},
                    expected_outcome={"arrive": meaning.place_id},
                    uncertainty=0.8,
                    reason="test_hypothesis",
                )
            )
        if activation["EXPLORATION"] > 0.25 or self.explore_boost > 0.15:
            found.append(
                ActionCandidate(
                    "explore",
                    ("basal",),
                    score_components={
                        "novelty": activation["EXPLORATION"] * 0.9,
                        # 退屈由来の押し出し（階層構造§2）。誤差ではなく静穏が熱源。
                        "boredom": self.explore_boost * 1.1,
                    },
                    expected_outcome={"discover": True},
                    novelty=1.0,
                    reason="exploration_drive",
                )
            )
        return found

    MEMORY_CANDIDATE_LIMIT = 3

    def _memory_candidates(self, perception):
        """W_ijが強い経路を候補として持ち上げる（NPC§3.4）。

        習慣は既存候補への重み付けとしてだけでなく、候補を新たに生み出す形でも
        働く必要がある。「この時間帯にこの場所ではこうする」が、身体圧や予定と
        独立に行動を提案できて初めて、生活構造が形成されたと言える。
        """
        found = []
        context = (perception.band, perception.place_id)
        active = [
            pattern
            for pattern in self.action_memory.patterns.values()
            if pattern.phase is not Phase.LAT
            and pattern.key[0] == context
            and pattern.weight > 0.25
        ]
        active.sort(key=lambda item: item.weight * item.confidence, reverse=True)

        for pattern in active:
            if len(found) >= self.MEMORY_CANDIDATE_LIMIT:
                break
            action_type, target = pattern.key[1], pattern.key[2]
            strength = pattern.weight * pattern.confidence
            if action_type == "go_place":
                found.append(
                    ActionCandidate(
                        "go_place",
                        ("memory",),
                        place_id=target,
                        score_components={"habit": strength},
                        expected_outcome={"arrive": target},
                        reason="habit",
                    )
                )
            elif action_type in {"talk", "approach"}:
                observation = perception.agent_named(target)
                if observation is None:
                    continue
                gap = distance(self.pos, observation.pos)
                kind = "talk" if gap <= PhysicalConstraintLayer.TALK_RANGE else "approach"
                found.append(
                    ActionCandidate(
                        kind,
                        ("memory",),
                        target=target,
                        target_pos=observation.pos,
                        score_components={"habit": strength},
                        expected_outcome={"response": self.relations.predict_response(target)},
                        uncertainty=1.0 - self.relations.state(target).predictability,
                        reason="habit",
                    )
                )
            elif action_type == "go_resource" and target:
                beliefs = [
                    belief
                    for belief in self.prediction_field.resources.values()
                    if belief.place_id == target and belief.reliability() > 0.2
                ]
                if not beliefs:
                    continue
                belief = max(beliefs, key=lambda item: item.reliability())
                found.append(
                    ActionCandidate(
                        "go_resource",
                        ("memory",),
                        node_id=belief.node_id,
                        place_id=belief.place_id,
                        target_pos=belief.pos,
                        score_components={"habit": strength},
                        expected_outcome={"approach": belief.node_id},
                        uncertainty=1.0 - belief.confidence,
                        reason="habit",
                    )
                )
        return found

    def _upper_candidates(self, perception):
        found = []
        block = self.upper.block_for(perception.band)
        if block:
            weight = (1.0 - block.flexibility) * 1.1 + self.upper.adherence * 0.4
            if perception.place_id != block.place_id:
                found.append(
                    ActionCandidate(
                        "go_place",
                        ("upper",),
                        place_id=block.place_id,
                        score_components={"schedule": weight},
                        expected_outcome={"arrive": block.place_id},
                        reason=f"schedule_{block.band}",
                    )
                )
            elif block.action_type == "rest":
                found.extend(self._resource_candidates("rest", perception, "upper", weight * 0.6))
            elif block.action_type in {"forage", "work"}:
                found.extend(self._resource_candidates("food", perception, "upper", weight * 0.5))
                found.extend(self._resource_candidates("material", perception, "upper", weight * 0.3))
        promise = self.upper.pending_promise(perception.band)
        if promise:
            found.append(
                ActionCandidate(
                    "go_place",
                    ("upper",),
                    place_id=promise["place"],
                    score_components={"promise": 0.9 + self.upper.adherence * 0.5},
                    expected_outcome={"meet": promise["partner"]},
                    reason="promise",
                )
            )
        return found


    def _social_candidates(self, perception):
        found = []
        social = self.basal.activation["SOCIAL"]
        for observation in perception.visible_agents:
            state = self.relations.state(observation.name)
            gap = distance(self.pos, observation.pos)
            gradient = state.approach_gradient()
            if gap <= PhysicalConstraintLayer.TALK_RANGE:
                found.append(
                    ActionCandidate(
                        "talk",
                        ("basal", "memory"),
                        target=observation.name,
                        target_pos=observation.pos,
                        score_components={
                            "relation": state.talk_gradient() * 0.8 + social * 0.6,
                            "w_ij": self.action_memory.weight(((perception.band, perception.place_id), "talk", observation.name)),
                        },
                        expected_outcome={"response": self.relations.predict_response(observation.name)},
                        uncertainty=1.0 - state.predictability,
                        reason="relation",
                    )
                )
                if self.inventory and state.obligation < 0.25 and gradient > 0.2:
                    # オキシトシン＝B_selfの拡張。拡張された相手の欠乏を、
                    # 自分の欠乏に近い重みで扱う（神経力学§1）。
                    seeking = observation.last_action in {"go_resource", "use_resource"}
                    extended_need = self.neuro.oxytocin * (0.4 + state.familiarity) * (1.6 if seeking else 0.6)
                    found.append(
                        ActionCandidate(
                            "give",
                            ("basal", "memory"),
                            target=observation.name,
                            target_pos=observation.pos,
                            score_components={
                                "reciprocity": gradient * 0.5 + social * 0.2,
                                "extended_self": extended_need,
                            },
                            expected_outcome={"accepted": 0.7},
                            reason="gift",
                        )
                    )
            else:
                found.append(
                    ActionCandidate(
                        "approach",
                        ("basal",),
                        target=observation.name,
                        target_pos=observation.pos,
                        score_components={"relation": gradient * 0.55 + social * 0.35},
                        expected_outcome={"response": self.relations.predict_response(observation.name)},
                        uncertainty=1.0 - state.predictability,
                        reason="relation_approach",
                    )
                )
        return found

    def _merge(self, candidates):
        merged = {}
        for candidate in candidates:
            key = candidate.key
            if key not in merged:
                merged[key] = candidate
                continue
            current = merged[key]
            for name, value in candidate.score_components.items():
                current.score_components[name] = max(current.score_components.get(name, 0.0), value)
            current.source_layers = tuple(dict.fromkeys(current.source_layers + candidate.source_layers))
        return list(merged.values())

    # ------------------------------------------------------------------
    # 6-7. ゲートと選択
    # ------------------------------------------------------------------

    def select(self, candidates, perception):
        normal, emergency, removed = self.gate.gate(candidates, self, perception)

        # generate_candidates は常に実行可能な wait を通常候補として足すため、
        # normal は空にならない。「通常候補が尽きたら緊急」では原理的に到達しない。
        # NPC§5.1 の状態は「B内に残った実行可能候補が極端に限定された結果」なので、
        # 危機度が閾値を越えた時点で候補集合そのものを緊急側へ切り替える。
        if emergency and self.body.crisis() >= self.EMERGENCY_CRISIS:
            chosen = max(emergency, key=lambda item: item.total())
            return chosen, "emergency_gate", removed, emergency[:3]
        pool = normal + emergency
        if not pool:
            fallback = ActionCandidate("wait", ("fallback",), score_components={"fallback": 0.1})
            return fallback, "fallback_no_candidate", removed, [fallback]

        scored = []
        for candidate in pool:
            # D1＝行動の実行促進、D2＝抑制・ブレーキ。
            score = candidate.total() * self.neuro.d1
            score += self.action_memory.weight(
                ((perception.band, perception.place_id), candidate.action_type, candidate.target or candidate.place_id)
            ) * 0.4
            score -= candidate.uncertainty * 0.15 * self.neuro.d2
            if candidate.place_id and candidate.place_id in self.explore_targets:
                score += 0.5
            scored.append((candidate, score))

        pressure = self.xi.exploration_pressure()
        mode = "normal_weighted"
        if pressure > 0.45 and self.rng.random() < pressure * 0.22:
            # ξ探索：M_Bを維持したまま低頻度候補を試す（NPC§6.1）
            rare = sorted(
                pool,
                key=lambda item: self.action_memory.usage(
                    ((perception.band, perception.place_id), item.action_type, item.target or item.place_id)
                ),
            )
            chosen = rare[0]
            return chosen, "xi_exploration", removed, [item for item, _ in sorted(scored, key=lambda x: x[1], reverse=True)[:3]]

        chosen, top = weighted_choice(scored, self.rng)
        # 層の判定は source_layers の個数ではなく、寄与の最大成分で行う。
        # memory 由来の候補は upper と同一キーで統合されるため、
        # 個数で判定すると習慣が常に upper に吸収されて見えなくなる。
        if chosen and chosen.score_components:
            dominant = max(chosen.score_components, key=lambda key: chosen.score_components[key])
            if dominant == "habit":
                mode = "habit_dominant"
            elif dominant in {"schedule", "promise"}:
                mode = "upper_goal_dominant"
        if self.phase is Phase.REFORMED:
            mode = "m_delta_reorganization"
            self.phase = Phase.ACT
        return chosen, mode, removed, [item for item, _ in top]

    # ------------------------------------------------------------------
    # 8. 実行前の予測登録
    # ------------------------------------------------------------------

    def register_prediction(self, candidate, perception, movement):
        pending = {
            "pos": self.pos,
            "expected_motion": movement["expected_motion"] if movement else 0.0,
            "expected_progress": movement["expected_progress"] if movement else 0.0,
            "action": candidate.action_type,
        }
        # 身体の回復を見込む行為はすべて予測を登録する。
        # use_stock と wait が外れていたため、蓄えからの摂取や待機は
        # body チャネルの予測差に一切現れていなかった。
        if candidate.action_type in {"use_resource", "use_stock", "wait"}:
            kind = candidate.expected_outcome.get("relief")
            if kind in {"food", "water", "rest"}:
                pending["relief_kind"] = kind
                pending["relief_before"] = self._relief_metric(kind)
                pending["expected_relief"] = candidate.expected_outcome.get("amount", 10.0)
        if candidate.action_type in {"talk", "approach", "give", "court"} and candidate.target:
            predicted = candidate.expected_outcome.get("response")
            if predicted is None:
                predicted = self.relations.predict_response(candidate.target)
            self.relations.register_prediction(candidate.target, predicted, candidate.action_type)
            pending["relation_target"] = candidate.target
            pending["relation_action"] = candidate.action_type
            pending["relation_accepted"] = None
            pending["relation_gap"] = distance(self.pos, candidate.target_pos) if candidate.target_pos else None
        block = self.upper.block_for(perception.band)
        if block:
            meaning = self.prediction_field.places.get(block.place_id)
            if meaning and meaning.center:
                pending["goal_place"] = block.place_id
                pending["goal_pos"] = meaning.center
                pending["goal_gap"] = distance(self.pos, meaning.center)
                pending["goal_pursued"] = candidate.place_id == block.place_id
        self.pending = pending

    # ------------------------------------------------------------------
    # 10. 学習と代謝
    # ------------------------------------------------------------------

    def learn(self, candidate, outcome, perception, t):
        key = ((perception.band, perception.place_id), candidate.action_type, candidate.target or candidate.place_id)
        result = outcome.get("result")
        if result == "unresolved":
            # 成功にも失敗にも確定させない（NPC§8.3）
            self.xi.hold(
                {
                    "kind": "action",
                    "key": key,
                    "action": candidate.action_type,
                    "target": candidate.target,
                    "held_at": t,
                },
                t,
            )
        else:
            error = outcome.get("error", 0.5)
            self.action_memory.pattern(key).reinforce(
                error, t, cost=outcome.get("cost", 0.0), fixation=self.neuro.d3
            )

        self._reevaluate_unresolved(t)

        self.action_memory.metabolize(t)
        self.dialogue.metabolize()
        self.relations.decay(t)
        self.prediction_field.decay(t)
        if candidate.action_type in {"talk", "give"}:
            self.ticks_since_dialogue = 0
        else:
            self.ticks_since_dialogue += 1
        self.last_action_name = candidate.action_type
        self.recent_events.append((t, candidate.action_type, result))

    MAX_HOLD_TICKS = 120

    def _reevaluate_unresolved(self, t):
        """ξに保持した未確定を、記録型ごとに再評価する（NPC§8.3）。

        判定できないものは削除せず期限を更新して戻す。
        固定値で強化するのは「後で再評価する」ではなく「適当に確定させる」であり、
        未確定という状態そのものを潰す。

        ξキューを消費するのはこのメソッドだけとする。
        """
        resolved = 0
        for record in self.xi.take_due(t):
            kind = record.get("kind")
            if kind not in {"action", "relation"}:
                # 扱える型でなければ確定させず、そのまま戻す。
                self.xi.hold(record, t, reevaluate_after=16)
                continue
            if t - record.get("held_at", t) > self.MAX_HOLD_TICKS:
                # 長く判定できないものは、判定不能として一度だけ記録して閉じる。
                # 黙って消すと「未確定を保持する」という定義が形骸化する。
                if kind == "action" and record.get("key"):
                    self.action_memory.pattern(record["key"]).reinforce(0.5, t)
                elif kind == "relation" and record.get("target"):
                    # ついに確かめられなかった予測は、構造として固着する。
                    state = self.relations.state(record["target"])
                    state.residue = clamp(state.residue + 0.20, 0.0, 1.5)
                self.recent_events.append((t, "unresolved_expired", kind))
                resolved += 1
                continue

            if kind == "action":
                key = record.get("key")
                if key is None:
                    self.xi.hold(record, t, reevaluate_after=16)
                    continue
                # 同じ行為・同じ相手について、その後に確定した結果があれば流用する。
                siblings = [
                    item
                    for item in self.action_memory.patterns.values()
                    if item.key[1] == key[1]
                    and item.key[2] == key[2]
                    and item.key != key
                    and item.positive_count + item.negative_count > 0
                ]
                if siblings:
                    rate = sum(item.positive_count for item in siblings) / sum(
                        item.positive_count + item.negative_count for item in siblings
                    )
                    self.action_memory.pattern(key).reinforce(1.0 - rate, t, fixation=self.neuro.d3)
                    resolved += 1
                else:
                    self.xi.hold(record, t, reevaluate_after=12)

            elif kind == "relation":
                name = record.get("target")
                if not name:
                    self.xi.hold(record, t, reevaluate_after=16)
                    continue
                state = self.relations.state(name)
                # 保持後に接触があったなら、その結果が判定材料になる。
                if state.last_contact > record.get("held_at", t):
                    observed = clamp(0.5 + state.affinity * 0.5, 0.0, 1.0)
                    error = abs(observed - record.get("predicted", 0.5))
                    self.h_vec.values["relation"] = clamp(
                        self.h_vec.values["relation"] + error * self.profile.h.gain_for("relation") * 0.5,
                        0.0,
                        self.profile.h.ceiling,
                    )
                    resolved += 1
                else:
                    self.xi.hold(record, t, reevaluate_after=12)
        return resolved

    def decision_log(self, perception, candidate, mode, removed, top, ledger, leap):
        return {
            "tick": perception.t,
            "npc": self.name,
            "band": perception.band,
            "pos": (round(self.x, 2), round(self.y, 2)),
            "place": perception.place_id,
            "B": dict(self.boundary.summary),
            "F": {
                "agents": len(perception.visible_agents),
                "resources": len(perception.visible_resources),
                "discomfort": round(perception.discomfort, 2),
            },
            "phase": self.phase.value,
            "body": self.body.snapshot(),
            "basal": self.basal.snapshot(),
            "H_vec": self.h_vec.snapshot(),
            "boredom": self.basal_heat.snapshot(),
            "xi": round(self.xi.value, 3),
            "theta": round(self.boundary.theta_effective(self.xi.value), 3),
            "E": {key: round(value, 3) for key, value in ledger.errors.items() if value > 0.005},
            "explained": ledger.explanation_labels(),
            "candidates": [item.brief() for item in top],
            "removed": [(item.action_type, reason) for item, reason in removed[:4]],
            "selected": candidate.action_type,
            "target": candidate.target or candidate.node_id or candidate.place_id,
            "selection_mode": mode,
            "leap": leap.as_record() if leap else None,
        }
