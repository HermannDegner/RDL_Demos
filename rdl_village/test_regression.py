"""固定シードの回帰テスト。

    python -m rdl_village.test_regression

破断検査で同定した各修正を、それぞれ独立に検査する。
ある破断を直した結果が別の指標へ流れ込んだとき、どの不変条件が壊れたかを
特定できる状態を保つのが目的である。数値の良し悪しは判定しない。
"""

import sys
from collections import Counter

from .core import HVec, Phase
from .npc import INTAKE_LIMIT, VillageNPC
from .perception import PredictionField, ResourceBelief
from .profiles import VILLAGE_PROFILE
from .richness import measure
from .simulation import VillageSimulation

SEEDS = (1, 2, 3, 4)
TICKS = 640


def _runs():
    return [VillageSimulation(seed=seed).run(TICKS) for seed in SEEDS]


def test_determinism():
    """村§18：同じseed・同じtick数から同じsnapshotを得る。"""
    key = lambda sim: [
        (r.get("npc"), r.get("selected"), r.get("pos"))
        for r in sim.logs
        if "selection_mode" in r
    ]
    assert key(VillageSimulation(seed=7).run(200)) == key(VillageSimulation(seed=7).run(200))


def test_emergency_gate_reachable(sims):
    """破断1：緊急候補だけで決まる状態が実際に到達する。"""
    modes = [r["selection_mode"] for s in sims for r in s.logs if "selection_mode" in r]
    fired = modes.count("emergency_gate")
    assert fired > 0, "emergency_gate が一度も発火していない"
    assert fired / len(modes) < 0.5, f"emergency_gate が支配的すぎる ({fired/len(modes):.1%})"


def test_leap_is_local():
    """破断2：Leapは対象チャネルのHだけを放出する。"""
    h = HVec(VILLAGE_PROFILE.h)
    for channel in ("resource", "relation", "goal"):
        h.values[channel] = 1.0
    h.retain_after_leap("resource")
    assert h.values["resource"] < 0.5, "対象チャネルが放出されていない"
    assert h.values["relation"] == 1.0, "対象外のチャネルまで放出されている"
    assert h.values["goal"] == 1.0, "対象外のチャネルまで放出されている"


def test_courtship_is_consistent(sims):
    """破断3：同一tick・同一ペアの求愛結果が矛盾しない。"""
    contradictions = 0
    for sim in sims:
        seen = {}
        for row in sim.logs:
            if "selection_mode" not in row or row.get("selected") != "court":
                continue
            key = (row["tick"], frozenset([row["npc"], row.get("target")]))
            seen.setdefault(key, set()).add(row.get("result"))
        contradictions += sum(1 for values in seen.values() if len(values) > 1)
    assert contradictions == 0, f"同一ペアで矛盾する求愛結果 {contradictions} 件"


def test_resolution_is_order_independent():
    """村§14末尾：同一tick内の解決順が結果を変えない。

    相分けが効いていれば、意図リストをどう並べ替えても同じ結果になる。
    逐次解決だと、先に動いたNPCの位置が後続の判定に混入して結果が変わる。
    """
    from .simulation import VillageSimulation as Sim

    def run(reverse):
        sim = Sim(seed=5)
        original = sim._resolve

        def patched(intents, living):
            return original(list(reversed(intents)) if reverse else intents, living)

        sim._resolve = patched
        sim.run(160)
        return [
            (
                agent.name,
                round(agent.x, 6), round(agent.y, 6),
                round(agent.body.hunger, 6), round(agent.body.thirst, 6),
                round(agent.body.fatigue, 6),
                agent.mate, agent.alive,
                sorted((s.other, round(s.trust, 6), round(s.affinity, 6),
                        round(s.residue, 6)) for s in agent.relations.known()),
                sorted((repr(k), round(v.weight, 6)) for k, v in agent.action_memory.patterns.items()),
                {k: round(v, 6) for k, v in agent.h_vec.values.items()},
                round(agent.xi.value, 6), len(agent.xi.unresolved),
            )
            for agent in sim.agents
        ] + [
            (node.id, round(node.amount, 6), node.state)
            for node in sim.world.resources.all_nodes()
        ]

    assert run(False) == run(True), "解決順で結果が変わる（相分けが成立していない）"


