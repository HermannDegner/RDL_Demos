// Canonical Core v2.3 semantic boundary for the Living Field migration.
//
// This module intentionally runs beside the historical ecology runtime. It does
// not reinterpret that runtime's H/xi/thetaEffective variables as current Core
// primitives. Those values remain demo-local until the staged cutover is done.
//
// Canonical path:
//   raw interaction(s)
//     -> acquisition under Purpose / B
//     -> InteractionSection (demo representation of RIB_B)
//     -> interp(M_B, RIB_B)
//     -> F
//
//   later interaction(s)
//     -> InteractionSection
//     -> same pre-update M_B
//     -> F'
//     -> E = Delta(F, F')
//     -> explicit assessment
//     -> unresolved component only
//     -> H
//
// Coverage / uncertainty / exploration pressure are separate implementation
// states. Core xi is not represented by a runtime scalar here.

function frozenObject(value = {}) {
  return Object.freeze({ ...value });
}

export class BoundaryContext {
  constructor({ boundaryId, purpose, question = null, observationTime = null, conditions = {} }) {
    if (!String(boundaryId ?? "").trim()) throw new Error("boundaryId must be non-empty");
    if (!String(purpose ?? "").trim()) throw new Error("purpose must be non-empty");
    this.boundaryId = boundaryId;
    this.purpose = purpose;
    this.question = question;
    this.observationTime = observationTime;
    this.conditions = frozenObject(conditions);
    Object.freeze(this);
  }
}

export class InteractionSection {
  constructor({ sectionId, context, payload, role = "observation", provenance = null }) {
    if (!String(sectionId ?? "").trim()) throw new Error("sectionId must be non-empty");
    if (!(context instanceof BoundaryContext)) throw new Error("context must be a BoundaryContext");
    if (!String(role ?? "").trim()) throw new Error("role must be non-empty");
    this.sectionId = sectionId;
    this.context = context;
    this.payload = frozenObject(payload);
    this.role = role;
    this.provenance = provenance ? frozenObject(provenance) : null;
    Object.freeze(this);
  }
}

export class InterpretationState {
  constructor({ values, sectionId, modelRef }) {
    this.values = frozenObject(values);
    this.sectionId = sectionId;
    this.modelRef = modelRef;
    Object.freeze(this);
  }
}

export class MismatchObservation {
  constructor({ values, reasons = [] }) {
    this.values = frozenObject(values);
    this.reasons = Object.freeze([...reasons]);
    Object.freeze(this);
  }

  get magnitude() {
    return Math.max(0, ...Object.values(this.values).map((value) => Math.abs(Number(value) || 0)));
  }
}

export const MISMATCH_ASSESSMENT_STATUSES = Object.freeze([
  "zero-difference",
  "pending-assessment",
  "ordinary-temporal-change",
  "boundary-or-coverage-change",
  "resolved-difference",
  "unresolved-mismatch",
]);

const MISMATCH_ASSESSMENT_STATUS_SET = new Set(MISMATCH_ASSESSMENT_STATUSES);
const EXPLICIT_ASSESSMENT_STATUSES = new Set([
  "ordinary-temporal-change",
  "boundary-or-coverage-change",
  "resolved-difference",
  "unresolved-mismatch",
]);

export class MismatchAssessment {
  constructor({ status, basis = null, provenance = null }) {
    if (!MISMATCH_ASSESSMENT_STATUS_SET.has(status)) {
      throw new Error(`unknown mismatch assessment status: ${status}`);
    }
    if (EXPLICIT_ASSESSMENT_STATUSES.has(status) && !String(basis ?? "").trim()) {
      throw new Error(`${status} requires a non-empty basis`);
    }
    this.status = status;
    this.basis = basis == null ? null : String(basis);
    this.provenance = provenance ? frozenObject(provenance) : null;
    Object.freeze(this);
  }

  get eligibleForH() {
    return this.status === "unresolved-mismatch";
  }

  get pending() {
    return this.status === "pending-assessment";
  }
}

export function assessMismatch(
  mismatch,
  { classification = null, basis = null, provenance = null } = {},
) {
  if (!(mismatch instanceof MismatchObservation)) {
    throw new Error("mismatch must be a MismatchObservation");
  }
  if (mismatch.magnitude === 0) {
    if (classification && classification !== "zero-difference") {
      throw new Error("zero mismatch cannot be classified as non-zero evidence");
    }
    return new MismatchAssessment({
      status: "zero-difference",
      basis: basis ?? "F and F' are equal under the same finite evaluator",
      provenance,
    });
  }

  const status = classification ?? "pending-assessment";
  if (status === "zero-difference") {
    throw new Error("non-zero mismatch cannot be classified as zero-difference");
  }
  return new MismatchAssessment({ status, basis, provenance });
}

