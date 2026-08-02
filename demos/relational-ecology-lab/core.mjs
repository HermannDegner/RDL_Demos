export const WORLD_WIDTH = 960;
export const WORLD_HEIGHT = 640;

export const CONFIG = Object.freeze({
  rabbitCount: 5,
  grassCount: 13,
  waterCount: 3,
  obstacleCount: 7,
  memoryColumns: 24,
  memoryRows: 16,
  visionRange: 205,
  soundRange: 285,
  threatVisionRange: 225,
  threatCaptureRange: 10,
  threatAttackRange: 34,
  threatAttackSpeed: 3.75,
  threatAttackTicks: 12,
  threatRecoverySpeed: 0.62,
  threatRecoveryTicks: 54,
  threatCaptureChanceUnaware: 0.78,
  threatCaptureChanceEscape: 0.28,
  resourceDormancyThreshold: 0.08,
  planInterval: 15,
  worldMargin: 18,
  resetDelay: 210,
});

const TAU = Math.PI * 2;

export function clamp(value, min = 0, max = 1) {
  return Math.max(min, Math.min(max, value));
}

export function lerp(a, b, amount) {
  return a + (b - a) * amount;
}

export function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

export function normalizeSeed(input) {
  if (Number.isFinite(Number(input))) {
    const numeric = Math.abs(Math.trunc(Number(input))) >>> 0;
    return numeric || 1;
  }

  const text = String(input ?? "rdl-living-field");
  let hash = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) || 1;
}

export class SeededRandom {
  constructor(seed = 1) {
    this.seed = normalizeSeed(seed);
    this.state = this.seed;
  }

  next() {
    this.state = (this.state + 0x6d2b79f5) >>> 0;
    let value = this.state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  }

  range(min, max) {
    return min + (max - min) * this.next();
  }

  integer(min, maxInclusive) {
    return Math.floor(this.range(min, maxInclusive + 1));
  }

  angle() {
    return this.range(0, TAU);
  }

  sign() {
    return this.next() < 0.5 ? -1 : 1;
  }
}

function pointToSegmentDistance(point, start, end) {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const lengthSquared = dx * dx + dy * dy;
  if (lengthSquared === 0) return distance(point, start);
  const projection = clamp(
    ((point.x - start.x) * dx + (point.y - start.y) * dy) / lengthSquared,
    0,
    1,
  );
  return Math.hypot(
    point.x - (start.x + projection * dx),
    point.y - (start.y + projection * dy),
  );
}

function vectorLength(x, y) {
  return Math.hypot(x, y);
}

function normalized(x, y) {
  const length = vectorLength(x, y) || 1;
  return { x: x / length, y: y / length };
}

function capVector(x, y, maximum) {
  const length = vectorLength(x, y);
  if (length <= maximum || length === 0) return { x, y };
  const scale = maximum / length;
  return { x: x * scale, y: y * scale };
}

function round(value, digits = 4) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

export class Resource {
  constructor({ id, kind, x, y, radius, amount, cover = 0 }) {
    this.id = id;
    this.kind = kind;
    this.x = x;
    this.y = y;
    this.radius = radius;
    this.amount = amount;
    this.cover = cover;
    this.dormant = false;
    this.dormantFor = 0;
    this.relocations = 0;
    this.previousPosition = null;
  }

  consume(requested) {
    if (this.dormant) return 0;
    const taken = Math.min(this.amount, requested);
    this.amount -= taken;
    return taken;
  }
}

export class TerrainObstacle {
  constructor({ id, x, y, radius }) {
    this.id = id;
    this.kind = "rock";
    this.x = x;
    this.y = y;
    this.radius = radius;
  }
}

export class MemoryField {
  constructor(columns = CONFIG.memoryColumns, rows = CONFIG.memoryRows) {
    this.columns = columns;
    this.rows = rows;
    this.size = columns * rows;
    this.food = new Float32Array(this.size);
    this.water = new Float32Array(this.size);
    this.cover = new Float32Array(this.size);
    this.danger = new Float32Array(this.size);
    this.motion = new Float32Array(this.size);
    this.visits = new Float32Array(this.size);
  }

  index(column, row) {
    return row * this.columns + column;
  }

  indexAt(x, y) {
    const column = clamp(Math.floor((x / WORLD_WIDTH) * this.columns), 0, this.columns - 1);
    const row = clamp(Math.floor((y / WORLD_HEIGHT) * this.rows), 0, this.rows - 1);
    return this.index(column, row);
  }

  cellCenter(column, row) {
    return {
      x: ((column + 0.5) / this.columns) * WORLD_WIDTH,
      y: ((row + 0.5) / this.rows) * WORLD_HEIGHT,
    };
  }

  sample(x, y) {
    const index = this.indexAt(x, y);
    return {
      food: this.food[index],
      water: this.water[index],
      cover: this.cover[index],
      danger: this.danger[index],
      motion: this.motion[index],
      visits: this.visits[index],
    };
  }

  decay() {
    for (let index = 0; index < this.size; index += 1) {
      this.food[index] *= 0.994;
      this.water[index] *= 0.994;
      this.cover[index] *= 0.997;
      this.danger[index] *= 0.965;
      this.motion[index] *= 0.986;
      this.visits[index] *= 0.998;
    }
  }

  stamp(field, x, y, strength, radiusInCells = 2) {
    const centerColumn = clamp(Math.floor((x / WORLD_WIDTH) * this.columns), 0, this.columns - 1);
    const centerRow = clamp(Math.floor((y / WORLD_HEIGHT) * this.rows), 0, this.rows - 1);
    for (let rowOffset = -radiusInCells; rowOffset <= radiusInCells; rowOffset += 1) {
      for (let columnOffset = -radiusInCells; columnOffset <= radiusInCells; columnOffset += 1) {
        const column = centerColumn + columnOffset;
        const row = centerRow + rowOffset;
        if (column < 0 || row < 0 || column >= this.columns || row >= this.rows) continue;
        const falloff = clamp(1 - Math.hypot(columnOffset, rowOffset) / (radiusInCells + 0.75));
        const index = this.index(column, row);
        field[index] = Math.max(field[index], clamp(strength * falloff));
      }
    }
  }