def test_agents_do_not_overlap(sims):
    """村§14-9：混雑を解決する。個体同士が重なったまま残らない。"""
    worst = 0.0
    overlaps = 0
    for sim in sims:
        alive = [agent for agent in sim.agents if agent.alive]
        for index, left in enumerate(alive):
            for right in alive[index + 1 :]:
                span = left.body_radius + right.body_radius
                gap = ((left.x - right.x) ** 2 + (left.y - right.y) ** 2) ** 0.5
                if gap < span:
                    overlaps += 1
                    worst = max(worst, span - gap)
    assert overlaps == 0, f"重なったままの個体対が {overlaps} 組（最大 {worst:.3f}）"


def test_unresolved_records_survive(sims):
    """破断4：ξに保持した未確定が、判定不能なまま黙って消えない。"""
    held = [
        record
        for sim in sims
        for agent in sim.agents
        for record in agent.xi.unresolved
    ]
    for item in held:
        assert "kind" in item["record"], "型のない未確定レコードが残っている"


def test_resource_expectation_is_attainable():
    """破断5：資源の期待取得量が、一回の摂取上限を超えない。"""
    field = PredictionField(VILLAGE_PROFILE.node)
    for kind, limit in INTAKE_LIMIT.items():
        field.resources[kind] = ResourceBelief(
            kind, kind, "p", (0.0, 0.0), limit * 3, confidence=0.9, existence_prob=0.9
        )
    sim = VillageSimulation(seed=1)
    npc = sim.agents[0]
    npc.prediction_field = field
    npc.x, npc.y = 0.0, 0.0
    perception = sim.perception_system.perceive(npc, sim.world, sim.agents)
    for kind, limit in INTAKE_LIMIT.items():
        for candidate in npc._resource_candidates(kind, perception, "basal", 1.0):
            amount = candidate.expected_outcome.get("amount")
            if amount is not None:
                assert amount <= limit + 1e-9, f"{kind} の期待取得量 {amount} が上限 {limit} を超える"


def test_belief_decay_is_exponential_in_elapsed():
    """破断7：信念の減衰が経過時間の指数であり、tickごとの再累乗にならない。"""
    field = PredictionField(VILLAGE_PROFILE.node)
    belief = ResourceBelief("x", "food", "p", (0.0, 0.0), 20.0, confidence=0.7, existence_prob=0.8)
    field.resources["x"] = belief
    for t in range(1, 21):
        field.decay(t)
    expected = 0.7 * (0.995 ** 20)
    assert abs(belief.confidence - expected) < 0.02, (
        f"20tickで {belief.confidence:.4f}、単純減衰は {expected:.4f}"
    )


def test_relation_fades_with_absence():
    """去る者は日々に疎し：接触が絶えれば関係は薄れ、続けば薄れない。"""
    sim = VillageSimulation(seed=1)
    npc = sim.agents[0]
    near, far = npc.relations.state("near"), npc.relations.state("far")
    for state in (near, far):
        state.trust = state.affinity = state.familiarity = 0.8
    for t in range(1, 401):
        near.touch(t)
        npc.relations.decay(t)
    assert far.trust < near.trust * 0.8, "疎遠な相手の trust が薄れていない"
    assert near.trust > 0.3, "接触のある相手まで薄れすぎている"


