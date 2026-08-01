import test from "node:test";
import assert from "node:assert/strict";

import {
  CONFIG,
  Simulation,
  WORLD_HEIGHT,
  WORLD_WIDTH,
} from "../demos/relational-ecology-lab/core.mjs";

test("同じ seed と fixed tick は同じ生態系状態を再現する", () => {
  const first = new Simulation({ seed: 2401 });
  const second = new Simulation({ seed: 2401 });

  first.step(720);
  second.step(720);

  assert.deepEqual(first.snapshot(), second.snapshot());
});

test("異なる seed は異なる初期配置を作る", () => {
  const first = new Simulation({ seed: 2401 });
  const second = new Simulation({ seed: 2402 });

  assert.notDeepEqual(first.snapshot().resources, second.snapshot().resources);
});

test("個体の記憶配列は共有されない", () => {
  const simulation = new Simulation({ seed: 41 });
  const first = simulation.rabbits[0].memory;
  const second = simulation.rabbits[1].memory;

  assert.notStrictEqual(first.food, second.food);
  first.food[0] = 0.91;
  assert.equal(second.food[0], 0);
});

test("資源は枯渇後に休眠し、同じ場所へ即時復活せず別地点で再生する", () => {
  const simulation = new Simulation({ seed: 77 });
  const resource = simulation.world.resources.find((candidate) => candidate.kind === "grass");
  const rabbit = simulation.rabbits[0];
  const events = [];
  const previous = { x: resource.x, y: resource.y };

  resource.amount = CONFIG.resourceDormancyThreshold + 0.001;
  rabbit.x = resource.x;
  rabbit.y = resource.y;
  rabbit.hunger = 0.8;
  simulation.world.interactRabbit(
    rabbit,
    simulation.rng,
    1,
    (event) => events.push(event),
  );

  assert.equal(resource.dormant, true);
  assert.equal(resource.amount, 0);
  assert.equal(events[0].type, "resource-dormant");

  resource.dormantFor = 2;
  simulation.world.update(simulation.rng, 2, (event) => events.push(event));
  assert.equal(resource.dormant, true);
  simulation.world.update(simulation.rng, 3, (event) => events.push(event));

  assert.equal(resource.dormant, false);
  assert.equal(resource.relocations, 1);
  assert.ok(Math.hypot(resource.x - previous.x, resource.y - previous.y) >= 150);
  assert.equal(events.at(-1).type, "resource-return");
});

test("H_vec が実効閾値を越えると最大誤差次元の Leap が起きる", () => {
  const simulation = new Simulation({ seed: 92 });
  const rabbit = simulation.rabbits[0];
  rabbit.memory.food.fill(0.8);
  rabbit.H.resource = rabbit.thetaEffective + 0.2;
  const reliabilityBefore = rabbit.reliability.resource;

  const leap = rabbit.maybeLeap(10);

  assert.equal(leap.dimension, "resource");
  assert.equal(rabbit.leapCount, 1);
  assert.ok(rabbit.reliability.resource < reliabilityBefore);
  assert.ok(rabbit.memory.food[0] < 0.8);
  assert.equal(rabbit.events[0].type, "leap");
});

test("遠方の脅威と資源は個体の知覚へ入らない", () => {
  const simulation = new Simulation({ seed: 13 });
  const rabbit = simulation.rabbits[0];
  rabbit.x = CONFIG.worldMargin + 12;
  rabbit.y = CONFIG.worldMargin + 12;
  simulation.threat.x = WORLD_WIDTH - CONFIG.worldMargin - 12;
  simulation.threat.y = WORLD_HEIGHT - CONFIG.worldMargin - 12;
  for (const resource of simulation.world.resources) {
    resource.x = WORLD_WIDTH - 80;
    resource.y = WORLD_HEIGHT - 80;
  }

  const perception = simulation.world.perceiveRabbit(rabbit, simulation.threat, simulation.rng);

  assert.equal(perception.visibleThreat, null);
  assert.equal(perception.heardThreat, null);
  assert.equal(perception.visibleResources.length, 0);
});

test("境界は閉じており、個体と脅威は wrap しない", () => {
  const simulation = new Simulation({ seed: 120 });
  simulation.step(2400);
  const margin = CONFIG.worldMargin;

  for (const rabbit of simulation.rabbits) {
    assert.ok(rabbit.x >= margin && rabbit.x <= WORLD_WIDTH - margin);
    assert.ok(rabbit.y >= margin && rabbit.y <= WORLD_HEIGHT - margin);
  }
  assert.ok(simulation.threat.x >= margin && simulation.threat.x <= WORLD_WIDTH - margin);
  assert.ok(simulation.threat.y >= margin && simulation.threat.y <= WORLD_HEIGHT - margin);
});

test("観測用 metrics と snapshot の読み出しは行動系列へ影響しない", () => {
  const untouched = new Simulation({ seed: 501 });
  const observed = new Simulation({ seed: 501 });

  for (let tick = 0; tick < 360; tick += 1) {
    untouched.step();
    observed.step();
    observed.metrics();
    observed.snapshot();
  }

  assert.deepEqual(untouched.snapshot(), observed.snapshot());
});
