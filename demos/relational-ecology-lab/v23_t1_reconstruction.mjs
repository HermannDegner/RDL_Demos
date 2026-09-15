// Living Field demo-local T1 reconstruction path.
//
// This module consumes an explicit MDeltaT1Handoff, objectifies the current
// finite agent model, expands a bounded candidate, probes it against later
// finite prediction/observation evidence, performs retain/reject/defer
// Selection, and forms an M_B' proposal. None of the numeric candidate rules
// below are Core laws; they are Living Field demo-local candidate generators.
import { MDeltaT1Handoff } from "./v23_mdelta_request.mjs";
import { PredictionAssessmentEvidence } from "./v23_observer.mjs";

const EPSILON = 1e-12;
const MODEL_CONTRACT = "living-field-finite-model-v1";
const CANDIDATE_CONTRACT = "living-field-reconstruction-candidate-v1";
const PROBE_CONTRACT = "living-field-shadow-probe-v1";
const SELECTION_CONTRACT = "living-field-selection-v1";
const RECONSTRUCTION_CONTRACT = "living-field-reconstruction-v1";

function nonEmpty(value) {
  return String(value ?? "").trim();
}

function frozenArray(values = []) {
  return Object.freeze([...values]);
}

function frozenObject(value = {}) {
  return Object.freeze({ ...value });
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function largestDimension(values = {}) {
  return Object.entries(values)
    .sort((a, b) => Math.abs(Number(b[1]) || 0) - Math.abs(Number(a[1]) || 0))[0]?.[0] ?? null;
}

function modelParameters(agent) {
  if (agent.profile?.kind === "rabbit") {
    return {
      "reliability.resource": agent.reliability.resource,
      "reliability.danger": agent.reliability.danger,
      "reliability.motion": agent.reliability.motion,
      "weights.memory": agent.weights.memory,
      "weights.danger": agent.weights.danger,
      "weights.cost": agent.weights.cost,
      exploration: agent.exploration,
      soundCaution: agent.soundCaution,
    };
  }
  if (agent.profile?.kind === "predator") {
    return {
      "reliability.prey": agent.reliability.prey,
      "reliability.motion": agent.reliability.motion,
      "weights.memory": agent.weights.memory,
      "weights.cost": agent.weights.cost,
      exploration: agent.exploration,
    };
  }
  throw new Error("unsupported Living Field species for finite model capture");
}

function parameterBounds(agent) {
  if (agent.profile?.kind === "rabbit") {
    return {
      "reliability.resource": { min: 0.18, max: 0.98 },
      "reliability.danger": { min: 0.18, max: 0.98 },
      "reliability.motion": { min: 0.18, max: 0.98 },
      "weights.memory": { min: 0.48, max: 1.2 },
      "weights.danger": { min: 1.4, max: 3.1 },
      "weights.cost": { min: 0.45, max: 1.2 },
      exploration: { min: 0.08, max: 0.72 },
      soundCaution: { min: 0.55, max: 1.3 },
    };
  }
  return {
    "reliability.prey": { min: 0.18, max: 0.98 },
    "reliability.motion": { min: 0.18, max: 0.98 },
    "weights.memory": { min: 0.48, max: 1.2 },
    "weights.cost": { min: 0.42, max: 1.2 },
    exploration: { min: 0.08, max: 0.72 },
  };
}

function boundedValue(model, key, value) {
  const bounds = model.bounds[key];
  if (!bounds) throw new Error(`candidate references an unmodeled parameter: ${key}`);
  return clamp(value, bounds.min, bounds.max);
}

function rabbitCandidate(model, dimension, candidateRef) {
  const p = model.parameters;
  if (dimension === "resource") {
    return new ReconstructionCandidate({
      candidateRef,
      targetDimension: dimension,
      mode: "phase-shift",
      parameterPatch: {
        "reliability.resource": boundedValue(model, "reliability.resource", p["reliability.resource"] * 0.72),
        "weights.memory": boundedValue(model, "weights.memory", p["weights.memory"] * 0.9),
        exploration: boundedValue(model, "exploration", p.exploration + 0.14),
      },
      operations: [{ type: "fade-resource-memory", factor: 0.48 }],
      basis: "reduce commitment to stale resource interpretation and widen exploration",
      breakConditions: ["resource probe stops improving", "selected coverage changes"],
    });
  }
  if (dimension === "danger") {
    return new ReconstructionCandidate({
      candidateRef,
      targetDimension: dimension,
      mode: "phase-shift",
      parameterPatch: {
        "reliability.danger": boundedValue(model, "reliability.danger", p["reliability.danger"] * 0.75),
        "weights.danger": boundedValue(model, "weights.danger", p["weights.danger"] + 0.22),
        soundCaution: boundedValue(model, "soundCaution", p.soundCaution + 0.1),
      },
      operations: [{ type: "soften-danger-memory", factor: 0.82 }],
      basis: "reduce confidence in the failing danger estimate while increasing conservative response weight",
      breakConditions: ["danger probe stops improving", "selected coverage changes"],
    });
  }
  if (dimension === "motion") {
    return new ReconstructionCandidate({
      candidateRef,
      targetDimension: dimension,
      mode: "phase-shift",
      parameterPatch: {
        "reliability.motion": boundedValue(model, "reliability.motion", p["reliability.motion"] * 0.72),
        "weights.cost": boundedValue(model, "weights.cost", p["weights.cost"] + 0.08),
        exploration: boundedValue(model, "exploration", p.exploration + 0.1),
      },
      operations: [{ type: "stamp-current-motion-break", strength: 1, radius: 2 }],
      basis: "reduce confidence in the stalled motion estimate and open alternate routes",
      breakConditions: ["motion probe stops improving", "selected coverage changes"],
    });
  }
  return null;
}

function predatorCandidate(model, dimension, candidateRef) {
  const p = model.parameters;
  if (dimension === "prey") {
    return new ReconstructionCandidate({
      candidateRef,
      targetDimension: dimension,
      mode: "phase-shift",
      parameterPatch: {
        "reliability.prey": boundedValue(model, "reliability.prey", p["reliability.prey"] * 0.72),
        "weights.memory": boundedValue(model, "weights.memory", p["weights.memory"] * 0.9),
        exploration: boundedValue(model, "exploration", p.exploration + 0.15),
      },
      operations: [{ type: "fade-prey-memory", factor: 0.44 }],
      basis: "reduce commitment to stale prey interpretation and widen search",
      breakConditions: ["prey probe stops improving", "selected coverage changes"],
    });
  }
  if (dimension === "motion") {
    return new ReconstructionCandidate({
      candidateRef,
      targetDimension: dimension,
      mode: "phase-shift",
      parameterPatch: {
        "reliability.motion": boundedValue(model, "reliability.motion", p["reliability.motion"] * 0.72),
        "weights.cost": boundedValue(model, "weights.cost", p["weights.cost"] + 0.08),
        exploration: boundedValue(model, "exploration", p.exploration + 0.1),
      },
      operations: [{ type: "stamp-current-motion-break", strength: 1, radius: 2 }],
      basis: "reduce confidence in the stalled pursuit path and open alternate approach angles",
      breakConditions: ["motion probe stops improving", "selected coverage changes"],
    });
  }
  return null;
}

function setAgentParameter(agent, key, value) {
  if (key.startsWith("reliability.")) {
    agent.reliability[key.slice("reliability.".length)] = value;
    return;
  }
  if (key.startsWith("weights.")) {
    agent.weights[key.slice("weights.".length)] = value;
    return;
  }
  agent[key] = value;
}

function applyMemoryOperation(agent, operation) {
  if (operation.type === "fade-resource-memory") {
    agent.memory.fadeResourceMemory(operation.factor);
    return;
  }
  if (operation.type === "soften-danger-memory") {
    agent.memory.softenDangerMemory(operation.factor);
    return;
  }
  if (operation.type === "fade-prey-memory") {
    agent.memory.fadePreyMemory(operation.factor);
    return;
  }
  if (operation.type === "stamp-current-motion-break") {
    agent.memory.stamp(
      agent.memory.motion,
      agent.x,
      agent.y,
      operation.strength,
      operation.radius,
    );
    return;
  }
  throw new Error(`unknown Living Field reconstruction operation: ${operation.type}`);
}

export class LivingFieldFiniteModel {
  constructor({ modelRef, subjectRef, agentRef, species, context, parameters, bounds, basis, capturer, provenance }) {
    this.modelRef = modelRef;
    this.subjectRef = subjectRef;
    this.agentRef = agentRef;
    this.species = species;
    this.context = frozenObject(context);
    this.parameters = frozenObject(parameters);
    this.bounds = Object.freeze(Object.fromEntries(
      Object.entries(bounds).map(([key, value]) => [key, frozenObject(value)]),
    ));
    this.basis = basis;
    this.capturer = capturer;
    this.provenance = frozenObject(provenance);
    this.xiStatus = "unrecovered-relations-remain";
    Object.freeze(this);
  }
}

export class ReconstructionCandidate {
  constructor({ candidateRef, targetDimension, mode, parameterPatch, operations, basis, breakConditions }) {
    this.candidateRef = candidateRef;
    this.targetDimension = targetDimension;
    this.mode = mode;
    this.parameterPatch = frozenObject(parameterPatch);
    this.operations = Object.freeze(operations.map((operation) => frozenObject(operation)));
    this.basis = basis;
    this.breakConditions = frozenArray(breakConditions);
    this.contract = CANDIDATE_CONTRACT;
    this.authority = "candidate-only";
    Object.freeze(this);
  }
}

export class CandidateProbeResult {
  constructor({ probeRef, candidateRef, targetDimension, evaluationTick, baselineWeightedResidual, candidateWeightedResidual, improvement, status, provenance }) {
    this.probeRef = probeRef;
    this.candidateRef = candidateRef;
    this.targetDimension = targetDimension;
    this.evaluationTick = evaluationTick;
    this.baselineWeightedResidual = baselineWeightedResidual;
    this.candidateWeightedResidual = candidateWeightedResidual;
    this.improvement = improvement;
    this.status = status;
    this.provenance = frozenObject(provenance);
    this.contract = PROBE_CONTRACT;
    Object.freeze(this);
  }
}

export class SelectionDecision {
  constructor({ status, candidateRef = null, basis, probeRefs = [], provenance = {} }) {
    if (!["retain", "reject", "defer"].includes(status)) {
      throw new Error(`unknown Living Field selection status: ${status}`);
    }
    this.status = status;
    this.candidateRef = candidateRef;
    this.basis = basis;
    this.probeRefs = frozenArray(probeRefs);
    this.provenance = frozenObject(provenance);
    this.contract = SELECTION_CONTRACT;
    Object.freeze(this);
  }
}

export class ReconstructedFiniteModel {
  constructor({ modelRef, previousModelRef, subjectRef, agentRef, species, context, parameters, operations, selection, validConditions, breakConditions, unresolvedItems, provenance }) {
    this.modelRef = modelRef;
    this.previousModelRef = previousModelRef;
    this.subjectRef = subjectRef;
    this.agentRef = agentRef;
    this.species = species;
    this.context = frozenObject(context);
    this.parameters = frozenObject(parameters);
    this.operations = Object.freeze(operations.map((operation) => frozenObject(operation)));
    this.selection = selection;
    this.validConditions = frozenObject(validConditions);
    this.breakConditions = frozenArray(breakConditions);
    this.unresolvedItems = frozenArray(unresolvedItems);
    this.xiStatus = "unrecovered-relations-remain";
    this.reentryRequired = true;
    this.contract = RECONSTRUCTION_CONTRACT;
    this.authority = "reconstruction-proposal";
    this.provenance = frozenObject(provenance);
    Object.freeze(this);
  }
}

export function captureLivingFieldFiniteModel(
  handoff,
  agent,
  { modelRef, basis, capturer, provenance = {} } = {},
) {
  if (!(handoff instanceof MDeltaT1Handoff)) {
    throw new Error("finite model capture requires an MDeltaT1Handoff");
  }
  if (!agent || typeof agent !== "object" || !agent.profile?.kind || !agent.focusKey) {
    throw new Error("finite model capture requires a Living Field agent");
  }
  if (!String(handoff.request.context.boundaryId ?? "").startsWith(`${agent.focusKey}:`)) {
    throw new Error("T1 handoff finite context does not belong to the supplied agent");
  }
  const ref = nonEmpty(modelRef);
  if (!ref) throw new Error("finite model capture requires modelRef");
  const finiteBasis = nonEmpty(basis);
  if (!finiteBasis) throw new Error("finite model capture requires basis");
  const capturerId = nonEmpty(capturer);
  if (!capturerId) throw new Error("finite model capture requires capturer");

  return new LivingFieldFiniteModel({
    modelRef: ref,
    subjectRef: handoff.subjectRef,
    agentRef: agent.focusKey,
    species: agent.profile.kind,
    context: handoff.request.context,
    parameters: modelParameters(agent),
    bounds: parameterBounds(agent),
    basis: finiteBasis,
    capturer: capturerId,
    provenance: {
      ...provenance,
      source: nonEmpty(provenance.source) || "living-field-agent-finite-model",
      modelContract: MODEL_CONTRACT,
      handoffRequestRef: handoff.request.requestRef,
    },
  });
}

export function expandLivingFieldCandidates(handoff, model, { candidateRefPrefix = "candidate" } = {}) {
  if (!(handoff instanceof MDeltaT1Handoff)) throw new Error("candidate expansion requires an MDeltaT1Handoff");
  if (!(model instanceof LivingFieldFiniteModel)) throw new Error("candidate expansion requires a LivingFieldFiniteModel");
  if (handoff.subjectRef !== model.subjectRef) throw new Error("candidate expansion subject mismatch");

  const dimension = largestDimension(handoff.request.HVector);
  if (!dimension) return Object.freeze([]);
  const ref = `${candidateRefPrefix}:${dimension}:phase-shift`;
  const candidate = model.species === "rabbit"
    ? rabbitCandidate(model, dimension, ref)
    : predatorCandidate(model, dimension, ref);
  return Object.freeze(candidate ? [candidate] : []);
}

export function probeLivingFieldCandidate(candidate, model, predictionEvidence, { probeRef } = {}) {
  if (!(candidate instanceof ReconstructionCandidate)) throw new Error("probe requires a ReconstructionCandidate");
  if (!(model instanceof LivingFieldFiniteModel)) throw new Error("probe requires a LivingFieldFiniteModel");
  if (!(predictionEvidence instanceof PredictionAssessmentEvidence)) {
    throw new Error("probe requires PredictionAssessmentEvidence");
  }
  const ref = nonEmpty(probeRef);
  if (!ref) throw new Error("probe requires probeRef");
  const key = candidate.targetDimension;
  const prediction = predictionEvidence.prediction?.[key];
  const observed = predictionEvidence.observed?.[key];
  const baselineCoefficient = predictionEvidence.coefficients?.[key];
  const candidateCoefficient = candidate.parameterPatch[`reliability.${key}`]
    ?? model.parameters[`reliability.${key}`];

  if (![prediction, observed, baselineCoefficient, candidateCoefficient].every(Number.isFinite)) {
    return new CandidateProbeResult({
      probeRef: ref,
      candidateRef: candidate.candidateRef,
      targetDimension: key,
      evaluationTick: predictionEvidence.provenance?.evaluationTick ?? null,
      baselineWeightedResidual: null,
      candidateWeightedResidual: null,
      improvement: null,
      status: "not-observed",
      provenance: {
        source: "living-field-shadow-probe",
        probeScope: "selected-prediction-dimension-only",
        reason: "finite prediction/observation/coefficient evidence missing",
      },
    });
  }

  const rawResidual = Math.abs(observed - prediction);
  const baselineWeightedResidual = rawResidual * baselineCoefficient;
  const candidateWeightedResidual = rawResidual * candidateCoefficient;
  const improvement = baselineWeightedResidual - candidateWeightedResidual;
  return new CandidateProbeResult({
    probeRef: ref,
    candidateRef: candidate.candidateRef,
    targetDimension: key,
    evaluationTick: predictionEvidence.provenance?.evaluationTick ?? null,
    baselineWeightedResidual,
    candidateWeightedResidual,
    improvement,
    status: improvement > EPSILON ? "improved" : "not-improved",
    provenance: {
      source: "living-field-shadow-probe",
      probeScope: "selected-prediction-dimension-only",
      predictionModelRef: predictionEvidence.modelRef,
      candidateContract: candidate.contract,
    },
  });
}

function reconstructSelected(model, candidate, selection, handoff, probeResults) {
  const parameters = { ...model.parameters, ...candidate.parameterPatch };
  return new ReconstructedFiniteModel({
    modelRef: `${model.modelRef}:M_B-prime:${candidate.targetDimension}`,
    previousModelRef: model.modelRef,
    subjectRef: model.subjectRef,
    agentRef: model.agentRef,
    species: model.species,
    context: model.context,
    parameters,
    operations: candidate.operations,
    selection,
    validConditions: {
      boundaryId: model.context.boundaryId,
      purpose: model.context.purpose,
      dimensions: model.context.dimensions,
      probeScope: "selected-prediction-dimension-only",
    },
    breakConditions: candidate.breakConditions,
    unresolvedItems: [
      "effects outside the selected prediction dimension remain unobserved",
      "future RIB_B conditions remain open to ξ and require re-entry validation",
    ],
    provenance: {
      source: "living-field-t1-reconstruction",
      reconstructionContract: RECONSTRUCTION_CONTRACT,
      handoffRequestRef: handoff.request.requestRef,
      candidateRef: candidate.candidateRef,
      probeRefs: frozenArray(probeResults.map((result) => result.probeRef)),
    },
  });
}

export class T1ReconstructionSession {
  constructor({ handoff, model, probeWindows = 2, minimumEvaluationTick = null } = {}) {
    if (!(handoff instanceof MDeltaT1Handoff)) throw new Error("T1 session requires MDeltaT1Handoff");
    if (!(model instanceof LivingFieldFiniteModel)) throw new Error("T1 session requires LivingFieldFiniteModel");
    if (!Number.isInteger(probeWindows) || probeWindows < 1) throw new Error("probeWindows must be a positive integer");
    this.handoff = handoff;
    this.model = model;
    this.probeWindows = probeWindows;
    this.minimumEvaluationTick = Number.isFinite(minimumEvaluationTick)
      ? Number(minimumEvaluationTick)
      : -Infinity;
    this.candidates = expandLivingFieldCandidates(handoff, model, {
      candidateRefPrefix: `${handoff.request.requestRef}:candidate`,
    });
    this.probeResults = [];
    this.seenProbeKeys = new Set();
    this.selection = null;
    this.reconstructedModel = null;
    this.status = this.candidates.length > 0 ? "probing" : "deferred-no-candidate";
    if (this.candidates.length === 0) {
      this.selection = new SelectionDecision({
        status: "defer",
        basis: "no demo-local reconstruction candidate exists for the dominant unresolved dimension",
        provenance: { source: "living-field-selection", selectionContract: SELECTION_CONTRACT },
      });
    }
  }

  observeProbe(predictionEvidence) {
    if (this.status !== "probing") return this.snapshot();
    if (!(predictionEvidence instanceof PredictionAssessmentEvidence)) return this.snapshot();
    const evaluationTick = Number(predictionEvidence.provenance?.evaluationTick);
    if (!Number.isFinite(evaluationTick) || evaluationTick <= this.minimumEvaluationTick) return this.snapshot();
    const probeKey = `${predictionEvidence.modelRef}:${evaluationTick}`;
    if (this.seenProbeKeys.has(probeKey)) return this.snapshot();
    this.seenProbeKeys.add(probeKey);

    const candidate = this.candidates[0];
    const result = probeLivingFieldCandidate(candidate, this.model, predictionEvidence, {
      probeRef: `${this.handoff.request.requestRef}:probe:${evaluationTick}`,
    });
    this.probeResults.push(result);
    if (this.probeResults.length < this.probeWindows) return this.snapshot();

    const observed = this.probeResults.filter((entry) => entry.status !== "not-observed");
    if (observed.length < this.probeWindows) {
      this.selection = new SelectionDecision({
        status: "defer",
        basis: "finite shadow Probe coverage was insufficient for Selection",
        probeRefs: this.probeResults.map((entry) => entry.probeRef),
        provenance: { source: "living-field-selection", selectionContract: SELECTION_CONTRACT },
      });
      this.status = "selection-deferred";
      return this.snapshot();
    }

    const allImproved = observed.every((entry) => entry.status === "improved");
    if (!allImproved) {
      this.selection = new SelectionDecision({
        status: "reject",
        candidateRef: candidate.candidateRef,
        basis: "candidate failed to improve every finite shadow Probe window",
        probeRefs: observed.map((entry) => entry.probeRef),
        provenance: { source: "living-field-selection", selectionContract: SELECTION_CONTRACT },
      });
      this.status = "selection-rejected";
      return this.snapshot();
    }

    this.selection = new SelectionDecision({
      status: "retain",
      candidateRef: candidate.candidateRef,
      basis: "candidate improved the selected unresolved prediction dimension across all finite shadow Probe windows",
      probeRefs: observed.map((entry) => entry.probeRef),
      provenance: {
        source: "living-field-selection",
        selectionContract: SELECTION_CONTRACT,
        scope: "selected-prediction-dimension-only",
      },
    });
    this.reconstructedModel = reconstructSelected(
      this.model,
      candidate,
      this.selection,
      this.handoff,
      observed,
    );
    this.status = "reconstructed-proposal-ready";
    return this.snapshot();
  }

  snapshot() {
    return Object.freeze({
      status: this.status,
      subjectRef: this.model.subjectRef,
      modelRef: this.model.modelRef,
      candidates: this.candidates,
      probeWindows: this.probeWindows,
      probeResults: frozenArray(this.probeResults),
      selection: this.selection,
      reconstructedModel: this.reconstructedModel,
      authority: "T1-read-only-until-apply",
    });
  }
}

export function applyReconstructedFiniteModel(
  agent,
  reconstructedModel,
  { applier, tick = null, provenance = {} } = {},
) {
  if (!(reconstructedModel instanceof ReconstructedFiniteModel)) {
    throw new Error("apply requires a ReconstructedFiniteModel");
  }
  if (!agent || agent.focusKey !== reconstructedModel.agentRef) {
    throw new Error("reconstructed model agentRef does not match the live agent");
  }
  if (reconstructedModel.selection.status !== "retain") {
    throw new Error("only retained reconstruction may be applied");
  }
  const applierId = nonEmpty(applier);
  if (!applierId) throw new Error("reconstruction apply requires applier");

  for (const [key, value] of Object.entries(reconstructedModel.parameters)) {
    if (!Number.isFinite(value)) throw new Error(`reconstructed parameter is non-finite: ${key}`);
    setAgentParameter(agent, key, value);
  }
  for (const operation of reconstructedModel.operations) applyMemoryOperation(agent, operation);

  return Object.freeze({
    status: "M_B-prime-applied",
    modelRef: reconstructedModel.modelRef,
    previousModelRef: reconstructedModel.previousModelRef,
    subjectRef: reconstructedModel.subjectRef,
    agentRef: reconstructedModel.agentRef,
    tick,
    applier: applierId,
    xiStatus: reconstructedModel.xiStatus,
    reentryRequired: true,
    provenance: frozenObject({
      ...provenance,
      source: nonEmpty(provenance.source) || "living-field-canonical-authority",
      reconstructionContract: reconstructedModel.contract,
    }),
  });
}
