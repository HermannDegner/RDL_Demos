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
    assert.ok(snapshots.some((entry) => entry.predictionChecks > 0));
    assert.ok(snapshots.some((entry) => entry.localAbsorptionAttempts > 0));
    for (const entry of snapshots) {
      const assessed = Object.values(entry.assessmentCounts).reduce((sum, count) => sum + count, 0);
      assert.equal(assessed, entry.comparisons);
      assert.ok(Object.keys(entry.assessmentCounts).every(
        (status) => status === "pending-assessment"
          || status === "zero-difference"
          || status === "resolved-difference",
      ));
      assert.equal(entry.assessmentCounts["unresolved-mismatch"] ?? 0, 0);

      const checked = Object.values(entry.predictionEvidenceCounts)
        .reduce((sum, count) => sum + count, 0);
      assert.equal(checked, entry.predictionChecks);
      assert.ok(Object.keys(entry.predictionEvidenceCounts).every(
        (status) => status === "prediction-matched-observation"
          || status === "prediction-residual-present"
          || status === "prediction-residual-after-bounded-local-adjustment"
          || status === "not-formed-missing-prediction"
          || status === "not-formed-missing-observation",
      ));

      const localChecks = Object.values(entry.localUpdateEvidenceCounts)
        .reduce((sum, count) => sum + count, 0);
      assert.equal(localChecks, entry.localUpdateChecks);
      assert.ok(Object.keys(entry.localUpdateEvidenceCounts).every(
        (status) => status === "bounded-local-adjustment-observed"
          || status === "no-observed-local-adjustment"
          || status === "confounded-structural-change"
          || status === "not-formed-missing-local-coefficient",
      ));
      assert.equal(
        entry.localAbsorptionAttempts,
        entry.localUpdateEvidenceCounts["bounded-local-adjustment-observed"] ?? 0,
      );
      if (entry.samples > 0) assert.ok(entry.predictionChecks > 0);
    }
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
  assert.equal(result.assessment.eligibleForH, false);
  assert.equal(observer.snapshot().assessmentCounts["pending-assessment"], 1);
  assert.equal(observer.snapshot().H, undefined);
});

test("reacquired prediction match can resolve a non-zero temporal E", () => {
  const observer = new LivingFieldObserver({ agentRef: "rabbit:0", dimensions: ["resource"] });
  observer.capture({
    tick: 1,
    observed: { resource: 0.2 },
    reliability: { resource: 0.5 },
  });
  observer.beginPredictionWindow({
    tick: 1,
    prediction: { resource: 0.8 },
    reliability: { resource: 0.5 },
  });

  const liveReliability = { resource: 0.9 };
  const result = observer.capture({
    tick: 2,
    observed: { resource: 0.8 },
    reliability: liveReliability,
  });

  assert.ok(result.E.magnitude > 0);
  assert.equal(result.predictionEvidence.status, "prediction-matched-observation");
  assert.equal(result.predictionEvidence.coefficients.resource, 0.5);
  assert.equal(result.predictionEvidence.weightedPrediction.resource, 0.4);
  assert.equal(result.predictionEvidence.weightedObserved.resource, 0.4);
  assert.equal(result.predictionEvidence.magnitude, 0);
  assert.equal(result.status, "resolved-difference");
  assert.equal(result.assessment.eligibleForH, false);
  assert.equal(result.assessment.provenance.source, "living-field-prediction-check");
  assert.equal(observer.snapshot().predictionChecks, 1);
  assert.equal(observer.snapshot().predictionEvidenceCounts["prediction-matched-observation"], 1);
});

test("prediction residual remains pending regardless of magnitude", () => {
  const observer = new LivingFieldObserver({ agentRef: "rabbit:0", dimensions: ["danger"] });
  observer.capture({
    tick: 1,
    observed: { danger: 0.1 },
    reliability: { danger: 0.8 },
  });
  observer.beginPredictionWindow({
    tick: 1,
    prediction: { danger: 0 },
    reliability: { danger: 0.8 },
  });
  const result = observer.capture({
    tick: 2,
    observed: { danger: 1 },
    reliability: { danger: 0.8 },
  });

  assert.equal(result.predictionEvidence.status, "prediction-residual-present");
  assert.equal(result.predictionEvidence.magnitude, 0.8);
  assert.equal(result.status, "pending-assessment");
  assert.equal(result.assessment.eligibleForH, false);
  assert.equal(observer.snapshot().assessmentCounts["pending-assessment"], 1);
});

