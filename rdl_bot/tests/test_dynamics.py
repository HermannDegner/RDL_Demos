"""動態係数の外部設定（dynamics.py）"""

import json
import os
import tempfile
import unittest

import dynamics
from dynamics import DynamicsConfig, load_dynamics_config
from h_state import HState, xi_pressure
from node_graph import Node, NodeGraph


class ConfigTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        # どのテストも既定値から始まり、終了時に必ず戻す
        original = dynamics.CONFIG
        self.addCleanup(lambda: dynamics.configure(original))
        dynamics.configure(DynamicsConfig())

    def write(self, payload: dict) -> str:
        path = os.path.join(self.tmpdir.name, "dyn.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path


class TestLoading(ConfigTestCase):
    def test_missing_file_uses_defaults(self):
        cfg = load_dynamics_config(os.path.join(self.tmpdir.name, "nope.json"))
        self.assertEqual(cfg.dissipation_gamma, DynamicsConfig().dissipation_gamma)

    def test_corrupt_file_falls_back_to_defaults(self):
        path = os.path.join(self.tmpdir.name, "broken.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{壊れた")
        self.assertEqual(load_dynamics_config(path).kappa_m0, DynamicsConfig().kappa_m0)

    def test_partial_file_overrides_only_named_keys(self):
        """変えたいキーだけ書けばよいこと。"""
        cfg = load_dynamics_config(self.write({"dissipation_gamma": 0.05}))
        self.assertEqual(cfg.dissipation_gamma, 0.05)
        self.assertEqual(cfg.kappa_m0, DynamicsConfig().kappa_m0)

    def test_unknown_keys_are_ignored(self):
        cfg = load_dynamics_config(self.write({"kappa_m0": 9.0, "存在しない係数": 1}))
        self.assertEqual(cfg.kappa_m0, 9.0)

    def test_round_trip(self):
        cfg = DynamicsConfig(dissipation_gamma=0.03, theta_initial=3.0)
        restored = DynamicsConfig.from_dict(cfg.to_dict())
        self.assertEqual(restored.dissipation_gamma, 0.03)
        self.assertEqual(restored.theta_initial, 3.0)


class TestConfigActuallyTakesEffect(ConfigTestCase):
    """設定が実際の動態に効くこと（宣言だけで繋がっていない、を防ぐ）。"""

    def test_theta_initial(self):
        dynamics.configure(DynamicsConfig(theta_initial=7.0))
        h = HState()
        self.assertEqual(h.theta, 7.0)
        self.assertEqual(h.theta_base, 7.0)

    def test_theta_raise_and_cap(self):
        dynamics.configure(DynamicsConfig(theta_initial=2.0, theta_raise_on_leap=2.0,
                                          theta_max=8.0))
        h = HState()
        h.leap_done("A")
        self.assertEqual(h.theta, 4.0)
        for _ in range(10):
            h.leap_done("A")
        self.assertEqual(h.theta, 8.0)

    def test_theta_relax(self):
        dynamics.configure(DynamicsConfig(theta_initial=2.0, theta_relax=0.5))
        h = HState(theta=4.0)
        h.theta_base = 2.0
        h.relax_theta()
        self.assertEqual(h.theta, 2.0)

    def test_xi_saturation(self):
        dynamics.configure(DynamicsConfig(xi_saturation=2.0))
        self.assertEqual(xi_pressure(["a", "b"]), 1.0)

    def test_xi_drop_ratio(self):
        dynamics.configure(DynamicsConfig(xi_drop_ratio=0.5, xi_jitter_ratio=0.0))
        h = HState(theta=2.0)
        self.assertAlmostEqual(h.theta_eff(1.0), 1.0)

    def test_zero_jitter_makes_the_boundary_deterministic(self):
        dynamics.configure(DynamicsConfig(xi_jitter_ratio=0.0))
        h = HState(theta=2.0)
        self.assertEqual(len({h.theta_eff(1.0) for _ in range(20)}), 1)

    def test_alignment_ceiling(self):
        dynamics.configure(DynamicsConfig(alignment_ceiling=0.6))
        n = Node(inputs=["x"], confidence=0.5)
        for _ in range(500):
            n.reinforce(0.1)
        self.assertAlmostEqual(n.confidence, 0.6, places=3)

    def test_kappa_m0(self):
        n = Node(inputs=["x"], confidence=1.0)
        dynamics.configure(DynamicsConfig(kappa_m0=1.0))
        tight = n.kappa()
        dynamics.configure(DynamicsConfig(kappa_m0=100.0))
        self.assertGreater(n.kappa(), tight)

    def test_inertia_weights(self):
        n = Node(inputs=["x"], confidence=1.0)
        n.usage_count = 10
        dynamics.configure(DynamicsConfig(inertia_usage_weight=0.0))
        self.assertEqual(n.inertia(), 1.0)
        dynamics.configure(DynamicsConfig(inertia_usage_weight=1.0))
        self.assertEqual(n.inertia(), 11.0)

    def test_dissipation_gamma_and_cap(self):
        n = Node(inputs=["x"], confidence=1.0)
        g = NodeGraph(os.path.join(self.tmpdir.name, "g.json"))
        g.add(n)

        dynamics.configure(DynamicsConfig(dissipation_gamma=0.5, dissipation_cap=1.0))
        self.assertAlmostEqual(g.dissipation_rates()[n.id], 0.5)

        dynamics.configure(DynamicsConfig(dissipation_gamma=0.5, dissipation_cap=0.2))
        self.assertAlmostEqual(g.dissipation_rates()[n.id], 0.2)

    def test_explicit_arguments_still_win(self):
        """テストや呼び出し側からの明示指定は設定より優先されること。"""
        dynamics.configure(DynamicsConfig(kappa_m0=1.0))
        n = Node(inputs=["x"], confidence=1.0)
        self.assertNotAlmostEqual(n.kappa(m_0=100.0), n.kappa())


if __name__ == "__main__":
    unittest.main()
