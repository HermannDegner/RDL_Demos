import test from "node:test";
import assert from "node:assert/strict";

import {
  Boundary,
  HVector,
  LeapEngine,
  MBGraph,
  MBNode,
  RIBSection,
} from "../rdl_system/core/index.mjs";

function assertClose(actual, expected, epsilon = 1e-12) {
  assert.ok(Math.abs(actual - expected) <= epsilon, `${actual} != ${expected}`);
}

test("Boundary は有限な RIBSection を切り出し、閾値は Core ξ に依存しない", () => {
  const boundary = new Boundary({
    id: "B-resource",
    dimensions: ["resource", "danger"],
    thetaBase: 0.8,
  });

  const section = boundary.section(
    { resource: 1, danger: 0.2, hidden: 99 },
    { id: "rib-1", provenance: "fixture" },
  );

  assert.ok(section instanceof RIBSection);
  assert.equal(section.boundaryId, "B-resource");
  assert.deepEqual(section.values, { resource: 1, danger: 0.2 });
  assert.equal(section.values.hidden, undefined);
  assert.equal(boundary.threshold(), 0.8);
});

test("HVector は unresolved mismatch だけを保持し、resolved tick では散逸する", () => {
  const h = new HVector({
    dimensions: ["resource", "danger"],
    decay: { resource: 0.5, danger: 0.25 },
    gain: 2,
    residualAfterLeap: 0.25,
  });

  h.recordUnresolved({ resource: 0.4, danger: 0.1 });
  h.recordUnresolved({ resource: 0.4, danger: 0 });

  assertClose(h.snapshot().resource, 1.2);
  assertClose(h.snapshot().danger, 0.05);
  h.dissipateTick();
  assertClose(h.snapshot().resource, 0.6);
  assertClose(h.snapshot().danger, 0.0125);
});

test("MBNode は同じ pre-update M_B で RIB_B(t) と RIB_B(t+Δ) を解釈して E を作る", () => {
  const boundary = new Boundary({
    id: "B-motion",
    dimensions: ["resource", "motion"],
    thetaBase: 2,
  });
  const node = new MBNode({
    id: "agent",
    boundary,
    reliability: { resource: 0.5, motion: 0.8 },
    alignRate: 0.5,
  });

  const current = boundary.section(
    { resource: 1, motion: 0.5 },
    { id: "rib-current", role: "current" },
  );
  const later = boundary.section(
    { resource: 0.4, motion: 1 },
    { id: "rib-later", role: "later" },
  );

  const result = node.compareSections({
    currentSection: current,
    laterSection: later,
    unresolved: true,
    tick: 1,
  });

  assert.deepEqual(result.F, { resource: 0.5, motion: 0.4 });
  assert.deepEqual(result.FPrime, { resource: 0.2, motion: 0.8 });
  assertClose(result.E.resource, 0.3);
  assertClose(result.E.motion, 0.4);
  assert.deepEqual(result.dMB.previous, { resource: 0.5, motion: 0.8 });
  assert.notDeepEqual(result.dMB.current, result.dMB.previous);
});

test("resolved E は観測できるが operational H には保持しない", () => {
  const boundary = new Boundary({ dimensions: ["x"], thetaBase: 0.2 });
  const node = new MBNode({
    id: "resolved",
    boundary,
    reliability: 1,
    alignRate: 0,
    h: new HVector({ dimensions: ["x"], decay: 1, gain: 1 }),
  });

  const result = node.compareSections({
    currentSection: boundary.section({ x: 0 }, { id: "a" }),
    laterSection: boundary.section({ x: 1 }, { id: "b" }),
    unresolved: false,
    tick: 1,
  });

  assert.equal(result.E.x, 1);
  assert.equal(result.H.x, 0);
  assert.equal(result.leap, null);
});

test("adaptationPressure はデモ固有診断量であり θ を変更しない", () => {
  const boundary = new Boundary({ dimensions: ["x"], thetaBase: 1 });
  const node = new MBNode({
    id: "pressure-diagnostic",
    boundary,
    reliability: 1,
    alignRate: 0,
    adaptationPressureGain: 0.5,
    adaptationPressureDecay: 1,
    adaptationPressureMax: 2,
  });

  node.compareSections({
    currentSection: boundary.section({ x: 0 }, { id: "a" }),
    laterSection: boundary.section({ x: 1 }, { id: "b" }),
    unresolved: false,
  });

  assert.equal(node.adaptationPressure, 0.5);
  assert.equal(boundary.threshold(), 1);
  assert.equal(node.snapshot().theta, 1);
  assert.equal("xi" in node.snapshot(), false);
});

test("LeapEngine は unresolved H が固定 θ 以上になったときだけ M_delta へ送る", () => {
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
    alignRate: 0,
    reliabilityMax: 1,
    h: new HVector({ dimensions: ["danger", "motion"], decay: 0, gain: 1 }),
    leapEngine,
  });

  const result = node.compareSections({
    currentSection: boundary.section({ danger: 0, motion: 0 }, { id: "a" }),
    laterSection: boundary.section({ danger: 1, motion: 0.1 }, { id: "b" }),
    unresolved: true,
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

test("LeapEngine の cooldown は即時再跳躍を止める", () => {
  const boundary = new Boundary({ dimensions: ["danger"], thetaBase: 0.2 });
  const node = new MBNode({
    id: "oscillation-guard",
    boundary,
    reliability: 1,
    alignRate: 0,
    h: new HVector({ dimensions: ["danger"], decay: 1, gain: 1 }),
  });

  const pair = () => ({
    currentSection: boundary.section({ danger: 0 }, { id: `a-${node.leapCount}` }),
    laterSection: boundary.section({ danger: 1 }, { id: `b-${node.leapCount}` }),
    unresolved: true,
  });

  const first = node.compareSections({ ...pair(), tick: 1 });
  const second = node.compareSections({ ...pair(), tick: 2 });

  assert.equal(first.leap.dimension, "danger");
  assert.equal(second.leap, null);
  assert.equal(node.leapCount, 1);
  assert.equal(node.leapCooldown, 9);
});

test("MBGraph は有限な M_B 実装断面どうしの関係を保持する", () => {
  const boundary = new Boundary({ dimensions: ["prey"] });
  const predator = new MBNode({ id: "predator", boundary });
  const preyMemory = new MBNode({ id: "prey-memory", boundary });
  const graph = new MBGraph();

  graph.add(predator);
  graph.add(preyMemory);
  graph.connect("predator", "prey-memory", {
    type: "contains",
    weight: 0.8,
    label: "implementation relation",
  });

  assert.equal(graph.neighbors("predator", "contains")[0].node.id, "prey-memory");
  assert.deepEqual(graph.snapshot().edges, [{
    from: "predator",
    to: "prey-memory",
    type: "contains",
    weight: 0.8,
    label: "implementation relation",
  }]);
});
