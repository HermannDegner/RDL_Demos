import test from "node:test";
import assert from "node:assert/strict";

import { Simulation } from "../demos/relational-ecology-lab/core.mjs";
import { installCanonicalLivingFieldAuthority } from "../demos/relational-ecology-lab/v23_canonical_authority.mjs";

test("canonical authority cuts legacy leap authority and completes reviewed reconstruction", () => {
  const simulation = new Simulation({ seed: 2401, observeV23: true });
  const authority = installCanonicalLivingFieldAuthority(simulation, {
    thetaByKind: { rabbit: 0.05, predator: 0.05 },
    probeWindows: 1,
    reentryValidationWindows: 1,
  });
  const rabbit = simulation.rabbits[0];
  const controller = authority.controller(rabbit.focusKey);

  const explorationBeforeLegacyCheck = rabbit.exploration;
  rabbit.H.resource = 999;
  rabbit.thetaBase = 0;
  rabbit.maybeLeap(1);
  assert.equal(rabbit.leapCount, 0);
  assert.equal(rabbit.exploration, explorationBeforeLegacyCheck);
  assert.equal(controller.snapshot().legacyLeapAuthority, false);

  const observer = rabbit.v23Observer;
  const reliability = { ...rabbit.reliability };
  observer.capture({
    tick: 10,
    observed: { resource: 0.1, danger: 0.1, motion: 0.5 },
    reliability,
  });
  observer.beginPredictionWindow({
    tick: 10,
    prediction: { resource: 0, danger: 0.1, motion: 0.5 },
    reliability: { ...reliability, resource: reliability.resource - 0.01 },
  });
  const comparison = observer.capture({
    tick: 11,
    observed: { resource: 1, danger: 0.1, motion: 0.5 },
    reliability: { ...reliability, resource: reliability.resource - 0.01 },
  });
  assert.equal(comparison.status, "pending-assessment");
  assert.equal(
    comparison.predictionEvidence.status,
    "prediction-residual-after-bounded-local-adjustment",
  );

  authority.review(rabbit.focusKey, {
    coverageDisposition: "stable-selected-coverage",
    temporalDisposition: "ordinary-temporal-change-excluded",
    basis: "finite authority test excludes coverage and ordinary temporal change",
    reviewer: "test:canonical-reviewer",
    evidenceRefs: ["test:canonical:review:1"],
  });
  assert.equal(controller.snapshot().phase, "M_delta-probing");

  observer.beginPredictionWindow({
    tick: 12,
    prediction: { resource: 0, danger: 0.1, motion: 0.5 },
    reliability,
  });
  observer.capture({
    tick: 13,
    observed: { resource: 1, danger: 0.1, motion: 0.5 },
    reliability,
  });
  rabbit.maybeLeap(13);

  const reconstructed = controller.snapshot();
  assert.equal(reconstructed.completedCycles, 1);
  assert.equal(reconstructed.phase, "reentry-validation");
  assert.equal(reconstructed.reconstruction.xiStatus, "unrecovered-relations-remain");
  assert.equal(reconstructed.reconstruction.selection.status, "retain");
  assert.equal(rabbit.leapCount, 1);
  assert.ok(rabbit.reliability.resource < reliability.resource);

  const reentryObserver = rabbit.v23Observer;
  const post = { ...rabbit.reliability };
  reentryObserver.capture({
    tick: 20,
    observed: { resource: 0.4, danger: 0.2, motion: 0.6 },
    reliability: post,
  });
  reentryObserver.beginPredictionWindow({
    tick: 20,
    prediction: { resource: 0.4, danger: 0.2, motion: 0.6 },
    reliability: post,
  });
  reentryObserver.capture({
    tick: 21,
    observed: { resource: 0.4, danger: 0.2, motion: 0.6 },
    reliability: post,
  });
  rabbit.maybeLeap(21);

  const completion = authority.finalizeReentry(rabbit.focusKey, {
    basis: "one finite post-reconstruction comparison returned to zero mismatch in test boundary",
    validator: "test:canonical-validator",
    evidenceRefs: ["test:canonical:reentry:1"],
  });
  assert.equal(completion.status, "normal-operation-restored");
  assert.equal(completion.xiStatus, "unrecovered-relations-remain");
  assert.equal(controller.snapshot().phase, "cruising");
});

test("canonical authority requires explicit theta and reinstalls after episode creation", () => {
  const simulation = new Simulation({ seed: 41, observeV23: true });
  assert.throws(() => installCanonicalLivingFieldAuthority(simulation), /requires explicit theta/);

  const authority = installCanonicalLivingFieldAuthority(simulation, {
    theta: 0.5,
    probeWindows: 1,
    reentryValidationWindows: 1,
  });
  const first = authority.controller("rabbit:0");
  simulation.createEpisode();
  const second = authority.controller("rabbit:0");
  assert.notStrictEqual(first, second);
  assert.equal(second.snapshot().authority, "canonical-v23");
  assert.equal(simulation.rabbits[0].v23CanonicalController, second);
});
