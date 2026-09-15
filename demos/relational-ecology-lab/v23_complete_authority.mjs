// Complete opt-in Living Field v2.3 authority.
//
// The general Rabbit/Predator observer boundary is delegated to
// v23_canonical_authority.mjs. Predator attack is handled by a separate
// attempt-specific B_attack so an unattempted attack is never converted into a
// zero-valued failure. Both paths require explicit finite reviews before H.
import { installCanonicalLivingFieldAuthority } from "./v23_canonical_authority.mjs";
import { installAttackAttemptInstrumentation } from "./v23_attack_boundary.mjs";
import { LivingFieldHSidecar } from "./v23_h_sidecar.mjs";
import { reviewPostAdjustmentResidual } from "./v23_post_adjustment_review.mjs";
import { bindMDeltaSubject, requestMDelta } from "./v23_mdelta_request.mjs";

const EPSILON = 1e-12;

function nonEmpty(value) {
  return String(value ?? "").trim();
}

function frozenArray(values = []) {
  return Object.freeze([...values]);
}

function frozenObject(value = {}) {
  return Object.freeze({ ...value });
}

function attackTheta(options = {}) {
  if (Number.isFinite(options.attackTheta) && options.attackTheta >= 0) {
    return Number(options.attackTheta);
  }
  if (Number.isFinite(options.theta) && options.theta >= 0) return Number(options.theta);
  const configured = options.thetaByKind?.predator;
  if (Number.isFinite(configured) && configured >= 0) return Number(configured);
  throw new Error("complete Living Field authority requires explicit predator attack theta");
}

function attackModelParameters(predator) {
  return Object.freeze({
    "reliability.attack": predator.reliability.attack,
    "weights.attack": predator.weights.attack,
    attackLeadTicks: predator.attackLeadTicks,
    attackRangeFactor: predator.attackRangeFactor,
  });
}

function attackCandidate(model, requestRef) {
  const p = model.parameters;
  return Object.freeze({
    candidateRef: `${requestRef}:candidate:attack:phase-shift`,
    targetDimension: "attack",
    mode: "phase-shift",
    parameterPatch: Object.freeze({
      "reliability.attack": Math.max(0.18, Math.min(0.98, p["reliability.attack"] * 0.7)),
      attackLeadTicks: p.attackLeadTicks >= 5 ? 1.8 : Math.min(6, p.attackLeadTicks + 0.9),
      attackRangeFactor: Math.max(0.58, Math.min(1, p.attackRangeFactor * 0.88)),
    }),
    basis: "reduce confidence in the failing capture expectation and alter finite launch timing/range",
    validConditions: Object.freeze({
      boundaryId: model.context.boundaryId,
      purpose: model.context.purpose,
      dimensions: model.context.dimensions,
      probeScope: "attempted-capture-outcome-only",
    }),
    breakConditions: Object.freeze([
      "attack attempt probe stops improving",
      "attempt outcome coverage changes",
      "capture interaction regime changes",
    ]),
    authority: "candidate-only",
  });
}

function setAttackParameter(predator, key, value) {
  if (key === "reliability.attack") predator.reliability.attack = value;
  else if (key === "weights.attack") predator.weights.attack = value;
  else predator[key] = value;
}

class AttackFiniteModel {
  constructor({ modelRef, subjectRef, agentRef, context, parameters, basis, provenance }) {
    this.modelRef = modelRef;
    this.subjectRef = subjectRef;
    this.agentRef = agentRef;
    this.species = "predator";
    this.context = frozenObject(context);
    this.parameters = frozenObject(parameters);
    this.basis = basis;
    this.xiStatus = "unrecovered-relations-remain";
    this.provenance = frozenObject(provenance);
    Object.freeze(this);
  }
}