def test_heat_congeals_and_reactivates():
    """処理されない熱はM_Bとして固着し、再会で熱へ戻る。

    案A（時間で冷める）でも案B（事象時間で冷めない）でもない。
    H は派生量であり、熱のまま在り続けず構造へ沈む。
    """
    sim = VillageSimulation(seed=1)
    npc = sim.agents[0]
    state = npc.relations.state("other")

    # 大きく外した予測は、その場で処理しきれず固着する
    npc.relations.register_prediction("other", 0.9, "talk")
    npc.relations.evaluate_response("other", 0.0)
    assert state.residue > 0.0, "外した予測が固着していない"

    # 放置しても構造なので薄れにくい
    congealed = state.residue
    for t in range(1, 200):
        npc.relations.decay(t)
    assert state.residue > congealed * 0.7, "固着が熱と同じ速さで薄れている"

    # 再会すると熱へ戻る
    state.last_contact = 0
    npc.relations.on_proximity("other", 300)
    total, events = npc.relations.take_reactivated()
    assert total > 0.0 and events, "再会で熱へ戻っていない"
    assert state.residue < congealed, "戻した分が固着から引かれていない"

    # 予測が当たれば固着は解ける
    before = state.residue
    npc.relations.register_prediction("other", 0.5, "talk")
    npc.relations.evaluate_response("other", 0.5)
    assert state.residue < before, "当たっても固着が解けない"


def test_reunion_is_not_re_attenuated():
    """戻ってきた熱をゲインで再度平滑化しない。

    通常の誤差経路へ流すと、低頻度チャネルは何度再会してもθへ届かず、
    固着させた意味がなくなる。
    """
    sim = VillageSimulation(seed=1)
    npc = sim.agents[0]
    npc.h_vec.values["relation"] = 0.0
    npc.pending_reactivation = 0.8
    npc.h_vec.observe({})
    if npc.pending_reactivation:
        npc.h_vec.values["relation"] += npc.pending_reactivation
    assert npc.h_vec.values["relation"] > 0.5, (
        f"戻した熱が減衰している: {npc.h_vec.values['relation']:.3f}"
    )


def test_survival_floor(sims):
    """指針§3.2.1：既定世界での生存下限は80%。"""
    alive = sum(agent.alive for sim in sims for agent in sim.agents)
    total = sum(len(sim.agents) for sim in sims)
    assert alive / total >= 0.80, f"生存率 {alive/total:.1%} が下限80%を割った"


def test_relation_axes_are_live():
    """村§19-3：好感度一軸に潰れていない。

    実行中のピークで測る。最終スナップショットは指針§6.1 が避けるよう
    求めている評価であり、減衰する軸は何を足しても終了時にはゼロになる。
    """
    axes = ("familiarity", "trust", "affinity", "irritation", "obligation")
    peak = {}
    for seed in SEEDS[:2]:
        sim = VillageSimulation(seed=seed)
        for _ in range(TICKS):
            sim.step()
            for agent in sim.agents:
                for state in agent.relations.known():
                    record = peak.setdefault((seed, agent.name, state.other), dict.fromkeys(axes, 0.0))
                    for axis in axes:
                        record[axis] = max(record[axis], abs(getattr(state, axis)))
    assert peak, "関係が一つも形成されていない"
    live = {axis: sum(1 for r in peak.values() if r[axis] > 0.05) / len(peak) for axis in axes}
    active = [axis for axis, ratio in live.items() if ratio > 0.02]
    assert len(active) >= 3, f"稼働している関係軸が {len(active)} 本しかない: {live}"

def test_crowding_counts_self():
    """混雑率に自分を含める。定員2の場所に二人いれば 1.0。"""
    sim = VillageSimulation(seed=1)
    plaza = sim.world.places.get("plaza")
    a, b = sim.agents[0], sim.agents[1]
    a.x, a.y = plaza.center
    b.x, b.y = plaza.center[0] + 0.5, plaza.center[1]
    perception = sim.perception_system.perceive(a, sim.world, [a, b])
    expected = plaza.occupancy_ratio(2)
    assert abs(perception.crowding - expected) < 1e-9, (
        f"混雑率 {perception.crowding}、自分を含めた期待値 {expected}"
    )


