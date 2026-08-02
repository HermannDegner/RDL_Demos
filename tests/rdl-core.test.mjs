import test from "node:test";
import assert from "node:assert/strict";

import {
  Boundary,
  HVector,
  LeapEngine,
  MBGraph,
  MBNode,
} from "../rdl_core/index.mjs";

function assertClose(actual, expected, epsilon = 1e-12) {
  assert.ok(Math.abs(actual - expected) <= epsilon, `${actual} != ${expected}`);
}

test("Boundary は ξ に応じて実効閾値を揺らす", () => {
  const boundary = new Boundary({
    dimensions: ["resource"],
    thetaBase: 1,
    thetaMin: 0.5,
    xiThetaWeight: 0.25,
  });

  assert.equal(boundary.thetaEffective(0), 1);
  assert.equal(boundary.thetaEffective(1), 0.75);
  assert.equal(boundary.thetaEffective(9), 0.5);
});

test("HVector は次元ごとに予測誤差を蓄積し、Leap後も残存する", () => {
  const h = new HVector({
    dimensions: ["resource", "danger"],
    decay: { resource: 0.5, danger: 0.25 },
    gain: 2,
    residualAfterLeap: 0.25,
  });

  h.record({ resource: 0.4, danger: 0.1 });
  h.record({ resource: 0.4, danger: 0 });

  assertClose(h.snapshot().resource, 1.2);
  assertClose(h.snapshot().danger, 0.05);
  assert.equal(h.strongest()[0], "resource");
  assertClose(h.strongest()[1], 1.2);
  const retained = h.retainAfterLeap();
  assertClose(retained.resource, 0.3);
  assertClose(retained.danger, 0.0125);
});

test("MBNode は EFP を F に解釈し、慣性投影との差を E として記録する", () => {
  const boundary = new Boundary({
    id: "B-resource",
    dimensions: ["resource", "motion"],
    thetaBase: 2,
  });
  const node = new MBNode({
    id: "agent",
    boundary,
    reliability: { resource: 0.5, motion: 0.8 },
    xiGain: 0,
  });

  const first = node.update({
    efp: { resource: 1, motion: 0.5 },
    predictedF: { resource: 0.2, motion: 0.2 },
    tick: 1,
  });

  assert.deepEqual(first.F, { resource: 0.5, motion: 0.4 });
  assert.deepEqual(first.E, { resource: 0.3, motion: 0.2 });
  assert.equal(first.leap, null);
  assert.equal(node.snapshot().phase, "M_act");
});

test("LeapEngine は H が閾値を越えた最大次元を M_delta へ送る", () => {
  const boundary = new Boundary({
    dimensions: ["danger", "motion"],
    thetaBase: 0.6,
  });
  const leapEngine = new LeapEngine({
    cooldownTicks: 3,
    handlers: {
      danger: ({ node }) => {
        node.reliability.danger *= 0.5;
        return { title: "危険仮説を再編", detail: "danger reliability reduced" };
      },
    },
  });
  const node = new MBNode({
    id: "rabbit",
    boundary,
    reliability: 1,
    h: new HVector({ dimensions: ["danger", "motion"], decay: 0, gain: 1 }),
    leapEngine,
    xiGain: 0,
  });

  const result = node.update({
    actualF: { danger: 1, motion: 0.1 },
    predictedF: { danger: 0, motion: 0 },
    tick: 7,
  });

  assert.equal(result.leap.dimension, "danger");
  assert.equal(result.leap.title, "危険仮説を再編");
  assert.equal(result.phase, "M_delta");
  assert.equal(node.leapCount, 1);
  assert.equal(node.leapCooldown, 3);
  assert.equal(node.reliability.danger, 0.5);
  assert.equal(node.h.snapshot().danger, 0.28);
});

test("MBGraph は M_B 間の W_ij を保持する", () => {
  const boundary = new Boundary({ dimensions: ["prey"] });
  const predator = new MBNode({ id: "predator", boundary });
  const preyMemory = new MBNode({ id: "prey-memory", boundary });
  const graph = new MBGraph();

  graph.add(predator);
  graph.add(preyMemory);
  graph.connect("predator", "prey-memory", {
    type: "contains",
    weight: 0.8,
    label: "nested M_B",
  });

  assert.equal(graph.neighbors("predator", "contains")[0].node.id, "prey-memory");
  assert.deepEqual(graph.snapshot().edges, [{
    from: "predator",
    to: "prey-memory",
    type: "contains",
    weight: 0.8,
    label: "nested M_B",
  }]);
});
