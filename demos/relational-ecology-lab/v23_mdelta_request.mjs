// Read-only Living Field M_delta request / T1 handoff contract.
//
// T0 only establishes that H >= theta requires transition into the M_delta
// reorganization phase. It does not invent M_B', a reconstruction target, or a
// numeric xi. The actual probe / selection / reconstruction path belongs to T1.
import { LivingFieldHSidecar } from "./v23_h_sidecar.mjs";
import { PostAdjustmentResidualReview } from "./v23_post_adjustment_review.mjs";

const EPSILON = 1e-12;
const REQUEST_CONTRACT = "living-field-m-delta-request-v1";
const HANDOFF_CONTRACT = "living-field-m-delta-t1-handoff-v1";

function nonEmpty(value) {
  return String(value ?? "").trim();
}

function frozenObject(value = {}) {
  return Object.freeze({ ...value });
}

function frozenArray(values = []) {
  return Object.freeze([...values]);
}

function sameContext(a, b) {
  return a?.boundaryId === b?.boundaryId
    && a?.purpose === b?.purpose
    && a?.dimensions === b?.dimensions;
}

function reviewContext(review) {
  const context = review?.finiteContext?.earlier ?? {};
  return Object.freeze({
    boundaryId: context.boundaryId ?? null,
    purpose: context.purpose ?? null,
    dimensions: context.dimensions ?? null,
  });
}

function accumulateReviewVector(reviews) {
  const values = {};
  for (const review of reviews) {
    for (const [key, value] of Object.entries(review.mismatch.values)) {
      values[key] = (values[key] ?? 0) + Math.abs(Number(value) || 0);
    }
  }
  return values;
}

function sameVector(a, b) {
  const keys = new Set([...Object.keys(a ?? {}), ...Object.keys(b ?? {})]);
  for (const key of keys) {
    if (Math.abs((a?.[key] ?? 0) - (b?.[key] ?? 0)) > EPSILON) return false;
  }
  return true;
}

function reviewProvenanceSummary(review) {
  return Object.freeze({
    reviewer: review.reviewer,
    basis: review.basis,
    evidenceRefs: frozenArray(review.evidenceRefs),
    provenance: frozenObject(review.provenance),
  });
}

export class MDeltaRequest {
  constructor({
    requestRef,
    requester,
    basis,
    context,
    HVector,
    H,
    theta,
    normRef,
    reviewProvenance,
    provenance,
  }) {
    this.requestRef = requestRef;
    this.requester = requester;
    this.basis = basis;
    this.context = frozenObject(context);
    this.HVector = frozenObject(HVector);
    this.H = H;
    this.theta = theta;
    this.normRef = normRef;
    this.reviewCount = reviewProvenance.length;
    this.reviewProvenance = frozenArray(reviewProvenance);
    this.provenance = frozenObject(provenance);
    this.status = "m-delta-requested";
    this.subjectRef = null;
    this.reconstructionTargetRef = null;
    this.reconstructedModelRef = null;
    this.authority = "handoff-only";
    this.nextLayer = "T1";
    Object.freeze(this);
  }
}

export class MDeltaT1Handoff {
  constructor({ request, subjectRef, basis, binder, provenance }) {
    this.request = request;
    this.subjectRef = subjectRef;
    this.subjectRole = "SILN_SELF-current-M_B";
    this.basis = basis;
    this.binder = binder;
    this.provenance = frozenObject(provenance);
    this.reconstructionTargetRef = null;
    this.reconstructedModelRef = null;
    this.selectionStatus = "not-performed";
    this.authority = "T1-handoff-only";
    Object.freeze(this);
  }
}

export function requestMDelta(
  sidecar,
  {
    reviews,
    requestRef,
    requester,
    basis,
    provenance = {},
  } = {},
) {
  if (!(sidecar instanceof LivingFieldHSidecar)) {
    throw new Error("M_delta request requires a LivingFieldHSidecar");
  }
  const snapshot = sidecar.snapshot();
  if (!snapshot.shouldReconstruct || snapshot.H < snapshot.theta) {
    throw new Error("M_delta request requires H >= theta");
  }
  if (!Array.isArray(reviews) || reviews.length === 0) {
    throw new Error("M_delta request requires the finite unresolved reviews supporting H");
  }
  if (reviews.length !== snapshot.unresolvedReviews) {
    throw new Error("M_delta request review count must match the H sidecar unresolved review count");
  }
  if (!snapshot.context) {
    throw new Error("M_delta request requires a finite H context");
  }

  for (const review of reviews) {
    if (!(review instanceof PostAdjustmentResidualReview)) {
      throw new Error("M_delta request reviews must be PostAdjustmentResidualReview values");
    }
    if (!review.eligibleForLivingFieldH) {
      throw new Error("M_delta request accepts only reviewed unresolved mismatches");
    }
    if (!sameContext(snapshot.context, reviewContext(review))) {
      throw new Error("M_delta request cannot mix finite review contexts");
    }
  }

  const rebuiltVector = accumulateReviewVector(reviews);
  if (!sameVector(snapshot.HVector, rebuiltVector)) {
    throw new Error("M_delta request reviews must reproduce the current H vector");
  }

  const finiteRequestRef = nonEmpty(requestRef);
  if (!finiteRequestRef) throw new Error("M_delta request requires an explicit requestRef");
  const requesterId = nonEmpty(requester);
  if (!requesterId) throw new Error("M_delta request requires a requester");
  const requestBasis = nonEmpty(basis);
  if (!requestBasis) throw new Error("M_delta request requires a non-empty basis");

  return new MDeltaRequest({
    requestRef: finiteRequestRef,
    requester: requesterId,
    basis: requestBasis,
    context: snapshot.context,
    HVector: snapshot.HVector,
    H: snapshot.H,
    theta: snapshot.theta,
    normRef: snapshot.normRef,
    reviewProvenance: reviews.map(reviewProvenanceSummary),
    provenance: {
      ...provenance,
      source: nonEmpty(provenance.source) || "living-field-h-sidecar",
      requestContract: REQUEST_CONTRACT,
      sidecarAuthority: snapshot.authority,
    },
  });
}

export function bindMDeltaSubject(
  request,
  {
    subjectRef,
    basis,
    binder,
    provenance = {},
  } = {},
) {
  if (!(request instanceof MDeltaRequest)) {
    throw new Error("T1 handoff requires an MDeltaRequest");
  }
  const finiteSubjectRef = nonEmpty(subjectRef);
  if (!finiteSubjectRef) {
    throw new Error("T1 handoff requires an explicit current M_B subjectRef");
  }
  const bindingBasis = nonEmpty(basis);
  if (!bindingBasis) throw new Error("T1 handoff requires a non-empty binding basis");
  const binderId = nonEmpty(binder);
  if (!binderId) throw new Error("T1 handoff requires a binder");

  return new MDeltaT1Handoff({
    request,
    subjectRef: finiteSubjectRef,
    basis: bindingBasis,
    binder: binderId,
    provenance: {
      ...provenance,
      source: nonEmpty(provenance.source) || "living-field-m-delta-subject-binding",
      handoffContract: HANDOFF_CONTRACT,
      requestRef: request.requestRef,
    },
  });
}
