import test from "node:test";
import assert from "node:assert/strict";

import { LivingFieldHSidecar } from "../demos/relational-ecology-lab/v23_h_sidecar.mjs";
import {
  bindMDeltaSubject,
  requestMDelta,
} from "../demos/relational-ecology-lab/v23_mdelta_request.mjs";
import { LivingFieldObserver } from "../demos/relational-ecology-lab/v23_observer.mjs";
import { reviewPostAdjustmentResidual } from "../demos/relational-ecology-lab/v23_post_adjustment_review.mjs";

function unresolvedReview(agentRef = "rabbit:mdelta") {
  const observer = new LivingFieldObserver({ agentRef, dimensions: ["danger", "motion"] });
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
  const comparison = observer.capture({
    tick: 2,
    observed: { danger: 1, motion: 0.5 },
    reliability: { danger: 0.79, motion: 0.59 },
  });
  return reviewPostAdjustmentResidual(comparison, {
    coverageDisposition: "stable-selected-coverage",
    temporalDisposition: "ordinary-temporal-change-excluded",
    basis: "finite review leaves a post-adjustment residual under stable selected coverage",
    reviewer: "living-field:mdelta-reviewer",
    evidenceRefs: [`review:${agentRef}:1`],
    provenance: { source: "mdelta-test-review" },
  });
}

function thresholdSidecar(review, theta = 0.7) {
  const sidecar = new LivingFieldHSidecar({ theta });
  sidecar.observeReview(review);
  return sidecar;
}

test("H below theta cannot form an M_delta request", () => {
  const review = unresolvedReview();
  const sidecar = thresholdSidecar(review, 10);
  assert.equal(sidecar.snapshot().shouldReconstruct, false);
  assert.throws(
    () => requestMDelta(sidecar, {
      reviews: [review],
      requestRef: "mdelta:req:below",
      requester: "living-field:test",
      basis: "invalid threshold request",
    }),
    /requires H >= theta/,
  );
});

test("threshold request preserves finite context and review provenance without inventing M_B prime", () => {
  const review = unresolvedReview();
  const sidecar = thresholdSidecar(review);
  const request = requestMDelta(sidecar, {
    reviews: [review],
    requestRef: "mdelta:req:1",
    requester: "living-field:test",
    basis: "reviewed unresolved H reached the explicit diagnostic theta",
    provenance: { source: "test-request" },
  });

  assert.equal(request.status, "m-delta-requested");
  assert.equal(request.requestRef, "mdelta:req:1");
  assert.equal(request.context.boundaryId, "rabbit:mdelta:normalized-window-v1");
  assert.deepEqual(request.HVector, sidecar.snapshot().HVector);
  assert.equal(request.H, sidecar.snapshot().H);
  assert.equal(request.theta, 0.7);
  assert.equal(request.reviewCount, 1);
  assert.equal(request.reviewProvenance[0].reviewer, "living-field:mdelta-reviewer");
  assert.deepEqual(request.reviewProvenance[0].evidenceRefs, ["review:rabbit:mdelta:1"]);
  assert.equal(request.subjectRef, null);
  assert.equal(request.reconstructionTargetRef, null);
  assert.equal(request.reconstructedModelRef, null);
  assert.equal(request.nextLayer, "T1");
  assert.equal(request.authority, "handoff-only");
  assert.equal("xi" in request, false);
  assert.equal("M_BPrime" in request, false);
});

test("M_delta request cannot substitute fake reviews or incomplete H provenance", () => {
  const review = unresolvedReview();
  const sidecar = thresholdSidecar(review);
  assert.throws(
    () => requestMDelta(sidecar, {
      reviews: [{ eligibleForLivingFieldH: true, mismatch: review.mismatch }],
      requestRef: "mdelta:req:fake",
      requester: "living-field:test",
      basis: "fake review must not enter",
    }),
    /PostAdjustmentResidualReview/,
  );
  assert.throws(
    () => requestMDelta(sidecar, {
      reviews: [],
      requestRef: "mdelta:req:missing",
      requester: "living-field:test",
      basis: "missing provenance must not enter",
    }),
    /requires the finite unresolved reviews supporting H/,
  );
});

test("T1 handoff binds only the explicit current M_B subject and still invents no reconstruction target", () => {
  const review = unresolvedReview();
  const sidecar = thresholdSidecar(review);
  const request = requestMDelta(sidecar, {
    reviews: [review],
    requestRef: "mdelta:req:2",
    requester: "living-field:test",
    basis: "explicit diagnostic threshold crossing",
  });

  assert.throws(
    () => bindMDeltaSubject(request, {
      basis: "missing subject must fail",
      binder: "living-field:test",
    }),
    /explicit current M_B subjectRef/,
  );

  const handoff = bindMDeltaSubject(request, {
    subjectRef: "living-field:agent-constraint-structure:rabbit:mdelta",
    basis: "bind the explicitly identified current finite constraint structure as SILN_SELF",
    binder: "living-field:test",
    provenance: { source: "test-subject-binding" },
  });
  assert.equal(handoff.subjectRef, "living-field:agent-constraint-structure:rabbit:mdelta");
  assert.equal(handoff.subjectRole, "SILN_SELF-current-M_B");
  assert.equal(handoff.reconstructionTargetRef, null);
  assert.equal(handoff.reconstructedModelRef, null);
  assert.equal(handoff.selectionStatus, "not-performed");
  assert.equal(handoff.authority, "T1-handoff-only");
  assert.equal(handoff.request, request);
  assert.throws(() => { handoff.reconstructionTargetRef = "invented"; }, TypeError);
});
