import re
import unittest
from pathlib import Path

from .simulation import VillageSimulation
from .v23_compatibility import (
    ALIASES,
    CANONICAL_V23_MODULES,
    compatibility_snapshot,
    village_local_dynamics_view,
)


class VillageV23CompatibilityTests(unittest.TestCase):
    def test_historical_aliases_are_explicitly_non_core_compatibility_roles(self):
        by_name = {item.historical_name: item for item in ALIASES}
        self.assertEqual(by_name["HVec"].local_role_name, "LocalLoadVector")
        self.assertEqual(by_name["XiPool"].local_role_name, "ExplorationState")
        self.assertEqual(by_name["Boundary"].local_role_name, "ActionBoundary")
        self.assertEqual(by_name["BasalHeat"].local_role_name, "BasalExplorationLoad")
        for item in ALIASES:
            self.assertEqual(item.core_identity, "none")
            self.assertEqual(item.authority, "compatibility-only")

    def test_local_dynamics_view_exposes_no_core_h_or_xi_identity(self):
        simulation = VillageSimulation(seed=17)
        view = village_local_dynamics_view(simulation.agents[0])
        self.assertIn("localLoadVector", view)
        self.assertIn("explorationState", view)
        self.assertIn("actionBoundary", view)
        self.assertIn("basalExplorationLoad", view)
        self.assertFalse(view["legacyNumericXiIsCoreXi"])
        self.assertFalse(view["localLoadIsCoreH"])
        self.assertFalse(view["actionBoundaryIsCompleteCoreB"])
        self.assertNotIn("H", view)
        self.assertNotIn("xi", view)

    def test_canonical_v23_modules_do_not_depend_on_historical_aliases_or_load_fields(self):
        root = Path(__file__).resolve().parent
        forbidden_names = ("HVec", "XiPool", "BasalHeat")
        forbidden_runtime_reads = (
            ".h_vec",
            ".xi.value",
            ".theta_effective(",
            ".basal_heat",
        )
        for filename in CANONICAL_V23_MODULES:
            text = (root / filename).read_text(encoding="utf-8")
            for name in forbidden_names:
                self.assertIsNone(
                    re.search(rf"\b{re.escape(name)}\b", text),
                    f"{filename} reintroduced historical alias {name}",
                )
            for token in forbidden_runtime_reads:
                self.assertNotIn(
                    token,
                    text,
                    f"{filename} reintroduced compatibility state as canonical evidence: {token}",
                )

    def test_compatibility_snapshot_keeps_xi_open_and_aliases_quarantined(self):
        snapshot = compatibility_snapshot()
        self.assertEqual(snapshot["policy"], "legacy-names-quarantined-not-Core-semantics")
        self.assertEqual(snapshot["xiStatus"], "unrecovered-relations-remain")
        self.assertEqual(
            {item["historicalName"] for item in snapshot["aliases"]},
            {"HVec", "XiPool", "Boundary", "BasalHeat"},
        )


if __name__ == "__main__":
    unittest.main()