test("bounded local coefficient adjustment is finite absorption-attempt evidence only", () => {
  const observer = new LivingFieldObserver({ agentRef: "rabbit:0", dimensions: ["danger"] });
  observer.capture({
    tick: 1,
    observed: { danger: 0.1 },
    reliability: { danger: 0.8 },
  });
  const staged = observer.beginPredictionWindow({
    tick: 1,
    prediction: { danger: 0 },
    reliability: { danger: 0.79 },
  });

  assert.equal(staged.localAbsorptionAttempt.status, "bounded-local-adjustment-observed");
  assert.equal(staged.localAbsorptionAttempt.qualifiesAsFiniteAttempt, true);
  assert.deepEqual(staged.localAbsorptionAttempt.changedDimensions, ["danger"]);
  assert.equal(staged.localAbsorptionAttempt.beforeCoefficients.danger, 0.8);
  assert.equal(staged.localAbsorptionAttempt.afterCoefficients.danger, 0.79);

  const result = observer.capture({
    tick: 2,
    observed: { danger: 1 },
    reliability: { danger: 0.79 },
  });
  assert.equal(
    result.predictionEvidence.status,
    "prediction-residual-after-bounded-local-adjustment",
  );
  assert.equal(result.predictionEvidence.residualAfterFiniteAbsorptionAttempt, true);
  assert.equal(result.predictionEvidence.localAbsorptionAttempt.captureTick, 1);
  assert.equal(result.status, "pending-assessment");
  assert.equal(result.assessment.eligibleForH, false);
  assert.equal(observer.snapshot().localAbsorptionAttempts, 1);
  assert.equal(
    observer.snapshot().localUpdateEvidenceCounts["bounded-local-adjustment-observed"],
    1,
  );
});

test("structural change outside the bounded local updater is excluded from absorption evidence", () => {
  const observer = new LivingFieldObserver({ agentRef: "rabbit:0", dimensions: ["danger"] });
  observer.capture({
    tick: 1,
    observed: { danger: 0.1 },
    reliability: { danger: 0.8 },
  });
  const staged = observer.beginPredictionWindow({
    tick: 1,
    prediction: { danger: 0 },
    reliability: { danger: 0.6 },
  });

  assert.equal(staged.localAbsorptionAttempt.status, "confounded-structural-change");
  assert.equal(staged.localAbsorptionAttempt.qualifiesAsFiniteAttempt, false);
  assert.deepEqual(staged.localAbsorptionAttempt.confoundedDimensions, ["danger"]);

  const result = observer.capture({
    tick: 2,
    observed: { danger: 1 },
    reliability: { danger: 0.6 },
  });
  assert.equal(result.predictionEvidence.status, "prediction-residual-present");
  assert.equal(result.status, "pending-assessment");
  assert.equal(result.assessment.eligibleForH, false);
  assert.equal(observer.snapshot().localAbsorptionAttempts, 0);
});

test("incomplete prediction evidence does not invent a zero or unresolved result", () => {
  const observer = new LivingFieldObserver({
    agentRef: "rabbit:0",
    dimensions: ["resource", "danger"],
  });
  observer.capture({
    tick: 1,
    observed: { resource: 0.2, danger: 0.1 },
    reliability: { resource: 0.7, danger: 0.8 },
  });
  const staged = observer.beginPredictionWindow({
    tick: 1,
    prediction: { resource: 0.4 },
    reliability: { resource: 0.7, danger: 0.8 },
  });
  assert.equal(staged.status, "not-formed-missing-prediction");

  const result = observer.capture({
    tick: 2,
    observed: { resource: 0.7, danger: 0.6 },
    reliability: { resource: 0.7, danger: 0.8 },
  });
  assert.equal(result.predictionEvidence.status, "not-formed-missing-prediction");
  assert.deepEqual(result.predictionEvidence.missingDimensions, ["danger"]);
  assert.equal(result.status, "pending-assessment");
  assert.equal(result.assessment.eligibleForH, false);
});

test("observer accepts explicit evidence-backed classification without creating H", () => {
  const observer = new LivingFieldObserver({ agentRef: "rabbit:0", dimensions: ["danger"] });
  observer.capture({
    tick: 1,
    observed: { danger: 0.1 },
    reliability: { danger: 0.8 },
  });
  const result = observer.capture({
    tick: 2,
    observed: { danger: 0.7 },
    reliability: { danger: 0.8 },
    assessment: {
      classification: "unresolved-mismatch",
      basis: "explicit finite review says the mismatch remained after local absorption",
      provenance: { source: "test-review" },
    },
  });

  assert.equal(result.status, "unresolved-mismatch");
  assert.equal(result.assessment.eligibleForH, true);
  assert.equal(result.assessment.provenance.source, "test-review");
  assert.equal(observer.snapshot().assessmentCounts["unresolved-mismatch"], 1);
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
  assert.throws(() => { snapshot[0].assessmentCounts.fake = 999; }, TypeError);
  assert.throws(() => { snapshot[0].predictionEvidenceCounts.fake = 999; }, TypeError);
  assert.throws(() => { snapshot[0].localUpdateEvidenceCounts.fake = 999; }, TypeError);
  assert.notStrictEqual(simulation.rabbits[0].v23Observer, simulation.rabbits[1].v23Observer);
  const old = simulation.rabbits[0].v23Observer;
  simulation.createEpisode();
  assert.notStrictEqual(simulation.rabbits[0].v23Observer, old);
  assert.ok(simulation.v23Snapshot().every((entry) => entry.samples === 0));
});
