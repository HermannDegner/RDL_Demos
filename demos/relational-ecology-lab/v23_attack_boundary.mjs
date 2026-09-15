// Attempt-specific Predator attack boundary for the Living Field v2.3 path.
//
// Unattempted attack is never encoded as zero failure. A finite attack section
// exists only after beginAttack() establishes an actual attempt. Outcomes keep
// contact / escape / obstacle / timeout distinctions in provenance. This is a
// separate B_attack from the general prey/motion observer boundary.
import {
  BoundaryContext,
  acquireInteractionSection,
  assessMismatch,
  compareInterpretations,
  interpretSection,
} from "./v23_state.mjs";
import {
  LocalAbsorptionAttemptEvidence,
  PredictionAssessmentEvidence,
} from "./v23_observer.mjs";

const LOCAL_RELIABILITY_RATE = 0.035;
const LOCAL_RELIABILITY_MIN = 0.18;
const LOCAL_RELIABILITY_MAX = 0.98;
const EPSILON = 1e-12;

function frozenObject(value = {}) {
  return Object.freeze({ ...value });
}

function attackEnvelope(value) {
  return Object.freeze({
    minimum: Math.max(
      LOCAL_RELIABILITY_MIN,
      value + (0 - value) * LOCAL_RELIABILITY_RATE,
    ),
    maximum: Math.min(
      LOCAL_RELIABILITY_MAX,
      value + (1 - value) * LOCAL_RELIABILITY_RATE,
    ),
  });
}

export class AttackAttemptObserver {
  constructor({ agentRef }) {
    this.agentRef = agentRef;
    this.activeAttempt = null;
    this.localUpdateBaseline = null;
    this.latest = null;
    this.attempts = 0;
    this.completed = 0;
    this.missing = 0;
    this.outcomeCounts = {};
    this.localUpdateEvidenceCounts = {};
  }

  context(tick, attemptRef) {
    return new BoundaryContext({
      boundaryId: `${this.agentRef}:attack-attempt-v1`,
      purpose: "Compare an actually attempted capture prediction with its finite outcome",
      question: "Did this attempted capture outcome match the frozen finite capture expectation?",
      observationTime: String(tick),
      conditions: {
        dimensions: "attack",
        attempted: "true",
        attemptRef,
      },
    });
  }

  inspectLocalUpdate({ tick, reliability }) {
    const baseline = this.localUpdateBaseline;
    this.localUpdateBaseline = null;
    if (!baseline) return null;
    if (!Number.isFinite(baseline.reliability) || !Number.isFinite(reliability)) {
      const evidence = new LocalAbsorptionAttemptEvidence({
        status: "not-formed-missing-local-coefficient",
        beforeCoefficients: Number.isFinite(baseline.reliability)
          ? { attack: baseline.reliability }
          : null,
        captureTick: baseline.tick,
        planTick: tick,
        confoundedDimensions: ["attack"],
        provenance: {
          source: "attack-reliability-transition-audit",
          agentRef: this.agentRef,
          auditContract: "bounded-attack-reliability-step-v1",
        },
      });
      this.recordLocalUpdate(evidence);
      return evidence;
    }

    const before = baseline.reliability;
    const after = reliability;
    const envelope = attackEnvelope(before);
    const delta = after - before;
    let status = "no-observed-local-adjustment";
    let confoundedDimensions = [];
    let changedDimensions = [];
    if (after < envelope.minimum - EPSILON || after > envelope.maximum + EPSILON) {
      status = "confounded-structural-change";
      confoundedDimensions = ["attack"];
    } else if (Math.abs(delta) > EPSILON) {
      status = "bounded-local-adjustment-observed";
      changedDimensions = ["attack"];
    }
    const evidence = new LocalAbsorptionAttemptEvidence({
      status,
      beforeCoefficients: { attack: before },
      afterCoefficients: { attack: after },
      deltas: { attack: delta },
      changedDimensions,
      confoundedDimensions,
      captureTick: baseline.tick,
      planTick: tick,
      provenance: {
        source: "attack-reliability-transition-audit",
        agentRef: this.agentRef,
        auditContract: "bounded-attack-reliability-step-v1",
      },
    });
    this.recordLocalUpdate(evidence);
    return evidence;
  }

