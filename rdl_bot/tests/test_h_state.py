"""H蓄積とleap判定（h_state.py）"""

import random
import unittest

from h_state import HState, XI_SATURATION, xi_pressure


class TestXiPressure(unittest.TestCase):
    def test_empty_pool_has_no_pressure(self):
        self.assertEqual(xi_pressure([]), 0.0)

    def test_pressure_grows_with_the_pool(self):
        self.assertLess(xi_pressure(["a"]), xi_pressure(["a", "b", "c"]))

    def test_pressure_saturates_at_one(self):
        self.assertEqual(xi_pressure(["x"] * int(XI_SATURATION * 5)), 1.0)

    def test_zero_saturation_is_harmless(self):
        self.assertEqual(xi_pressure(["a"], saturation=0), 0.0)


class TestThetaEff(unittest.TestCase):
    """Core §6.2: θ_eff(t) = θ + g(ξ(t))"""

    def test_no_xi_leaves_theta_untouched(self):
        """ξが無ければ θ_eff は厳密に θ（既存挙動と一致すること）。"""
        h = HState(theta=2.0)
        for _ in range(20):
            self.assertEqual(h.theta_eff(0.0), 2.0)

    def test_xi_lowers_the_boundary_on_average(self):
        """
        回帰テスト: ξプールは存在したが θ に一切影響せず、ξ が動態から
        切り離されていた（Core §6.2 の g(ξ) が未実装）。
        """
        h = HState(theta=2.0, rng=random.Random(0))
        samples = [h.theta_eff(1.0) for _ in range(200)]
        self.assertLess(sum(samples) / len(samples), 2.0)

    def test_xi_makes_the_boundary_fluctuate(self):
        """Core は ξ が閾値を『揺らす』と定める。決定的な線ではなくなること。"""
        h = HState(theta=2.0, rng=random.Random(0))
        samples = {round(h.theta_eff(1.0), 6) for _ in range(50)}
        self.assertGreater(len(samples), 1)

    def test_boundary_stays_positive(self):
        h = HState(theta=2.0, rng=random.Random(0))
        for _ in range(500):
            self.assertGreater(h.theta_eff(1.0), 0.0)

    def test_more_xi_widens_the_swing(self):
        h = HState(theta=2.0, rng=random.Random(1))
        def spread(p):
            s = [h.theta_eff(p) for _ in range(400)]
            return max(s) - min(s)
        self.assertGreater(spread(1.0), spread(0.3))

    def test_xi_makes_leaping_easier(self):
        """同じHでも、ξが溜まっていれば跳躍しやすくなること。"""
        def leaps(pressure, seed):
            h = HState(theta=2.0, rng=random.Random(seed))
            h.on_deny("A"); h.on_deny("A")   # H_post=2.0 — θちょうどでは超えない
            return h.should_leap(pressure)[0]
        self.assertFalse(leaps(0.0, 0))
        self.assertTrue(any(leaps(1.0, s) for s in range(20)))

    def test_summary_reports_theta_eff(self):
        self.assertIn("θ_eff", HState(theta=2.0).summary(0.5))


class TestMergedH(unittest.TestCase):
    def test_combines_pre_and_post_with_weights(self):
        h = HState(theta=2.0)
        h.on_miss("A")      # H_pre += 0.5
        h.on_deny("A")      # H_post += 1.0
        self.assertAlmostEqual(h.merged_h("A"), 0.5 * HState.H_PRE_WEIGHT + 1.0)

    def test_untouched_node_is_zero(self):
        self.assertEqual(HState().merged_h("nope"), 0.0)


