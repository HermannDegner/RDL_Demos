import test from "node:test";
import assert from "node:assert/strict";

import { Simulation } from "../demos/relational-ecology-lab/core.mjs";
import {
  createLiveCanonicalLivingFieldSimulation,
  installLiveCanonicalLivingFieldRuntime,
} from "../demos/relational-ecology-lab/v23_live_runtime.mjs";

test("live canonical factory requires explicit finite thresholds", () => {
  assert.throws(
    () => createLiveCanonicalLivingFieldSimulation({ seed: 2401 }),
    /requires explicit non-negative theta/,
  );
  assert.throws(
    () => createLiveCanonicalLivingFieldSimulation({ seed: 2401, theta: 1, attackTheta: -1 }),
    /requires explicit non-negative attackTheta/,
  );
});

test("operational reviewer requires repeated distinct post-adjustment windows before unresolved review", () => {
  const simulation = new Simulation({ seed: 2401, observeV23: true });
  const runtime = installLiveCanonicalLivingFieldRuntime(simulation, {
    theta: 0.05,
    attackTheta: 0.05,
    reviewWindows: 2,
    attackReviewWindows: 2,
    probeWindows: 1,
    attackProbeWindows: 1,
    reentryValidationWindows: 1,
    attackReentryValidationWindows: 1,
  });
  const rabbit = simulation.rabbits[0];
  const observer = rabbit.v23Observer;
  const reliability = { ...rabbit.reliability };

  observer.capture({
    tick: 1,
    observed: { resource: 0.1, danger: 0.1, motion: 0.5 },
    reliability,
  });
  observer.beginPredictionWindow({
    tick: 1,
    prediction: { resource: 0, danger: 0.1, motion: 0.5 },
    reliability: { ...reliability, resource: reliability.resource - 0.01 },
  });
  observer.capture({
    tick: 2,
    observed: { resource: 1, danger: 0.1, motion: 0.5 },
    reliability: { ...reliability, resource: reliability.resource - 0.01 },
  });
  runtime.reviewer.beforeReplan(rabbit, 2);
  assert.equal(runtime.authority.general.controller(rabbit.focusKey).snapshot().phase, "cruising");

  // Re-reading the same finite window cannot manufacture persistence.
  runtime.reviewer.beforeReplan(rabbit, 3);
  assert.equal(runtime.authority.general.controller(rabbit.focusKey).snapshot().phase, "cruising");

  observer.beginPredictionWindow({
    tick: 4,
    prediction: { resource: 0, danger: 0.1, motion: 0.5 },
    reliability: { ...reliability, resource: reliability.resource - 0.02 },
  });
  observer.capture({
    tick: 5,
    observed: { resource: 0.8, danger: 0.1, motion: 0.5 },
    reliability: { ...reliability, resource: reliability.resource - 0.02 },
  });
  runtime.reviewer.beforeReplan(rabbit, 5);

  const state = runtime.authority.general.controller(rabbit.focusKey).snapshot();
  assert.equal(state.phase, "M_delta-probing");
  assert.equal(state.H.unresolvedReviews, 1);
});

test("autonomous runtime keeps operational review explicitly finite and non-terminal", () => {
  const runtime = createLiveCanonicalLivingFieldSimulation({
    seed: 41,
    theta: 1,
    attackTheta: 1,
    reviewWindows: 2,
    attackReviewWindows: 2,
  });
  const snapshot = runtime.reviewer.snapshot();
  assert.equal(snapshot.reviewer, "living-field-operational-reviewer-v1");
  assert.equal(snapshot.reviewWindows, 2);
  assert.equal(snapshot.terminalTruthClaim, false);
  assert.equal(snapshot.authority.legacyGeneralLeapAuthority, false);
  assert.equal(snapshot.authority.legacyAttackLeapAuthority, false);
  assert.equal(snapshot.authority.legacyNumericXiIsCoreXi, false);
});