  integrate(perception, rabbit) {
    this.decay();
    let staleResource = 0;

    for (const cell of perception.observedCells ?? []) {
      const index = cell.index;
      if (cell.food < 0.04 && this.food[index] > 0.28) {
        staleResource = Math.max(staleResource, this.food[index] - cell.food);
      }
      if (cell.water < 0.04 && this.water[index] > 0.28) {
        staleResource = Math.max(staleResource, this.water[index] - cell.water);
      }
      this.food[index] = lerp(this.food[index], cell.food, cell.food > 0.04 ? 0.78 : 0.38);
      this.water[index] = lerp(this.water[index], cell.water, cell.water > 0.04 ? 0.78 : 0.38);
      this.cover[index] = lerp(this.cover[index], cell.cover, cell.cover > 0.04 ? 0.65 : 0.2);
    }

    for (const resource of perception.visibleResources ?? []) {
      if (resource.kind === "grass") {
        this.stamp(this.food, resource.x, resource.y, resource.amount, 2);
        this.stamp(this.cover, resource.x, resource.y, resource.cover, 2);
      } else {
        this.stamp(this.water, resource.x, resource.y, resource.amount, 2);
      }
    }

    for (const obstacle of perception.visibleObstacles ?? []) {
      const radiusInCells = Math.max(1, Math.ceil(obstacle.radius / 40));
      this.stamp(this.motion, obstacle.x, obstacle.y, 1, radiusInCells);
    }

    if (perception.visibleThreat) {
      this.stamp(
        this.danger,
        perception.visibleThreat.x,
        perception.visibleThreat.y,
        perception.visibleThreat.intensity,
        3,
      );
    } else if (perception.heardThreat) {
      const distanceGuess = 72 + (1 - perception.heardThreat.confidence) * 78;
      this.stamp(
        this.danger,
        rabbit.x + perception.heardThreat.x * distanceGuess,
        rabbit.y + perception.heardThreat.y * distanceGuess,
        0.25 + perception.heardThreat.confidence * 0.42,
        3,
      );
    }

    const visitIndex = this.indexAt(rabbit.x, rabbit.y);
    this.visits[visitIndex] = clamp(this.visits[visitIndex] + 0.2);
    return staleResource;
  }

  recordMotion(x, y, blocked) {
    const index = this.indexAt(x, y);
    const target = blocked ? 1 : 0;
    this.motion[index] = lerp(this.motion[index], target, blocked ? 0.5 : 0.05);
    this.visits[index] = clamp(this.visits[index] + 0.018);
  }

  fadeResourceMemory(factor) {
    for (let index = 0; index < this.size; index += 1) {
      this.food[index] *= factor;
      this.water[index] *= factor;
    }
  }

  softenDangerMemory(factor) {
    for (let index = 0; index < this.size; index += 1) this.danger[index] *= factor;
  }
}

export class World {
  constructor(rng, config = CONFIG) {
    this.config = config;
    this.obstacles = [];
    this.resources = [];
    this.createObstacles(rng);
    this.createResources(rng);
  }

  createObstacles(rng) {
    for (let index = 0; index < this.config.obstacleCount; index += 1) {
      const radius = rng.range(28, 48);
      const position = this.findObstaclePosition(rng, radius);
      this.obstacles.push(new TerrainObstacle({
        id: `R${index + 1}`,
        x: position.x,
        y: position.y,
        radius,
      }));
    }
  }

  findObstaclePosition(rng, radius) {
    const edge = this.config.worldMargin + radius + 24;
    let best = { x: WORLD_WIDTH / 2, y: WORLD_HEIGHT / 2 };
    let bestGap = -Infinity;
    for (let attempt = 0; attempt < 160; attempt += 1) {
      const candidate = {
        x: rng.range(edge, WORLD_WIDTH - edge),
        y: rng.range(edge, WORLD_HEIGHT - edge),
      };
      const gap = this.obstacles.reduce(
        (minimum, obstacle) => Math.min(
          minimum,
          distance(candidate, obstacle) - radius - obstacle.radius,
        ),
        Infinity,
      );
      if (gap > bestGap) {
        best = candidate;
        bestGap = gap;
      }
      if (gap >= 38) return candidate;
    }
    return best;
  }

  createResources(rng) {
    for (let index = 0; index < this.config.grassCount; index += 1) {
      const radius = rng.range(24, 38);
      const position = this.findOpenPosition(rng, 58, null, radius);
      this.resources.push(new Resource({
        id: `G${index + 1}`,
        kind: "grass",
        x: position.x,
        y: position.y,
        radius,
        amount: rng.range(0.52, 0.88),
        cover: rng.range(0.5, 1),
      }));
    }

    for (let index = 0; index < this.config.waterCount; index += 1) {
      const radius = rng.range(28, 42);
      const position = this.findOpenPosition(rng, 100, null, radius);
      this.resources.push(new Resource({
        id: `W${index + 1}`,
        kind: "water",
        x: position.x,
        y: position.y,
        radius,
        amount: rng.range(0.58, 0.86),
      }));
    }
  }

  findOpenPosition(rng, minimumDistance = 60, previousPosition = null, radius = 0) {
    let candidate = { x: WORLD_WIDTH / 2, y: WORLD_HEIGHT / 2 };
    let terrainSafeFallback = null;
    for (let attempt = 0; attempt < 160; attempt += 1) {
      candidate = {
        x: rng.range(64, WORLD_WIDTH - 64),
        y: rng.range(64, WORLD_HEIGHT - 64),
      };
      const awayFromObstacles = this.isPositionOpen(candidate, radius, 12);
      if (awayFromObstacles && terrainSafeFallback === null) terrainSafeFallback = candidate;
      const awayFromResources = this.resources.every(
        (resource) => resource.dormant || distance(candidate, resource) >= minimumDistance,
      );
      const awayFromPrevious = !previousPosition || distance(candidate, previousPosition) >= 150;
      if (awayFromObstacles && awayFromResources && awayFromPrevious) return candidate;
    }
    return terrainSafeFallback ?? candidate;
  }

  isPositionOpen(position, radius = 0, clearance = 0) {
    return this.obstacles.every(
      (obstacle) => distance(position, obstacle) >= obstacle.radius + radius + clearance,
    );
  }

  activeResources(kind = null) {
    return this.resources.filter(
      (resource) => !resource.dormant && (!kind || resource.kind === kind),
    );
  }

  coverAt(x, y) {
    let cover = 0;
    for (const resource of this.activeResources("grass")) {
      const extent = resource.radius * (0.8 + resource.cover * 0.25);
      if (Math.hypot(x - resource.x, y - resource.y) <= extent) {
        cover = Math.max(cover, resource.cover);
      }
    }
    return cover;
  }

