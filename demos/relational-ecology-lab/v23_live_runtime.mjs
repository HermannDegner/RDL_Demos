// Autonomous Living Field v2.3 runtime built on explicit finite review rules.
//
// This is a demo-local operational reviewer, not an ontological truth oracle.
// It may exclude ordinary temporal change only after the same dominant residual
// persists across multiple distinct finite windows, each following a bounded
// local adjustment, under the same B / Purpose / selected dimensions.
import { Simulation } from "./core.mjs";
import { installCompleteLivingFieldAuthority } from "./v23_complete_authority.mjs";

function nonEmpty(value) {
  return String(value ?? "").trim();
}

function finiteContext(comparison) {
  const context = comparison?.earlierSection?.context;
  return Object.freeze({
    boundaryId: context?.boundaryId ?? null,
    purpose: context?.purpose ?? null,
    dimensions: context?.conditions?.dimensions ?? null,
  });
}

function sameContext(a, b) {
  return a?.boundaryId === b?.boundaryId
    && a?.purpose === b?.purpose
    && a?.dimensions === b?.dimensions;
}

function dominantDimension(E) {
  return Object.entries(E?.values ?? {})
    .sort((a, b) => Math.abs(Number(b[1]) || 0) - Math.abs(Number(a[1]) || 0))[0]?.[0] ?? null;
}

function newStreak() {
  return {
    dimension: null,
    context: null,
    count: 0,
    evidenceRefs: [],
    lastEvidenceKey: null,
  };
}

export class LivingFieldOperationalReviewer {
  constructor(completeAuthority, { reviewWindows = 2, attackReviewWindows = null } = {}) {
    if (!completeAuthority?.simulation || !completeAuthority?.general || !completeAuthority?.attack) {
      throw new Error("operational reviewer requires CompleteLivingFieldAuthority");
    }
    if (!Number.isInteger(reviewWindows) || reviewWindows < 2) {
      throw new Error("operational reviewWindows must be an integer >= 2");
    }
    const attackWindows = attackReviewWindows ?? reviewWindows;
    if (!Number.isInteger(attackWindows) || attackWindows < 2) {
      throw new Error("operational attackReviewWindows must be an integer >= 2");
    }
    this.authority = completeAuthority;
    this.reviewWindows = reviewWindows;
    this.attackReviewWindows = attackWindows;
    this.generalStreaks = new Map();
    this.attackStreak = newStreak();
    this.reviewedGeneralKeys = new Set();
    this.reviewedAttackKeys = new Set();
    this.installedAgents = new WeakSet();
    this.installCurrentAgents();
  }

  installCurrentAgents() {
    for (const agent of this.authority.simulation.relationalAgents()) {
      if (this.installedAgents.has(agent)) continue;
      const canonicalMaybeLeap = agent.maybeLeap.bind(agent);
      agent.maybeLeap = (tick) => {
        this.beforeReplan(agent, tick);
        return canonicalMaybeLeap(tick);
      };
      this.installedAgents.add(agent);
    }
  }

  resetEpisodeState() {
    this.generalStreaks = new Map();
    this.attackStreak = newStreak();
    this.reviewedGeneralKeys = new Set();
    this.reviewedAttackKeys = new Set();
    this.installCurrentAgents();
  }

  beforeReplan(agent, tick) {
    this.considerGeneral(agent, tick);
    if (agent.profile?.kind === "predator") this.considerAttack(agent, tick);
  }

  otherPredatorPathIsBusy(kind) {
    const predatorRef = this.authority.simulation.predator.focusKey;
    const generalPhase = this.authority.general.controller(predatorRef).snapshot().phase;
    const attackPhase = this.authority.attack.snapshot().phase;
    if (kind === "general") return attackPhase !== "cruising";
    return generalPhase !== "cruising";
  }

  considerGeneral(agent, tick) {
    const controller = this.authority.general.controller(agent.focusKey);
    const phase = controller.snapshot().phase;
    if (phase.startsWith("M_delta")) return;
    if (agent.profile?.kind === "predator" && this.otherPredatorPathIsBusy("general")) return;

    const comparison = agent.v23Observer?.latest;
    const evidence = comparison?.predictionEvidence;
    const evidenceKey = Number.isFinite(comparison?.tick)
      ? `${agent.focusKey}:general:${comparison.tick}`
      : null;
    if (!evidenceKey || this.reviewedGeneralKeys.has(evidenceKey)) return;

    if (
      comparison?.status !== "pending-assessment"
      || !evidence?.residualAfterFiniteAbsorptionAttempt
      || !evidence.localAbsorptionAttempt?.qualifiesAsFiniteAttempt
      || !(comparison.E?.magnitude > 0)
    ) {
      this.generalStreaks.set(agent.focusKey, newStreak());
      return;
    }

    const dimension = dominantDimension(comparison.E);
    const context = finiteContext(comparison);
    if (!dimension || !context.boundaryId || !context.purpose || !context.dimensions) {
      this.generalStreaks.set(agent.focusKey, newStreak());
      return;
    }
    let streak = this.generalStreaks.get(agent.focusKey) ?? newStreak();
    if (
      streak.lastEvidenceKey === evidenceKey
      || streak.dimension !== dimension
      || !sameContext(streak.context, context)
    ) {
      streak = newStreak();
      streak.dimension = dimension;
      streak.context = context;
    }
    streak.count += 1;
    streak.lastEvidenceKey = evidenceKey;
    streak.evidenceRefs.push(evidenceKey);
    this.generalStreaks.set(agent.focusKey, streak);
    if (streak.count < this.reviewWindows) return;

    const refs = streak.evidenceRefs.slice(-this.reviewWindows);
    this.authority.review(agent.focusKey, {
      coverageDisposition: "stable-selected-coverage",
      temporalDisposition: "ordinary-temporal-change-excluded",
      basis:
        `demo-local operational review: ${dimension} residual persisted across `
        + `${this.reviewWindows} distinct post-adjustment finite windows under the same B/Purpose/dimensions`,
      reviewer: "living-field-operational-reviewer-v1",
      evidenceRefs: refs,
      provenance: {
        source: "living-field-operational-reviewer",
        reviewRule: "persistent-post-adjustment-residual-v1",
        dominantDimension: dimension,
        reviewWindows: this.reviewWindows,
        triggerTick: tick,
      },
    });
    this.reviewedGeneralKeys.add(evidenceKey);
    this.generalStreaks.set(agent.focusKey, newStreak());
  }

