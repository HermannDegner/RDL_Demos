import test from "node:test";
import assert from "node:assert/strict";

import { Simulation } from "../demos/relational-ecology-lab/core.mjs";
import { AttackAttemptObserver } from "../demos/relational-ecology-lab/v23_attack_boundary.mjs";
import { installCompleteLivingFieldAuthority } from "../demos/relational-ecology-lab/v23_complete_authority.mjs";

test("B_attack forms only for actual attempts and keeps outcome distinctions", () => {
  const observer = new AttackAttemptObserver({ agentRef: "predator:predator" });
  assert.equal(observer.snapshot().attempts, 0);
  assert.equal(observer.snapshot().unattemptedIsFailureZero, false);
  assert.equal(observer.resolveAttempt({
    tick: 1,
    success: false,
    outcome: "not-an-attempt",
    reliability: 0.7,
  }), null);
  assert.equal(observer.snapshot().completed, 0);

  observer.beginAttempt({ tick: 2, targetId: 0, prediction: 0.8, reliability: 0.72 });
  const first = observer.resolveAttempt({
    tick: 3,
    success: false,
    outcome: "contact-escape",
    contact: true,
    escaped: true,
    reliability: 0.72,
    targetId: 0,
  });
  assert.equal(first.attempted, true);
  assert.equal(first.contact, true);
  assert.equal(first.escaped, true);
  assert.equal(first.success, false);
  assert.equal(first.status, "pending-assessment");
  assert.equal(first.predictionEvidence.status, "prediction-residual-present");

  observer.beginAttempt({ tick: 4, targetId: 1, prediction: 0.8, reliability: 0.70 });
  const second = observer.resolveAttempt({
    tick: 5,
    success: false,
    outcome: "obstacle-failure",
    obstacle: true,
    reliability: 0.70,
    targetId: 1,
  });
  assert.equal(
    second.predictionEvidence.status,
    "prediction-residual-after-bounded-local-adjustment",
  );
  assert.equal(second.predictionEvidence.localAbsorptionAttempt.qualifiesAsFiniteAttempt, true);
  assert.equal(second.obstacle, true);
  assert.deepEqual(observer.snapshot().outcomeCounts, {
    "contact-escape": 1,
    "obstacle-failure": 1,
  });
});

test("complete authority canonicalizes attack reconstruction without legacy attack leap", () => {
  const simulation = new Simulation({ seed: 2401, observeV23: true });
  const authority = installCompleteLivingFieldAuthority(simulation, {
    thetaByKind: { rabbit: 0.05, predator: 0.05 },
    attackTheta: 0.05,
    probeWindows: 1,
    attackProbeWindows: 1,
    reentryValidationWindows: 1,
    attackReentryValidationWindows: 1,
  });
  const predator = simulation.predator;
  const attackController = predator.v23AttackCanonicalController;

  const leadBeforeLegacyCheck = predator.attackLeadTicks;
  predator.H.attack = 999;
  predator.thetaBase = 0;
  predator.maybeLeap(1);
  assert.equal(predator.leapCount, 0);
  assert.equal(predator.attackLeadTicks, leadBeforeLegacyCheck);
  assert.equal(authority.snapshot().legacyAttackLeapAuthority, false);

  const observer = predator.v23AttackObserver;
  observer.beginAttempt({ tick: 10, targetId: 0, prediction: 0.8, reliability: 0.72 });
  observer.resolveAttempt({
    tick: 11,
    success: false,
    outcome: "contact-escape",
    contact: true,
    escaped: true,
    reliability: 0.72,
    targetId: 0,
  });
  observer.beginAttempt({ tick: 12, targetId: 1, prediction: 0.8, reliability: 0.70 });
  const reviewedComparison = observer.resolveAttempt({
    tick: 13,
    success: false,
    outcome: "obstacle-failure",
    obstacle: true,
    reliability: 0.70,
    targetId: 1,
  });
  assert.equal(
    reviewedComparison.predictionEvidence.status,
    "prediction-residual-after-bounded-local-adjustment",
  );

  authority.reviewAttack({
    coverageDisposition: "stable-selected-coverage",
    temporalDisposition: "ordinary-temporal-change-excluded",
    basis: "attempt-specific finite review excludes coverage and ordinary temporal change",
    reviewer: "test:B_attack-reviewer",
    evidenceRefs: ["test:B_attack:review:1"],
  });
  assert.equal(attackController.snapshot().phase, "M_delta-probing");

  observer.beginAttempt({ tick: 14, targetId: 2, prediction: 0.8, reliability: predator.reliability.attack });
  observer.resolveAttempt({
    tick: 15,
    success: false,
    outcome: "timeout-or-range-failure",
    reliability: predator.reliability.attack,
    targetId: 2,
  });
  predator.maybeLeap(15);

  const reconstructed = attackController.snapshot();
  assert.equal(reconstructed.completedCycles, 1);
  assert.equal(reconstructed.phase, "reentry-validation");
  assert.equal(reconstructed.selection.status, "retain");
  assert.equal(reconstructed.reconstruction.xiStatus, "unrecovered-relations-remain");
  assert.ok(predator.reliability.attack < 0.72);
  assert.equal(predator.leapCount, 1);

  const reentryObserver = predator.v23AttackObserver;
  reentryObserver.beginAttempt({
    tick: 20,
    targetId: 3,
    prediction: 0,
    reliability: predator.reliability.attack,
  });
  const clean = reentryObserver.resolveAttempt({
    tick: 21,
    success: false,
    outcome: "timeout-or-range-failure",
    reliability: predator.reliability.attack,
    targetId: 3,
  });
  assert.equal(clean.status, "zero-difference");
  predator.maybeLeap(21);

  const completion = authority.finalizeAttackReentry({
    basis: "finite attempted-capture outcome returned to zero mismatch after reconstruction",
    validator: "test:B_attack-validator",
    evidenceRefs: ["test:B_attack:reentry:1"],
  });
  assert.equal(completion.status, "normal-operation-restored");
  assert.equal(completion.xiStatus, "unrecovered-relations-remain");
  assert.equal(attackController.snapshot().phase, "cruising");
});

test("complete authority reinstalls attack instrumentation across episodes", () => {
  const simulation = new Simulation({ seed: 41, observeV23: true });
  const authority = installCompleteLivingFieldAuthority(simulation, {
    theta: 0.5,
    attackTheta: 0.5,
    probeWindows: 1,
    attackProbeWindows: 1,
    reentryValidationWindows: 1,
    attackReentryValidationWindows: 1,
  });
  const oldPredator = simulation.predator;
  const oldAttack = authority.attack;
  simulation.createEpisode();
  assert.notStrictEqual(simulation.predator, oldPredator);
  assert.notStrictEqual(authority.attack, oldAttack);
  assert.ok(simulation.predator.v23AttackObserver);
  assert.equal(authority.snapshot().attack.unattemptedIsFailureZero, false);
});
