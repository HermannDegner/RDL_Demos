// Read-only Living Field H sidecar.
//
// Only completed PostAdjustmentResidualReview values may enter this module.
// Generic assessment labels, prediction residual magnitude, and the historical
// ecology runtime's H / xi / thetaEffective fields are intentionally excluded.
//
// The L2 norm below is a demo-local finite concretization of H = ||H_vec||. It
// is not asserted as the unique Core norm.
import { PostAdjustmentResidualReview } from "./v23_post_adjustment_review.mjs";

const NORM_REF = "l2-demo-local-v1";

function contextKey(review) {
  const context = review.finiteContext?.earlier ?? {};
  return Object.freeze({
    boundaryId: context.boundaryId ?? null,
    purpose: context.purpose ?? null,
    dimensions: context.dimensions ?? null,
  });
}

function sameContext(a, b) {
  return a?.boundaryId === b?.boundaryId
    && a?.purpose === b?.purpose
    && a?.dimensions === b?.dimensions;
}

function l2(values = {}) {
  return Math.sqrt(
    Object.values(values).reduce((sum, value) => sum + (Number(value) || 0) ** 2, 0),
  );
}

export class LivingFieldHSidecar {
  constructor({ theta } = {}) {
    if (!Number.isFinite(theta) || theta < 0) {
      throw new Error("Living Field H sidecar requires an explicit non-negative theta");
    }
    this.theta = Number(theta);
    this.context = null;
    this.values = {};
    this.reviewed = 0;
    this.unresolvedReviews = 0;
    this.lastReview = null;
  }

  observeReview(review) {
    if (!(review instanceof PostAdjustmentResidualReview)) {
      throw new Error("Living Field H sidecar accepts only PostAdjustmentResidualReview values");
    }
    this.reviewed += 1;
    this.lastReview = review;

    if (!review.eligibleForLivingFieldH) {
      return this.snapshot();
    }

    const nextContext = contextKey(review);
    if (!this.context) this.context = nextContext;
    else if (!sameContext(this.context, nextContext)) {
      throw new Error("cannot accumulate Living Field H across different finite review contexts");
    }

    const next = { ...this.values };
    for (const [key, value] of Object.entries(review.mismatch.values)) {
      next[key] = (next[key] ?? 0) + Math.abs(Number(value) || 0);
    }
    this.values = next;
    this.unresolvedReviews += 1;
    return this.snapshot();
  }

  get magnitude() {
    return l2(this.values);
  }

  get shouldReconstruct() {
    return this.magnitude >= this.theta;
  }

  snapshot() {
    return Object.freeze({
      context: this.context ? Object.freeze({ ...this.context }) : null,
      HVector: Object.freeze({ ...this.values }),
      H: this.magnitude,
      theta: this.theta,
      shouldReconstruct: this.shouldReconstruct,
      reviewed: this.reviewed,
      unresolvedReviews: this.unresolvedReviews,
      normRef: NORM_REF,
      authority: "diagnostic-only",
    });
  }
}