class TestLeapThreshold(unittest.TestCase):
    def test_h_pre_is_weighted_lighter_than_h_post(self):
        h = HState(theta=2.0)
        for _ in range(5):
            h.on_miss("A")   # +0.5 ×5 = 2.5 → ×0.4 = 1.0
        self.assertFalse(h.should_leap()[0])

        h2 = HState(theta=2.0)
        for _ in range(3):
            h2.on_deny("A")  # +1.0 ×3 = 3.0（重み1.0）
        self.assertEqual(h2.should_leap(), (True, "A"))

    def test_agree_cools_the_node(self):
        h = HState(theta=2.0)
        for _ in range(3):
            h.on_deny("A")
        self.assertTrue(h.should_leap()[0])
        for _ in range(4):
            h.on_agree("A")  # ×0.7 ずつ
        self.assertFalse(h.should_leap()[0])

    def test_leap_done_decays_both_pre_and_post(self):
        h = HState(theta=2.0)
        h.on_miss("A")
        h.on_deny("A")
        h.on_deny("A")
        h.leap_done("A")
        self.assertAlmostEqual(h.H_pre["A"], 0.5 * 0.3)
        self.assertAlmostEqual(h.H_post["A"], 2.0 * 0.3)
        self.assertFalse(h.should_leap()[0])

    def test_empty_state_never_leaps(self):
        self.assertEqual(HState().should_leap(), (False, ""))


class TestThetaDynamics(unittest.TestCase):
    def test_leap_raises_theta_up_to_cap(self):
        h = HState(theta=2.0)
        for _ in range(200):
            h.leap_done("A")
        self.assertEqual(h.theta, 5.0)

    def test_relax_theta_returns_toward_base(self):
        """
        回帰テスト: 以前は θ を上げる経路しかなく、一度上限に張り付くと
        二度と下がらなかった（設計書 §2 は「動的調整」と規定）。
        """
        h = HState(theta=2.0)
        for _ in range(200):
            h.leap_done("A")
        self.assertEqual(h.theta, 5.0)
        for _ in range(500):
            h.relax_theta()
        self.assertEqual(h.theta, 2.0)

    def test_relax_never_goes_below_base(self):
        h = HState(theta=2.0)
        for _ in range(50):
            h.relax_theta()
        self.assertEqual(h.theta, h.theta_base)


class TestForgetAndPrune(unittest.TestCase):
    def test_forget_removes_all_accumulation(self):
        h = HState(theta=2.0)
        h.on_miss("ghost")
        h.on_deny("ghost")
        h.forget("ghost")
        self.assertNotIn("ghost", h.H_pre)
        self.assertNotIn("ghost", h.H_post)

    def test_phantom_id_no_longer_blocks_real_nodes(self):
        """
        回帰テスト: 修正対象が存在しない疑似ID（__llm__ など）にHが溜まると、
        毎ターン should_leap() の最大値を占め続け実ノードのleapを妨げていた。
        """
        h = HState(theta=2.0)
        for _ in range(3):
            h.on_deny("__llm__")     # 実ノードに対応しない
        for _ in range(3):
            h.on_deny("real-node")
        self.assertEqual(h.should_leap()[1], "__llm__")
        h.forget("__llm__")
        self.assertEqual(h.should_leap(), (True, "real-node"))

    def test_prune_drops_ids_missing_from_graph(self):
        h = HState(theta=2.0)
        h.on_deny("alive")
        h.on_miss("retired")
        h.on_deny("__crisis__")
        dropped = h.prune({"alive"})
        self.assertEqual(dropped, 2)
        self.assertEqual(set(h.H_post), {"alive"})
        self.assertEqual(set(h.H_pre), set())

    def test_prune_returns_zero_when_all_valid(self):
        h = HState(theta=2.0)
        h.on_deny("alive")
        self.assertEqual(h.prune({"alive", "other"}), 0)

    def test_prune_keeps_the_pending_miss_bucket(self):
        """未解決入力の蓄積は実ノードではないが、退場処理の巻き添えにしない。"""
        h = HState(theta=2.0)
        h.on_miss(None)
        h.prune(set())
        self.assertIn(HState.PENDING_MISS_ID, h.H_pre)


