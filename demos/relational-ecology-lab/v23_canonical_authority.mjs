// Opt-in canonical Living Field authority.
//
// Installing this controller replaces each live agent's legacy maybeLeap
// authority with the reviewed v2.3 path. Historical H / xi / thetaEffective
// fields may continue to update for compatibility diagnostics, but they cannot
// trigger reconstruction while this authority is installed.
import { LivingFieldHSidecar } from "./v23_h_sidecar.mjs";
import { LivingFieldObserver } from "./v23_observer.mjs";
import { reviewPostAdjustmentResidual } from "./v23_post_adjustment_review.mjs";
import { bindMDeltaSubject, requestMDelta } from "./v23_mdelta_request.mjs";
import {
  T1ReconstructionSession,
  applyReconstructedFiniteModel,
  captureLivingFieldFiniteModel,
} from "./v23_t1_reconstruction.mjs";

function nonEmpty(value) {
  return String(value ?? "").trim();
}

function frozenArray(values = []) {
  return Object.freeze([...values]);
}

function frozenObject(value = {}) {
  return Object.freeze({ ...value });
}

function thetaFor(agent, { theta = null, thetaByKind = null } = {}) {
  if (Number.isFinite(theta) && theta >= 0) return Number(theta);
  const configured = thetaByKind?.[agent.profile?.kind];
  if (Number.isFinite(configured) && configured >= 0) return Number(configured);
  throw new Error(`canonical Living Field authority requires explicit theta for ${agent.profile?.kind}`);
}

export class CanonicalLivingFieldController {
  constructor({ agent, theta, probeWindows = 2, reentryValidationWindows = 2 }) {
    if (!agent?.v23Observer) {
      throw new Error("canonical Living Field controller requires an active v23 observer");
    }
    if (!Number.isFinite(theta) || theta < 0) throw new Error("canonical controller theta must be non-negative");
    if (!Number.isInteger(probeWindows) || probeWindows < 1) throw new Error("probeWindows must be positive");
    if (!Number.isInteger(reentryValidationWindows) || reentryValidationWindows < 1) {
      throw new Error("reentryValidationWindows must be positive");
    }
    this.agent = agent;
    this.theta = Number(theta);
    this.probeWindows = probeWindows;
    this.reentryValidationWindows = reentryValidationWindows;
    this.sidecar = new LivingFieldHSidecar({ theta: this.theta });
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
    this.lastObservedReentryTick = null;
    this.installed = false;
    this.originalMaybeLeap = null;
  }

  install() {
    if (this.installed) return this;
    this.originalMaybeLeap = this.agent.maybeLeap.bind(this.agent);
    this.agent.maybeLeap = (tick) => this.onReplan(tick);
    this.agent.v23CanonicalController = this;
    this.installed = true;
    return this;
  }

  reviewLatest({
    coverageDisposition,
    temporalDisposition,
    basis,
    reviewer,
    evidenceRefs = [],
    provenance = {},
  } = {}) {
    const comparison = this.agent.v23Observer?.latest;
    const review = reviewPostAdjustmentResidual(comparison, {
      coverageDisposition,
      temporalDisposition,
      basis,
      reviewer,
      evidenceRefs,
      provenance,
    });

    this.completedReviews.push(review);
    this.sidecar.observeReview(review);
    if (review.eligibleForLivingFieldH) this.unresolvedReviews.push(review);
    this.recordReentryReview(comparison?.tick, review);

    if (this.sidecar.shouldReconstruct && !this.session) {
      this.beginReconstructionCycle(comparison?.tick ?? null);
    }
    return review;
  }