  lineBlockedByCover(start, end) {
    for (const grass of this.activeResources("grass")) {
      const endpointInside = distance(grass, start) <= grass.radius * 1.08
        || distance(grass, end) <= grass.radius * 1.08;
      if (endpointInside) continue;
      if (pointToSegmentDistance(grass, start, end) < grass.radius * (0.56 + grass.cover * 0.22)) {
        return true;
      }
    }
    return false;
  }

  lineBlockedByObstacle(start, end, ignoredObstacleId = null) {
    for (const obstacle of this.obstacles) {
      if (obstacle.id === ignoredObstacleId) continue;
      if (pointToSegmentDistance(obstacle, start, end) < obstacle.radius) return true;
    }
    return false;
  }

  lineBlocked(start, end) {
    return this.lineBlockedByObstacle(start, end) || this.lineBlockedByCover(start, end);
  }

  canThreatSee(threat, rabbit) {
    if (!rabbit.alive) return false;
    const cover = this.coverAt(rabbit.x, rabbit.y);
    const range = this.config.threatVisionRange * (cover > 0.35 ? 0.5 : 1);
    return distance(threat, rabbit) <= range && !this.lineBlocked(threat, rabbit);
  }

  perceiveRabbit(rabbit, threat, rng) {
    const visibleResources = this.activeResources().filter(
      (resource) => distance(rabbit, resource) <= this.config.visionRange
        && !this.lineBlocked(rabbit, resource),
    );
    const visibleObstacles = this.obstacles.filter(
      (obstacle) => Math.max(0, distance(rabbit, obstacle) - obstacle.radius) <= this.config.visionRange
        && !this.lineBlockedByObstacle(rabbit, obstacle, obstacle.id)
        && !this.lineBlockedByCover(rabbit, obstacle),
    );
    const threatDistance = distance(rabbit, threat);
    const seesThreat = threatDistance <= this.config.visionRange
      && !this.lineBlocked(rabbit, threat);
    let visibleThreat = null;
    let heardThreat = null;

    if (seesThreat) {
      visibleThreat = {
        x: threat.x,
        y: threat.y,
        distance: threatDistance,
        intensity: clamp(1 - threatDistance / this.config.visionRange),
      };
    } else if (threatDistance <= this.config.soundRange) {
      const trueDirection = Math.atan2(threat.y - rabbit.y, threat.x - rabbit.x);
      const confidence = clamp(1 - threatDistance / this.config.soundRange);
      const uncertainty = lerp(0.72, 0.16, confidence);
      const noisyDirection = trueDirection + rng.range(-uncertainty, uncertainty);
      heardThreat = {
        x: Math.cos(noisyDirection),
        y: Math.sin(noisyDirection),
        confidence,
      };
    }

    return {
      visibleResources,
      visibleObstacles,
      visibleThreat,
      heardThreat,
      insideCover: this.coverAt(rabbit.x, rabbit.y),
      observedCells: null,
    };
  }

  enrichPerception(rabbit, perception) {
    const observedCells = [];
    for (let row = 0; row < rabbit.memory.rows; row += 1) {
      for (let column = 0; column < rabbit.memory.columns; column += 1) {
        const center = rabbit.memory.cellCenter(column, row);
        if (distance(rabbit, center) > this.config.visionRange) continue;
        if (this.lineBlocked(rabbit, center)) continue;

        let food = 0;
        let water = 0;
        let cover = 0;
        for (const resource of this.activeResources()) {
          const edgeDistance = Math.max(0, distance(center, resource) - resource.radius);
          if (edgeDistance > 78) continue;
          const influence = clamp(1 - edgeDistance / 78) * resource.amount;
          if (resource.kind === "grass") {
            food = Math.max(food, influence);
            cover = Math.max(cover, clamp(1 - edgeDistance / 88) * resource.cover);
          } else {
            water = Math.max(water, influence);
          }
        }
        observedCells.push({
          index: rabbit.memory.index(column, row),
          food,
          water,
          cover,
        });
      }
    }
    return { ...perception, observedCells };
  }

  constrainEntityDetailed(entity, radius = 7) {
    const minimumX = this.config.worldMargin + radius;
    const maximumX = WORLD_WIDTH - this.config.worldMargin - radius;
    const minimumY = this.config.worldMargin + radius;
    const maximumY = WORLD_HEIGHT - this.config.worldMargin - radius;
    let blocked = false;
    let boundary = false;
    let hitObstacle = null;

    if (entity.x < minimumX || entity.x > maximumX) {
      entity.x = clamp(entity.x, minimumX, maximumX);
      entity.vx *= -0.72;
      blocked = true;
      boundary = true;
    }
    if (entity.y < minimumY || entity.y > maximumY) {
      entity.y = clamp(entity.y, minimumY, maximumY);
      entity.vy *= -0.72;
      blocked = true;
      boundary = true;
    }

    for (const obstacle of this.obstacles) {
      const dx = entity.x - obstacle.x;
      const dy = entity.y - obstacle.y;
      const currentDistance = Math.hypot(dx, dy);
      const minimumDistance = obstacle.radius + radius;
      if (currentDistance >= minimumDistance) continue;

      let normalX;
      let normalY;
      if (currentDistance > 0.0001) {
        normalX = dx / currentDistance;
        normalY = dy / currentDistance;
      } else {
        const motionSpeed = vectorLength(entity.vx, entity.vy);
        normalX = motionSpeed > 0.0001 ? -entity.vx / motionSpeed : 1;
        normalY = motionSpeed > 0.0001 ? -entity.vy / motionSpeed : 0;
      }

      entity.x = obstacle.x + normalX * minimumDistance;
      entity.y = obstacle.y + normalY * minimumDistance;
      const inwardSpeed = entity.vx * normalX + entity.vy * normalY;
      if (inwardSpeed < 0) {
        entity.vx -= inwardSpeed * normalX;
        entity.vy -= inwardSpeed * normalY;
      }
      blocked = true;
      hitObstacle ??= obstacle;
    }
    return { blocked, boundary, obstacle: hitObstacle };
  }

  constrainEntity(entity, radius = 7) {
    return this.constrainEntityDetailed(entity, radius).blocked;
  }

  beginDormancy(resource, rng, tick, emit) {
    if (resource.dormant) return;
    resource.amount = 0;
    resource.dormant = true;
    resource.dormantFor = resource.kind === "grass"
      ? rng.integer(210, 370)
      : rng.integer(430, 650);
    resource.previousPosition = { x: resource.x, y: resource.y };
    emit({
      tick,
      type: "resource-dormant",
      title: `${resource.id} が休眠`,
      detail: `${resource.dormantFor} tick 後に別地点で再生`,
    });
  }