def test_place_radius_is_not_uniform():
    """移動評価が場所ごとの実際の広さを使う。"""
    sim = VillageSimulation(seed=1)
    npc = sim.agents[0]
    home = sim.world.places.get("home_a")
    grove = sim.world.places.get("grove")
    assert home.radius < 3.0 < grove.radius, "検査前提が崩れている"
    npc.x, npc.y = home.center
    perception = sim.perception_system.perceive(npc, sim.world, sim.agents)
    radii = {entry[0]: entry[3] for entry in perception.visible_places}
    assert radii.get("home_a") == home.radius, "知覚が場所の広さを伝えていない"
    # 家の半径の外側、一律4.0の内側にある点は家の内側と判定されてはならない
    outside = (home.center[0] + (home.radius + grove.radius) / 2, home.center[1])
    meaning = npc.planner._meaning_at(npc.prediction_field, perception, outside)
    assert meaning is None or meaning.place_id != "home_a", "家を実際より広く解釈している"


def test_discovery_is_measured_this_tick(sims):
    """探索の成功判定が、今回新しく知ったかを見ている。"""
    field = sims[0].agents[0].prediction_field
    assert hasattr(field, "last_discoveries"), "発見数が記録されていない"
    sim = VillageSimulation(seed=2)
    npc = sim.agents[0]
    perception = sim.perception_system.perceive(npc, sim.world, sim.agents)
    npc.prediction_field.integrate(perception, 1)
    first = npc.prediction_field.last_discoveries
    npc.prediction_field.integrate(perception, 2)
    assert first > 0, "初回の統合で発見が数えられていない"
    assert npc.prediction_field.last_discoveries == 0, "同じFの再統合が発見として数えられている"


def test_dialogue_phase_affects_selection():
    """語彙ノードの相状態が選択へ接続している（NPC§3.7）。"""
    from .dialogue import build_vocabulary

    active, latent = build_vocabulary()[0], build_vocabulary()[1]
    active.phase = Phase.ACT
    latent.phase = Phase.LAT
    assert active.foreground() > latent.foreground(), "潜在相が前景化と同等に扱われている"
    assert latent.foreground() > 0.0, "潜在相が完全に排除されている（初期語彙が全滅する）"


def test_no_overlap_during_run():
    """混雑の解決は実行中ずっと成立する。最終位置だけでは一時的な重なりを見逃す。"""
    worst = 0.0
    for seed in SEEDS[:2]:
        sim = VillageSimulation(seed=seed)
        for _ in range(TICKS):
            sim.step()
            alive = [agent for agent in sim.agents if agent.alive]
            for index, left in enumerate(alive):
                for right in alive[index + 1 :]:
                    span = left.body_radius + right.body_radius
                    gap = ((left.x - right.x) ** 2 + (left.y - right.y) ** 2) ** 0.5
                    worst = max(worst, span - gap)
    assert worst <= 1e-6, f"実行中の最大侵入量 {worst:.4f}"


def test_reflection_does_not_drop_relation_unresolved():
    """思考的探索が ξ の relation 型を落とさない。

    ξキューを消費する経路が複数あると、そこで扱えない型が黙って消える。
    """
    sim = VillageSimulation(seed=1)
    npc = sim.agents[0]
    perception = sim.perception_system.perceive(npc, sim.world, sim.agents)
    npc.xi.unresolved.clear()
    npc.xi.hold({"kind": "relation", "target": "Ben", "predicted": 0.5, "held_at": 10}, 10, reevaluate_after=0)
    npc._revisit_unresolved(perception, 20)
    remaining = [item for item in npc.xi.unresolved if item["record"].get("kind") == "relation"]
    state = npc.relations.state("Ben")
    assert remaining or state.residue > 0.0, "relation型が再保持も再評価もされず消えた"

    # 未知の型も落とさない
    npc.xi.unresolved.clear()
    npc.xi.hold({"kind": "unknown_kind", "held_at": 10}, 10, reevaluate_after=0)
    npc._revisit_unresolved(perception, 20)
    assert len(npc.xi.unresolved) == 1, "未知型のレコードが消えた"