class AttackProbeResult {
  constructor({ probeRef, evaluationTick, baselineWeightedResidual, candidateWeightedResidual, improvement, status, provenance }) {
    this.probeRef = probeRef;
    this.targetDimension = "attack";
    this.evaluationTick = evaluationTick;
    this.baselineWeightedResidual = baselineWeightedResidual;
    this.candidateWeightedResidual = candidateWeightedResidual;
    this.improvement = improvement;
    this.status = status;
    this.provenance = frozenObject(provenance);
    Object.freeze(this);
  }
}

class AttackSelectionDecision {
  constructor({ status, candidateRef = null, basis, probeRefs = [], provenance = {} }) {
    if (!["retain", "reject", "defer"].includes(status)) {
      throw new Error(`unknown attack Selection status: ${status}`);
    }
    this.status = status;
    this.candidateRef = candidateRef;
    this.basis = basis;
    this.probeRefs = frozenArray(probeRefs);
    this.provenance = frozenObject(provenance);
    Object.freeze(this);
  }
}

class AttackReconstructedFiniteModel {
  constructor({ modelRef, previousModelRef, subjectRef, agentRef, context, parameters, selection, validConditions, breakConditions, provenance }) {
    this.modelRef = modelRef;
    this.previousModelRef = previousModelRef;
    this.subjectRef = subjectRef;
    this.agentRef = agentRef;
    this.species = "predator";
    this.context = frozenObject(context);
    this.parameters = frozenObject(parameters);
    this.selection = selection;
    this.validConditions = frozenObject(validConditions);
    this.breakConditions = frozenArray(breakConditions);
    this.unresolvedItems = frozenArray([
      "unattempted attack states remain outside B_attack",
      "future capture interactions remain open to unrecovered relations",
    ]);
    this.xiStatus = "unrecovered-relations-remain";
    this.reentryRequired = true;
    this.authority = "reconstruction-proposal";
    this.provenance = frozenObject(provenance);
    Object.freeze(this);
  }
}

function captureAttackFiniteModel(handoff, predator, cycle) {
  if (predator.profile?.kind !== "predator") throw new Error("attack reconstruction requires predator");
  if (!String(handoff.request.context.boundaryId ?? "").startsWith(`${predator.focusKey}:attack-attempt`)) {
    throw new Error("attack T1 handoff must originate from B_attack");
  }
  return new AttackFiniteModel({
    modelRef: `${predator.focusKey}:attack-M_B:${cycle}:pre-reconstruction`,
    subjectRef: handoff.subjectRef,
    agentRef: predator.focusKey,
    context: handoff.request.context,
    parameters: attackModelParameters(predator),
    basis: "capture finite predator attack parameters at M_delta entry",
    provenance: {
      source: "living-field-attack-finite-model",
      requestRef: handoff.request.requestRef,
    },
  });
}

function probeAttackCandidate(candidate, model, evidence, probeRef) {
  const prediction = evidence?.prediction?.attack;
  const observed = evidence?.observed?.attack;
  const baselineCoefficient = evidence?.coefficients?.attack;
  const candidateCoefficient = candidate.parameterPatch["reliability.attack"];
  if (![prediction, observed, baselineCoefficient, candidateCoefficient].every(Number.isFinite)) {
    return new AttackProbeResult({
      probeRef,
      evaluationTick: evidence?.provenance?.evaluationTick ?? null,
      baselineWeightedResidual: null,
      candidateWeightedResidual: null,
      improvement: null,
      status: "not-observed",
      provenance: {
        source: "living-field-attack-shadow-probe",
        reason: "finite attempted-capture evidence missing",
      },
    });
  }
  const rawResidual = Math.abs(observed - prediction);
  const baselineWeightedResidual = rawResidual * baselineCoefficient;
  const candidateWeightedResidual = rawResidual * candidateCoefficient;
  const improvement = baselineWeightedResidual - candidateWeightedResidual;
  return new AttackProbeResult({
    probeRef,
    evaluationTick: evidence.provenance?.evaluationTick ?? null,
    baselineWeightedResidual,
    candidateWeightedResidual,
    improvement,
    status: improvement > EPSILON ? "improved" : "not-improved",
    provenance: {
      source: "living-field-attack-shadow-probe",
      attemptRef: evidence.provenance?.attemptRef ?? null,
      outcome: evidence.provenance?.outcome ?? null,
      attempted: true,
      probeScope: "attempted-capture-outcome-only",
    },
  });
}

