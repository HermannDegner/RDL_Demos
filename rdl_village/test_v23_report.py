import json
import unittest

from .v23_report import run_operational_baseline


class VillageV23OperationalReportTests(unittest.TestCase):
    def test_baseline_report_is_read_only_and_json_serializable(self):
        report = run_operational_baseline(ticks=24, seed=23, theta=1.0, required_review_windows=3)
        json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(report["report"], "village-v23-operational-baseline")
        self.assertEqual(report["reviewPolicy"], "advisory-only-until-explicit-review")
        self.assertEqual(report["finiteContextPolicy"], "no-cross-context-generalization")
        self.assertEqual(report["xiStatus"], "unrecovered-relations-remain")
        self.assertFalse(report["terminalTruthClaim"])

        for agent in report["agents"].values():
            self.assertEqual(agent["explicitReviewCount"], 0)
            self.assertEqual(agent["canonicalH"]["H"], 0.0)
            self.assertFalse(agent["canonicalH"]["shouldReconstructDiagnostic"])
            self.assertEqual(agent["installedFiniteContextCount"], 0)
            self.assertEqual(agent["activeRuntimeSessionCount"], 0)
            for recommendation in agent["reviewRecommendations"]:
                self.assertEqual(recommendation["classificationStatus"], "not-performed")
                self.assertEqual(recommendation["authority"], "advisory-only")

    def test_same_seed_produces_same_operational_baseline(self):
        first = run_operational_baseline(ticks=16, seed=41, theta=1.0)
        second = run_operational_baseline(ticks=16, seed=41, theta=1.0)
        self.assertEqual(first, second)

    def test_negative_tick_count_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "ticks must be non-negative"):
            run_operational_baseline(ticks=-1)


if __name__ == "__main__":
    unittest.main()