  beginReconstructionCycle(triggerTick = null) {
    if (!this.sidecar.shouldReconstruct) {
      throw new Error("canonical reconstruction cycle requires H >= theta");
    }
    const cycle = this.completedCycles + 1;
    const request = requestMDelta(this.sidecar, {
      reviews: this.unresolvedReviews,
      requestRef: `${this.agent.focusKey}:m-delta:${cycle}`,
      requester: "living-field-canonical-authority",
      basis: "reviewed unresolved mismatch reached the explicit canonical theta",
      provenance: {
        source: "living-field-canonical-authority",
        triggerTick,
      },
    });
    this.handoff = bindMDeltaSubject(request, {
      subjectRef: `${this.agent.focusKey}:current-M_B:${cycle}`,
      basis: "bind the current live agent finite model as SILN_SELF for T1 reconstruction",
      binder: "living-field-canonical-authority",
      provenance: { source: "living-field-canonical-authority" },
    });
    this.model = captureLivingFieldFiniteModel(this.handoff, this.agent, {
      modelRef: `${this.agent.focusKey}:M_B:${cycle}:pre-reconstruction`,
      basis: "finite action-relevant model captured at M_delta entry",
      capturer: "living-field-canonical-authority",
      provenance: { source: "living-field-canonical-authority", triggerTick },
    });
    this.session = new T1ReconstructionSession({
      handoff: this.handoff,
      model: this.model,
      probeWindows: this.probeWindows,
      minimumEvaluationTick: triggerTick,
    });
    this.phase = this.session.status === "probing" ? "M_delta-probing" : "M_delta-deferred";
    this.agent.log(
      triggerTick ?? 0,
      "m-delta",
      "Canonical M_Δ: 再編相へ移行",
      `H ${request.H.toFixed(2)} / θ ${request.theta.toFixed(2)} / ${request.context.dimensions}`,
    );
    return this.session.snapshot();
  }

  onReplan(tick) {
    this.observeReentryComparison();
    if (!this.session || this.session.status !== "probing") return null;

    this.session.observeProbe(this.agent.v23Observer?.latest?.predictionEvidence ?? null);
    if (this.session.status === "reconstructed-proposal-ready") {
      return this.applySelectedReconstruction(tick);
    }
    if (this.session.selection?.status === "reject" || this.session.selection?.status === "defer") {
      this.lastSelection = this.session.selection;
      this.phase = `M_delta-${this.session.selection.status}`;
      this.agent.log(
        tick,
        "m-delta-selection",
        `Canonical Selection: ${this.session.selection.status}`,
        this.session.selection.basis,
      );
    }
    return null;
  }

  applySelectedReconstruction(tick) {
    const reconstructed = this.session?.reconstructedModel;
    if (!reconstructed) throw new Error("no retained reconstruction proposal is ready to apply");
    const dimensions = [...this.agent.v23Observer.dimensions];
    const audit = applyReconstructedFiniteModel(this.agent, reconstructed, {
      applier: "living-field-canonical-authority",
      tick,
      provenance: { source: "living-field-canonical-authority" },
    });

    this.completedCycles += 1;
    this.lastSelection = this.session.selection;
    this.lastReconstruction = reconstructed;
    this.lastApplyAudit = audit;
    this.agent.leapCount += 1; // compatibility/UI counter; not the authority source.
    this.agent.leapPulse = 34;
    this.agent.log(
      tick,
      "canonical-reconstruction",
      `Canonical M_B' 定着: ${reconstructed.selection.candidateRef}`,
      `T1 Selection=retain / ${reconstructed.validConditions.probeScope}`,
    );

    this.agent.v23Observer = new LivingFieldObserver({
      agentRef: this.agent.focusKey,
      dimensions,
    });
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
      cleanComparisons: 0,
      requiredComparisons: this.reentryValidationWindows,
      reviewedTicks: new Set(),
      status: "pending",
      completion: null,
    };
    this.lastObservedReentryTick = null;
    return audit;
  }

  observeReentryComparison() {
    if (!this.reentry || this.reentry.status !== "pending") return;
    const latest = this.agent.v23Observer?.latest;
    if (!latest?.E || !Number.isFinite(latest.tick) || latest.tick <= this.reentry.startedTick) return;
    if (this.lastObservedReentryTick === latest.tick) return;
    if (this.reentry.reviewedTicks.has(latest.tick)) return;
    this.lastObservedReentryTick = latest.tick;

    if (latest.status === "zero-difference" || latest.status === "resolved-difference") {
      this.reentry.cleanComparisons += 1;
    }
  }

  recordReentryReview(tick, review) {
    if (!this.reentry || this.reentry.status !== "pending" || !Number.isFinite(tick)) return;
    if (tick <= this.reentry.startedTick || this.reentry.reviewedTicks.has(tick)) return;
    this.reentry.reviewedTicks.add(tick);
    if (review.eligibleForLivingFieldH) {
      this.reentry.cleanComparisons = 0;
    } else {
      this.reentry.cleanComparisons += 1;
    }
  }

  finalizeReentry({ basis, validator, evidenceRefs = [], provenance = {} } = {}) {
    if (!this.reentry || this.reentry.status !== "pending") {
      throw new Error("no pending canonical re-entry validation exists");
    }
    if (this.sidecar.shouldReconstruct || this.sidecar.H >= this.sidecar.theta) {
      throw new Error("cannot finalize re-entry while H >= theta");
    }
    if (this.reentry.cleanComparisons < this.reentry.requiredComparisons) {
      throw new Error("re-entry requires more finite post-reconstruction comparisons");
    }
    const finiteBasis = nonEmpty(basis);
    const validatorId = nonEmpty(validator);
    const refs = evidenceRefs.map(nonEmpty).filter(Boolean);
    if (!finiteBasis || !validatorId || refs.length === 0) {
      throw new Error("re-entry completion requires basis, validator, and finite evidenceRefs");
    }
    const completion = Object.freeze({
      status: "normal-operation-restored",
      modelRef: this.reentry.modelRef,
      basis: finiteBasis,
      validator: validatorId,
      evidenceRefs: frozenArray(refs),
      H: this.sidecar.H,
      theta: this.sidecar.theta,
      xiStatus: "unrecovered-relations-remain",
      provenance: frozenObject({
        ...provenance,
        source: nonEmpty(provenance.source) || "living-field-reentry-validation",
      }),
    });
    this.reentry.status = "complete";
    this.reentry.completion = completion;
    this.phase = "cruising";
    this.agent.log(
      this.agent.v23Observer?.latest?.tick ?? this.reentry.startedTick,
      "canonical-reentry",
      "Canonical M_B' 通常運転へ復帰",
      `${this.reentry.cleanComparisons} finite comparisons / H ${this.sidecar.H.toFixed(2)}`,
    );
    return completion;
  }

  snapshot() {
    return Object.freeze({
      agentRef: this.agent.focusKey,
      authority: "canonical-v23",
      phase: this.phase,
      theta: this.theta,
      H: this.sidecar.snapshot(),
      completedCycles: this.completedCycles,
      selection: this.lastSelection,
      reconstruction: this.lastReconstruction,
      applyAudit: this.lastApplyAudit,
      reentry: this.reentry
        ? Object.freeze({
          modelRef: this.reentry.modelRef,
          startedTick: this.reentry.startedTick,
          cleanComparisons: this.reentry.cleanComparisons,
          requiredComparisons: this.reentry.requiredComparisons,
          status: this.reentry.status,
          completion: this.reentry.completion,
        })
        : null,
      legacyLeapAuthority: false,
      legacyNumericXiIsCoreXi: false,
    });
  }
}