  update(rng, tick, emit) {
    for (const resource of this.resources) {
      if (!resource.dormant) continue;
      resource.dormantFor -= 1;
      if (resource.dormantFor > 0) continue;
      const next = this.findOpenPosition(
        rng,
        resource.kind === "water" ? 105 : 62,
        resource.previousPosition,
        resource.radius,
      );
      resource.x = next.x;
      resource.y = next.y;
      resource.amount = rng.range(0.75, 1);
      resource.dormant = false;
      resource.relocations += 1;
      emit({
        tick,
        type: "resource-return",
        title: `${resource.id} が再生`,
        detail: "枯渇地点ではなく、新しい関係位置へ移った",
      });
    }
  }

  interactRabbit(rabbit, rng, tick, emit) {
    const outcome = {
      food: 0,
      water: 0,
      rest: 0,
      insideCover: 0,
      terrain: "open",
    };

    for (const resource of this.activeResources()) {
      if (distance(rabbit, resource) > resource.radius + 6) continue;
      if (resource.kind === "grass") {
        outcome.insideCover = Math.max(outcome.insideCover, resource.cover);
        outcome.terrain = "grass";
        if (rabbit.hunger > 0.08) outcome.food += resource.consume(0.0062);
        if (vectorLength(rabbit.vx, rabbit.vy) < 1.1) outcome.rest += 0.0012 * resource.cover;
      } else {
        outcome.terrain = "water";
        if (rabbit.thirst > 0.06) outcome.water += resource.consume(0.0072);
      }
      if (resource.amount <= this.config.resourceDormancyThreshold) {
        this.beginDormancy(resource, rng, tick, emit);
      }
    }

    if (outcome.terrain === "water") {
      rabbit.vx *= 0.88;
      rabbit.vy *= 0.88;
    } else if (outcome.insideCover > 0.2) {
      rabbit.vx *= 0.945;
      rabbit.vy *= 0.945;
    }
    return outcome;
  }
}

const ACTIONS = [
  { x: 0, y: 0, name: "stay" },
  ...Array.from({ length: 12 }, (_, index) => {
    const angle = (index / 12) * TAU;
    return { x: Math.cos(angle), y: Math.sin(angle), name: `move-${index}` };
  }),
];

export class Rabbit {
  constructor(id, x, y, rng, config = CONFIG) {
    const angle = rng.angle();
    this.id = id;
    this.x = x;
    this.y = y;
    this.vx = Math.cos(angle) * rng.range(0.4, 0.9);
    this.vy = Math.sin(angle) * rng.range(0.4, 0.9);
    this.alive = true;
    this.causeOfDeath = null;
    this.hunger = rng.range(0.2, 0.36);
    this.thirst = rng.range(0.18, 0.34);
    this.fatigue = rng.range(0.08, 0.18);
    this.fear = rng.range(0.02, 0.07);
    this.memory = new MemoryField(config.memoryColumns, config.memoryRows);
    this.weights = {
      food: rng.range(1.05, 1.3),
      water: rng.range(1.08, 1.34),
      cover: rng.range(0.72, 0.95),
      danger: rng.range(1.8, 2.15),
      cost: rng.range(0.55, 0.78),
      memory: rng.range(0.78, 0.95),
    };
    this.reliability = { resource: 0.78, danger: 0.8, motion: 0.86 };
    this.exploration = rng.range(0.14, 0.22);
    this.soundCaution = rng.range(0.72, 0.9);
    this.H = { resource: 0, danger: 0, motion: 0 };
    this.lastError = { resource: 0, danger: 0, motion: 0 };
    this.xi = 0;
    this.thetaBase = rng.range(0.76, 0.88);
    this.planTimer = 0;
    this.decision = null;
    this.lastPerception = null;
    this.lastSawThreat = false;
    this.leapCount = 0;
    this.leapPulse = 0;
    this.leapCooldown = 0;
    this.events = [];
    this.lastIntakeLogTick = -999;
    this.lastLoggedDecision = { title: null, tick: -999 };
    this.config = config;
  }

  get thetaEffective() {
    return clamp(this.thetaBase - this.xi * 0.26, 0.5, 1.05);
  }

  log(tick, type, title, detail = "") {
    this.events.unshift({ tick, type, title, detail });
    if (this.events.length > 12) this.events.length = 12;
  }

  shouldReplan(perception) {
    if (!this.decision || this.planTimer <= 0) return true;
    if (perception.visibleThreat && !this.lastSawThreat) return true;
    return this.fear > 0.62 && this.decision.label !== "escape";
  }

  updateNeeds(perception) {
    this.hunger = clamp(this.hunger + 0.00025);
    this.thirst = clamp(this.thirst + 0.00034);
    this.fear *= 0.991;
    this.xi *= 0.9985;

    let dangerExposure = 0;
    if (perception.visibleThreat) {
      dangerExposure = perception.visibleThreat.intensity;
      this.fear = clamp(this.fear + 0.012 + dangerExposure * 0.025);
    } else if (perception.heardThreat) {
      dangerExposure = perception.heardThreat.confidence * 0.26;
      this.fear = clamp(this.fear + 0.003 + perception.heardThreat.confidence * 0.006);
    }

    if (this.decision) {
      this.decision.actual.danger = Math.max(this.decision.actual.danger, dangerExposure);
      if (perception.heardThreat && !perception.visibleThreat) this.decision.actual.heardUnseen += 1;
    }
  }

  evaluateDecision(tick) {
    if (!this.decision || this.decision.age < 3) return;
    const actual = this.decision.actual;
    const observed = {
      resource: clamp((actual.food + actual.water) * 5.2),
      danger: clamp(actual.danger),
      motion: actual.expectedDistance > 0
        ? clamp(actual.moved / actual.expectedDistance)
        : 0,
    };
    const predicted = this.decision.prediction;
    const error = {
      resource: Math.abs(observed.resource - predicted.resource),
      danger: Math.abs(observed.danger - predicted.danger),
      motion: Math.abs(observed.motion - predicted.motion),
    };
    this.lastError = error;
    this.H.resource = this.H.resource * 0.78 + error.resource * 0.72;
    this.H.danger = this.H.danger * 0.8 + error.danger * 0.82;
    this.H.motion = this.H.motion * 0.76 + error.motion * 0.64;
    this.reliability.resource = clamp(lerp(this.reliability.resource, 1 - error.resource, 0.035), 0.18, 0.98);
    this.reliability.danger = clamp(lerp(this.reliability.danger, 1 - error.danger, 0.035), 0.18, 0.98);
    this.reliability.motion = clamp(lerp(this.reliability.motion, 1 - error.motion, 0.035), 0.18, 0.98);
    this.xi = clamp(
      this.xi
        + Math.min(0.16, actual.heardUnseen * 0.004)
        + Math.min(0.12, actual.blocked * 0.045),
      0,
      1.2,
    );

    const largestError = Math.max(error.resource, error.danger, error.motion);
    if (largestError > 0.42) {
      this.log(
        tick,
        "error",
        `予測差 ${largestError.toFixed(2)}`,
        `資源 ${error.resource.toFixed(2)} / 危険 ${error.danger.toFixed(2)} / 移動 ${error.motion.toFixed(2)}`,
      );
    }
  }

