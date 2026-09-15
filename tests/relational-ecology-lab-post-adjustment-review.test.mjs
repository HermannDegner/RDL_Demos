import test from "node:test";
import assert from "node:assert/strict";

import { LivingFieldObserver } from "../demos/relational-ecology-lab/v23_observer.mjs";
import {
  PostAdjustmentResidualReview,
  reviewPostAdjustmentResidual,
} from "../demos/relational-ecology-lab/v23_post_adjustment_review.mjs";

function comparisonAfterBoundedAttempt() {
  const observer = new LivingFieldObserver({
    agentRef: "rabbit:review",
    dimensions: ["danger"],
  });
  observer.capture({
    tick: 1,
    observed: { danger: 0.1 },
    reliability: { danger: 0.8 },
  });
  const staged = observer.beginPredictionWindow({
    tick: 1,
    prediction: { danger: 0 },
    reliability: { danger: 0.79 },
  });
  assert.equal(staged.localAbsorptionAttempt.status, "bounded-local-adjustment-observed");
  const comparison = observer.capture({
    tick: 2,
    observed: { danger: 1 },
    reliability: { danger: 0.79 },
  });
  assert.equal(comparison.status, "pending-assessment");
  assert.equal(
    comparison.predictionEvidence.status,
    "prediction-residual-after-bounded-local-adjustment",
  );
  return comparison;
}

function reviewInput(overrides = {}) {
  return {
    coverageDisposition: "stable-selected-coverage",
    temporalDisposition: "ordinary-temporal-change-excluded",
    basis: "same finite acquisition remained available and finite review found the residual persisted beyond the bounded local adjustment",
    reviewer: "living-field:test-reviewer",
    evidenceRefs: ["rabbit:review:window:1->2"],
    provenance: { source: "test-finite-review" },
    ...overrides,
  };
}

test("unresolved requires same finite context, bounded absorption evidence, and explicit exclusions", () => {
  const comparison = comparisonAfterBoundedAttempt();
  const review = reviewPostAdjustmentResidual(comparison, reviewInput());

  assert.ok(review instanceof PostAdjustmentResidualReview);
  assert.equal(review.status, "unresolved-mismatch");
  assert.equal(review.eligibleForLivingFieldH, true);
  assert.equal(review.assessment.eligibleForH, true);
  assert.equal(review.finiteContext.sameBoundary, true);
  assert.equal(review.finiteContext.samePurpose, true);
  assert.equal(review.finiteContext.sameDimensions, true);
  assert.equal(review.provenance.reviewContract, "living-field-post-adjustment-review-v1");
  assert.equal(review.provenance.reviewer, "living-field:test-reviewer");
  assert.deepEqual(review.provenance.evidenceRefs, ["rabbit:review:window:1->2"]);
});

test("coverage change wins over residual and blocks unresolved classification", () => {
  const review = reviewPostAdjustmentResidual(
    comparisonAfterBoundedAttempt(),
    reviewInput({
      coverageDisposition: "coverage-change-observed",
      basis: "finite acquisition coverage changed during the reviewed interval",
    }),
  );

  assert.equal(review.status, "boundary-or-coverage-change");
  assert.equal(review.eligibleForLivingFieldH, false);
  assert.equal(review.assessment.eligibleForH, false);
});

test("ordinary temporal change wins over residual and blocks unresolved classification", () => {
  const review = reviewPostAdjustmentResidual(
    comparisonAfterBoundedAttempt(),
    reviewInput({
      temporalDisposition: "ordinary-temporal-change",
      basis: "finite review attributes the observed difference to ordinary temporal change",
    }),
  );

  assert.equal(review.status, "ordinary-temporal-change");
  assert.equal(review.eligibleForLivingFieldH, false);
  assert.equal(review.assessment.eligibleForH, false);
});

test("prediction residual without bounded local absorption evidence cannot become unresolved", () => {
  const observer = new LivingFieldObserver({
    agentRef: "rabbit:no-attempt",
    dimensions: ["danger"],
  });
  observer.capture({
    tick: 1,
    observed: { danger: 0.1 },
    reliability: { danger: 0.8 },
  });
  observer.beginPredictionWindow({
    tick: 1,
    prediction: { danger: 0 },
    reliability: { danger: 0.8 },
  });
  const comparison = observer.capture({
    tick: 2,
    observed: { danger: 1 },
    reliability: { danger: 0.8 },
  });
  assert.equal(comparison.predictionEvidence.status, "prediction-residual-present");

  assert.throws(
    () => reviewPostAdjustmentResidual(comparison, reviewInput()),
    /requires residual after a bounded local absorption attempt/,
  );
});

test("review cannot silently infer coverage, temporal exclusion, reviewer, or evidence", () => {
  const comparison = comparisonAfterBoundedAttempt();

  assert.throws(
    () => reviewPostAdjustmentResidual(comparison, reviewInput({ coverageDisposition: null })),
    /coverageDisposition/,
  );
  assert.throws(
    () => reviewPostAdjustmentResidual(comparison, reviewInput({ temporalDisposition: null })),
    /temporalDisposition/,
  );
  assert.throws(
    () => reviewPostAdjustmentResidual(comparison, reviewInput({ reviewer: "" })),
    /requires a reviewer/,
  );
  assert.throws(
    () => reviewPostAdjustmentResidual(comparison, reviewInput({ evidenceRefs: [] })),
    /finite evidence reference/,
  );
});

test("completed review records are immutable and remain finite review claims", () => {
  const review = reviewPostAdjustmentResidual(comparisonAfterBoundedAttempt(), reviewInput());
  assert.throws(() => { review.coverageDisposition = "coverage-change-observed"; }, TypeError);
  assert.throws(() => { review.evidenceRefs.push("invented"); }, TypeError);
  assert.throws(() => { review.provenance.reviewer = "other"; }, TypeError);
});