class AttackT1Session {
  constructor({ handoff, model, probeWindows, minimumEvaluationTick }) {
    this.handoff = handoff;
    this.model = model;
    this.probeWindows = probeWindows;
    this.minimumEvaluationTick = minimumEvaluationTick;
    this.candidate = attackCandidate(model, handoff.request.requestRef);
    this.probeResults = [];
    this.seen = new Set();
    this.selection = null;
    this.reconstructedModel = null;
    this.status = "probing";
  }

  observe(evidence) {
    if (this.status !== "probing" || !evidence) return this.snapshot();
    const tick = Number(evidence.provenance?.evaluationTick);
    if (!Number.isFinite(tick) || tick <= this.minimumEvaluationTick) return this.snapshot();
    const key = `${evidence.provenance?.attemptRef ?? evidence.modelRef}:${tick}`;
    if (this.seen.has(key)) return this.snapshot();
    this.seen.add(key);
    const result = probeAttackCandidate(
      this.candidate,
      this.model,
      evidence,
      `${this.handoff.request.requestRef}:attack-probe:${tick}`,
    );
    this.probeResults.push(result);
    if (this.probeResults.length < this.probeWindows) return this.snapshot();

    const observed = this.probeResults.filter((entry) => entry.status !== "not-observed");
    if (observed.length < this.probeWindows) {
      this.selection = new AttackSelectionDecision({
        status: "defer",
        basis: "attempt-specific finite Probe coverage was insufficient",
        probeRefs: this.probeResults.map((entry) => entry.probeRef),
        provenance: { source: "living-field-attack-selection" },
      });
      this.status = "selection-deferred";
      return this.snapshot();
    }
    if (!observed.every((entry) => entry.status === "improved")) {
      this.selection = new AttackSelectionDecision({
        status: "reject",
        candidateRef: this.candidate.candidateRef,
        basis: "attack candidate failed to improve every finite attempted-outcome Probe",
        probeRefs: observed.map((entry) => entry.probeRef),
        provenance: { source: "living-field-attack-selection" },
      });
      this.status = "selection-rejected";
      return this.snapshot();
    }

    this.selection = new AttackSelectionDecision({
      status: "retain",
      candidateRef: this.candidate.candidateRef,
      basis: "attack candidate improved every finite attempted-outcome Probe window",
      probeRefs: observed.map((entry) => entry.probeRef),
      provenance: {
        source: "living-field-attack-selection",
        scope: "attempted-capture-outcome-only",
      },
    });
    this.reconstructedModel = new AttackReconstructedFiniteModel({
      modelRef: `${this.model.modelRef}:M_B-prime:attack`,
      previousModelRef: this.model.modelRef,
      subjectRef: this.model.subjectRef,
      agentRef: this.model.agentRef,
      context: this.model.context,
      parameters: { ...this.model.parameters, ...this.candidate.parameterPatch },
      selection: this.selection,
      validConditions: this.candidate.validConditions,
      breakConditions: this.candidate.breakConditions,
      provenance: {
        source: "living-field-attack-reconstruction",
        requestRef: this.handoff.request.requestRef,
        probeRefs: frozenArray(observed.map((entry) => entry.probeRef)),
      },
    });
    this.status = "reconstructed-proposal-ready";
    return this.snapshot();
  }

  snapshot() {
    return Object.freeze({
      status: this.status,
      candidate: this.candidate,
      probeResults: frozenArray(this.probeResults),
      selection: this.selection,
      reconstructedModel: this.reconstructedModel,
      authority: "T1-attack-read-only-until-apply",
    });
  }
}