  maybeLeap(tick) {
    if (this.leapCooldown > 0) return null;
    const entries = Object.entries(this.H).sort((a, b) => b[1] - a[1]);
    const [dimension, pressure] = entries[0];
    if (pressure < this.thetaEffective) return null;

    let title;
    let detail;
    if (dimension === "resource") {
      this.memory.fadeResourceMemory(0.48);
      this.reliability.resource = clamp(this.reliability.resource * 0.72, 0.18, 1);
      this.weights.memory = clamp(this.weights.memory * 0.9, 0.48, 1.2);
      this.exploration = clamp(this.exploration + 0.14, 0.08, 0.72);
      title = "Leap: 資源仮説を組み替え";
      detail = "古い資源記憶を弱め、未訪問方向の価値を上げた";
    } else if (dimension === "danger") {
      this.memory.softenDangerMemory(0.82);
      this.reliability.danger = clamp(this.reliability.danger * 0.75, 0.18, 1);
      this.weights.danger = clamp(this.weights.danger + 0.22, 1.4, 3.1);
      this.soundCaution = clamp(this.soundCaution + 0.1, 0.55, 1.3);
      title = "Leap: 危険モデルを組み替え";
      detail = "音の曖昧さを重く扱い、安全側の距離を広げた";
    } else {
      const angle = Math.atan2(this.decision?.direction.y ?? this.vy, this.decision?.direction.x ?? this.vx)
        + Math.PI * 0.66;
      this.vx = Math.cos(angle) * 1.1;
      this.vy = Math.sin(angle) * 1.1;
      this.reliability.motion = clamp(this.reliability.motion * 0.72, 0.18, 1);
      this.weights.cost = clamp(this.weights.cost + 0.08, 0.45, 1.2);
      this.exploration = clamp(this.exploration + 0.1, 0.08, 0.72);
      this.memory.stamp(this.memory.motion, this.x, this.y, 1, 2);
      title = "Leap: 経路仮説を組み替え";
      detail = "停滞した方向を避け、別の進行角へ切り替えた";
    }

    this.H.resource *= 0.28;
    this.H.danger *= 0.28;
    this.H.motion *= 0.28;
    this.leapCount += 1;
    this.leapPulse = 34;
    this.leapCooldown = 96;
    this.log(tick, "leap", title, detail);
    return { dimension, title, detail };
  }

  plan(perception, rng, tick) {
    const currentDirection = normalized(this.vx, this.vy);
    const candidates = ACTIONS.map((action) => {
      const target = {
        x: this.x + action.x * 82,
        y: this.y + action.y * 82,
      };
      const memory = this.memory.sample(target.x, target.y);
      const food = memory.food * this.hunger;
      const water = memory.water * this.thirst;
      const cover = memory.cover * (this.fear * 1.5 + this.fatigue * 0.42);
      let danger = memory.danger * (0.65 + this.fear);

      if (perception.visibleThreat) {
        const projectedDistance = Math.hypot(
          target.x - perception.visibleThreat.x,
          target.y - perception.visibleThreat.y,
        );
        danger = Math.max(danger, clamp(1 - projectedDistance / this.config.visionRange));
      } else if (perception.heardThreat && action.name !== "stay") {
        const towardSound = Math.max(
          0,
          action.x * perception.heardThreat.x + action.y * perception.heardThreat.y,
        );
        danger += towardSound * perception.heardThreat.confidence * this.soundCaution * 0.5;
      }

      const outside = target.x < 30 || target.x > WORLD_WIDTH - 30
        || target.y < 30 || target.y > WORLD_HEIGHT - 30;
      const turnCost = action.name === "stay"
        ? 0.1
        : (1 - (action.x * currentDirection.x + action.y * currentDirection.y)) * 0.18;
      const cost = memory.motion * 0.72
        + (outside ? 0.9 : 0)
        + turnCost
        + (action.name === "stay" ? 0 : this.fatigue * 0.24);
      const rest = action.name === "stay"
        ? this.fatigue * (perception.insideCover > 0.2 ? 0.95 : 0.22)
        : 0;
      const explore = (1 - memory.visits) * this.exploration * (action.name === "stay" ? 0.1 : 1);
      const resourceValue = this.reliability.resource * this.weights.memory
        * (food * this.weights.food + water * this.weights.water);
      const dangerCost = this.reliability.danger * danger * this.weights.danger;
      const motionCost = this.reliability.motion * cost * this.weights.cost;
      const total = resourceValue
        + cover * this.weights.cover
        + rest
        + explore
        - dangerCost
        - motionCost
        + rng.range(-0.018, 0.018);

      return {
        action,
        target,
        memory,
        food,
        water,
        cover,
        danger: clamp(danger),
        cost: clamp(cost),
        rest,
        explore,
        total,
      };
    });

    candidates.sort((a, b) => b.total - a.total);
    const best = candidates[0];
    let label = "explore";
    let title = "未知方向を探索";
    let reason = `未訪問価値 ${best.explore.toFixed(2)} / 移動費 ${best.cost.toFixed(2)}`;

    if (perception.visibleThreat || (this.fear > 0.4 && best.danger < 0.45)) {
      label = "escape";
      title = "脅威から退避";
      reason = `恐怖 ${this.fear.toFixed(2)} / 予測危険 ${best.danger.toFixed(2)}`;
    } else if (best.water * this.weights.water > Math.max(best.food * this.weights.food, best.explore) && this.thirst > 0.25) {
      label = "water";
      title = "水の記憶へ移動";
      reason = `渇き ${this.thirst.toFixed(2)} × 水記憶 ${best.memory.water.toFixed(2)}`;
    } else if (best.food * this.weights.food > best.explore && this.hunger > 0.25) {
      label = "food";
      title = "草の記憶へ移動";
      reason = `空腹 ${this.hunger.toFixed(2)} × 草記憶 ${best.memory.food.toFixed(2)}`;
    } else if (best.rest > 0.16) {
      label = "rest";
      title = "遮蔽内で休息";
      reason = `疲労 ${this.fatigue.toFixed(2)} / 遮蔽 ${perception.insideCover.toFixed(2)}`;
    } else if (best.cover > 0.16) {
      label = "cover";
      title = "遮蔽へ寄る";
      reason = `恐怖 ${this.fear.toFixed(2)} × 遮蔽記憶 ${best.memory.cover.toFixed(2)}`;
    }

    const resourcePrediction = clamp((best.food + best.water) * 0.42);
    const motionPrediction = best.action.name === "stay"
      ? 0.2
      : clamp(1 - best.cost * 0.46, 0.2, 1);
    this.decision = {
      label,
      title,
      reason,
      direction: { x: best.action.x, y: best.action.y },
      target: best.target,
      score: best.total,
      components: {
        food: best.food,
        water: best.water,
        cover: best.cover,
        danger: best.danger,
        cost: best.cost,
        explore: best.explore,
      },
      prediction: {
        resource: resourcePrediction,
        danger: best.danger,
        motion: motionPrediction,
      },
      actual: {
        food: 0,
        water: 0,
        danger: 0,
        moved: 0,
        expectedDistance: 0,
        blocked: 0,
        heardUnseen: 0,
      },
      age: 0,
    };
    this.planTimer = this.config.planInterval;
    if (title !== this.lastLoggedDecision.title || tick - this.lastLoggedDecision.tick >= 60) {
      this.log(tick, "decision", title, reason);
      this.lastLoggedDecision = { title, tick };
    }
  }