export class UnresolvedMismatchState {
  constructor({ theta = 1, decay = 1 } = {}) {
    if (theta < 0) throw new Error("theta must be non-negative");
    if (decay < 0 || decay > 1) throw new Error("decay must be in [0, 1]");
    this.theta = Number(theta);
    this.decay = Number(decay);
    this.values = {};
  }

  observe(mismatch, { unresolved = null, assessment = null } = {}) {
    if (!(mismatch instanceof MismatchObservation)) {
      throw new Error("mismatch must be a MismatchObservation");
    }
    let unresolvedFlag = unresolved;
    if (assessment !== null) {
      if (!(assessment instanceof MismatchAssessment)) {
        throw new Error("assessment must be a MismatchAssessment");
      }
      if (assessment.pending) {
        throw new Error("pending mismatch assessment cannot update H");
      }
      unresolvedFlag = assessment.eligibleForH;
    }
    if (typeof unresolvedFlag !== "boolean") {
      throw new Error("observe requires unresolved boolean or completed assessment");
    }

    const keys = new Set([...Object.keys(this.values), ...Object.keys(mismatch.values)]);
    const next = {};
    for (const key of keys) {
      const retained = (this.values[key] ?? 0) * this.decay;
      const increment = unresolvedFlag ? Math.abs(mismatch.values[key] ?? 0) : 0;
      next[key] = retained + increment;
    }
    this.values = next;
  }

  get magnitude() {
    return Math.max(0, ...Object.values(this.values));
  }

  get shouldReconstruct() {
    return this.magnitude >= this.theta;
  }

  snapshot() {
    return { ...this.values };
  }
}

export class CoverageState {
  constructor() {
    this.missingObservation = 0;
    this.unknownRelation = 0;
    this.rejectedObservation = 0;
  }

  recordMissing(count = 1) {
    this.missingObservation += Math.max(0, Number.parseInt(count, 10) || 0);
  }

  recordUnknownRelation(count = 1) {
    this.unknownRelation += Math.max(0, Number.parseInt(count, 10) || 0);
  }

  recordRejected(count = 1) {
    this.rejectedObservation += Math.max(0, Number.parseInt(count, 10) || 0);
  }

  snapshot() {
    return {
      missingObservation: this.missingObservation,
      unknownRelation: this.unknownRelation,
      rejectedObservation: this.rejectedObservation,
    };
  }
}

export function acquireInteractionSection({
  sectionId,
  context,
  payload,
  role = "observation",
  provenance = null,
}) {
  return new InteractionSection({ sectionId, context, payload, role, provenance });
}

export function interpretSection(section, { modelRef, interpreter }) {
  if (!(section instanceof InteractionSection)) {
    throw new Error("section must be an InteractionSection");
  }
  if (typeof interpreter !== "function") throw new Error("interpreter must be a function");
  return new InterpretationState({
    values: interpreter(section),
    sectionId: section.sectionId,
    modelRef,
  });
}

export function compareInterpretations(current, later) {
  if (!(current instanceof InterpretationState) || !(later instanceof InterpretationState)) {
    throw new Error("current and later must be InterpretationState values");
  }
  if (current.modelRef !== later.modelRef) {
    throw new Error("F and F' must use the same pre-update modelRef");
  }
  const keys = new Set([...Object.keys(current.values), ...Object.keys(later.values)]);
  const values = {};
  for (const key of keys) {
    values[key] = Math.abs((later.values[key] ?? 0) - (current.values[key] ?? 0));
  }
  const reasons = Object.keys(values).filter((key) => values[key] > 0).sort();
  return new MismatchObservation({ values, reasons });
}

export function legacyLocalDynamicsView(agent) {
  // Staged compatibility adapter for the historical Living Field runtime.
  //
  // These renamed fields preserve the demo's current behaviour while making
  // their semantic status explicit. None of them is promoted into Core xi/H.
  // A shallow copy of H is returned so callers cannot mutate the runtime by
  // editing the view object.
  if (!agent || typeof agent !== "object") throw new Error("agent must be an object");
  const localLoad = frozenObject(agent.H ?? {});
  const adaptationPressure = Number(agent.xi ?? 0);
  const localLeapThreshold = Number(agent.thetaEffective ?? agent.thetaBase ?? 0);
  return Object.freeze({
    localLoad,
    adaptationPressure,
    localLeapThreshold,
    sourceFields: Object.freeze({
      localLoad: "H",
      adaptationPressure: "xi",
      localLeapThreshold: "thetaEffective",
    }),
  });
}