function applyAttackReconstruction(predator, reconstructedModel, tick) {
  if (!(reconstructedModel instanceof AttackReconstructedFiniteModel)) {
    throw new Error("attack apply requires retained reconstructed model");
  }
  if (reconstructedModel.selection.status !== "retain") throw new Error("attack reconstruction is not retained");
  for (const [key, value] of Object.entries(reconstructedModel.parameters)) {
    if (!Number.isFinite(value)) throw new Error(`non-finite attack reconstructed parameter: ${key}`);
    setAttackParameter(predator, key, value);
  }
  return Object.freeze({
    status: "M_B-prime-applied",
    modelRef: reconstructedModel.modelRef,
    previousModelRef: reconstructedModel.previousModelRef,
    agentRef: predator.focusKey,
    tick,
    boundaryId: reconstructedModel.context.boundaryId,
    xiStatus: reconstructedModel.xiStatus,
    reentryRequired: true,
    provenance: Object.freeze({ source: "living-field-complete-authority:B_attack" }),
  });
}

class AttackCanonicalController {
  constructor({ predator, theta, probeWindows = 2, reentryValidationWindows = 2 }) {
    this.predator = predator;
    this.theta = theta;
    this.probeWindows = probeWindows;
    this.reentryValidationWindows = reentryValidationWindows;
    this.sidecar = new LivingFieldHSidecar({ theta });
    this.completedReviews = [];
    this.unresolvedReviews = [];
    this.session = null;
    this.handoff = null;
    this.model = null;
    this.phase = "cruising";
    this.completedCycles = 0;
    this.lastSelection = null;
    this.lastReconstruction = null;
    this.lastApplyAudit = null;
    this.reentry = null;
    this.lastObservedReentryAttemptRef = null;
  }

  reviewLatest(input = {}) {
    const comparison = this.predator.v23AttackObserver?.latest;
    const review = reviewPostAdjustmentResidual(comparison, input);
    this.completedReviews.push(review);
    this.sidecar.observeReview(review);
    if (review.eligibleForLivingFieldH) this.unresolvedReviews.push(review);
    this.recordReentryReview(comparison?.attemptRef, review);
    if (this.sidecar.shouldReconstruct && !this.session) {
      this.beginCycle(comparison?.tick ?? null);
    }
    return review;
  }

  beginCycle(triggerTick) {
    const cycle = this.completedCycles + 1;
    const request = requestMDelta(this.sidecar, {
      reviews: this.unresolvedReviews,
      requestRef: `${this.predator.focusKey}:attack-m-delta:${cycle}`,
      requester: "living-field-complete-authority:B_attack",
      basis: "reviewed attempted-capture mismatch reached explicit B_attack theta",
      provenance: { source: "living-field-complete-authority:B_attack", triggerTick },
    });
    this.handoff = bindMDeltaSubject(request, {
      subjectRef: `${this.predator.focusKey}:current-M_B:attack:${cycle}`,
      basis: "bind current predator attack finite structure as SILN_SELF",
      binder: "living-field-complete-authority:B_attack",
    });
    this.model = captureAttackFiniteModel(this.handoff, this.predator, cycle);
    this.session = new AttackT1Session({
      handoff: this.handoff,
      model: this.model,
      probeWindows: this.probeWindows,
      minimumEvaluationTick: triggerTick,
    });
    this.phase = "M_delta-probing";
    this.predator.log(
      triggerTick ?? 0,
      "m-delta-attack",
      "Canonical B_attack M_Δ: 捕食モデル再編へ",
      `H ${request.H.toFixed(2)} / θ ${request.theta.toFixed(2)}`,
    );
  }

  onReplan(tick) {
    this.observeReentryAttempt();
    if (!this.session || this.session.status !== "probing") return null;
    this.session.observe(this.predator.v23AttackObserver?.latest?.predictionEvidence ?? null);
    if (this.session.status === "reconstructed-proposal-ready") {
      return this.apply(tick);
    }
    if (this.session.selection?.status === "reject" || this.session.selection?.status === "defer") {
      this.lastSelection = this.session.selection;
      this.phase = `M_delta-${this.session.selection.status}`;
      this.predator.log(
        tick,
        "m-delta-attack-selection",
        `Canonical B_attack Selection: ${this.session.selection.status}`,
        this.session.selection.basis,
      );
    }
    return null;
  }