  advance(perception, shouldPlan, rng, tick) {
    if (!this.alive) return;
    if (this.leapPulse > 0) this.leapPulse -= 1;
    if (this.leapCooldown > 0) this.leapCooldown -= 1;
    this.updateNeeds(perception);

    if (shouldPlan) {
      this.evaluateDecision(tick);
      const staleResource = this.memory.integrate(perception, this);
      if (staleResource > 0.25) {
        this.xi = clamp(this.xi + staleResource * 0.24, 0, 1.2);
        this.log(
          tick,
          "mismatch",
          "資源記憶と視界が不一致",
          `古い期待 ${staleResource.toFixed(2)} を ξ に加算`,
        );
      }
      this.maybeLeap(tick);
      this.plan(perception, rng, tick);
    }

    this.lastPerception = perception;
    this.lastSawThreat = Boolean(perception.visibleThreat);
    this.planTimer -= 1;
    if (!this.decision) return;

    const direction = this.decision.direction;
    const fearBoost = this.fear * 1.6;
    const fatiguePenalty = this.fatigue * 0.72;
    const maximumSpeed = clamp(1.55 + fearBoost - fatiguePenalty, 0.72, 3.05);
    const desiredSpeed = this.decision.label === "rest" ? 0.08 : maximumSpeed;
    const desiredX = direction.x * desiredSpeed;
    const desiredY = direction.y * desiredSpeed;
    const steering = capVector(desiredX - this.vx, desiredY - this.vy, this.fear > 0.5 ? 0.2 : 0.13);
    this.vx += steering.x;
    this.vy += steering.y;
    const capped = capVector(this.vx, this.vy, maximumSpeed);
    this.vx = capped.x;
    this.vy = capped.y;
    this.x += this.vx;
    this.y += this.vy;
    this.decision.age += 1;
    this.decision.actual.expectedDistance += Math.max(0.12, desiredSpeed);

    const sprint = Math.max(0, vectorLength(this.vx, this.vy) - 1.55);
    this.fatigue = clamp(this.fatigue + sprint * sprint * 0.00065);
  }

  applyOutcome(outcome, tick) {
    if (!this.alive) return;
    this.hunger = clamp(this.hunger - outcome.food * 1.15);
    this.thirst = clamp(this.thirst - outcome.water * 1.38);
    this.fatigue = clamp(this.fatigue - outcome.rest);
    if (outcome.insideCover > 0.2 && vectorLength(this.vx, this.vy) < 0.75) {
      this.fatigue = clamp(this.fatigue - 0.0007 * outcome.insideCover);
    }
    if (this.decision) {
      this.decision.actual.food += outcome.food;
      this.decision.actual.water += outcome.water;
      this.decision.actual.moved += outcome.moved;
      if (outcome.blocked) this.decision.actual.blocked += 1;
    }
    this.memory.recordMotion(this.x, this.y, outcome.blocked);

    if ((outcome.food > 0 || outcome.water > 0) && tick - this.lastIntakeLogTick > 75) {
      const title = outcome.water > outcome.food ? "水を摂取" : "草を摂取";
      const value = Math.max(outcome.food, outcome.water);
      this.log(tick, "intake", title, `流入 ${value.toFixed(3)} がニーズを下げた`);
      this.lastIntakeLogTick = tick;
    }
  }

  surviveAttack(tick, threat) {
    const away = normalized(this.x - threat.x, this.y - threat.y);
    const currentSpeed = vectorLength(this.vx, this.vy);
    const escapeSpeed = clamp(currentSpeed + 0.72, 1.8, 3.05);
    this.vx = away.x * escapeSpeed;
    this.vy = away.y * escapeSpeed;
    this.fear = Math.max(this.fear, 0.86);
    this.memory.stamp(this.memory.danger, threat.x, threat.y, 1, 2);
    if (this.decision) this.decision.actual.danger = 1;
    else this.H.danger = Math.max(this.H.danger, this.thetaEffective);
    this.planTimer = 0;
    this.log(
      tick,
      "attack-survived",
      "捕食から離脱",
      "接触を生き延び、危険地点を記憶して退避行動を更新",
    );
  }

  die(tick, cause) {
    if (!this.alive) return;
    this.alive = false;
    this.causeOfDeath = cause;
    this.vx = 0;
    this.vy = 0;
    this.log(tick, "death", "行動停止", cause);
  }
}

export class Threat {
  constructor(x, y, rng, config = CONFIG) {
    const angle = rng.angle();
    this.x = x;
    this.y = y;
    this.vx = Math.cos(angle) * 0.8;
    this.vy = Math.sin(angle) * 0.8;
    this.state = "wander";
    this.targetId = null;
    this.lastSeen = null;
    this.memoryTicks = 0;
    this.restTicks = 0;
    this.attackTicks = 0;
    this.attackDirection = null;
    this.recoveryTicks = 0;
    this.config = config;
  }

