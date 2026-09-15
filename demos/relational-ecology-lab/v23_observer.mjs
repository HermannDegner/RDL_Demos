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
    this.provenance = provenance ? frozenObject(provenance) : null;
    Object.freeze(this);
  }

  get magnitude() {
    return this.residual ? maxMagnitude(this.residual) : null;
  }

  get resolvesObservedDifference() {
    return this.status === "prediction-matched-observation";
  }
}

export class LivingFieldObserver {
  constructor({ agentRef, dimensions }) {
    this.agentRef = agentRef;
    this.dimensions = Object.freeze([...dimensions]);
    this.previous = null;
    this.predictionWindow = null;
    this.latest = null;
    this.samples = 0;
    this.comparisons = 0;
    this.missing = 0;
    this.assessmentCounts = {};
    this.predictionChecks = 0;
    this.predictionEvidenceCounts = {};
  }

  beginPredictionWindow({ tick, prediction, reliability }) {
    const missingDimensions = this.dimensions.filter(
      (key) => !Number.isFinite(prediction?.[key]) || !Number.isFinite(reliability?.[key]),
    );
    if (missingDimensions.length > 0) {
      this.predictionWindow = Object.freeze({
        status: "not-formed-missing-prediction",
        tick,
        missingDimensions: Object.freeze([...missingDimensions]),
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
    const status = maxMagnitude(residual) === 0
      ? "prediction-matched-observation"
      : "prediction-residual-present";
    const evidence = new PredictionAssessmentEvidence({
      status,
      modelRef: window.modelRef,
      prediction: window.prediction,
      observed,
      coefficients: window.coefficients,
      weightedPrediction,
      weightedObserved,
      residual,
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
      latest: this.latest,
    });
  }
}
