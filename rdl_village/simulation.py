"""tick進行・イベント配布・結果評価・非介入観測。

参照:
  RDL_簡易村シミュレーター §14（1 tickの更新順）, §16（主要クラス）, §17（ログと観察画面）, §18（再現性）

同一tick内の意思決定順が恒常的な優位を生まないよう、意図をまとめて提出してから解決する（村§14末尾）。
観測者記録はNPCの意思決定へ入力しない（村§3.6, §4.4）。
"""

import hashlib
import math
import random
from collections import defaultdict

from .action import TAU, PhysicalConstraintLayer, RelationalAction
from .core import Phase, clamp, distance, normalized
from .npc import INTAKE_LIMIT, WAIT_RELIEF, ScheduleBlock, VillageNPC
from .perception import PerceptionSystem, ResourceBelief
from .profiles import NEURO_PRESETS, VILLAGE_PROFILE
from .world import BANDS, PhysicalWorld

PRESETS = {
    "farmer": {"COMFORT": 0.6, "SOCIAL": 0.7, "EXPLORATION": 0.4, "CREATION": 0.6, "RECOGNITION": 0.5, "PAIRING": 0.9},
    "forager": {"COMFORT": 0.5, "SOCIAL": 0.5, "EXPLORATION": 0.9, "CREATION": 0.7, "RECOGNITION": 0.4, "PAIRING": 0.8},
    "keeper": {"COMFORT": 0.7, "SOCIAL": 0.9, "EXPLORATION": 0.3, "CREATION": 0.5, "RECOGNITION": 0.8, "PAIRING": 1.0},
    "quiet": {"COMFORT": 0.8, "SOCIAL": 0.3, "EXPLORATION": 0.5, "CREATION": 0.6, "RECOGNITION": 0.3, "PAIRING": 0.6},
    "social": {"COMFORT": 0.5, "SOCIAL": 1.0, "EXPLORATION": 0.5, "CREATION": 0.4, "RECOGNITION": 0.9, "PAIRING": 1.1},
    "wanderer": {"COMFORT": 0.4, "SOCIAL": 0.4, "EXPLORATION": 1.1, "CREATION": 0.5, "RECOGNITION": 0.4, "PAIRING": 0.7},
}

VILLAGERS = [
    ("Aki", "farmer", "home_a", (8.5, 9.0), ["well", "garden", "plaza", "home_a"]),
    ("Ben", "forager", "home_a", (7.5, 8.5), ["well", "garden", "grove", "home_a"]),
    ("Cai", "keeper", "home_c", (33.0, 8.0), ["stream", "shop", "plaza", "home_c"]),
    ("Dio", "quiet", "home_c", (33.5, 6.5), ["stream", "field", "home_c", "home_c"]),
    ("Emi", "social", "home_b", (32.0, 31.0), ["stream", "field", "plaza", "home_b"]),
    ("Fay", "wanderer", "home_b", (31.5, 32.5), ["stream", "grove", "plaza", "home_b"]),
]

BAND_ACTIONS = {"morning": "drink", "noon": "work", "evening": "talk", "night": "rest"}


def build_schedule(place_ids):
    bands = ("morning", "noon", "evening", "night")
    return [
        ScheduleBlock(band, place_id, BAND_ACTIONS[band], flexibility=0.35 if band == "night" else 0.5)
        for band, place_id in zip(bands, place_ids)
    ]


class VillageEventBus:
    """当事者・観察者へ出来事を配布する（村§16）。

    全NPCへ自動配布しない。見えた者、聞こえた者だけが受け取る（村§19-2, §11.3）。
    """

    def __init__(self, world):
        self.world = world
        self.log = []

    def publish(self, action, result, agents, participants, radius=6.0):
        record = {"t": self.world.clock.t, **action.as_record(), "result": result}
        self.log.append(record)
        for observer in agents:
            if not observer.alive or observer.name in participants:
                continue
            gap = distance(observer.pos, participants_center(participants, agents))
            if gap > radius * action.visibility:
                continue
            if self.world.line_blocked(observer.pos, participants_center(participants, agents)):
                continue
            confidence = clamp(1.0 - gap / (radius * action.visibility), 0.1, 1.0)
            observer.relations.on_witnessed(
                action.actor, action.target, action.action_type, result, confidence, self.world.clock.t
            )
        return record


def participants_center(participants, agents):
    positions = [agent.pos for agent in agents if agent.name in participants]
    if not positions:
        return 0.0, 0.0
    return (
        sum(pos[0] for pos in positions) / len(positions),
        sum(pos[1] for pos in positions) / len(positions),
    )


class OutcomeEvaluator:
    """期待結果と観測結果の差を評価する（NPC§5.6 / §10）。"""

    @staticmethod
    def evaluate(candidate, observed):
        expected = candidate.expected_outcome
        if observed.get("result") == "unresolved":
            return {"result": "unresolved", "error": None, "cost": observed.get("cost", 0.0)}
        error = 0.5
        if "relief" in expected:
            wanted = max(1.0, expected.get("amount", 10.0))
            got = observed.get("gained", 0.0)
            error = clamp(abs(wanted - got) / wanted, 0.0, 1.0)
        elif "response" in expected:
            error = clamp(abs(expected["response"] - observed.get("response", 0.5)), 0.0, 1.0)
        elif "arrive" in expected or "approach" in expected:
            error = clamp(1.0 - observed.get("progress_ratio", 0.0), 0.0, 1.0)
        elif "accepted" in expected:
            error = clamp(abs(expected["accepted"] - (1.0 if observed.get("accepted") else 0.0)), 0.0, 1.0)
        elif "discover" in expected:
            error = 0.2 if observed.get("discovered") else 0.7
        return {"result": observed.get("result", "done"), "error": error, "cost": observed.get("cost", 0.0)}


