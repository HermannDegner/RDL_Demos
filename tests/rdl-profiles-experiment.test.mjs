import test from "node:test";
import assert from "node:assert/strict";

import { Boundary, MBNode } from "../rdl_system/core/index.mjs";
import {
  botProfile,
  createProfiledNode,
  livingFieldProfile,
  mergeProfile,
} from "../rdl_system/profiles/index.mjs";
import { summarizeSnapshots } from "../rdl_system/experiment/durability_metrics.mjs";
import {
  expandParameterGrid,
  runParameterSearch,
} from "../rdl_system/experiment/parameter_search.mjs";

test("profiles は rdl_system/core の外でデモ係数を束ねる", () => {
  const profile = mergeProfile(livingFieldProfile, {
    node: { adaptationPressureDecay: 0.9 },
    leap: { cooldownTicks: 12 },
  });

  const node = createProfiledNode({
    id: "rabbit",
    dimensions: ["resource", "danger"],
    profile,
  });

  assert.equal(node.adaptationPressureDecay, 0.9);
  assert.equal(node.leapEngine.cooldownTicks, 12);
  assert.equal(node.boundary.thetaBase, livingFieldProfile.boundary.thetaBase);
});

test("botProfile は turn-based 境界向けの保守的なデモ係数を持つ", () => {
  const node = createProfiledNode({
    id: "bot-node",
    dimensions: ["concept"],
    profile: botProfile,
  });

  assert.equal(node.boundary.thetaBase, 2);
  assert.equal(node.adaptationPressureMax, 1);
  assert.equal(node.leapEngine.cooldownTicks, 4);
});

test("durability metrics はデモ固有pressure飽和と跳躍率を要約する", () => {
  const metrics = summarizeSnapshots([
    { adaptationPressure: 0.1, H: { a: 0.2 }, reliability: { a: 0.9 }, leapCount: 0 },
    { adaptationPressure: 1.2, H: { a: 0.001 }, reliability: { a: 0.1 }, leapCount: 2 },
  ], { adaptationPressureMax: 1.2 });

  assert.equal(metrics.ticks, 2);
  assert.equal(metrics.leapRate, 1);
  assert.equal(metrics.adaptationPressureSaturationRate, 0.5);
  assert.equal(metrics.hSilenceRate, 0.5);
  assert.equal(metrics.reliabilityCollapseRate, 0.5);
});

test("parameter search はデモ固有係数を展開して高スコア順に返す", () => {
  assert.deepEqual(expandParameterGrid({
    adaptationPressureDecay: [0.8, 0.9],
    cooldownTicks: [1, 2],
  }), [
    { adaptationPressureDecay: 0.8, cooldownTicks: 1 },
    { adaptationPressureDecay: 0.8, cooldownTicks: 2 },
    { adaptationPressureDecay: 0.9, cooldownTicks: 1 },
    { adaptationPressureDecay: 0.9, cooldownTicks: 2 },
  ]);

  const search = runParameterSearch({
    parameterGrid: { adaptationPressureGain: [0.01, 0.5] },
    seeds: [1],
    ticks: 12,
    makeSimulation: ({ params }) => {
      const boundary = new Boundary({ dimensions: ["x"], thetaBase: 2 });
      const node = new MBNode({
        id: "search-node",
        boundary,
        reliability: 1,
        alignRate: 0,
        adaptationPressureGain: params.adaptationPressureGain,
      });
      return {
        step: (tick) => node.compareSections({
          currentSection: boundary.section({ x: 0 }, { id: `a-${tick}` }),
          laterSection: boundary.section({ x: 0.4 }, { id: `b-${tick}` }),
          unresolved: false,
          tick,
        }),
        snapshot: () => node.snapshot(),
      };
    },
  });

  assert.equal(search.results.length, 2);
  assert.equal(search.best.params.adaptationPressureGain, 0.01);
});
