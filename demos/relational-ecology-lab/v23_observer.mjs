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

export class LivingFieldObserver {
  constructor({ agentRef, dimensions }) {
    this.agentRef = agentRef;
    this.dimensions = Object.freeze([...dimensions]);
    this.previous = null;
    this.latest = null;
    this.samples = 0;
    this.comparisons = 0;
    this.missing = 0;
    this.assessmentCounts = {};
  }

  capture({ tick, observed, reliability, assessment = null }) {
    const values = {};
    const coefficients = {};
    for (const key of this.dimensions) {
      if (!Number.isFinite(observed[key]) || !Number.isFinite(reliability[key])) {
        this.missing += 1;
        this.previous = null; // Do not bridge an unobserved window.
        this.latest = Object.freeze({ status: "not-formed-missing-observation", tick });
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
    this.samples += 1;
    if (this.previous) {
      const earlier = this.previous;
      const interpreter = (input) => Object.fromEntries(
        this.dimensions.map((key) => [key, input.payload[key] * earlier.coefficients[key]]),
      );
      const F = interpretSection(earlier.section, { modelRef: earlier.modelRef, interpreter });
      const FPrime = interpretSection(section, { modelRef: earlier.modelRef, interpreter });
      const E = compareInterpretations(F, FPrime);
      const EAssessment = assessMismatch(E, assessment ?? {});
      this.comparisons += 1;
      this.assessmentCounts[EAssessment.status] =
        (this.assessmentCounts[EAssessment.status] ?? 0) + 1;
      this.latest = Object.freeze({
        status: EAssessment.status,
        assessment: EAssessment,
        tick,
        earlierSection: earlier.section,
        laterSection: section,
        F,
        FPrime,
        E,
      });
    } else {
      this.latest = Object.freeze({ status: "window-started", tick, section });
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
      latest: this.latest,
    });
  }
}
