import test from "node:test";
import assert from "node:assert/strict";
import { Simulation } from "../demos/relational-ecology-lab/core.mjs";
import { LivingFieldObserver } from "../demos/relational-ecology-lab/v23_observer.mjs";

test("actual Rabbit and Predator windows are observed without changing seeded evolution", () => {
  for (const seed of [41, 2401]) {
    const normal = new Simulation({ seed });
    const watched = new Simulation({ seed, observeV23: true });
    for (let step = 0; step < 8; step += 1) {
      normal.step(90);
      watched.step(90);
      assert.deepEqual(watched.snapshot(), normal.snapshot());
      for (let i = 0; i < normal.relationalAgents().length; i += 1) {
        const a = normal.relationalAgents()[i];
        const b = watched.relationalAgents()[i];
        assert.deepEqual(b.memory, a.memory);
        assert.deepEqual(b.reliability, a.reliability);
        assert.deepEqual(b.H, a.H);
        assert.deepEqual(b.events, a.events);
        assert.deepEqual(b.decision, a.decision);
      }
      assert.deepEqual(watched.rng, normal.rng);
    }
    const snapshots = watched.v23Snapshot();
    assert.ok(snapshots.some((entry) => entry.agentRef.startsWith("rabbit:") && entry.comparisons > 0));
    assert.ok(snapshots.some((entry) => entry.agentRef.startsWith("predator:") && entry.comparisons > 0));
    assert.ok(snapshots.every((entry) => !entry.dimensions.includes("attack")));
    assert.ok(normal.v23Snapshot().every((entry) => entry === null));
  }
});

test("later observation uses earlier copied coefficients despite live adaptation", () => {
  const observer = new LivingFieldObserver({ agentRef: "rabbit:0", dimensions: ["resource"] });
  const reliability = { resource: 0.5 };
  const observed = { resource: 0.2 };
  observer.capture({ tick: 1, observed, reliability });
  reliability.resource = 0.9;
  observed.resource = 0.8;
  const result = observer.capture({ tick: 2, observed, reliability });
  assert.equal(result.F.values.resource, 0.1);
  assert.equal(result.FPrime.values.resource, 0.4);
  assert.ok(Math.abs(result.E.values.resource - 0.3) < 1e-12);
  assert.equal(result.F.modelRef, result.FPrime.modelRef);
  assert.equal(result.earlierSection.payload.resource, 0.2);
  assert.equal(result.status, "pending-assessment");
  assert.equal(observer.snapshot().H, undefined);
});

test("missing observation breaks the comparison window rather than inventing zero", () => {
  const observer = new LivingFieldObserver({ agentRef: "rabbit:0", dimensions: ["motion"] });
  const reliability = { motion: 0.8 };
  observer.capture({ tick: 1, observed: { motion: 1 }, reliability });
  assert.equal(observer.capture({ tick: 2, observed: {}, reliability }).status,
    "not-formed-missing-observation");
  assert.equal(observer.capture({ tick: 3, observed: { motion: 0.4 }, reliability }).status,
    "window-started");
  assert.equal(observer.snapshot().comparisons, 0);
  assert.equal(observer.snapshot().missing, 1);
});

test("diagnostic snapshots are immutable and isolated between agents and episodes", () => {
  const simulation = new Simulation({ seed: 2401, observeV23: true });
  simulation.step(120);
  const snapshot = simulation.v23Snapshot();
  assert.throws(() => { snapshot[0].samples = 999; }, TypeError);
  assert.notStrictEqual(simulation.rabbits[0].v23Observer, simulation.rabbits[1].v23Observer);
  const old = simulation.rabbits[0].v23Observer;
  simulation.createEpisode();
  assert.notStrictEqual(simulation.rabbits[0].v23Observer, old);
  assert.ok(simulation.v23Snapshot().every((entry) => entry.samples === 0));
});