  apply(tick) {
    const reconstructed = this.session?.reconstructedModel;
    if (!reconstructed) throw new Error("no retained attack reconstruction is ready");
    const audit = applyAttackReconstruction(this.predator, reconstructed, tick);
    this.completedCycles += 1;
    this.lastSelection = this.session.selection;
    this.lastReconstruction = reconstructed;
    this.lastApplyAudit = audit;
    this.predator.leapCount += 1;
    this.predator.leapPulse = 34;
    this.predator.log(
      tick,
      "canonical-attack-reconstruction",
      "Canonical B_attack M_B' 定着",
      `${reconstructed.selection.candidateRef} / attempt-specific Selection=retain`,
    );

    this.predator.v23AttackObserver = installAttackAttemptInstrumentation(this.predator);
    // installAttackAttemptInstrumentation is idempotent; replace the observer so
    // no pre-reconstruction attempt comparison crosses the new M_B' boundary.
    const ObserverCtor = this.predator.v23AttackObserver.constructor;
    this.predator.v23AttackObserver = new ObserverCtor({ agentRef: this.predator.focusKey });
    this.sidecar = new LivingFieldHSidecar({ theta: this.theta });
    this.completedReviews = [];
    this.unresolvedReviews = [];
    this.session = null;
    this.handoff = null;
    this.model = null;
    this.phase = "reentry-validation";
    this.reentry = {
      modelRef: reconstructed.modelRef,
      startedTick: tick,
      cleanAttempts: 0,
      requiredAttempts: this.reentryValidationWindows,
      reviewedAttemptRefs: new Set(),
      status: "pending",
      completion: null,
    };
    this.lastObservedReentryAttemptRef = null;
    return audit;
  }

  observeReentryAttempt() {
    if (!this.reentry || this.reentry.status !== "pending") return;
    const latest = this.predator.v23AttackObserver?.latest;
    if (!latest?.E || !latest.attemptRef) return;
    if (latest.tick <= this.reentry.startedTick) return;
    if (this.lastObservedReentryAttemptRef === latest.attemptRef) return;
    if (this.reentry.reviewedAttemptRefs.has(latest.attemptRef)) return;
    this.lastObservedReentryAttemptRef = latest.attemptRef;
    if (latest.status === "zero-difference" || latest.status === "resolved-difference") {
      this.reentry.cleanAttempts += 1;
    }
  }

  recordReentryReview(attemptRef, review) {
    if (!this.reentry || this.reentry.status !== "pending" || !attemptRef) return;
    if (this.reentry.reviewedAttemptRefs.has(attemptRef)) return;
    this.reentry.reviewedAttemptRefs.add(attemptRef);
    if (review.eligibleForLivingFieldH) this.reentry.cleanAttempts = 0;
    else this.reentry.cleanAttempts += 1;
  }

  finalizeReentry({ basis, validator, evidenceRefs = [], provenance = {} } = {}) {
    if (!this.reentry || this.reentry.status !== "pending") {
      throw new Error("no pending B_attack re-entry validation exists");
    }
    if (this.sidecar.shouldReconstruct || this.sidecar.H >= this.sidecar.theta) {
      throw new Error("cannot finalize B_attack re-entry while H >= theta");
    }
    if (this.reentry.cleanAttempts < this.reentry.requiredAttempts) {
      throw new Error("B_attack re-entry requires more finite post-reconstruction attempts");
    }
    const finiteBasis = nonEmpty(basis);
    const validatorId = nonEmpty(validator);
    const refs = evidenceRefs.map(nonEmpty).filter(Boolean);
    if (!finiteBasis || !validatorId || refs.length === 0) {
      throw new Error("B_attack re-entry completion requires basis, validator, and finite evidenceRefs");
    }
    const completion = Object.freeze({
      status: "normal-operation-restored",
      boundaryId: `${this.predator.focusKey}:attack-attempt-v1`,
      modelRef: this.reentry.modelRef,
      basis: finiteBasis,
      validator: validatorId,
      evidenceRefs: frozenArray(refs),
      H: this.sidecar.H,
      theta: this.sidecar.theta,
      xiStatus: "unrecovered-relations-remain",
      provenance: frozenObject({
        ...provenance,
        source: nonEmpty(provenance.source) || "living-field-B_attack-reentry-validation",
      }),
    });
    this.reentry.status = "complete";
    this.reentry.completion = completion;
    this.phase = "cruising";
    return completion;
  }