  beginAttack(target) {
    const leadTicks = 3;
    this.attackDirection = normalized(
      target.x + target.vx * leadTicks - this.x,
      target.y + target.vy * leadTicks - this.y,
    );
    this.state = "attack";
    this.targetId = target.id;
    this.attackTicks = this.config.threatAttackTicks;
    this.memoryTicks = 0;
    this.lastSeen = { x: target.x, y: target.y };

    const launchSpeed = Math.min(
      this.config.threatAttackSpeed,
      Math.max(2.55, vectorLength(this.vx, this.vy)),
    );
    this.vx = this.attackDirection.x * launchSpeed;
    this.vy = this.attackDirection.y * launchSpeed;
    return {
      type: "attack",
      targetId: target.id,
      title: `Rabbit ${target.id + 1} へ捕食行動`,
      detail: `${this.config.threatAttackTicks} tick の加速後、回復状態へ移る`,
    };
  }

  beginRecovery(targetId = this.targetId) {
    const slowed = capVector(this.vx, this.vy, this.config.threatRecoverySpeed);
    this.vx = slowed.x;
    this.vy = slowed.y;
    this.state = "recover";
    this.targetId = null;
    this.attackTicks = 0;
    this.attackDirection = null;
    this.recoveryTicks = this.config.threatRecoveryTicks;
    this.memoryTicks = 0;
    this.lastSeen = null;
    return {
      type: "attack-miss",
      targetId,
      title: "捕食行動が不成立",
      detail: `${this.config.threatRecoveryTicks} tick は速度が低下する`,
    };
  }

  advanceAttack(world) {
    const desired = this.attackDirection ?? normalized(this.vx, this.vy);
    const speed = this.config.threatAttackSpeed;
    const steering = capVector(desired.x * speed - this.vx, desired.y * speed - this.vy, 0.34);
    this.vx += steering.x;
    this.vy += steering.y;
    const capped = capVector(this.vx, this.vy, speed);
    this.vx = capped.x;
    this.vy = capped.y;
    this.x += this.vx;
    this.y += this.vy;
    this.attackTicks -= 1;
    const collision = world.constrainEntityDetailed(this, 10);
    if (!collision.obstacle) return null;

    const recovery = this.beginRecovery();
    return {
      ...recovery,
      type: "attack-obstacle",
      title: "捕食行動が地形に阻まれた",
      detail: `${collision.obstacle.id} へ衝突し、低速回復へ移る`,
    };
  }

  resolveAttack(rabbits, rng, tick) {
    if (this.state !== "attack") return null;
    const target = rabbits.find((rabbit) => rabbit.id === this.targetId && rabbit.alive);
    if (!target || distance(this, target) > this.config.threatCaptureRange) return null;

    const away = normalized(target.x - this.x, target.y - this.y);
    const awaySpeed = target.vx * away.x + target.vy * away.y;
    const escaping = target.decision?.label === "escape" && awaySpeed >= 0.8;
    const captureChance = escaping
      ? this.config.threatCaptureChanceEscape
      : this.config.threatCaptureChanceUnaware;

    if (rng.next() < captureChance) {
      target.die(tick, "捕食行動を受け、離脱できなかった");
      const targetId = target.id;
      this.state = "rest";
      this.targetId = null;
      this.attackTicks = 0;
      this.attackDirection = null;
      this.recoveryTicks = 0;
      this.memoryTicks = 0;
      this.lastSeen = null;
      this.restTicks = 150;
      this.vx *= 0.24;
      this.vy *= 0.24;
      return {
        type: "capture",
        targetId,
        title: `Rabbit ${targetId + 1} を捕食`,
        detail: `${escaping ? "逃走成立" : "逃走未成立"}の接触 / 成功率 ${(captureChance * 100).toFixed(0)}%`,
      };
    }

    target.surviveAttack(tick, this);
    const event = this.beginRecovery(target.id);
    return {
      ...event,
      type: "attack-escaped",
      title: `Rabbit ${target.id + 1} が離脱`,
      detail: `${escaping ? "逃走成立" : "逃走未成立"}の接触を生還 / 捕食者は速度低下`,
    };
  }

  update(world, rabbits, rng) {
    if (this.restTicks > 0) {
      this.restTicks -= 1;
      this.state = "rest";
      this.targetId = null;
      this.memoryTicks = 0;
      this.lastSeen = null;
      this.vx *= 0.94;
      this.vy *= 0.94;
      this.x += this.vx;
      this.y += this.vy;
      world.constrainEntity(this, 10);
      return;
    }

    if (this.recoveryTicks > 0) {
      this.recoveryTicks -= 1;
      this.state = "recover";
      this.targetId = null;
      this.vx *= 0.965;
      this.vy *= 0.965;
      const slowed = capVector(this.vx, this.vy, this.config.threatRecoverySpeed);
      this.vx = slowed.x;
      this.vy = slowed.y;
      this.x += this.vx;
      this.y += this.vy;
      world.constrainEntity(this, 10);
      return null;
    }

    if (this.state === "attack") {
      if (this.attackTicks <= 0) return this.beginRecovery();
      return this.advanceAttack(world);
    }

    let visibleTarget = null;
    let nearest = Infinity;
    for (const rabbit of rabbits) {
      if (!world.canThreatSee(this, rabbit)) continue;
      const currentDistance = distance(this, rabbit);
      if (currentDistance < nearest) {
        nearest = currentDistance;
        visibleTarget = rabbit;
      }
    }

    if (visibleTarget) {
      this.state = "chase";
      this.targetId = visibleTarget.id;
      this.lastSeen = { x: visibleTarget.x, y: visibleTarget.y };
      this.memoryTicks = 82;
    } else if (this.memoryTicks > 0 && this.lastSeen) {
      this.state = "search";
      this.memoryTicks -= 1;
    } else {
      this.state = "wander";
      this.targetId = null;
      this.lastSeen = null;
    }

    if (visibleTarget && nearest <= this.config.threatAttackRange) {
      const event = this.beginAttack(visibleTarget);
      return this.advanceAttack(world) ?? event;
    }

    let desired = null;
    let speed = 1.0;
    if (this.state === "chase" && visibleTarget) {
      desired = normalized(visibleTarget.x - this.x, visibleTarget.y - this.y);
      speed = 1.86;
    } else if (this.state === "search" && this.lastSeen) {
      desired = normalized(this.lastSeen.x - this.x, this.lastSeen.y - this.y);
      speed = 1.42;
      if (distance(this, this.lastSeen) < 14) this.memoryTicks = 0;
    } else {
      if (rng.next() < 0.045) {
        const angle = Math.atan2(this.vy, this.vx) + rng.range(-0.85, 0.85);
        desired = { x: Math.cos(angle), y: Math.sin(angle) };
      } else {
        desired = normalized(this.vx, this.vy);
      }
    }

    const steering = capVector(desired.x * speed - this.vx, desired.y * speed - this.vy, 0.105);
    this.vx += steering.x;
    this.vy += steering.y;
    const capped = capVector(this.vx, this.vy, speed);
    this.vx = capped.x;
    this.vy = capped.y;
    this.x += this.vx;
    this.y += this.vy;
    world.constrainEntity(this, 10);
  }
}