class VillageSimulation:
    """tick進行と全モジュールの接続（村§16）。"""

    def __init__(self, seed=7, scale=1.0):
        self.rng = random.Random(seed)
        self.world = PhysicalWorld(self.rng, scale=scale)
        self.perception_system = PerceptionSystem()
        self.bus = VillageEventBus(self.world)
        self.logs = []
        self.village_log = defaultdict(int)
        self._last_band = None
        self.tick_positions = {}
        self.tick_perceptions = {}
        self.agents = []
        for name, role, home, pos, places in VILLAGERS:
            spawn = self.world.nearest_open_point((pos[0] * scale, pos[1] * scale))
            self.agents.append(
                VillageNPC(
                    name,
                    role,
                    PRESETS[role],
                    home,
                    build_schedule(places),
                    spawn,
                    VILLAGE_PROFILE,
                    # 個体ごとに独立した乱数列を持たせる。
                    # 共有すると、解決順が変わるだけで乱数の消費順が変わり、
                    # 相を分けても順序独立性が成立しない（村§14末尾）。
                    random.Random(f"{seed}:{name}"),
                    NEURO_PRESETS[role],
                )
            )

    # ------------------------------------------------------------------

    def step(self):
        """村§14 の更新順に対応。

        文書の 2（予測差の比較）は現在のFを必要とするため、3-4 の後に実行している。
        比較が候補生成より前に来るという順序上の要件は保っている。
        """
        # 1. 村時計・天候・資源循環
        environment_events = self.world.advance_environment()
        for event in environment_events:
            self.logs.append({"t": self.world.clock.t, **event})
            self.village_log[event["kind"]] += 1

        t = self.world.clock.t
        band = self.world.clock.band
        if self._last_band is not None and band != self._last_band:
            self._resolve_promises(self._last_band)
        self._last_band = band
        living = []
        for agent in self.agents:
            if not agent.alive:
                continue
            place = self.world.places.place_at(agent.pos)
            sheltered = bool(place) and bool({"rest", "sleep"} & set(place.affordances))
            agent.body.tick(band, sheltered, self.world.clock.light)
            cause = agent.body.fatal()
            if cause:
                agent.alive = False
                self.logs.append(
                    {"t": t, "kind": "death", "npc": agent.name, "cause": cause}
                )
                self.village_log["death"] += 1
                continue
            living.append(agent)

        intents = []
        for agent in living:
            # 3. 個体固有のFを生成
            perception = self.perception_system.perceive(agent, self.world, living)
            # 4. 個体予測場を更新
            if perception.place_id:
                agent.visited_this_band.add(perception.place_id)
            field_errors = agent.prediction_field.integrate(perception, t)
            for observation in perception.visible_agents:
                agent.relations.on_proximity(observation.name, t)
            # 2 + 5. 予測差からH_vecを更新し、条件を満たせば再編
            agent.update_boundary(perception)
            ledger, leap = agent.evaluate_prediction(perception, field_errors, t)
            # 6. 候補生成
            candidates = agent.generate_candidates(perception)
            # 7-8. 統合評価と物理ゲート
            chosen, mode, removed, top = agent.select(candidates, perception)
            intents.append(
                {
                    "agent": agent,
                    "perception": perception,
                    "candidate": chosen,
                    "mode": mode,
                    "removed": removed,
                    "top": top,
                    "ledger": ledger,
                    "leap": leap,
                }
            )

        # 意図提出後にまとめて解決する（村§14末尾）
        self.rng.shuffle(intents)
        # 9-10. 移動と離散作用の解決
        outcomes = self._resolve(intents, living)
        # 11-12. 配布と結果保存、13. ログ
        for intent in intents:
            agent = intent["agent"]
            observed = outcomes[agent.name]
            evaluation = OutcomeEvaluator.evaluate(intent["candidate"], observed)
            agent.learn(intent["candidate"], evaluation, intent["perception"], t)
            record = agent.decision_log(
                intent["perception"],
                intent["candidate"],
                intent["mode"],
                intent["removed"],
                intent["top"],
                intent["ledger"],
                intent["leap"],
            )
            record["outcome"] = {key: value for key, value in observed.items() if key != "result"}
            record["result"] = observed.get("result")
            self.logs.append(record)
            self.village_log[intent["candidate"].action_type] += 1
            if intent["leap"]:
                self.village_log[f"leap:{intent['leap'].channel}"] += 1

    MOVEMENT_ACTIONS = {"go_resource", "go_place", "approach", "explore"}

    def _resolve(self, intents, living):
        """村§14 の9〜11を相に分けて解く。

        逐次解決だと、先に処理されたNPCの移動後の状態を後続が見ることになり、
        「意図提出後にまとめて解決する」（村§14末尾）が名目だけになる。
        相を分けることで、順序独立性が偶然ではなく構造として保たれる。

            相1  tick開始時点の状態を固定
            相2  全移動案を計算（状態を変えない）
            相3  移動を一括適用し、混雑を解決
            相4  資源競合と対人作用を一括確定
            相5  相互求愛を一つのペアイベントとして確定
        """
        outcomes = {}
        claims = defaultdict(list)
        courtships = defaultdict(list)
        movements, dialogues, transfers, standing = [], [], [], []

        # --- 相1：状態の固定 ---
        self.tick_positions = {agent.name: agent.pos for agent in living}
        self.tick_perceptions = {
            intent["agent"].name: intent["perception"] for intent in intents
        }

        for intent in intents:
            agent = intent["agent"]
            candidate = intent["candidate"]
            agent.intended_place_label = candidate.place_id or intent["perception"].place_id
            action_type = candidate.action_type
            if action_type in {"use_resource", "gather"}:
                claims[candidate.node_id].append(intent)
            elif action_type in {"use_stock", "deposit", "take_stored"}:
                standing.append(intent)
            elif action_type == "court":
                courtships[candidate.target].append(intent)
            elif action_type in self.MOVEMENT_ACTIONS:
                movements.append(intent)
            elif action_type == "talk":
                dialogues.append(intent)
            elif action_type == "give":
                transfers.append(intent)
            else:
                standing.append(intent)

        # --- 相2：全移動案の計算（この段階では誰も動かない） ---
        plans = []
        for intent in movements:
            agent = intent["agent"]
            target = self._target_for(agent, intent["candidate"], intent["perception"])
            plan = agent.planner.plan(
                agent, intent["perception"], target, agent.xi.exploration_pressure()
            )
            agent.register_prediction(intent["candidate"], intent["perception"], plan)
            plans.append((intent, target, plan))

        # --- 相3：移動の一括適用と混雑の解決 ---
        self._apply_movements(plans, outcomes, living)

        # --- 相4：資源競合と対人作用 ---
        # 相内の処理順は、提出順ではなく安定なキーで固定する。
        by_actor = lambda item: item["agent"].name
        for node_id in sorted(claims):
            self._resolve_resource_claims(
                node_id, sorted(claims[node_id], key=by_actor), outcomes, living
            )
        self._resolve_dialogues(sorted(dialogues, key=by_actor), outcomes, living)
        for intent in sorted(transfers, key=by_actor):
            outcomes[intent["agent"].name] = self._resolve_give(intent, living)
        for intent in sorted(standing, key=by_actor):
            outcomes[intent["agent"].name] = self._resolve_standing(intent)

        # --- 相5：相互求愛、続いて片側求愛 ---
        self._resolve_mutual_courtships(courtships, outcomes, living)
        for target_name, suitors in courtships.items():
            if suitors:
                self._resolve_courtship(target_name, suitors, outcomes, living)

        self.tick_positions = {}
        self.tick_perceptions = {}
        return outcomes

    def _apply_movements(self, plans, outcomes, living):
        """全員の移動を同時に適用し、そのあとで重なりを解く。

        村§14-9 は「境界・障害物・混雑を解決する」と定めている。
        個体同士の重なりはこれまで一切解かれていなかった。

        静止している個体も混雑解決の対象に含める。移動する側だけを見ると、
        その場に留まっている相手の上へ着地できてしまう。
        """
        moved = {}
        for intent, target, plan in plans:
            agent = intent["agent"]
            before = self.tick_positions[agent.name]
            landing, blocked = self.world.move_with_collisions(
                before, plan["vx"], plan["vy"], agent.body_radius
            )
            moved[agent.name] = {
                "agent": agent,
                "intent": intent,
                "target": target,
                "plan": plan,
                "before": before,
                "pos": landing,
                "blocked": blocked,
            }
        standing = {
            agent.name: {"agent": agent, "intent": None, "pos": self.tick_positions[agent.name]}
            for agent in living
            if agent.name not in moved
        }

        self._separate_crowding({**moved, **standing})

        for record in standing.values():
            record["agent"].x, record["agent"].y = record["pos"]

        for name, record in moved.items():
            intent = record["intent"]
            agent = intent["agent"]
            agent.x, agent.y = record["pos"]
            agent.vx, agent.vy = record["plan"]["vx"], record["plan"]["vy"]
            travelled = distance(record["before"], record["pos"])
            agent.body.fatigue += travelled * 0.20

            target = record["target"]
            progress_ratio = 0.0
            if target is not None:
                before_gap = distance(record["before"], target)
                if before_gap > 0.01:
                    progress_ratio = clamp(
                        (before_gap - distance(record["pos"], target)) / max(0.05, agent.body.speed()),
                        0.0,
                        1.0,
                    )
            discovered = agent.prediction_field.last_discoveries > 0
            hard = record["blocked"] and travelled < agent.body.speed() * 0.2
            outcomes[name] = {
                "result": "blocked" if hard else "moved",
                "progress_ratio": progress_ratio,
                "travelled": round(travelled, 3),
                "blocked": record["blocked"],
                "discovered": discovered,
                "cost": travelled * 0.2,
            }

    def _separate_crowding(self, moved):
        """同時に同じ地点へ入った個体を押し分ける。

        誰が先に処理されたかで勝敗が決まらないよう、両者を等しく退かせる。
        """
        names = sorted(moved)
        # 収束するまで回す。三者以上が寄ると一巡では解けない。
        for _ in range(12):
            resolved = True
            for index, left in enumerate(names):
                for right in names[index + 1 :]:
                    a, b = moved[left], moved[right]
                    span = a["agent"].body_radius + b["agent"].body_radius
                    gap = distance(a["pos"], b["pos"])
                    if gap >= span:
                        continue
                    resolved = False
                    if gap < 1e-6:
                        # 完全に同一点。名前から決定論的な方向を作る。
                        # 組み込み hash はプロセスごとに乱数化されるため使えない。
                        digest = hashlib.blake2b(
                            f"{left}\0{right}".encode("utf-8"), digest_size=8
                        ).digest()
                        angle = int.from_bytes(digest, "big") / 2 ** 64 * TAU
                        away = (math.cos(angle), math.sin(angle))
                    else:
                        away = normalized(a["pos"][0] - b["pos"][0], a["pos"][1] - b["pos"][1])
                    push = (span - gap) / 2 + 0.03
                    for record, sign in ((a, 1.0), (b, -1.0)):
                        agent = record["agent"]
                        candidate = (
                            record["pos"][0] + away[0] * push * sign,
                            record["pos"][1] + away[1] * push * sign,
                        )
                        if self.world.is_position_open(candidate, agent.body_radius):
                            record["pos"] = candidate
                        elif record["intent"] is not None:
                            # 押し戻せないなら移動そのものを取り消す。
                            record["pos"] = record["before"]
            if resolved:
                break

    def _resolve_standing(self, intent):
        agent = intent["agent"]
        candidate = intent["candidate"]
        if candidate.action_type == "deposit":
            agent.register_prediction(candidate, intent["perception"], None)
            place = self.world.places.get(candidate.place_id)
            kind = candidate.node_id
            amount = agent.consume_carried(kind, agent.carried(kind))
            if place is not None and amount > 0.0:
                place.store(kind, amount)
            self.village_log["deposit"] += 1
            return {"result": "deposited", "gained": round(amount, 2), "kind": kind}
        if candidate.action_type == "take_stored":
            agent.register_prediction(candidate, intent["perception"], None)
            place = self.world.places.get(candidate.place_id)
            kind = candidate.node_id
            need = agent.body.hunger if kind == "food" else agent.body.thirst
            want = min(INTAKE_LIMIT.get(kind, 12.0), need)
            gained = place.take_stored(kind, max(0.0, want)) if place else 0.0
            if kind == "food":
                agent.body.hunger = max(0.0, agent.body.hunger - gained)
            elif kind == "water":
                agent.body.thirst = max(0.0, agent.body.thirst - gained)
            self.village_log["take_stored"] += 1
            return {"result": "took_stored", "gained": round(gained, 2), "kind": kind}
        if candidate.action_type == "use_stock":
            agent.register_prediction(candidate, intent["perception"], None)
            kind = candidate.node_id
            # 身体の不足を超えて取り出さない。超えた分は蓄えから消えるだけで、
            # しかも「期待どおり得られた」として完全成功に学習されてしまう。
            need = agent.body.hunger if kind == "food" else agent.body.thirst
            want = min(agent.carried(kind), INTAKE_LIMIT.get(kind, 12.0), need)
            gained = agent.consume_carried(kind, max(0.0, want))
            if kind == "food":
                agent.body.hunger = max(0.0, agent.body.hunger - gained)
            elif kind == "water":
                agent.body.thirst = max(0.0, agent.body.thirst - gained)
            self.village_log["use_stock"] += 1
            return {"result": "used_stock", "gained": round(gained, 2), "kind": kind}
        if candidate.action_type == "reflect":
            agent.register_prediction(candidate, intent["perception"], None)
            record = agent.reflect(intent["perception"], self.world.clock.t)
            agent.body.fatigue = max(0.0, agent.body.fatigue - 0.6)
            self.village_log[f"reflect:{record['op']}"] += 1
            self.logs.append(
                {"t": self.world.clock.t, "kind": "reflect", "npc": agent.name, **record}
            )
            return {"result": "reflected", "internal": True, "op": record["op"]}
        agent.register_prediction(candidate, intent["perception"], None)
        # 実際の回復量を返す。0固定だと、疲労を回復しているのに
        # OutcomeEvaluator が毎回 error=1.0 と評価し、待機が一度も
        # 成功として学習されない。
        before = agent.body.fatigue
        agent.body.fatigue = max(0.0, before - WAIT_RELIEF)
        return {"result": "waited", "gained": before - agent.body.fatigue}

    def _gap(self, a, b):
        """tick開始時点の位置で測る。"""
        left = self.tick_positions.get(a.name, a.pos)
        right = self.tick_positions.get(b.name, b.pos)
        return distance(left, right)

    def _resolve_mutual_courtships(self, courtships, outcomes, living):
        """相互求愛は二つの独立イベントではなく一つのペアイベントとして解く。

        別々に解くと、先に処理された方向でつがいが成立し、逆方向が
        「既につがい」として拒否され、同一tick・同一ペアで矛盾した結果が出る。
        """
        by_name = {agent.name: agent for agent in living}
        seen = set()
        for target_name, suitors in list(courtships.items()):
            for intent in list(suitors):
                actor = intent["agent"]
                pair = frozenset((actor.name, target_name))
                if pair in seen or target_name not in courtships:
                    continue
                back = next(
                    (item for item in courtships.get(actor.name, []) if item["agent"].name == target_name),
                    None,
                )
                if back is None:
                    continue
                seen.add(pair)
                other = by_name.get(target_name)
                courtships[target_name].remove(intent)
                courtships[actor.name].remove(back)
                for side in (intent, back):
                    side["agent"].register_prediction(side["candidate"], side["perception"], None)
                    side["agent"].courtship_attempts += 1
                if other is None:
                    for side in (intent, back):
                        outcomes[side["agent"].name] = {"result": "unresolved", "response": 0.5}
                    continue

                # 双方が望んでいる。片方だけ拒否になる理由がない。
                accepted = (
                    actor.mate is None
                    and other.mate is None
                    and self._gap(actor, other) <= PhysicalConstraintLayer.TALK_RANGE
                )
                for side, partner in ((actor, other), (other, actor)):
                    if accepted:
                        side.courtship[partner.name] = clamp(
                            side.courtship[partner.name] + 0.5, 0.0, 1.0
                        )
                        side.relations.on_courted(partner.name, True, self.world.clock.t)
                    else:
                        side.on_rejected_by(partner.name, None, self.world.clock.t)
                    side.courted_by.append((partner.name, self.world.clock.t, accepted))
                bonded = accepted and min(
                    actor.courtship[other.name], other.courtship[actor.name]
                ) >= 0.6
                if bonded:
                    actor.bond_with(other.name, self.world.clock.t)
                    other.bond_with(actor.name, self.world.clock.t)
                    self.village_log["bond_formed"] += 1
                    self.logs.append(
                        {"t": self.world.clock.t, "kind": "bond", "npc": actor.name, "mate": other.name, "mutual": True}
                    )
                result = "bonded" if bonded else ("courted" if accepted else "rejected")
                for side in (intent, back):
                    agent = side["agent"]
                    if agent.pending is not None:
                        agent.pending["relation_accepted"] = accepted
                    outcomes[agent.name] = {
                        "result": result,
                        "accepted": accepted,
                        "response": 1.0 if accepted else 0.0,
                    }
                self.village_log["court"] += 2
                self.village_log["court_mutual"] += 1

    def _resolve_courtship(self, target_name, suitors, outcomes, living):
        """求愛は相手が選ぶ側になる。ここで初めて社会的な失敗が発生する。

        村§7.4 の競合作用のうち、これまで資源にしか存在しなかった競合を対人へ広げる。
        選ばれなかった側には拒否が返り、競合相手への territoriality と irritation が立つ。
        """
        target = next((item for item in living if item.name == target_name), None)
        for intent in suitors:
            intent["agent"].register_prediction(intent["candidate"], intent["perception"], None)
            intent["agent"].courtship_attempts += 1

        if target is None:
            for intent in suitors:
                outcomes[intent["agent"].name] = {"result": "unresolved", "response": 0.5}
            return

        # 相手側の評価。既につがいなら全員拒否。
        ranked = sorted(
            suitors,
            key=lambda item: target._attractiveness(item["agent"].name),
            reverse=True,
        )
        best = ranked[0]["agent"]
        appeal = target._attractiveness(best.name)
        target_pressure = target.basal.activation["PAIRING"]
        accepted = (
            target.mate is None
            and target_pressure > 0.28
            and appeal > 0.35
            and self._gap(target, best) <= PhysicalConstraintLayer.TALK_RANGE
        )
        for index, intent in enumerate(ranked):
            agent = intent["agent"]
            chosen = accepted and index == 0
            # 競合は同一tickの重なりではなく、期間内の重なりで成立する。
            rival = best.name if (len(ranked) > 1 and index > 0) else target.recent_rival(agent.name, self.world.clock.t)
            target.courted_by.append((agent.name, self.world.clock.t, chosen))
            if chosen:
                agent.courtship[target_name] = clamp(agent.courtship[target_name] + 0.45, 0.0, 1.0)
                target.courtship[agent.name] = clamp(target.courtship[agent.name] + 0.35, 0.0, 1.0)
                agent.relations.on_courted(target_name, True, self.world.clock.t)
                target.relations.on_courted(agent.name, True, self.world.clock.t)
                bonded = agent.courtship[target_name] >= 0.9 and target.courtship[agent.name] >= 0.6
                if bonded:
                    agent.bond_with(target_name, self.world.clock.t)
                    target.bond_with(agent.name, self.world.clock.t)
                    self.village_log["bond_formed"] += 1
                    self.logs.append(
                        {"t": self.world.clock.t, "kind": "bond", "npc": agent.name, "mate": target_name}
                    )
                outcomes[agent.name] = {
                    "result": "bonded" if bonded else "courted",
                    "accepted": True,
                    "response": 1.0,
                }
            else:
                agent.on_rejected_by(
                    target_name, rival if rival != agent.name else None, self.world.clock.t
                )
                if rival and rival != agent.name:
                    self.village_log["court_contested"] += 1
                agent.relations.on_courted(target_name, False, self.world.clock.t)
                target.relations.on_courted(agent.name, False, self.world.clock.t)
                outcomes[agent.name] = {"result": "rejected", "accepted": False, "response": 0.0}
            if agent.pending is not None and agent.pending.get("relation_target") == target_name:
                agent.pending["relation_accepted"] = chosen
            action = RelationalAction(
                agent.name, "court", "dialogue", target_name, place=intent["perception"].place_id, visibility=0.9
            )
            self.bus.publish(
                action, "accepted" if chosen else "rejected", living, {agent.name, target_name}
            )
        self.village_log["court"] += len(suitors)


    def _target_for(self, agent, candidate, perception):
        if candidate.target_pos is not None:
            return candidate.target_pos
        if candidate.place_id:
            place = self.world.places.get(candidate.place_id)
            if place:
                return place.center
        if candidate.action_type == "explore":
            return self._exploration_target(agent, perception)
        return None

    def _exploration_target(self, agent, perception):
        """探索の行き先。

        平常の探索は目的地を持たない。村§12.2 の ξ探索の例は
        「違う帰路を通る」「普段行かない場所へ行く」のように、
        いつもの行動を少しずらす操作であって遠征ではない。
        NPC§6.1 も「実行可能領域内で低頻度候補を試す」と定めている。

        具体的な目標を与えると、探索が往復コストを伴う遠征になり、
        余裕のない個体はそのまま戻れなくなる。
        目標なしで返すと、移動評価は探索重み・障害物回避・継続性・ξ揺らぎだけで
        駆動され、周辺を軽く回る動きになる。

        遠くへ出るのは退屈由来の押し出し中だけに限る（階層構造§2）。
        """
        if agent.outward_ticks > 0:
            centers = [m.center for m in agent.prediction_field.known_places() if m.center]
            if centers:
                cx = sum(c[0] for c in centers) / len(centers)
                cy = sum(c[1] for c in centers) / len(centers)
                away = normalized(agent.x - cx, agent.y - cy)
                if away == (0.0, 0.0):
                    angle = agent.rng.random() * TAU
                    away = (math.cos(angle), math.sin(angle))
                jitter = agent.rng.uniform(-0.5, 0.5)
                away = normalized(away[0] + jitter, away[1] - jitter)
                return (
                    clamp(agent.x + away[0] * 12.0, 1.0, self.world.size - 1.0),
                    clamp(agent.y + away[1] * 12.0, 1.0, self.world.size - 1.0),
                )

        return None


    def _resolve_resource_claims(self, node_id, contenders, outcomes, living):
        node = self.world.resources.at(node_id)

        # 残量を先に固定し、取得量を一括で決めてから反映する。
        # 逐次 take すると、処理順の先頭が総取りし、後続が0になる。
        # 残量10へ二人が17ずつ要求したら 10/0 ではなく 5/5 が同時分配である。
        requests = {}
        for intent in contenders:
            candidate = intent["candidate"]
            kind = candidate.expected_outcome.get("relief", node.kind if node else "food")
            # 候補が見込んだ量を超えて要求しない。上限を一律に要求すると、
            # 余った分が世界から消えたまま誰の身にもならない。
            want = min(
                candidate.expected_outcome.get("amount", INTAKE_LIMIT.get(kind, 12.0)),
                INTAKE_LIMIT.get(kind, 12.0),
            )
            requests[intent["agent"].name] = (max(0.0, want), kind)

        # 休眠中・再生中のノードからは取れない。amount を直接見ると、
        # 世界から減らないまま個体へ流入する（物質が生成される）。
        available = node.amount if (node is not None and node.usable) else 0.0
        total_requested = sum(amount for amount, _ in requests.values())
        allocation = {}
        if total_requested > 0.0:
            for name, (amount, _) in requests.items():
                allocation[name] = (
                    amount
                    if total_requested <= available
                    else available * amount / total_requested
                )

        # 実際に取れた量へ按分し直す。take の戻り値を無視しない。
        planned = sum(allocation.values())
        actual = node.take(planned) if (node is not None and planned > 0.0) else 0.0
        if planned > 0.0 and abs(actual - planned) > 1e-9:
            scale = actual / planned
            allocation = {name: amount * scale for name, amount in allocation.items()}
        share = 1.0 / len(contenders)

        for intent in contenders:
            agent = intent["agent"]
            candidate = intent["candidate"]
            agent.register_prediction(candidate, intent["perception"], None)
            kind = candidate.expected_outcome.get("relief", node.kind if node else "food")
            gained = allocation.get(agent.name, 0.0)

            if gained <= 0.01:
                outcomes[agent.name] = {"result": "depleted", "gained": 0.0}
                belief = agent.prediction_field.belief(node_id)
                if belief:
                    belief.weaken(self.world.clock.t, rate=0.4)
                # 取り負けた側こそ競合を経験している。ここで抜けると
                # 完全な敗者ほど territoriality が立たないという逆転が起きる。
                if len(contenders) > 1:
                    for other in contenders:
                        if other is not intent:
                            agent.relations.on_contested_resource(
                                other["agent"].name, lost=True, t=self.world.clock.t
                            )
                continue

            provisioning = candidate.action_type == "gather"
            if provisioning:
                # 消費せずに蓄えへ入れる（村§7.3「取る」）。
                stored = agent.store_surplus(kind, gained)
                outcomes[agent.name] = {
                    "result": "gathered",
                    "gained": round(stored, 2),
                    "kind": kind,
                }
                self.village_log["gather"] += 1
                continue

            if kind == "food":
                before = agent.body.hunger
                agent.body.hunger = max(0.0, before - gained)
                # 使い切れなかった分は持ち帰る。
                agent.store_surplus("food", gained - (before - agent.body.hunger))
                agent.basal.satisfy("COMFORT", 0.1)
            elif kind == "water":
                before = agent.body.thirst
                agent.body.thirst = max(0.0, before - gained)
                agent.store_surplus("water", gained - (before - agent.body.thirst))
            elif kind == "rest":
                agent.body.fatigue = max(0.0, agent.body.fatigue - gained)
                agent.basal.satisfy("COMFORT", 0.25)
            elif kind == "material":
                agent.inventory.append({"kind": "material", "amount": gained})
                del agent.inventory[:-3]
                agent.basal.satisfy("CREATION", 0.3)

            meaning = agent.prediction_field.meaning(node.place_id)
            meaning.resource_expectation = clamp(meaning.resource_expectation + 0.06, 0.0, 1.0)
            if len(contenders) > 1:
                for other in contenders:
                    if other is not intent:
                        agent.relations.on_contested_resource(
                            other["agent"].name, lost=share < 0.5, t=self.world.clock.t
                        )
            outcomes[agent.name] = {"result": "used", "gained": round(gained, 2), "kind": kind}

    # 同一tickで一人が応答できる会話数。応答は行動枠を消費しない反射作用だが、
    # 無制限にすると一人が全員と同時に話せてしまう。
    MAX_REPLIES_PER_TICK = 2

    def _resolve_dialogues(self, intents, outcomes, living):
        """対話を二段階で解く。

        逐次に解くと、先に処理された会話が相手の関係状態・語彙ノード・会話履歴を
        書き換え、後続の会話結果を変える。名前順に固定しても恒常的な優位が残るだけで、
        社会作用の同時性にはならない（村§14末尾）。

            段階1  全会話の発話と応答案を、tick開始時の状態から計算する
            段階2  一人が受けられる件数を確定し、結果を一括反映する
        """
        by_name = {agent.name: agent for agent in living}

        # 段階1：誰が誰と話すかだけを決める。発話はまだ生成しない。
        # open()/reply() はターン数・語彙ノード・乱数を変えるため、
        # 全件を先に呼ぶと「一件目の提案が二件目の前提を変える」ことになる。
        by_listener = defaultdict(list)
        for intent in intents:
            agent = intent["agent"]
            agent.register_prediction(intent["candidate"], intent["perception"], None)
            other = by_name.get(intent["candidate"].target)
            if other is None or self._gap(agent, other) > PhysicalConstraintLayer.TALK_RANGE:
                outcomes[agent.name] = {"result": "unresolved", "response": 0.5}
                continue
            by_listener[other.name].append(intent)

        # 段階2：受け手が選ぶ。話者の名前順ではなく、受け手から見た関係で決める。
        selected = []
        for listener_name in sorted(by_listener):
            listener = by_name[listener_name]
            ranked = sorted(
                by_listener[listener_name],
                key=lambda item: (
                    -listener.relations.state(item["agent"].name).talk_gradient(),
                    item["agent"].name,
                ),
            )
            for index, intent in enumerate(ranked):
                if index < self.MAX_REPLIES_PER_TICK:
                    selected.append((intent, listener))
                else:
                    outcomes[intent["agent"].name] = {"result": "unresolved", "response": 0.5}
                    self.village_log["dialogue_overflow"] += 1

        # 段階3：採用された組だけ発話を生成し、その場で確定する。
        for intent, listener in selected:
            proposal = self._propose_dialogue(intent, listener)
            agent = intent["agent"]
            if proposal["reason"] is not None:
                outcomes[agent.name] = {"result": "unresolved", "response": 0.5}
                continue
            outcomes[agent.name] = self._commit_dialogue(proposal, living)

    def _propose_dialogue(self, intent, other):
        """採用が決まった組について、発話と応答を生成する。

        open()/reply() は語彙ノードとターン数を更新するため、
        成立しない会話に対して呼んではならない。呼ぶ時点で既に
        会話履歴が変わり、上限超過で不成立になっても痕跡が残る。
        """
        agent = intent["agent"]
        perception = intent["perception"]
        relation = agent.relations.state(other.name)
        opening = agent.dialogue.open(agent, other.name, relation, perception)
        if opening is None:
            agent.dialogue.close(other.name)
            return {"intent": intent, "other": other, "reason": "no_opening"}

        other_perception = self.tick_perceptions.get(other.name)
        if other_perception is None:
            other_perception = intent["perception"]
        reply, accepted = other.dialogue.reply(
            opening, other, other.relations.state(agent.name), other_perception
        )
        return {
            "intent": intent,
            "other": other,
            "reason": None,
            "opening": opening,
            "reply": reply,
            "accepted": accepted,
            "perception": perception,
        }

    def _commit_dialogue(self, proposal, living):
        """計算済みの応答を反映する。"""
        intent = proposal["intent"]
        agent = intent["agent"]
        other = proposal["other"]
        opening, reply, accepted = proposal["opening"], proposal["reply"], proposal["accepted"]
        perception = proposal["perception"]

        agent.relations.on_dialogue(other.name, opening.speech_act, accepted, self.world.clock.t)
        other.relations.on_dialogue(agent.name, reply.speech_act, accepted, self.world.clock.t)
        if agent.pending is not None and agent.pending.get("relation_target") == other.name:
            agent.pending["relation_accepted"] = accepted
        agent.dialogue.register_outcome(other.name, opening, accepted)
        other.ticks_since_dialogue = 0
        agent.basal.satisfy("SOCIAL", 0.3 if accepted else 0.1)
        other.basal.satisfy("SOCIAL", 0.25)
        if accepted:
            agent.basal.satisfy("RECOGNITION", 0.2)

        if opening.speech_act == "invite" and accepted:
            next_band = BANDS[(BANDS.index(perception.band) + 1) % len(BANDS)]
            place = self._meeting_place(agent, other, next_band)
            if place in self.world.places.places:
                agent.upper.add_promise(other.name, place, next_band)
                other.upper.add_promise(agent.name, place, next_band)
                agent.coordination_partner = other.name
                other.coordination_partner = agent.name
                self.village_log["promise_made"] += 1

        shared = 0
        for event, speaker, listener in ((opening, agent, other), (reply, other, agent)):
            if event.speech_act == "tell" and event.topic in {"food", "place", "water"}:
                shared += self._share_belief(speaker, listener)
        if shared:
            agent.basal.satisfy("RECOGNITION", 0.15)
            self.village_log["belief_shared"] += shared

        action = RelationalAction(
            agent.name, "talk", "dialogue", other.name, place=perception.place_id, visibility=0.8
        )
        self.bus.publish(action, "accepted" if accepted else "refused", living, {agent.name, other.name})
        self.logs.append({"t": self.world.clock.t, "kind": "dialogue", **opening.as_record()})
        self.logs.append({"t": self.world.clock.t, "kind": "dialogue", **reply.as_record()})
        self.village_log["dialogue"] += 1
        return {
            "result": "talked",
            "accepted": accepted,
            "response": 1.0 if accepted else 0.0,
            "text": opening.surface_text,
        }


    def _resolve_promises(self, band):
        """時間帯の終わりに約束の成否を判定する（村§13.2）。

        双方がその場所に居合わせて初めて成立とする。片方だけでは不成立で、
        待った側にH_goal・H_relationが立つ。
        """
        by_name = {agent.name: agent for agent in self.agents}
        for agent in self.agents:
            for promise in agent.upper.promises:
                if promise["band"] != band or promise["kept"] is not None:
                    continue
                partner = by_name.get(promise["partner"])
                arrived = promise["place"] in agent.visited_this_band
                partner_arrived = bool(partner) and promise["place"] in partner.visited_this_band
                kept = arrived and partner_arrived
                agent.upper.resolve_promise(promise, kept)
                if kept:
                    agent.relations.on_cooperation(promise["partner"], True, self.world.clock.t)
                    self.village_log["promise_kept"] += 1
                else:
                    agent.relations.on_cooperation(promise["partner"], False, self.world.clock.t)
                    if arrived and not partner_arrived:
                        agent.promise_break = 0.85
                        agent.relations.state(promise["partner"]).nudge("irritation", 0.12, 0.0, 1.0)
                    else:
                        agent.promise_break = 0.4
                    self.village_log["promise_broken"] += 1
                self.logs.append(
                    {
                        "t": self.world.clock.t,
                        "kind": "promise",
                        "npc": agent.name,
                        "partner": promise["partner"],
                        "place": promise["place"],
                        "band": band,
                        "kept": kept,
                    }
                )
        for agent in self.agents:
            agent.visited_this_band = set()

    def _meeting_place(self, agent, other, band):
        """双方が行きうる場所を選ぶ。

        誘う側の予定地を一方的に相手へ登録すると、聞き手の予定と必ず衝突し、
        約束は構造的に破れる。破れること自体は村§13.2 が扱う現象だが、
        破れる以外の結末が起きない設計は、その現象を観測できなくする。

        優先順：予定の一致 → 相手の予定地が会話可能な場所 → 自分の予定地が同様 → 広場
        """
        mine = agent.upper.block_for(band)
        theirs = other.upper.block_for(band)
        mine_id = mine.place_id if mine else None
        theirs_id = theirs.place_id if theirs else None
        if mine_id and mine_id == theirs_id:
            return mine_id

        def social(place_id):
            place = self.world.places.get(place_id) if place_id else None
            return place is not None and "talk" in place.affordances

        for candidate in (theirs_id, mine_id):
            if social(candidate):
                return candidate
        return "plaza"

    def _share_belief(self, speaker, listener):
        """伝聞は一次観測より弱い信念として着地する（村§3.4, §9.1）。

        自分が知っていて相手が知らない資源のうち、聞き手の身体的不足に合うものを優先する。
        """
        need = "water" if listener.body.thirst_ratio() > listener.body.hunger_ratio() else "food"
        pool = [
            belief
            for belief in speaker.prediction_field.resources.values()
            if belief.node_id not in listener.prediction_field.resources
            and belief.reliability() > 0.4
        ]
        if not pool:
            return 0
        pool.sort(key=lambda item: (item.kind != need, -item.reliability()))
        source = pool[0]
        copied = ResourceBelief(
            source.node_id,
            source.kind,
            source.place_id,
            source.pos,
            source.expected_amount * 0.8,
            confidence=clamp(source.confidence * 0.7, 0.05, 0.98),
            existence_prob=clamp(source.existence_prob * 0.8, 0.0, 1.0),
            last_seen=source.last_seen,
            phase=Phase.LAT,
        )
        listener.prediction_field.resources[source.node_id] = copied
        listener.prediction_field.meaning(source.place_id).resource_expectation = clamp(
            listener.prediction_field.meaning(source.place_id).resource_expectation + 0.15, 0.0, 1.0
        )
        listener.recent_events.append((self.world.clock.t, "heard_about", source.node_id))
        return 1

    def _resolve_give(self, intent, living):
        agent = intent["agent"]
        candidate = intent["candidate"]
        agent.register_prediction(candidate, intent["perception"], None)
        other = next((item for item in living if item.name == candidate.target), None)
        if other is None or not agent.inventory:
            return {"result": "unresolved", "accepted": False}

        item = agent.inventory.pop()
        wants = other.body.hunger_ratio() > 0.4 or item["kind"] == "material"
        accepted = wants and other.relations.state(agent.name).fear < 0.4
        if accepted:
            other.inventory.append(item)
            del other.inventory[:-3]
            other.relations.on_received_gift(agent.name, item["amount"], self.world.clock.t)
            other.basal.satisfy("COMFORT", 0.1)
        else:
            agent.inventory.append(item)
        agent.relations.on_gave_gift(other.name, item["amount"], accepted, self.world.clock.t)
        agent.basal.satisfy("RECOGNITION", 0.25 if accepted else 0.0)
        if agent.pending is not None and agent.pending.get("relation_target") == other.name:
            agent.pending["relation_accepted"] = accepted

        action = RelationalAction(
            agent.name, "give", "transfer", other.name, object=item["kind"], visibility=0.9
        )
        self.bus.publish(action, "accepted" if accepted else "refused", living, {agent.name, other.name})
        self.village_log["give"] += 1
        return {"result": "gave", "accepted": accepted, "response": 1.0 if accepted else 0.0}

    def run(self, ticks=480):
        for _ in range(ticks):
            self.step()
        return self