  recordLocalUpdate(evidence) {
    this.localUpdateEvidenceCounts[evidence.status] =
      (this.localUpdateEvidenceCounts[evidence.status] ?? 0) + 1;
  }

  beginAttempt({ tick, targetId, prediction, reliability }) {
    if (!Number.isFinite(prediction) || !Number.isFinite(reliability)) {
      this.missing += 1;
      this.activeAttempt = null;
      this.latest = Object.freeze({
        status: "not-formed-missing-attack-prediction",
        tick,
        attempted: true,
        targetId: targetId ?? null,
      });
      return this.latest;
    }
    const attemptRef = `${this.agentRef}:attack:${this.attempts + 1}:${tick}`;
    const context = this.context(tick, attemptRef);
    const section = acquireInteractionSection({
      sectionId: `${attemptRef}:prediction`,
      context,
      payload: { attack: prediction },
      role: "attempt-prediction",
      provenance: {
        source: "predator.beginAttack.decision.prediction.attack",
        agentRef: this.agentRef,
        tick,
        targetId: targetId ?? null,
        attempted: true,
      },
    });
    const localAbsorptionAttempt = this.inspectLocalUpdate({ tick, reliability });
    this.activeAttempt = Object.freeze({
      attemptRef,
      tick,
      targetId: targetId ?? null,
      prediction,
      reliability,
      section,
      modelRef: `${this.agentRef}:attack-reliability:${tick}`,
      localAbsorptionAttempt,
    });
    this.attempts += 1;
    this.latest = Object.freeze({
      status: "attack-attempt-started",
      tick,
      attemptRef,
      attempted: true,
      targetId: targetId ?? null,
      localAbsorptionAttempt,
    });
    return this.latest;
  }

  resolveAttempt({
    tick,
    success,
    outcome,
    contact = false,
    escaped = false,
    obstacle = false,
    reliability,
    targetId = null,
  }) {
    const attempt = this.activeAttempt;
    this.activeAttempt = null;
    if (!attempt) return null;
    if (typeof success !== "boolean" || !Number.isFinite(reliability)) {
      this.missing += 1;
      this.latest = Object.freeze({
        status: "not-formed-missing-attack-outcome",
        tick,
        attemptRef: attempt.attemptRef,
        attempted: true,
      });
      return this.latest;
    }

    const observed = success ? 1 : 0;
    const laterSection = acquireInteractionSection({
      sectionId: `${attempt.attemptRef}:outcome`,
      context: attempt.section.context,
      payload: { attack: observed },
      role: "attempt-outcome",
      provenance: {
        source: "predator.attack-outcome",
        agentRef: this.agentRef,
        tick,
        attempted: true,
        success,
        outcome,
        contact: Boolean(contact),
        escaped: Boolean(escaped),
        obstacle: Boolean(obstacle),
        targetId: targetId ?? attempt.targetId,
      },
    });
    const interpreter = (input) => ({
      attack: input.payload.attack * attempt.reliability,
    });
    const F = interpretSection(attempt.section, {
      modelRef: attempt.modelRef,
      interpreter,
    });
    const FPrime = interpretSection(laterSection, {
      modelRef: attempt.modelRef,
      interpreter,
    });
    const E = compareInterpretations(F, FPrime);
    const weightedPrediction = { attack: F.values.attack };
    const weightedObserved = { attack: FPrime.values.attack };
    const residual = { attack: E.values.attack };
    let evidenceStatus = E.magnitude === 0
      ? "prediction-matched-observation"
      : "prediction-residual-present";
    if (
      E.magnitude > 0
      && attempt.localAbsorptionAttempt?.qualifiesAsFiniteAttempt
    ) {
      evidenceStatus = "prediction-residual-after-bounded-local-adjustment";
    }
    const predictionEvidence = new PredictionAssessmentEvidence({
      status: evidenceStatus,
      modelRef: attempt.modelRef,
      prediction: { attack: attempt.prediction },
      observed: { attack: observed },
      coefficients: { attack: attempt.reliability },
      weightedPrediction,
      weightedObserved,
      residual,
      localAbsorptionAttempt: attempt.localAbsorptionAttempt,
      provenance: {
        source: "living-field-attack-attempt-check",
        agentRef: this.agentRef,
        predictionTick: attempt.tick,
        evaluationTick: tick,
        attemptRef: attempt.attemptRef,
        outcome,
        attempted: true,
        contact: Boolean(contact),
        escaped: Boolean(escaped),
        obstacle: Boolean(obstacle),
      },
    });
    const assessment = assessMismatch(E);
    const result = Object.freeze({
      status: assessment.status,
      assessment,
      predictionEvidence,
      tick,
      attempted: true,
      attemptRef: attempt.attemptRef,
      targetId: targetId ?? attempt.targetId,
      outcome,
      success,
      contact: Boolean(contact),
      escaped: Boolean(escaped),
      obstacle: Boolean(obstacle),
      earlierSection: attempt.section,
      laterSection,
      F,
      FPrime,
      E,
    });
    this.latest = result;
    this.completed += 1;
    this.outcomeCounts[outcome] = (this.outcomeCounts[outcome] ?? 0) + 1;
    this.localUpdateBaseline = Object.freeze({ tick, reliability });
    return result;
  }