export class Simulation {
  constructor({ seed = 2401, config = CONFIG } = {}) {
    this.seed = normalizeSeed(seed);
    this.config = config;
    this.rng = new SeededRandom(this.seed);
    this.tick = 0;
    this.episode = 1;
    this.resetCountdown = null;
    this.observerEvents = [];
    this.createEpisode();
    this.emitObserver({
      tick: 0,
      type: "episode",
      title: `Episode ${this.episode} 開始`,
      detail: `seed ${this.seed} / 個体記憶は相互に非共有`,
    });
  }

  createEpisode() {
    this.world = new World(this.rng, this.config);
    this.rabbits = [];
    for (let id = 0; id < this.config.rabbitCount; id += 1) {
      let position = null;
      for (let attempt = 0; attempt < 48; attempt += 1) {
        const candidate = {
          x: this.rng.range(120, WORLD_WIDTH - 120),
          y: this.rng.range(100, WORLD_HEIGHT - 100),
        };
        if (
          this.world.isPositionOpen(candidate, 7, 12)
          && this.rabbits.every((rabbit) => distance(candidate, rabbit) > 54)
        ) {
          position = candidate;
          break;
        }
      }
      position ??= this.world.findOpenPosition(this.rng, 42, null, 7);
      this.rabbits.push(new Rabbit(id, position.x, position.y, this.rng, this.config));
    }
    let threatPosition = this.world.findOpenPosition(this.rng, 80, null, 10);
    for (let attempt = 0; attempt < 24; attempt += 1) {
      const candidate = this.world.findOpenPosition(this.rng, 80, null, 10);
      if (this.rabbits.every((rabbit) => distance(candidate, rabbit) > 170)) {
        threatPosition = candidate;
        break;
      }
    }
    this.threat = new Threat(threatPosition.x, threatPosition.y, this.rng, this.config);
  }

  emitObserver(event) {
    this.observerEvents.unshift(event);
    if (this.observerEvents.length > 16) this.observerEvents.length = 16;
  }

  step(steps = 1) {
    for (let iteration = 0; iteration < steps; iteration += 1) this.stepOnce();
  }

  stepOnce() {
    this.tick += 1;
    this.world.update(this.rng, this.tick, (event) => this.emitObserver(event));
    const alive = this.rabbits.filter((rabbit) => rabbit.alive);
    const threatEvent = this.threat.update(this.world, alive, this.rng);
    if (threatEvent) this.emitObserver({ tick: this.tick, ...threatEvent });

    const attackEvent = this.threat.resolveAttack(this.rabbits, this.rng, this.tick);
    if (attackEvent) this.emitObserver({ tick: this.tick, ...attackEvent });

    for (const rabbit of this.rabbits) {
      if (!rabbit.alive) continue;
      let perception = this.world.perceiveRabbit(rabbit, this.threat, this.rng);
      const shouldPlan = rabbit.shouldReplan(perception);
      if (shouldPlan) perception = this.world.enrichPerception(rabbit, perception);
      const previous = { x: rabbit.x, y: rabbit.y };
      rabbit.advance(perception, shouldPlan, this.rng, this.tick);
      const blocked = this.world.constrainEntity(rabbit, 7);
      const moved = distance(previous, rabbit);
      const outcome = this.world.interactRabbit(
        rabbit,
        this.rng,
        this.tick,
        (event) => this.emitObserver(event),
      );
      rabbit.applyOutcome({ ...outcome, blocked, moved }, this.tick);

      if (rabbit.thirst >= 0.999) rabbit.die(this.tick, "脱水でニーズを維持できなかった");
      else if (rabbit.hunger >= 0.999) rabbit.die(this.tick, "飢餓でニーズを維持できなかった");
    }

    const livingCount = this.rabbits.filter((rabbit) => rabbit.alive).length;
    if (livingCount === 0) {
      if (this.resetCountdown === null) this.resetCountdown = this.config.resetDelay;
      this.resetCountdown -= 1;
      if (this.resetCountdown <= 0) {
        this.episode += 1;
        this.resetCountdown = null;
        this.createEpisode();
        this.emitObserver({
          tick: this.tick,
          type: "episode",
          title: `Episode ${this.episode} 開始`,
          detail: "同じ seed 系列の次エピソードへ移行",
        });
      }
    } else {
      this.resetCountdown = null;
    }
  }

  metrics() {
    return {
      tick: this.tick,
      episode: this.episode,
      living: this.rabbits.filter((rabbit) => rabbit.alive).length,
      dormant: this.world.resources.filter((resource) => resource.dormant).length,
      relocations: this.world.resources.reduce((sum, resource) => sum + resource.relocations, 0),
      leaps: this.rabbits.reduce((sum, rabbit) => sum + rabbit.leapCount, 0),
      threatState: this.threat.state,
    };
  }

  snapshot() {
    return {
      seed: this.seed,
      tick: this.tick,
      episode: this.episode,
      rabbits: this.rabbits.map((rabbit) => ({
        id: rabbit.id,
        alive: rabbit.alive,
        x: round(rabbit.x),
        y: round(rabbit.y),
        hunger: round(rabbit.hunger),
        thirst: round(rabbit.thirst),
        leaps: rabbit.leapCount,
      })),
      threat: {
        x: round(this.threat.x),
        y: round(this.threat.y),
        state: this.threat.state,
      },
      obstacles: this.world.obstacles.map((obstacle) => ({
        id: obstacle.id,
        x: round(obstacle.x),
        y: round(obstacle.y),
        radius: round(obstacle.radius),
      })),
      resources: this.world.resources.map((resource) => ({
        id: resource.id,
        x: round(resource.x),
        y: round(resource.y),
        amount: round(resource.amount),
        dormant: resource.dormant,
        relocations: resource.relocations,
      })),
    };
  }
}