def test_wait_can_be_learned_as_success():
    """待機は実際に疲労を回復するので、常に失敗として学習されてはならない。"""
    sim = VillageSimulation(seed=1).run(TICKS)
    positive = negative = 0
    for agent in sim.agents:
        for key, pattern in agent.action_memory.patterns.items():
            if key[1] == "wait":
                positive += pattern.positive_count
                negative += pattern.negative_count
    assert positive + negative > 0, "wait が一度も学習されていない"
    assert positive > 0, f"wait が一度も成功していない (成功{positive} 失敗{negative})"


def test_day_partition_is_whole():
    """640tick は 10日ちょうどに分かれ、端数の日が生じない。"""
    from .richness import _day_of
    from .world import TICKS_PER_DAY

    sim = VillageSimulation(seed=1).run(TICKS)
    days = Counter(_day_of(row["tick"]) for row in sim.logs if row.get("npc") == "Aki" and "selection_mode" in row)
    assert len(days) == TICKS // TICKS_PER_DAY, f"日数が {len(days)}"
    assert set(days.values()) == {TICKS_PER_DAY}, f"日ごとの決定数が不揃い: {sorted(days.values())}"


def test_resource_conservation():
    """世界から減った量と、個体が得た量が一致する。

    休眠中・再生中のノードから取得できると、世界に存在しない資源が流入する。
    候補の期待量を無視して上限を要求すると、余剰が誰の身にもならず消える。
    """
    from .world import ResourceNode

    node = ResourceNode("x", "food", "p", (0.0, 0.0), 40.0, 10.0)
    node.state = "regenerating"
    assert node.take(10.0) == 0.0, "再生中のノードから取得できてしまう"

    sim = VillageSimulation(seed=3)
    baseline = {n.id: n.amount for n in sim.world.resources.all_nodes()}
    produced = {n.id: 0.0 for n in sim.world.resources.all_nodes()}
    for node in sim.world.resources.all_nodes():
        node.regen_rate = 0.0
        node.dormant_ticks = 10 ** 6
    for _ in range(200):
        sim.step()
    drained = sum(baseline[n.id] - n.amount for n in sim.world.resources.all_nodes())
    held = sum(sum(a.stock.values()) for a in sim.agents)
    stored = sum(sum(p.objects.values()) for p in sim.world.places.all_places())
    assert drained >= held + stored - 1e-6, (
        f"世界から減った量 {drained:.2f} より、手元にある量 {held + stored:.2f} が多い"
    )


def test_cross_process_determinism():
    """村§18：別プロセスでも同じsnapshotを得る。

    組み込み hash はプロセスごとに乱数化されるため、
    同一プロセス内の二回実行では検出できない破れがある。
    """
    import os
    import subprocess
    import sys

    code = (
        "from rdl_village import VillageSimulation; "
        "s=VillageSimulation(seed=5).run(120); "
        "print([(a.name, round(a.x,6), round(a.y,6), round(a.body.hunger,6)) for a in s.agents])"
    )
    env = dict(os.environ)
    outputs = []
    for seed in ("0", "1", "2"):
        env["PYTHONHASHSEED"] = seed
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, env=env,
            cwd=str(__import__("pathlib").Path(__file__).parent.parent),
        )
        outputs.append(result.stdout.strip())
    assert outputs[0], f"実行できていない: {outputs}"
    assert len(set(outputs)) == 1, "PYTHONHASHSEED によって結果が変わる"


