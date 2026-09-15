import test from "node:test";
import assert from "node:assert/strict";

import { Simulation } from "../demos/relational-ecology-lab/core.mjs";
import { LivingFieldHSidecar } from "../demos/relational-ecology-lab/v23_h_sidecar.mjs";
import { LivingFieldObserver } from "../demos/relational-ecology-lab/v23_observer.mjs";
import { reviewPostAdjustmentResidual } from "../demos/relational-ecology-lab/v23_post_adjustment_review.mjs";
import { bindMDeltaSubject, requestMDelta } from "../demos/relational-ecology-lab/v23_mdelta_request.mjs";
import {
  T1ReconstructionSession,
  applyReconstructedFiniteModel,
  captureLivingFieldFiniteModel,
} from "../demos/relational-ecology-lab/v23_t1_reconstruction.mjs";

function buildUnresolvedHandoff(agent) {
  const observer = new LivingFieldObserver({
    agentRef: agent.focusKey,
    dimensions: ["resource"],
  });
  const startReliability = agent.reliability.resource;
  observer.capture({
    tick: 1,
    observed: { resource: 0.1 },
    reliability: { resource: startReliability },
  });
  observer.beginPredictionWindow({
    tick: 1,
    prediction: { resource: 0 },
    reliability: { resource: startReliability - 0.01 },
  });
  const comparison = observer.capture({
    tick: 2,
    observed: { resource: 1 },
    reliability: { resource: startReliability - 0.01 },
  });
  const review = reviewPostAdjustmentResidual(comparison, {
    coverageDisposition: "stable-selected-coverage",
    temporalDisposition: "ordinary-temporal-change-excluded",
    basis: "finite test review excludes coverage and ordinary temporal change",
    reviewer: "test:t1-reviewer",
    evidenceRefs: ["test:t1:review:1"],
  });
  const H = new LivingFieldHSidecar({ theta: 0.05 });
  H.observeReview(review);
  const request = requestMDelta(H, {
    reviews: [review],
    requestRef: `${agent.focusKey}:test-m-delta`,
    requester: "test:t1",
    basis: "reviewed unresolved mismatch crossed test theta",
    provenance: { triggerTick: 2 },
  });
  const handoff = bindMDeltaSubject(request, {
    subjectRef: `${agent.focusKey}:current-M_B:test`,
    basis: "bind current finite model for T1 test",
    binder: "test:t1",
  });
  return { observer, handoff };
}

test("T1 Probe -> Selection -> Reconstruction forms finite M_B' with xi still open", () => {
  const simulation = new Simulation({ seed: 2401, observeV23: true });
  const agent = simulation.rabbits[0];
  const { observer, handoff } = buildUnresolvedHandoff(agent);
  const model = captureLivingFieldFiniteModel(handoff, agent, {
    modelRef: `${agent.focusKey}:M_B:test:0`,
    basis: "capture action-relevant finite model",
    capturer: "test:t1",
  });
  const session = new T1ReconstructionSession({
    handoff,
    model,
    probeWindows: 1,
    minimumEvaluationTick: 2,
  });

  observer.beginPredictionWindow({
    tick: 3,
    prediction: { resource: 0 },
    reliability: { resource: agent.reliability.resource },
  });
  const probeComparison = observer.capture({
    tick: 4,
    observed: { resource: 1 },
    reliability: { resource: agent.reliability.resource },
  });
  const snapshot = session.observeProbe(probeComparison.predictionEvidence);

  assert.equal(snapshot.selection.status, "retain");
  assert.equal(snapshot.status, "reconstructed-proposal-ready");
  assert.equal(snapshot.reconstructedModel.xiStatus, "unrecovered-relations-remain");
  assert.equal(snapshot.reconstructedModel.reentryRequired, true);
  assert.equal(snapshot.reconstructedModel.validConditions.boundaryId, handoff.request.context.boundaryId);
  assert.ok(snapshot.reconstructedModel.parameters["reliability.resource"] < model.parameters["reliability.resource"]);

  const beforeReliability = agent.reliability.resource;
  const audit = applyReconstructedFiniteModel(agent, snapshot.reconstructedModel, {
    applier: "test:t1",
    tick: 5,
  });
  assert.equal(audit.status, "M_B-prime-applied");
  assert.equal(audit.xiStatus, "unrecovered-relations-remain");
  assert.ok(agent.reliability.resource < beforeReliability);
});

test("T1 Selection rejects a candidate when finite shadow Probe does not improve", () => {
  const simulation = new Simulation({ seed: 2401, observeV23: true });
  const agent = simulation.rabbits[0];
  const { observer, handoff } = buildUnresolvedHandoff(agent);
  const model = captureLivingFieldFiniteModel(handoff, agent, {
    modelRef: `${agent.focusKey}:M_B:test:reject`,
    basis: "capture finite model",
    capturer: "test:t1",
  });
  const session = new T1ReconstructionSession({ handoff, model, probeWindows: 1, minimumEvaluationTick: 2 });

  observer.beginPredictionWindow({
    tick: 3,
    prediction: { resource: 0.4 },
    reliability: { resource: agent.reliability.resource },
  });
  const probeComparison = observer.capture({
    tick: 4,
    observed: { resource: 0.4 },
    reliability: { resource: agent.reliability.resource },
  });
  const snapshot = session.observeProbe(probeComparison.predictionEvidence);

  assert.equal(snapshot.selection.status, "reject");
  assert.equal(snapshot.reconstructedModel, null);
});

test("T1 finite model capture cannot cross agent identity", () => {
  const simulation = new Simulation({ seed: 2401, observeV23: true });
  const source = simulation.rabbits[0];
  const other = simulation.rabbits[1];
  const { handoff } = buildUnresolvedHandoff(source);
  assert.throws(
    () => captureLivingFieldFiniteModel(handoff, other, {
      modelRef: "wrong-agent-model",
      basis: "invalid cross-agent capture",
      capturer: "test:t1",
    }),
    /does not belong to the supplied agent/,
  );
});
