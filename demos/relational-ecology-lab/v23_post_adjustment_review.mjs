// Living Field demo-local review gate for post-adjustment residuals.
//
// This module does not auto-detect truth from residual magnitude. It only lets a
// completed finite review classify a post-adjustment residual after preserving
// the same observer B / Purpose / selected dimensions. The review remains
// revisable and is not an ontological claim about the whole interaction field.
import { assessMismatch } from "./v23_state.mjs";

const COVERAGE_DISPOSITIONS = new Set([
  "stable-selected-coverage",
  "coverage-change-observed",
]);
const TEMPORAL_DISPOSITIONS = new Set([
  "ordinary-temporal-change",
  "ordinary-temporal-change-excluded",
]);
const REVIEW_CONTRACT = "living-field-post-adjustment-review-v1";

function nonEmpty(value) {
  return String(value ?? "").trim();
}

function frozenArray(values = []) {
  return Object.freeze([...values]);
}

function finiteContextOf(section) {
  const context = section?.context;
  return Object.freeze({
    boundaryId: context?.boundaryId ?? null,
    purpose: context?.purpose ?? null,
    dimensions: context?.conditions?.dimensions ?? null,
  });
}

function sameFiniteContext(earlierSection, laterSection) {
  const earlier = finiteContextOf(earlierSection);
  const later = finiteContextOf(laterSection);
  return Object.freeze({
    sameBoundary: earlier.boundaryId === later.boundaryId,
    samePurpose: earlier.purpose === later.purpose,
    sameDimensions: earlier.dimensions === later.dimensions,
    earlier,
    later,
  });
}

export class PostAdjustmentResidualReview {
  constructor({
    assessment,
    finiteContext,
    coverageDisposition,
    temporalDisposition,
    basis,
    reviewer,
    evidenceRefs,
    provenance,
  }) {
    this.assessment = assessment;
    this.finiteContext = finiteContext;
    this.coverageDisposition = coverageDisposition;
    this.temporalDisposition = temporalDisposition;
    this.basis = basis;
    this.reviewer = reviewer;
    this.evidenceRefs = frozenArray(evidenceRefs);
    this.provenance = Object.freeze({ ...provenance });
    Object.freeze(this);
  }

  get status() {
    return this.assessment.status;
  }

  get eligibleForLivingFieldH() {
    return this.status === "unresolved-mismatch";
  }
}

export function reviewPostAdjustmentResidual(
  comparison,
  {
    coverageDisposition,
    temporalDisposition,
    basis,
    reviewer,
    evidenceRefs = [],
    provenance = {},
  } = {},
) {
  if (!comparison?.E || !comparison?.assessment) {
    throw new Error("comparison must contain E and its current assessment");
  }
  if (!comparison.assessment.pending) {
    throw new Error("only a pending comparison can enter post-adjustment review");
  }
  if (!(comparison.E.magnitude > 0)) {
    throw new Error("post-adjustment review requires non-zero E");
  }
  if (!COVERAGE_DISPOSITIONS.has(coverageDisposition)) {
    throw new Error("coverageDisposition must explicitly state stable coverage or coverage change");
  }
  if (!TEMPORAL_DISPOSITIONS.has(temporalDisposition)) {
    throw new Error("temporalDisposition must explicitly classify ordinary temporal change");
  }
  const reviewBasis = nonEmpty(basis);
  if (!reviewBasis) throw new Error("post-adjustment review requires a non-empty basis");
  const reviewerId = nonEmpty(reviewer);
  if (!reviewerId) throw new Error("post-adjustment review requires a reviewer");
  const refs = evidenceRefs.map((value) => nonEmpty(value)).filter(Boolean);
  if (refs.length === 0) throw new Error("post-adjustment review requires at least one finite evidence reference");

  const finiteContext = sameFiniteContext(comparison.earlierSection, comparison.laterSection);
  const contextChanged = !finiteContext.sameBoundary
    || !finiteContext.samePurpose
    || !finiteContext.sameDimensions;

  let classification;
  if (contextChanged || coverageDisposition === "coverage-change-observed") {
    classification = "boundary-or-coverage-change";
  } else if (temporalDisposition === "ordinary-temporal-change") {
    classification = "ordinary-temporal-change";
  } else {
    const predictionEvidence = comparison.predictionEvidence;
    if (!predictionEvidence?.residualAfterFiniteAbsorptionAttempt) {
      throw new Error(
        "unresolved review requires residual after a bounded local absorption attempt",
      );
    }
    if (!predictionEvidence.localAbsorptionAttempt?.qualifiesAsFiniteAttempt) {
      throw new Error("unresolved review requires finite local absorption-attempt evidence");
    }
    classification = "unresolved-mismatch";
  }

  const reviewProvenance = Object.freeze({
    ...provenance,
    source: nonEmpty(provenance.source) || "living-field-post-adjustment-review",
    reviewContract: REVIEW_CONTRACT,
    reviewer: reviewerId,
    evidenceRefs: frozenArray(refs),
    predictionModelRef: comparison.predictionEvidence?.modelRef ?? null,
  });
  const assessment = assessMismatch(comparison.E, {
    classification,
    basis: reviewBasis,
    provenance: reviewProvenance,
  });

  return new PostAdjustmentResidualReview({
    assessment,
    finiteContext,
    coverageDisposition,
    temporalDisposition,
    basis: reviewBasis,
    reviewer: reviewerId,
    evidenceRefs: refs,
    provenance: reviewProvenance,
  });
}