class TestPendingMiss(unittest.TestCase):
    def test_miss_without_nearest_goes_to_the_pending_bucket(self):
        """
        回帰テスト: 最近傍が無い未知入力のHを無関係な既存ノードへ積むと、
        そのノードが後で誤って修正・隔離の対象に選ばれてしまう。
        """
        h = HState(theta=2.0)
        h.on_miss(None)
        self.assertEqual(list(h.H_pre), [HState.PENDING_MISS_ID])

    def test_miss_with_nearest_goes_to_that_node(self):
        h = HState(theta=2.0)
        h.on_miss("near-node")
        self.assertEqual(list(h.H_pre), ["near-node"])

    def test_pending_bucket_can_reach_the_threshold(self):
        h = HState(theta=2.0)
        for _ in range(11):
            h.on_miss(None)
        self.assertEqual(h.should_leap(), (True, HState.PENDING_MISS_ID))

    def test_resolve_miss_defaults_to_the_pending_bucket(self):
        h = HState(theta=2.0)
        h.on_miss(None)
        before = h.H_pre[HState.PENDING_MISS_ID]
        h.resolve_miss(None)
        self.assertLess(h.H_pre[HState.PENDING_MISS_ID], before)


class TestEventTracking(unittest.TestCase):
    def test_dominant_cause(self):
        h = HState(theta=2.0)
        h.on_miss("A")
        for _ in range(3):
            h.on_deny("A")
        self.assertEqual(h.dominant_cause("A"), "deny")

    def test_dominant_cause_of_untouched_node(self):
        self.assertEqual(HState().dominant_cause("nope"), "unknown")

    def test_last_event_seq_increases(self):
        h = HState(theta=2.0)
        h.on_deny("A")
        first = h.last_event_seq("A")
        h.on_deny("B")
        h.on_deny("A")
        self.assertGreater(h.last_event_seq("A"), first)
        self.assertEqual(HState().last_event_seq("nope"), 0)


class TestDriftDeltas(unittest.TestCase):
    def test_events_are_counted_once(self):
        """
        回帰テスト: 以前は毎回history全体を数え直しており、同じイベントが
        M_Δ相のたびにdrift_factorへ繰り返し加算されていた。
        """
        h = HState()
        h.on_deny("A")
        h.on_agree("A")
        h.on_llm_call()
        first = h.drift_deltas()
        self.assertEqual(first, {"deny": 1, "agree": 1, "llm_usage": 1})
        self.assertEqual(h.drift_deltas(), {"deny": 0, "agree": 0, "llm_usage": 0})

        h.on_deny("B")
        self.assertEqual(h.drift_deltas()["deny"], 1)


class TestPersistence(unittest.TestCase):
    def test_round_trip(self):
        h = HState(theta=2.0)
        h.on_deny("A")
        h.on_miss("B")
        h.leap_done("A")
        restored = HState.from_dict(h.to_dict())
        self.assertEqual(restored.H_pre, h.H_pre)
        self.assertEqual(restored.H_post, h.H_post)
        self.assertEqual(restored.theta, h.theta)
        self.assertEqual(restored.theta_base, h.theta_base)
        self.assertEqual(restored.drift_checkpoint_seq, h.drift_checkpoint_seq)
        self.assertEqual(len(restored.history), len(h.history))

    def test_legacy_state_without_theta_base(self):
        """theta_base 未保存の旧セッションで、上がりきったθが下限に固定されないこと。"""
        restored = HState.from_dict({"theta": 4.5, "H_pre": {}, "H_post": {}})
        self.assertEqual(restored.theta, 4.5)
        self.assertEqual(restored.theta_base, 2.0)

    def test_history_is_trimmed(self):
        h = HState()
        for _ in range(600):
            h.on_miss("A")
        self.assertEqual(len(h.history), 500)
        self.assertEqual(h._seq_counter, 600)


if __name__ == "__main__":
    unittest.main()
