import test from "node:test";
import assert from "node:assert/strict";

import {
  CONFIG,
  SeededRandom,
  Simulation,
  TerrainObstacle,
  Threat,
  WORLD_HEIGHT,
  WORLD_WIDTH,
  distance,
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

test("岩は視線を遮り、視認した個体の移動場だけへ記録される", () => {
  const simulation = new Simulation({ seed: 131 });
  const observingRabbit = simulation.rabbits[0];
  const distantRabbit = simulation.rabbits[1];
  const rock = new TerrainObstacle({ id: "R-test", x: 200, y: 100, radius: 32 });
  simulation.world.obstacles = [rock];
  for (const resource of simulation.world.resources) resource.dormant = true;

  observingRabbit.x = 100;
  observingRabbit.y = 100;
  distantRabbit.x = 760;
  distantRabbit.y = 520;
  simulation.threat.x = 300;
  simulation.threat.y = 100;

  const perception = simulation.world.perceiveRabbit(
    observingRabbit,
    simulation.threat,
    simulation.rng,
  );
  const distantPerception = simulation.world.perceiveRabbit(
    distantRabbit,
    simulation.threat,
    simulation.rng,
  );

  assert.equal(perception.visibleThreat, null);
  assert.deepEqual(perception.visibleObstacles.map((obstacle) => obstacle.id), ["R-test"]);
  assert.equal(distantPerception.visibleObstacles.length, 0);

  observingRabbit.memory.integrate(perception, observingRabbit);
  distantRabbit.memory.integrate(distantPerception, distantRabbit);
  const rockCell = observingRabbit.memory.indexAt(rock.x, rock.y);
  assert.ok(observingRabbit.memory.motion[rockCell] > 0.5);
  assert.equal(distantRabbit.memory.motion[rockCell], 0);
});

test("岩との衝突は個体を外へ戻し、接線方向の移動を残す", () => {
  const simulation = new Simulation({ seed: 132 });
  const rock = new TerrainObstacle({ id: "R-test", x: 100, y: 100, radius: 30 });
  const entity = { x: 125, y: 115, vx: -1, vy: 1 };
  simulation.world.obstacles = [rock];

  const collision = simulation.world.constrainEntityDetailed(entity, 7);
  const normal = {
    x: (entity.x - rock.x) / distance(entity, rock),
    y: (entity.y - rock.y) / distance(entity, rock),
  };

  assert.equal(collision.blocked, true);
  assert.equal(collision.obstacle.id, "R-test");
  assert.ok(distance(entity, rock) >= rock.radius + 7 - 1e-9);
  assert.ok(entity.vx * normal.x + entity.vy * normal.y >= -1e-9);
  assert.ok(Math.hypot(entity.vx, entity.vy) > 0.1);
});

test("資源は生成時と再生時のどちらも岩の内部へ配置されない", () => {
  const simulation = new Simulation({ seed: 133 });
  const resource = simulation.world.resources[0];

  const assertTerrainClear = (candidate) => {
    for (const obstacle of simulation.world.obstacles) {
      assert.ok(distance(candidate, obstacle) >= candidate.radius + obstacle.radius + 12 - 1e-9);
    }
  };

  for (const candidate of simulation.world.resources) assertTerrainClear(candidate);
  resource.dormant = true;
  resource.dormantFor = 1;
  resource.previousPosition = { x: resource.x, y: resource.y };
  simulation.world.update(simulation.rng, 1, () => {});
  assertTerrainClear(resource);
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

test("捕食者は接近後に加速行動へ入り、終了後は低速で回復する", () => {
  const simulation = new Simulation({ seed: 808 });
  const rabbit = simulation.rabbits[0];
  const threat = simulation.threat;
  simulation.rabbits = [rabbit];
  simulation.world.canThreatSee = () => true;

  rabbit.x = 140;
  rabbit.y = 120;
  rabbit.vx = 0;
  rabbit.vy = 0;
  threat.x = 110;
  threat.y = 120;
  threat.vx = 1;
  threat.vy = 0;

  const event = threat.update(simulation.world, simulation.rabbits, simulation.rng);

  assert.equal(event.type, "attack");
  assert.equal(threat.state, "attack");
  assert.ok(Math.hypot(threat.vx, threat.vy) > 2.5);

  threat.attackTicks = 0;
  const miss = threat.update(simulation.world, simulation.rabbits, simulation.rng);

  assert.equal(miss.type, "attack-miss");
  assert.equal(threat.state, "recover");
  assert.ok(Math.hypot(threat.vx, threat.vy) <= CONFIG.threatRecoverySpeed);
});

test("捕食ダッシュが岩へ衝突すると、その場で攻撃を終えて回復へ移る", () => {
  const simulation = new Simulation({ seed: 818 });
  const threat = simulation.threat;
  simulation.world.obstacles = [
    new TerrainObstacle({ id: "R-test", x: 128, y: 100, radius: 15 }),
  ];
  threat.x = 100;
  threat.y = 100;
  threat.vx = 3;
  threat.vy = 0;
  threat.state = "attack";
  threat.targetId = simulation.rabbits[0].id;
  threat.attackTicks = 5;
  threat.attackDirection = { x: 1, y: 0 };

  const event = threat.update(simulation.world, simulation.rabbits, simulation.rng);

  assert.equal(event.type, "attack-obstacle");
  assert.equal(threat.state, "recover");
  assert.equal(threat.attackTicks, 0);
  assert.ok(Math.hypot(threat.vx, threat.vy) <= CONFIG.threatRecoverySpeed);
});

test("同じ接触値でも逃走成立時は離脱し、未成立時は捕食される", () => {
  const makeEncounter = (label) => {
    const simulation = new Simulation({ seed: 909 });
    const rabbit = simulation.rabbits[0];
    const threat = new Threat(100, 100, new SeededRandom(2), simulation.config);
    rabbit.x = 108;
    rabbit.y = 100;
    rabbit.vx = 1;
    rabbit.vy = 0;
    rabbit.decision = { label, actual: { danger: 0 } };
    threat.state = "attack";
    threat.targetId = rabbit.id;
    threat.attackTicks = 4;
    return { rabbit, threat };
  };
  const fixedRoll = { next: () => 0.5 };

  const escaping = makeEncounter("escape");
  const escapedEvent = escaping.threat.resolveAttack(
    [escaping.rabbit],
    fixedRoll,
    12,
  );
  assert.equal(escapedEvent.type, "attack-escaped");
  assert.equal(escaping.rabbit.alive, true);
  assert.equal(escaping.threat.state, "recover");
  assert.equal(escaping.rabbit.decision.actual.danger, 1);

  const unaware = makeEncounter("food");
  const captureEvent = unaware.threat.resolveAttack(
    [unaware.rabbit],
    fixedRoll,
    12,
  );
  assert.equal(captureEvent.type, "capture");
  assert.equal(unaware.rabbit.alive, false);
  assert.equal(unaware.threat.state, "rest");
});