  considerAttack(agent, tick) {
    const attackPhase = this.authority.attack.snapshot().phase;
    if (attackPhase.startsWith("M_delta")) return;
    if (this.otherPredatorPathIsBusy("attack")) return;

    const comparison = agent.v23AttackObserver?.latest;
    const evidence = comparison?.predictionEvidence;
    const evidenceKey = comparison?.attemptRef ?? null;
    if (!evidenceKey || this.reviewedAttackKeys.has(evidenceKey)) return;
    if (
      comparison?.status !== "pending-assessment"
      || !comparison.attempted
      || !evidence?.residualAfterFiniteAbsorptionAttempt
      || !evidence.localAbsorptionAttempt?.qualifiesAsFiniteAttempt
      || !(comparison.E?.magnitude > 0)
    ) {
      this.attackStreak = newStreak();
      return;
    }

    const context = finiteContext(comparison);
    let streak = this.attackStreak;
    if (
      streak.lastEvidenceKey === evidenceKey
      || streak.dimension !== "attack"
      || !sameContext(streak.context, context)
    ) {
      streak = newStreak();
      streak.dimension = "attack";
      streak.context = context;
    }
    streak.count += 1;
    streak.lastEvidenceKey = evidenceKey;
    streak.evidenceRefs.push(evidenceKey);
    this.attackStreak = streak;
    if (streak.count < this.attackReviewWindows) return;

    const refs = streak.evidenceRefs.slice(-this.attackReviewWindows);
    this.authority.reviewAttack({
      coverageDisposition: "stable-selected-coverage",
      temporalDisposition: "ordinary-temporal-change-excluded",
      basis:
        `demo-local operational review: attempted-capture residual persisted across `
        + `${this.attackReviewWindows} distinct post-adjustment attempts under B_attack`,
      reviewer: "living-field-operational-reviewer-v1:B_attack",
      evidenceRefs: refs,
      provenance: {
        source: "living-field-operational-reviewer",
        reviewRule: "persistent-attempted-capture-residual-v1",
        dominantDimension: "attack",
        reviewWindows: this.attackReviewWindows,
        triggerTick: tick,
      },
    });
    this.reviewedAttackKeys.add(evidenceKey);
    this.attackStreak = newStreak();
  }

  snapshot() {
    return Object.freeze({
      reviewer: "living-field-operational-reviewer-v1",
      reviewWindows: this.reviewWindows,
      attackReviewWindows: this.attackReviewWindows,
      rule: "persistent post-adjustment residual under stable finite context",
      terminalTruthClaim: false,
      authority: this.authority.snapshot(),
    });
  }
}

export class LiveCanonicalLivingFieldRuntime {
  constructor(simulation, authority, reviewer) {
    this.simulation = simulation;
    this.authority = authority;
    this.reviewer = reviewer;
    Object.freeze(this);
  }

  snapshot() {
    return Object.freeze({
      simulation: this.simulation.snapshot(),
      canonical: this.reviewer.snapshot(),
    });
  }
}

export function installLiveCanonicalLivingFieldRuntime(simulation, options = {}) {
  if (!simulation?.observeV23) {
    throw new Error("live canonical runtime requires Simulation({ observeV23: true })");
  }
  const authority = installCompleteLivingFieldAuthority(simulation, options);
  const reviewer = new LivingFieldOperationalReviewer(authority, {
    reviewWindows: options.reviewWindows ?? 2,
    attackReviewWindows: options.attackReviewWindows ?? options.reviewWindows ?? 2,
  });
  const completeEpisodeFactory = simulation.createEpisode.bind(simulation);
  simulation.createEpisode = (...args) => {
    const result = completeEpisodeFactory(...args);
    reviewer.resetEpisodeState();
    return result;
  };
  const runtime = new LiveCanonicalLivingFieldRuntime(simulation, authority, reviewer);
  simulation.v23LiveCanonicalRuntime = runtime;
  return runtime;
}

export function createLiveCanonicalLivingFieldSimulation({
  seed = 2401,
  config,
  theta,
  attackTheta = theta,
  reviewWindows = 2,
  attackReviewWindows = reviewWindows,
  probeWindows = 2,
  attackProbeWindows = probeWindows,
  reentryValidationWindows = 2,
  attackReentryValidationWindows = reentryValidationWindows,
} = {}) {
  if (!Number.isFinite(theta) || theta < 0) {
    throw new Error("live canonical simulation requires explicit non-negative theta");
  }
  if (!Number.isFinite(attackTheta) || attackTheta < 0) {
    throw new Error("live canonical simulation requires explicit non-negative attackTheta");
  }
  const simulation = new Simulation({ seed, config, observeV23: true });
  const runtime = installLiveCanonicalLivingFieldRuntime(simulation, {
    theta,
    attackTheta,
    reviewWindows,
    attackReviewWindows,
    probeWindows,
    attackProbeWindows,
    reentryValidationWindows,
    attackReentryValidationWindows,
  });
  return runtime;
}