  snapshot() {
    return Object.freeze({
      agentRef: this.agentRef,
      boundaryId: `${this.agentRef}:attack-attempt-v1`,
      attempts: this.attempts,
      completed: this.completed,
      missing: this.missing,
      outcomeCounts: frozenObject(this.outcomeCounts),
      localUpdateEvidenceCounts: frozenObject(this.localUpdateEvidenceCounts),
      activeAttempt: this.activeAttempt,
      latest: this.latest,
      unattemptedIsFailureZero: false,
    });
  }
}

function resolveObservedAttack(predator, event, tick) {
  if (!event || !predator.v23AttackObserver) return;
  if (event.type === "capture") {
    predator.v23AttackObserver.resolveAttempt({
      tick,
      success: true,
      outcome: "capture-success",
      contact: true,
      escaped: false,
      obstacle: false,
      reliability: predator.reliability.attack,
      targetId: event.targetId,
    });
  } else if (event.type === "attack-escaped") {
    predator.v23AttackObserver.resolveAttempt({
      tick,
      success: false,
      outcome: "contact-escape",
      contact: true,
      escaped: true,
      obstacle: false,
      reliability: predator.reliability.attack,
      targetId: event.targetId,
    });
  } else if (event.type === "attack-obstacle") {
    predator.v23AttackObserver.resolveAttempt({
      tick,
      success: false,
      outcome: "obstacle-failure",
      contact: false,
      escaped: false,
      obstacle: true,
      reliability: predator.reliability.attack,
      targetId: event.targetId,
    });
  } else if (event.type === "attack-miss") {
    predator.v23AttackObserver.resolveAttempt({
      tick,
      success: false,
      outcome: "timeout-or-range-failure",
      contact: false,
      escaped: false,
      obstacle: false,
      reliability: predator.reliability.attack,
      targetId: event.targetId,
    });
  }
}

export function installAttackAttemptInstrumentation(predator) {
  if (!predator || predator.profile?.kind !== "predator") {
    throw new Error("attack attempt instrumentation requires the Living Field predator");
  }
  if (predator.v23AttackInstrumentationInstalled) return predator.v23AttackObserver;

  predator.v23AttackObserver = new AttackAttemptObserver({ agentRef: predator.focusKey });
  const originalBeginAttack = predator.beginAttack.bind(predator);
  const originalUpdate = predator.update.bind(predator);
  const originalResolveAttack = predator.resolveAttack.bind(predator);

  predator.beginAttack = (target, tick = 0) => {
    const event = originalBeginAttack(target, tick);
    predator.v23AttackObserver.beginAttempt({
      tick,
      targetId: target?.id ?? predator.targetId,
      prediction: predator.decision?.prediction?.attack,
      reliability: predator.reliability.attack,
    });
    return event;
  };

  predator.update = (...args) => {
    const event = originalUpdate(...args);
    const tick = args[3] ?? 0;
    if (event?.type === "attack-obstacle" || event?.type === "attack-miss") {
      resolveObservedAttack(predator, event, tick);
    }
    return event;
  };

  predator.resolveAttack = (...args) => {
    const event = originalResolveAttack(...args);
    const tick = args[2] ?? 0;
    if (event?.type === "capture" || event?.type === "attack-escaped") {
      resolveObservedAttack(predator, event, tick);
    }
    return event;
  };

  predator.v23AttackInstrumentationInstalled = true;
  return predator.v23AttackObserver;
}