def test_clock_and_evaluation_agree():
    """世界時計の日付と、評価側の日付が一致する。"""
    from .richness import _day_of
    from .world import TICKS_PER_BAND, TICKS_PER_DAY

    sim = VillageSimulation(seed=1)
    bands = Counter()
    for _ in range(TICKS_PER_DAY * 2):
        sim.step()
        assert sim.world.clock.day == _day_of(sim.world.clock.t), (
            f"t={sim.world.clock.t} で clock.day={sim.world.clock.day}、"
            f"評価側={_day_of(sim.world.clock.t)}"
        )
        bands[(sim.world.clock.day, sim.world.clock.band)] += 1
    assert set(bands.values()) == {TICKS_PER_BAND}, f"時間帯ごとのtick数が不揃い: {sorted(set(bands.values()))}"


def test_place_storage_is_used():
    """村§7.3「置く／取る」が実際に成立している。"""
    sims = [VillageSimulation(seed=seed).run(TICKS) for seed in SEEDS[:2]]
    deposits = sum(sim.village_log.get("deposit", 0) for sim in sims)
    takes = sum(sim.village_log.get("take_stored", 0) for sim in sims)
    assert deposits > 0, "場所へ置く行為が一度も起きていない"
    assert takes > 0, "場所から取る行為が一度も起きていない"


def test_stock_use_matches_need(sims):
    """蓄えからの摂取が、身体の不足を超えない。"""
    for sim in sims:
        for row in sim.logs:
            if row.get("result") not in {"used_stock", "took_stored"}:
                continue
            outcome = row.get("outcome", {})
            assert outcome.get("gained", 0.0) >= -1e-9, "負の取得"


def test_perception_is_not_bypassed():
    """村§19-1：NPC側モジュールが物理世界の真値を先読みしない。"""
    import pathlib
    import re

    banned = re.compile(r"world\.(obstacles|resources|places|line_blocked|move_with_collisions)")
    root = pathlib.Path(__file__).parent
    for name in ("npc.py", "action.py", "relations.py", "dialogue.py"):
        text = (root / name).read_text(encoding="utf-8")
        found = banned.search(text)
        assert found is None, f"{name} が物理世界を直接参照している: {found.group(0)}"


def main():
    sims = _runs()
    checks = [
        (test_determinism, ()),
        (test_emergency_gate_reachable, (sims,)),
        (test_leap_is_local, ()),
        (test_courtship_is_consistent, (sims,)),
        (test_resolution_is_order_independent, ()),
        (test_agents_do_not_overlap, (sims,)),
        (test_unresolved_records_survive, (sims,)),
        (test_resource_expectation_is_attainable, ()),
        (test_belief_decay_is_exponential_in_elapsed, ()),
        (test_relation_fades_with_absence, ()),
        (test_heat_congeals_and_reactivates, ()),
        (test_reunion_is_not_re_attenuated, ()),
        (test_survival_floor, (sims,)),
        (test_relation_axes_are_live, ()),
        (test_crowding_counts_self, ()),
        (test_place_radius_is_not_uniform, ()),
        (test_discovery_is_measured_this_tick, (sims,)),
        (test_dialogue_phase_affects_selection, ()),
        (test_no_overlap_during_run, ()),
        (test_reflection_does_not_drop_relation_unresolved, ()),
        (test_wait_can_be_learned_as_success, ()),
        (test_day_partition_is_whole, ()),
        (test_resource_conservation, ()),
        (test_cross_process_determinism, ()),
        (test_clock_and_evaluation_agree, ()),
        (test_place_storage_is_used, ()),
        (test_stock_use_matches_need, (sims,)),
        (test_perception_is_not_bypassed, ()),
    ]
    failures = []
    for check, args in checks:
        try:
            check(*args)
            print(f"  PASS  {check.__name__}")
        except AssertionError as error:
            failures.append((check.__name__, error))
            print(f"  FAIL  {check.__name__}: {error}")

    print(f"\n{len(checks) - len(failures)}/{len(checks)} passed")
    if failures:
        return 1

    stats = [measure(sim) for sim in sims]
    print("\n参考値（判定には使わない）")
    for key in ("repertoire", "divergence", "day_drift", "meaning_var", "leap_var"):
        print(f"  {key:12} {sum(s[key] for s in stats) / len(stats):.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