export class CanonicalLivingFieldAuthority {
  constructor(simulation, options = {}) {
    if (!simulation?.observeV23) {
      throw new Error("canonical Living Field authority requires Simulation({ observeV23: true })");
    }
    this.simulation = simulation;
    this.options = options;
    this.controllers = new Map();
    this.originalCreateEpisode = simulation.createEpisode.bind(simulation);
    this.installed = false;
  }

  install() {
    if (this.installed) return this;
    this.installCurrentAgents();
    this.simulation.createEpisode = (...args) => {
      const result = this.originalCreateEpisode(...args);
      this.installCurrentAgents();
      return result;
    };
    this.simulation.v23CanonicalAuthority = this;
    this.installed = true;
    return this;
  }

  installCurrentAgents() {
    this.controllers = new Map();
    for (const agent of this.simulation.relationalAgents()) {
      const controller = new CanonicalLivingFieldController({
        agent,
        theta: thetaFor(agent, this.options),
        probeWindows: this.options.probeWindows ?? 2,
        reentryValidationWindows: this.options.reentryValidationWindows ?? 2,
      }).install();
      this.controllers.set(agent.focusKey, controller);
    }
  }

  controller(agentRef) {
    const controller = this.controllers.get(agentRef);
    if (!controller) throw new Error(`unknown canonical Living Field agentRef: ${agentRef}`);
    return controller;
  }

  review(agentRef, reviewInput) {
    return this.controller(agentRef).reviewLatest(reviewInput);
  }

  finalizeReentry(agentRef, input) {
    return this.controller(agentRef).finalizeReentry(input);
  }

  snapshot() {
    return Object.freeze(Array.from(this.controllers.values(), (controller) => controller.snapshot()));
  }
}

export function installCanonicalLivingFieldAuthority(simulation, options = {}) {
  if (simulation?.v23CanonicalAuthority) {
    throw new Error("canonical Living Field authority is already installed");
  }
  return new CanonicalLivingFieldAuthority(simulation, options).install();
}