  snapshot() {
    return Object.freeze({
      agentRef: this.predator.focusKey,
      boundaryId: `${this.predator.focusKey}:attack-attempt-v1`,
      authority: "canonical-v23-B_attack",
      phase: this.phase,
      H: this.sidecar.snapshot(),
      completedCycles: this.completedCycles,
      selection: this.lastSelection,
      reconstruction: this.lastReconstruction,
      applyAudit: this.lastApplyAudit,
      observer: this.predator.v23AttackObserver?.snapshot() ?? null,
      reentry: this.reentry
        ? Object.freeze({
          modelRef: this.reentry.modelRef,
          startedTick: this.reentry.startedTick,
          cleanAttempts: this.reentry.cleanAttempts,
          requiredAttempts: this.reentry.requiredAttempts,
          status: this.reentry.status,
          completion: this.reentry.completion,
        })
        : null,
      unattemptedIsFailureZero: false,
      legacyAttackLeapAuthority: false,
    });
  }
}

export class CompleteLivingFieldAuthority {
  constructor(simulation, options = {}) {
    if (!simulation?.observeV23) {
      throw new Error("complete Living Field authority requires Simulation({ observeV23: true })");
    }
    this.simulation = simulation;
    this.options = options;
    this.general = installCanonicalLivingFieldAuthority(simulation, options);
    this.attack = null;
    this.installAttackController();
    const generalEpisodeFactory = simulation.createEpisode.bind(simulation);
    simulation.createEpisode = (...args) => {
      const result = generalEpisodeFactory(...args);
      this.installAttackController();
      return result;
    };
    simulation.v23CompleteAuthority = this;
  }

  installAttackController() {
    const predator = this.simulation.predator;
    installAttackAttemptInstrumentation(predator);
    const generalMaybeLeap = predator.maybeLeap.bind(predator);
    const controller = new AttackCanonicalController({
      predator,
      theta: attackTheta(this.options),
      probeWindows: this.options.attackProbeWindows ?? this.options.probeWindows ?? 2,
      reentryValidationWindows:
        this.options.attackReentryValidationWindows
        ?? this.options.reentryValidationWindows
        ?? 2,
    });
    predator.maybeLeap = (tick) => {
      const generalResult = generalMaybeLeap(tick);
      const attackResult = controller.onReplan(tick);
      return attackResult ?? generalResult;
    };
    predator.v23AttackCanonicalController = controller;
    this.attack = controller;
  }

  review(agentRef, input) {
    return this.general.review(agentRef, input);
  }

  reviewAttack(input) {
    return this.attack.reviewLatest(input);
  }

  finalizeReentry(agentRef, input) {
    return this.general.finalizeReentry(agentRef, input);
  }

  finalizeAttackReentry(input) {
    return this.attack.finalizeReentry(input);
  }

  snapshot() {
    return Object.freeze({
      authority: "complete-canonical-v23",
      general: this.general.snapshot(),
      attack: this.attack.snapshot(),
      legacyGeneralLeapAuthority: false,
      legacyAttackLeapAuthority: false,
      legacyNumericXiIsCoreXi: false,
    });
  }
}

export function installCompleteLivingFieldAuthority(simulation, options = {}) {
  if (simulation?.v23CompleteAuthority || simulation?.v23CanonicalAuthority) {
    throw new Error("Living Field canonical authority is already installed");
  }
  return new CompleteLivingFieldAuthority(simulation, options);
}
