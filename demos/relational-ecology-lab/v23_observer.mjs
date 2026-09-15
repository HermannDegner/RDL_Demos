// Read-only, opt-in comparison of normalized decision-window observations.
// This finite reliability-weighted evaluator is NOT the full agent policy.
// Temporal differences require explicit assessment before they can be treated
// as unresolved mismatch; no assessment in this module mutates action policy.
import {
  BoundaryContext,
  acquireInteractionSection,
  assessMismatch,
  compareInterpretations,
  interpretSection,
} from "./v23_state.mjs";

function frozenObject(value = {}) {
  return Object.freeze({ ...value });
}

function maxMagnitude(values = {}) {
  return Math.max(0, ...Object.values(values).map((value) => Math.abs(Number(value) || 0)));
}

// Demo-local audit contract mirroring the current bounded reliability updater.
// It is not a Core constant and must not be read as canonical absorption law.
const LOCAL_RELIABILITY_RATE = 0.035;
const LOCAL_RELIABILITY_MIN = 0.18;
const LOCAL_RELIABILITY_MAX = 0.98;
const LOCAL_UPDATE_EPSILON = 1e-12;

function localReliabilityEnvelope(value) {
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

export class LocalAbsorptionAttemptEvidence {
  constructor({
    status,
    beforeCoefficients = null,
    afterCoefficients = null,
    deltas = null,
    changedDimensions = [],
    confoundedDimensions = [],
    captureTick = null,
    planTick = null,
    provenance = null,
  }) {
    this.status = status;
    this.beforeCoefficients = beforeCoefficients ? frozenObject(beforeCoefficients) : null;
    this.afterCoefficients = afterCoefficients ? frozenObject(afterCoefficients) : null;
    this.deltas = deltas ? frozenObject(deltas) : null;
    this.changedDimensions = Object.freeze([...changedDimensions]);
    this.confoundedDimensions = Object.freeze([...confoundedDimensions]);
    this.captureTick = captureTick;
    this.planTick = planTick;
    this.provenance = provenance ? frozenObject(provenance) : null;
    Object.freeze(this);
  }

  get qualifiesAsFiniteAttempt() {
    return this.status === "bounded-local-adjustment-observed";
  }
}

export class PredictionAssessmentEvidence {
  constructor({
    status,
    modelRef,
    prediction = null,
    observed = null,
    coefficients = null,
    weightedPrediction = null,
    weightedObserved = null,
    residual = null,
    missingDimensions = [],
    localAbsorptionAttempt = null,
    provenance = null,
  }) {
    this.status = status;
    this.modelRef = modelRef ?? null;
    this.prediction = prediction ? frozenObject(prediction) : null;
    this.observed = observed ? frozenObject(observed) : null;
    this.coefficients = coefficients ? frozenObject(coefficients) : null;
    this.weightedPrediction = weightedPrediction ? frozenObject(weightedPrediction) : null;
    this.weightedObserved = weightedObserved ? frozenObject(weightedObserved) : null;
    this.residual = residual ? frozenObject(residual) : null;
    this.missingDimensions = Object.freeze([...missingDimensions]);
    this.localAbsorptionAttempt = localAbsorptionAttempt ?? null;
    this.provenance = provenance ? frozenObject(provenance) : null;
    Object.freeze(this);
  }

  get magnitude() {
    return this.residual ? maxMagnitude(this.residual) : null;
  }

  get resolvesObservedDifference() {
    return this.status === "prediction-matched-observation";
  }

  get residualAfterFiniteAbsorptionAttempt() {
    return this.status === "prediction-residual-after-bounded-local-adjustment";
  }
}

export class LivingFieldObserver {
  constructor({ agentRef, dimensions }) {
    this.agentRef = agentRef;
    this.dimensions = Object.freeze([...dimensions]);
    this.previous = null;
    this.predictionWindow = null;
    this.localUpdateBaseline = null;
    this.latest = null;
    this.samples = 0;
    this.comparisons = 0;
    this.missing = 0;
    this.assessmentCounts = {};
    this.predictionChecks = 0;
    this.predictionEvidenceCounts = {};
    this.localUpdateChecks = 0;
    this.localAbsorptionAttempts = 0;
    this.localUpdateEvidenceCounts = {};
  }

  inspectLocalUpdateTransition({ tick, reliability }) {
    const baseline = this.localUpdateBaseline;
    this.localUpdateBaseline = null;
    if (!baseline) return null;

    const missingDimensions = this.dimensions.filter(
      (key) => !Number.isFinite(baseline.coefficients?.[key]) || !Number.isFinite(reliability?.[key]),
    );
    if (missingDimensions.length > 0) {
      const evidence = new LocalAbsorptionAttemptEvidence({
        status: "not-formed-missing-local-coefficient",
        beforeCoefficients: baseline.coefficients,
        captureTick: baseline.tick,
        planTick: tick,
        confoundedDimensions: missingDimensions,
        provenance: {
          source: "reliability-transition-audit",
          agentRef: this.agentRef,
          auditContract: "bounded-reliability-step-v1",
        },
      });
      this.recordLocalUpdateEvidence(evidence);
      return evidence;
    }

    const afterCoefficients = Object.fromEntries(
      this.dimensions.map((key) => [key, reliability[key]]),
    );
    const deltas = {};
    const changedDimensions = [];
    const confoundedDimensions = [];
    for (const key of this.dimensions) {
      const before = baseline.coefficients[key];
      const after = afterCoefficients[key];
      const delta = after - before;
      deltas[key] = delta;
      if (Math.abs(delta) > LOCAL_UPDATE_EPSILON) changedDimensions.push(key);
      const envelope = localReliabilityEnvelope(before);
      if (
        after < envelope.minimum - LOCAL_UPDATE_EPSILON
        || after > envelope.maximum + LOCAL_UPDATE_EPSILON
      ) {
        confoundedDimensions.push(key);
      }
    }

    let status = "no-observed-local-adjustment";
    if (confoundedDimensions.length > 0) status = "confounded-structural-change";
    else if (changedDimensions.length > 0) status = "bounded-local-adjustment-observed";

    const evidence = new LocalAbsorptionAttemptEvidence({
      status,
      beforeCoefficients: baseline.coefficients,
      afterCoefficients,
      deltas,
      changedDimensions,
      confoundedDimensions,
      captureTick: baseline.tick,
      planTick: tick,
      provenance: {
        source: "reliability-transition-audit",
        agentRef: this.agentRef,
        auditContract: "bounded-reliability-step-v1",
      },
    });
    this.recordLocalUpdateEvidence(evidence);
    return evidence;
  }

  recordLocalUpdateEvidence(evidence) {
    this.localUpdateChecks += 1;
    this.localUpdateEvidenceCounts[evidence.status] =
      (this.localUpdateEvidenceCounts[evidence.status] ?? 0) + 1;
    if (evidence.qualifiesAsFiniteAttempt) this.localAbsorptionAttempts += 1;
  }

  beginPredictionWindow({ tick, prediction, reliability }) {
    const localAbsorptionAttempt = this.inspectLocalUpdateTransition({ tick, reliability });
    const missingDimensions = this.dimensions.filter(
      (key) => !Number.isFinite(prediction?.[key]) || !Number.isFinite(reliability?.[key]),
    );
    if (missingDimensions.length > 0) {
      this.predictionWindow = Object.freeze({
        status: "not-formed-missing-prediction",
        tick,
        missingDimensions: Object.freeze([...missingDimensions]),
        localAbsorptionAttempt,
      });
      return this.predictionWindow;
    }

    const copiedPrediction = Object.fromEntries(
      this.dimensions.map((key) => [key, prediction[key]]),
    );
    const copiedCoefficients = Object.fromEntries(
      this.dimensions.map((key) => [key, reliability[key]]),
    );
    this.predictionWindow = Object.freeze({
      status: "ready",
      tick,
      prediction: frozenObject(copiedPrediction),
      coefficients: frozenObject(copiedCoefficients),
      modelRef: `${this.agentRef}:prediction-window:${tick}`,
      localAbsorptionAttempt,
    });
    return this.predictionWindow;
  }

  inspectPredictionWindow({ tick, observed }) {
    const window = this.predictionWindow;
    this.predictionWindow = null;
    if (!window) return null;

    if (window.status !== "ready") {
      const evidence = new PredictionAssessmentEvidence({
        status: window.status,
        modelRef: null,
        missingDimensions: window.missingDimensions,
        localAbsorptionAttempt: window.localAbsorptionAttempt,
        provenance: {
          source: "decision.prediction-reacquired",
          agentRef: this.agentRef,
          predictionTick: window.tick,
          evaluationTick: tick,
        },
      });
      this.predictionChecks += 1;
      this.predictionEvidenceCounts[evidence.status] =
        (this.predictionEvidenceCounts[evidence.status] ?? 0) + 1;
      return evidence;
    }

    const missingDimensions = this.dimensions.filter((key) => !Number.isFinite(observed?.[key]));
    if (missingDimensions.length > 0) {
      const evidence = new PredictionAssessmentEvidence({
        status: "not-formed-missing-observation",
        modelRef: window.modelRef,
        prediction: window.prediction,
        coefficients: window.coefficients,
        missingDimensions,
        localAbsorptionAttempt: window.localAbsorptionAttempt,
        provenance: {
          source: "decision.prediction-reacquired",
          agentRef: this.agentRef,
          predictionTick: window.tick,
          evaluationTick: tick,
        },
      });
      this.predictionChecks += 1;
      this.predictionEvidenceCounts[evidence.status] =
        (this.predictionEvidenceCounts[evidence.status] ?? 0) + 1;
      return evidence;
    }

    const weightedPrediction = {};
    const weightedObserved = {};
    const residual = {};
    for (const key of this.dimensions) {
      weightedPrediction[key] = window.prediction[key] * window.coefficients[key];
      weightedObserved[key] = observed[key] * window.coefficients[key];
      residual[key] = Math.abs(weightedObserved[key] - weightedPrediction[key]);
    }
    let status = "prediction-residual-present";
    if (maxMagnitude(residual) === 0) {
      status = "prediction-matched-observation";
    } else if (window.localAbsorptionAttempt?.qualifiesAsFiniteAttempt) {
      status = "prediction-residual-after-bounded-local-adjustment";
    }
    const evidence = new PredictionAssessmentEvidence({
      status,
      modelRef: window.modelRef,
      prediction: window.prediction,
      observed,
      coefficients: window.coefficients,
      weightedPrediction,
      weightedObserved,
      residual,
      localAbsorptionAttempt: window.localAbsorptionAttempt,
      provenance: {
        source: "decision.prediction-reacquired",
        agentRef: this.agentRef,
        predictionTick: window.tick,
        evaluationTick: tick,
      },
    });
    this.predictionChecks += 1;
    this.predictionEvidenceCounts[evidence.status] =
      (this.predictionEvidenceCounts[evidence.status] ?? 0) + 1;
    return evidence;
  }

  capture({ tick, observed, reliability, assessment = null }) {
    const values = {};
    const coefficients = {};
    for (const key of this.dimensions) {
      if (!Number.isFinite(observed[key]) || !Number.isFinite(reliability[key])) {
        this.missing += 1;
        this.previous = null; // Do not bridge an unobserved window.
        this.localUpdateBaseline = null;
        const predictionEvidence = this.inspectPredictionWindow({ tick, observed });
        this.latest = Object.freeze({
          status: "not-formed-missing-observation",
          tick,
          predictionEvidence,
        });
        return this.latest;
      }
      values[key] = observed[key];
      coefficients[key] = reliability[key];
    }
    const section = acquireInteractionSection({
      sectionId: `${this.agentRef}:window:${tick}`,
      context: new BoundaryContext({
        boundaryId: `${this.agentRef}:normalized-window-v1`,
        purpose: "Compare reliability-weighted observed decision windows",
        question: "How did selected normalized observations change?",
        observationTime: String(tick),
        conditions: { dimensions: this.dimensions.join(",") },
      }),
      payload: values,
      provenance: { source: "evaluateDecision.observed", agentRef: this.agentRef, tick },
    });
    const frozenCoefficients = Object.freeze(coefficients);
    const modelRef = `${this.agentRef}:reliability:${tick}`;
    const predictionEvidence = this.inspectPredictionWindow({ tick, observed: values });
    this.samples += 1;
    if (this.previous) {
      const earlier = this.previous;
      const interpreter = (input) => Object.fromEntries(
        this.dimensions.map((key) => [key, input.payload[key] * earlier.coefficients[key]]),
      );
      const F = interpretSection(earlier.section, { modelRef: earlier.modelRef, interpreter });
      const FPrime = interpretSection(section, { modelRef: earlier.modelRef, interpreter });
      const E = compareInterpretations(F, FPrime);
      let assessmentInput = assessment ?? {};
      if (
        assessment == null
        && E.magnitude > 0
        && predictionEvidence?.resolvesObservedDifference
      ) {
        assessmentInput = {
          classification: "resolved-difference",
          basis: "reacquired prediction matched the later observed window under frozen finite coefficients",
          provenance: {
            source: "living-field-prediction-check",
            modelRef: predictionEvidence.modelRef,
          },
        };
      }
      const EAssessment = assessMismatch(E, assessmentInput);
      this.comparisons += 1;
      this.assessmentCounts[EAssessment.status] =
        (this.assessmentCounts[EAssessment.status] ?? 0) + 1;
      this.latest = Object.freeze({
        status: EAssessment.status,
        assessment: EAssessment,
        predictionEvidence,
        tick,
        earlierSection: earlier.section,
        laterSection: section,
        F,
        FPrime,
        E,
      });
    } else {
      this.latest = Object.freeze({
        status: "window-started",
        tick,
        section,
        predictionEvidence,
      });
    }
    this.previous = Object.freeze({ section, coefficients: frozenCoefficients, modelRef });
    this.localUpdateBaseline = Object.freeze({
      tick,
      coefficients: frozenCoefficients,
      modelRef,
    });
    return this.latest;
  }

  snapshot() {
    return Object.freeze({
      agentRef: this.agentRef,
      dimensions: this.dimensions,
      samples: this.samples,
      comparisons: this.comparisons,
      missing: this.missing,
      assessmentCounts: Object.freeze({ ...this.assessmentCounts }),
      predictionChecks: this.predictionChecks,
      predictionEvidenceCounts: Object.freeze({ ...this.predictionEvidenceCounts }),
      localUpdateChecks: this.localUpdateChecks,
      localAbsorptionAttempts: this.localAbsorptionAttempts,
      localUpdateEvidenceCounts: Object.freeze({ ...this.localUpdateEvidenceCounts }),
      latest: this.latest,
    });
  }
}