class VillageObserver:
    """非介入の表示・ログ・統計（村§4.4, §17）。

    ここで作られる情報はNPCの意思決定へ入力しない。
    """

    MARKS = {"広場": "P", "水場": "W", "畑": "F", "店": "S", "林": "G", "家": "H"}

    def __init__(self, simulation):
        self.sim = simulation

    def render(self, width=56, height=28):
        world = self.sim.world
        grid = [["." for _ in range(width)] for _ in range(height)]

        def project(pos):
            return (
                int(clamp(pos[0] / world.size * width, 0, width - 1)),
                int(clamp(pos[1] / world.size * height, 0, height - 1)),
            )

        for place in world.places.all_places():
            cx, cy = project(place.center)
            radius = max(1, int(place.radius / world.size * width))
            mark = self.MARKS.get(place.kind, "?")
            for y in range(max(0, cy - radius // 2), min(height, cy + radius // 2 + 1)):
                for x in range(max(0, cx - radius), min(width, cx + radius + 1)):
                    grid[y][x] = mark.lower()
            grid[cy][cx] = mark
        for obstacle in world.obstacles:
            ox, oy = project(obstacle)
            radius = max(1, int(obstacle[2] / world.size * width))
            for y in range(max(0, oy - radius // 2), min(height, oy + radius // 2 + 1)):
                for x in range(max(0, ox - radius), min(width, ox + radius + 1)):
                    grid[y][x] = "#"
        for node in world.resources.all_nodes():
            if node.state != "available":
                continue
            x, y = project(node.pos)
            grid[y][x] = {"food": "*", "water": "~", "material": "+", "rest": "_"}[node.kind]
        for index, agent in enumerate(self.sim.agents):
            if agent.alive:
                x, y = project(agent.pos)
                grid[y][x] = chr(ord("A") + index)
        return "\n".join("".join(row) for row in grid)

    def summary(self):
        lines = []
        world = self.sim.world
        lines.append("=== RDL Village Simulation ===")
        lines.append(f"経過: {world.clock.t} tick ({world.clock.label()}) / 天候 {world.weather}")
        lines.append(f"生存: {sum(agent.alive for agent in self.sim.agents)} / {len(self.sim.agents)}")

        lines.append("\n--- 行動分布 ---")
        for key, count in sorted(self.sim.village_log.items(), key=lambda item: -item[1])[:12]:
            lines.append(f"  {key}: {count}")

        lines.append("\n--- 資源状態 ---")
        states = defaultdict(list)
        for node in world.resources.all_nodes():
            states[node.state].append(f"{node.id}({node.amount:.0f})")
        for state, items in states.items():
            lines.append(f"  {state}: {', '.join(items)}")

        lines.append("\n--- 個体 ---")
        for agent in self.sim.agents:
            leaps = defaultdict(int)
            for record in agent.leap_log:
                leaps[record["channel"]] += 1
            strongest = agent.relations.strongest(2)
            relation_text = ", ".join(
                f"{state.other}({state.approach_gradient():+.2f} fam={state.familiarity:.2f} "
                f"trust={state.trust:.2f} obl={state.obligation:.2f})"
                for state in strongest
            )
            neuro = agent.neuro
            lines.append(
                f"  {agent.name}[{agent.role}] {agent.body.snapshot()} "
                f"H={agent.h_vec.snapshot()} xi={agent.xi.value:.2f} "
                f"θ={agent.boundary.theta_effective(agent.xi.value):.2f} "
                f"leaps={dict(leaps) or '-'} places={len(agent.prediction_field.places)} "
                f"beliefs={len(agent.prediction_field.resources)}"
            )
            lines.append(
                f"      基層: D1={neuro.d1} D4={neuro.d4} セロトニン={neuro.serotonin} "
                f"オキシトシン={neuro.oxytocin} ノルアドレナリン={neuro.noradrenaline} "
                f"| 退屈={agent.basal_heat.value:.2f} 静穏={agent.basal_heat.quiet_ticks}tick "
                f"| Hゲイン={agent.profile.h.gain:.3f}"
            )
            lines.append(f"      関係: {relation_text or '-'}")

        lines.append("\n--- Leap 発生位置 ---")
        leap_rows = [row for row in self.sim.logs if row.get("leap")]
        for row in leap_rows[-8:]:
            leap = row["leap"]
            lines.append(
                f"  t={leap['t']} {row['npc']} ch={leap['channel']} "
                f"H={leap['pressure']} θ={leap['threshold']} ξ={leap['xi']} → {'; '.join(leap['actions'])}"
            )
        if not leap_rows:
            lines.append("  （なし）")

        lines.append("\n--- 直近の対話 ---")
        dialogue_rows = [row for row in self.sim.logs if row.get("kind") == "dialogue"]
        for row in dialogue_rows[-8:]:
            lines.append(
                f"  t={row['t']} {row['speaker']}→{row['listener']} "
                f"[{row['speech_act']}/{row['topic']}/{row['stance']}] 「{row['text']}」"
            )
        if not dialogue_rows:
            lines.append("  （なし）")

        lines.append("\n--- 関係ネットワーク（approach_gradient > 0.15） ---")
        for agent in self.sim.agents:
            edges = [
                f"{state.other}:{state.approach_gradient():.2f}"
                for state in agent.relations.known()
                if state.approach_gradient() > 0.15
            ]
            lines.append(f"  {agent.name} → {', '.join(edges) or '-'}")

        lines.append("\n--- 視覚野 ---")
        lines.append(self.render())
        return "\n".join(lines)

    def sample_decision_log(self, count=2):
        rows = [row for row in self.sim.logs if "selection_mode" in row]
        return rows[-count:]
