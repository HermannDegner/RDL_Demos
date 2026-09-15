import test from "node:test";
import assert from "node:assert/strict";

import { LivingFieldHSidecar } from "../demos/relational-ecology-lab/v23_h_sidecar.mjs";
import { LivingFieldObserver } from "../demos/relational-ecology-lab/v23_observer.mjs";
import { reviewPostAdjustmentResidual } from "../demos/relational-ecology-lab/v23_post_adjustment_review.mjs";

function comparisonAfterBoundedAttempt(agentRef = "rabbit:h", dimensions = ["danger", "motion"]) {
  const observer = new LivingFieldObserver({ agentRef, dimensions });
  observer.capture({
    tick: 1,
    observed: { danger: 0.1, motion: 0.2 },
    reliability: { danger: 0.8, motion: 0.6 },
  });
  observer.beginPredictionWindow({
    tick: 1,
    prediction: { danger: 0, motion: 0 },
    reliability: { danger: 0.79, motion: 0.59 },
  });
  return observer.capture({
    tick: 2,
    observed: { danger: 1, motion: 0.5 },
    reliability: { danger: 0.79, motion: 0.59 },
  });
}

function reviewed(comparison, overrides = {}) {
  return reviewPostAdjustmentResidual(comparison, {
    coverageDisposition: "stable-selected-coverage",
    temporalDisposition: "ordinary-temporal-change-excluded",
    basis: "finite review excludes coverage change and ordinary temporal change after bounded local adjustment",
    reviewer: "living-field:h-reviewer",
    evidenceRefs: ["finite-review:h:1"],
    provenance: { source: "test-reviewed-h" },
    ...overrides,
  });
}

test("only reviewed unresolved mismatch enters H_vec and L2 H", () => {
  const review = reviewed(comparisonAfterBoundedAttempt());
  const sidecar = new LivingFieldHSidecar({ theta: 0.7 });
  const snapshot = sidecar.observeReview(review);

  assert.ok(Math.abs(snapshot.HVector.danger - 0.72) < 1e-12);
  assert.ok(Math.abs(snapshot.HVector.motion - 0.18) < 1e-12);
  assert.ok(Math.abs(snapshot.H - Math.hypot(0.72, 0.18)) < 1e-12);
  assert.equal(snapshot.normRef, "l2-demo-local-v1");
  assert.equal(snapshot.theta, 0.7);
  assert.equal(snapshot.shouldReconstruct, true);
  assert.equal(snapshot.unresolvedReviews, 1);
  assert.equal(snapshot.authority, "diagnostic-only");
});

test("ordinary temporal or coverage review does not enter H", () => {
  const comparison = comparisonAfterBoundedAttempt();
  const temporal = reviewed(comparison, {
    temporalDisposition: "ordinary-temporal-change",
    basis: "finite review attributes the difference to ordinary temporal change",
  });
  const coverage = reviewed(comparisonAfterBoundedAttempt("rabbit:h2"), {
    coverageDisposition: "coverage-change-observed",
    basis: "finite review observed changed acquisition coverage",
    evidenceRefs: ["finite-review:h:coverage"],
  });
  const sidecar = new LivingFieldHSidecar({ theta: 0.1 });

  sidecar.observeReview(temporal);
  const snapshot = sidecar.observeReview(coverage);
  assert.deepEqual(snapshot.HVector, {});
  assert.equal(snapshot.H, 0);
  assert.equal(snapshot.shouldReconstruct, false);
  assert.equal(snapshot.reviewed, 2);
  assert.equal(snapshot.unresolvedReviews, 0);
});

test("generic assessment-shaped objects and legacy numeric state cannot enter H sidecar", () => {
  const sidecar = new LivingFieldHSidecar({ theta: 1 });
  assert.throws(
    () => sidecar.observeReview({
      status: "unresolved-mismatch",
      eligibleForLivingFieldH: true,
      mismatch: { values: { danger: 999 } },
      H: 999,
      xi: 999,
      thetaEffective: 0,
    }),
    /accepts only PostAdjustmentResidualReview/,
  );
  assert.deepEqual(sidecar.snapshot().HVector, {});
});

test("H accumulation cannot silently cross finite observer contexts", () => {
  const sidecar = new LivingFieldHSidecar({ theta: 10 });
  sidecar.observeReview(reviewed(comparisonAfterBoundedAttempt("rabbit:h-a"), {
    evidenceRefs: ["finite-review:h:a"],
  }));

  assert.throws(
    () => sidecar.observeReview(reviewed(comparisonAfterBoundedAttempt("rabbit:h-b"), {
      evidenceRefs: ["finite-review:h:b"],
    })),
    /different finite review contexts/,
  );
});

test("theta is explicit and H snapshot is immutable diagnostic state", () => {
  assert.throws(() => new LivingFieldHSidecar(), /explicit non-negative theta/);
  const sidecar = new LivingFieldHSidecar({ theta: 2 });
  const snapshot = sidecar.observeReview(reviewed(comparisonAfterBoundedAttempt()));
  assert.throws(() => { snapshot.HVector.danger = 100; }, TypeError);
  assert.throws(() => { snapshot.authority = "policy"; }, TypeError);
});
