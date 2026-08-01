/*
RDF Rabbit Demo v3.1 : Active Threat + 5 Rabbits + Reset
*/

let rabbits = [];
let grassPatches = [];
let waterSources = [];
let hunter;
let resetTimer = 0;

const NUM_RABBITS = 5;
const NUM_GRASS = 12;
const NUM_WATER = 2;

function setup() {
  createCanvas(960, 640);
  initWorld();
}

function initWorld() {
  grassPatches = []; waterSources = []; rabbits = []; resetTimer = 0;

  for (let i = 0; i < NUM_GRASS; i++) {
    grassPatches.push(new GrassPatch(random(70, width - 70), random(70, height - 70)));
  }
  for (let i = 0; i < NUM_WATER; i++) {
    waterSources.push(new WaterSource(random(120, width - 120), random(120, height - 120)));
  }
  for (let i = 0; i < NUM_RABBITS; i++) {
    rabbits.push(new Rabbit(random(width * 0.2, width * 0.8), random(height * 0.2, height * 0.8), i));
  }
  hunter = new ActiveThreat(random(width), random(height));
}

function draw() {
  background(18, 20, 24, 50);
  drawGrid();
  for (const g of grassPatches) { g.update(); g.show(); }
  for (const w of waterSources) { w.update(); w.show(); }
  const aliveRabbits = rabbits.filter(r => r.alive);
  hunter.update(aliveRabbits);
  hunter.show();
  for (const rabbit of rabbits) { rabbit.update(hunter); rabbit.show(); }
  drawUI(aliveRabbits.length);
  if (aliveRabbits.length === 0) {
    resetTimer++;
    drawResetOverlay();
    if (resetTimer > 90) initWorld();
  }
}

function drawGrid() {
  stroke(255, 255, 255, 10); strokeWeight(1);
  for (let x = 0; x < width; x += 40) line(x, 0, x, height);
  for (let y = 0; y < height; y += 40) line(0, y, width, y);
}

function drawUI(aliveCount) {
  noStroke(); fill(255); textSize(14);
  text('RDF Rabbit Demo v3.1 / 5 rabbits / active threat / death + reset', 20, 24);
  text(`alive rabbits: ${aliveCount} / hunter mode: ${hunter.mode}`, 20, 44);
  const focus = rabbits.find(r => r.alive) || rabbits[0];
  const x = 20, y = height - 118;
  fill(0, 0, 0, 120); rect(x - 10, y - 18, 520, 106, 8);
  fill(255); textSize(13);
  text(`focus rabbit: #${focus.id} ${focus.alive ? '' : '(dead)'}`, x, y);
  text(`hunger: ${focus.hunger.toFixed(2)}`, x + 140, y);
  text(`thirst: ${focus.thirst.toFixed(2)}`, x + 240, y);
  text(`fatigue: ${focus.fatigue.toFixed(2)}`, x + 340, y);
  text(`fear: ${focus.fear.toFixed(2)}`, x + 440, y);
  text(`mode: ${focus.label()}`, x, y + 22);
  text(`speed: ${focus.vel.mag().toFixed(2)}`, x + 140, y + 22);
  text(`hunter target: ${hunter.target ? '#' + hunter.target.id : 'none'}`, x + 240, y + 22);
  text(`dist: ${hunter.target ? p5.Vector.dist(hunter.pos, hunter.target.pos).toFixed(1) : '-'}`, x + 410, y + 22);
  text(`eat-flow: ${focus.intakeFood.toFixed(3)}`, x, y + 44);
  text(`drink-flow: ${focus.intakeWater.toFixed(3)}`, x + 140, y + 44);
  text(`rest-flow: ${focus.restFlux.toFixed(3)}`, x + 280, y + 44);
  text(`anchor cd: ${focus.anchorCooldown}`, x + 420, y + 44);
}

function drawResetOverlay() {
  fill(0, 0, 0, 140); rect(0, 0, width, height);
  fill(255); textAlign(CENTER, CENTER); textSize(28);
  text('All rabbits dead - resetting...', width / 2, height / 2);
  textAlign(LEFT, BASELINE);
}

class GrassPatch {
  constructor(x, y) {
    this.pos = createVector(x, y); this.radius = random(22, 36);
    this.nutrition = random(0.55, 1.0); this.cover = random(0.35, 1.0);
    this.stopEase = random(0.45, 1.0); this.growRate = random(0.0008, 0.0018);
  }
  update() { this.nutrition = min(1.0, this.nutrition + this.growRate); }
  consume(amount) { const eaten = min(this.nutrition, amount); this.nutrition -= eaten; return eaten; }
  show() {
    noStroke();
    const alpha = map(this.nutrition, 0, 1, 22, 140);
    fill(40, 170, 70, alpha); circle(this.pos.x, this.pos.y, this.radius * 2);
    fill(90, 220, 120, alpha * 0.9); circle(this.pos.x, this.pos.y, this.radius * 1.1);
  }
}

class WaterSource {
  constructor(x, y) {
    this.pos = createVector(x, y); this.radius = random(28, 42);
    this.hydration = random(0.85, 1.0); this.available = random(0.6, 1.0);
    this.stopEase = random(0.4, 0.8); this.recoverRate = random(0.0008, 0.0014);
  }
  update() { this.available = min(1.0, this.available + this.recoverRate); }
  drink(amount) { const drank = min(this.available, amount); this.available -= drank; return drank; }
  show() {
    noStroke();
    const alpha = map(this.available, 0, 1, 40, 150);
    fill(40, 100, 220, alpha); circle(this.pos.x, this.pos.y, this.radius * 2);
    fill(110, 180, 255, alpha * 0.95); circle(this.pos.x, this.pos.y, this.radius * 1.2);
  }
}

class ActiveThreat {
  constructor(x, y) {
    this.pos = createVector(x, y); this.vel = p5.Vector.random2D().mult(0.9);
    this.acc = createVector(0, 0); this.radius = 18; this.mode = 'wander';
    this.detectRange = 230; this.soundRange = 260; this.killRange = 12;
    this.memory = 0; this.lastSeen = null; this.target = null;
  }

  canSee(rabbit) {
    if (!rabbit || !rabbit.alive) return false;
    const d = p5.Vector.dist(this.pos, rabbit.pos);
    if (d > this.detectRange) return false;
    for (const g of grassPatches) {
      if (distancePointToSegment(g.pos, this.pos, rabbit.pos) < g.radius * 0.9) return false;
    }
    return true;
  }

  chooseTarget(rabbits) {
    let best = null, bestD = Infinity;
    for (const rabbit of rabbits) {
      if (!rabbit.alive) continue;
      const d = p5.Vector.dist(this.pos, rabbit.pos);
      if (this.canSee(rabbit) && d < bestD) { best = rabbit; bestD = d; }
    }
    return best;
  }

  update(rabbits) {
    this.acc.mult(0);
    const visibleTarget = this.chooseTarget(rabbits);
    if (visibleTarget) { this.target = visibleTarget; this.mode = 'chase'; this.memory = 85; this.lastSeen = visibleTarget.pos.copy(); }
    else if (this.memory > 0 && this.lastSeen) { this.mode = 'search'; this.memory--; if (this.target && !this.target.alive) this.target = null; }
    else { this.mode = 'wander'; this.lastSeen = null; this.target = null; }

    if (this.mode === 'chase' && this.target && this.target.alive) {
      this.acc.add(p5.Vector.sub(this.target.pos, this.pos).normalize().mult(0.18));
    } else if (this.mode === 'search' && this.lastSeen) {
      const dir = p5.Vector.sub(this.lastSeen, this.pos);
      if (dir.mag() > 5) this.acc.add(dir.normalize().mult(0.1));
      if (random() < 0.04) this.acc.add(p5.Vector.random2D().mult(0.08));
    } else {
      if (random() < 0.06) this.acc.add(p5.Vector.random2D().mult(0.12));
    }

    this.vel.add(this.acc);
    this.vel.limit(this.mode === 'chase' ? 2.5 : this.mode === 'search' ? 1.8 : 1.2);
    this.pos.add(this.vel);
    wrapPosition(this.pos);

    if (this.target && this.target.alive && p5.Vector.dist(this.pos, this.target.pos) < this.killRange) {
      this.target.die(); this.mode = 'wander'; this.target = null; this.lastSeen = null; this.memory = 0;
    }
  }

  show() {
    noFill(); stroke(255, 70, 70, this.mode === 'chase' ? 130 : 70);
    circle(this.pos.x, this.pos.y, this.radius * 6.8);
    push(); translate(this.pos.x, this.pos.y); noStroke();
    fill(this.mode === 'chase' ? color(255, 80, 80) : color(210, 90, 90));
    rotate(this.vel.heading()); triangle(14, 0, -10, -7, -10, 7); pop();
  }
}

class Rabbit {
  constructor(x, y, id) {
    this.id = id; this.alive = true;
    this.pos = createVector(x, y); this.vel = p5.Vector.random2D().mult(0.8);
    this.acc = createVector(0, 0); this.M = 0.935; this.H = 0;
    this.hunger = random(0.2, 0.35); this.thirst = random(0.18, 0.32);
    this.fatigue = random(0.08, 0.16); this.fear = random(0.04, 0.1);
    this.noiseScale = 0.05;
    this.intakeFood = 0; this.intakeWater = 0; this.restFlux = 0;
    this.isAnchored = false; this.anchorType = null; this.anchorTarget = null; this.anchorCooldown = 0;
    this.lastForces = { food: createVector(0,0), water: createVector(0,0), cover: createVector(0,0), danger: createVector(0,0), cost: createVector(0,0) };
  }

  die() { this.alive = false; this.isAnchored = false; this.vel.set(0,0); this.acc.set(0,0); }

  label() {
    if (!this.alive) return 'dead';
    if (this.isAnchored && this.anchorType === 'grass') return 'anchored-grass';
    if (this.isAnchored && this.anchorType === 'water') return 'anchored-water';
    if (this.fear > 0.58) return 'escape-bias';
    if (this.thirst > 0.62) return 'water-bias';
    if (this.fatigue > 0.62) return 'rest-bias';
    if (this.hunger > 0.62) return 'food-bias';
    return 'mixed-flow';
  }

  update(hunter) {
    if (!this.alive) return;
    this.acc.mult(0); this.intakeFood = 0; this.intakeWater = 0; this.restFlux = 0;
    if (this.anchorCooldown > 0) this.anchorCooldown--;
    this.updateNeeds();

    if (this.isAnchored) {
      this.senseDangerOnly(hunter); this.applyAnchoredFlows();
      if (this.fear > 0.42) this.clearAnchor(35);
      return;
    }

    const field = this.buildGradientField(hunter);
    this.lastForces = field;
    const inertialFlow = p5.Vector.mult(this.vel, this.M);
    let total = createVector(0,0);
    total.add(field.food); total.add(field.water); total.add(field.cover);
    total.add(field.cost); total.add(field.danger);

    const error = p5.Vector.sub(total, inertialFlow).mag();
    this.H += error * 0.012 + this.fatigue * 0.0015; this.H *= 0.988;
    total.add(p5.Vector.random2D().mult(this.noiseScale + this.H * 0.03));
    this.vel.add(total); this.vel.limit(this.computeMaxSpeed());
    this.pos.add(this.vel); wrapPosition(this.pos);
    this.resolveLocalInteractions(); this.tryAnchorPhase();
  }

  updateNeeds() {
    this.hunger = constrain(this.hunger + 0.0012, 0, 1);
    this.thirst = constrain(this.thirst + 0.0018, 0, 1);
    this.fear *= 0.97;
    const thirstExcess = max(0, this.thirst - 0.48);
    const hungerExcess = max(0, this.hunger - 0.54);
    const fatigueExcess = max(0, this.fatigue - 0.60);
    this.H += thirstExcess * thirstExcess * 0.12;
    this.H += hungerExcess * hungerExcess * 0.08;
    this.H += fatigueExcess * fatigueExcess * 0.05;
    const speed = this.vel.mag();
    const sprintExcess = max(0, speed - 1.35);
    this.fatigue = constrain(this.fatigue + sprintExcess * sprintExcess * 0.0032, 0, 1);
    if (!this.isAnchored && speed < 0.4) this.fatigue = max(0, this.fatigue - 0.0018);
  }

  senseDangerOnly(hunter) {
    const d = max(p5.Vector.dist(this.pos, hunter.pos), 1);
    if (d < hunter.soundRange) this.fear = min(1, this.fear + 0.0025);
    if (hunter.canSee(this) && d < hunter.detectRange) this.fear = min(1, this.fear + 0.012);
  }

  buildGradientField(hunter) {
    let F_food = createVector(0,0), F_water = createVector(0,0);
    let F_cover = createVector(0,0), F_danger = createVector(0,0), F_cost = createVector(0,0);
    const thirstUrgency = max(0, this.thirst - 0.45) * 1.8;

    for (const g of grassPatches) {
      const to = p5.Vector.sub(g.pos, this.pos);
      const dRaw = to.mag(), dEff = max(dRaw, g.radius * 0.7);
      const dir = to.copy().normalize();
      const foodPull = this.hunger * g.nutrition * (1.0 - min(0.55, thirstUrgency * 0.28)) / dEff;
      const coverPull = (this.fear * 1.6) * g.cover / dEff;
      const restPull = this.fatigue * g.stopEase / dEff;
      if (dRaw < 240) F_food.add(p5.Vector.mult(dir, foodPull));
      if (dRaw < 210) F_cover.add(p5.Vector.mult(dir, coverPull + restPull));
    }

    for (const w of waterSources) {
      const to = p5.Vector.sub(w.pos, this.pos);
      const dRaw = to.mag(), dEff = max(dRaw, w.radius * 0.7);
      const dir = to.copy().normalize();
      const waterPull = this.thirst * w.hydration * w.available * 3.2 / dEff;
      const restPull = this.fatigue * w.stopEase * 0.4 / dEff;
      if (dRaw < 280) F_water.add(p5.Vector.mult(dir, waterPull));
      if (dRaw < 220) F_cover.add(p5.Vector.mult(dir, restPull));
    }

    const d = max(p5.Vector.dist(this.pos, hunter.pos), 1);
    const away = p5.Vector.sub(this.pos, hunter.pos).normalize();
    if (d < hunter.soundRange) { F_danger.add(p5.Vector.mult(away, (0.15 + this.fear) * 0.8 / d)); this.fear = min(1, this.fear + 0.0018); }
    if (hunter.canSee(this) && d < hunter.detectRange) { F_danger.add(p5.Vector.mult(away, (0.35 + this.fear) * 2.8 / d)); this.fear = min(1, this.fear + 0.0075); }

    const wallMargin = 38;
    if (this.pos.x < wallMargin) F_cost.add(createVector(0.02, 0));
    if (this.pos.x > width - wallMargin) F_cost.add(createVector(-0.02, 0));
    if (this.pos.y < wallMargin) F_cost.add(createVector(0, 0.02));
    if (this.pos.y > height - wallMargin) F_cost.add(createVector(0, -0.02));

    return { food: F_food, water: F_water, cover: F_cover, danger: F_danger, cost: F_cost };
  }

  computeMaxSpeed() {
    return map(this.fear, 0, 1, 1.4, 4.0) * map(this.fatigue, 0, 1, 1.0, 0.56);
  }

  resolveLocalInteractions() {
    for (const g of grassPatches) {
      const d = p5.Vector.dist(this.pos, g.pos);
      const overlap = max(0, 1 - d / (g.radius * 0.95));
      const calmness = (1 - this.fear) * max(0, 1 - this.vel.mag() / 1.25);
      const intake = overlap * calmness;
      if (intake > 0) {
        this.intakeFood = max(this.intakeFood, intake * g.nutrition * 0.010);
        this.restFlux = max(this.restFlux, intake * g.stopEase * 0.004);
        this.vel.mult(1.0 - overlap * 0.16);
      }
    }
    for (const w of waterSources) {
      const d = p5.Vector.dist(this.pos, w.pos);
      const overlap = max(0, 1 - d / (w.radius * 0.95));
      const calmness = (1 - this.fear) * max(0, 1 - this.vel.mag() / 1.35);
      const intake = overlap * calmness;
      if (intake > 0) {
        this.intakeWater = max(this.intakeWater, intake * w.hydration * w.available * 0.012);
        this.restFlux = max(this.restFlux, intake * w.stopEase * 0.003);
        this.vel.mult(1.0 - overlap * 0.14);
      }
    }
    this.applyIntakeFlows();
  }

  applyIntakeFlows() {
    if (this.intakeFood > 0) {
      let remaining = this.intakeFood;
      for (const g of grassPatches) {
        const d = p5.Vector.dist(this.pos, g.pos);
        if (d < g.radius * 0.95 && remaining > 0) {
          const eaten = g.consume(min(remaining, 0.010));
          this.hunger = max(0, this.hunger - eaten * 0.9); remaining -= eaten;
        }
      }
    }
    if (this.intakeWater > 0) {
      let remaining = this.intakeWater;
      for (const w of waterSources) {
        const d = p5.Vector.dist(this.pos, w.pos);
        if (d < w.radius * 0.95 && remaining > 0) {
          const drank = w.drink(min(remaining, 0.012));
          this.thirst = max(0, this.thirst - drank * 1.3); remaining -= drank;
        }
      }
    }
    if (this.restFlux > 0) this.fatigue = max(0, this.fatigue - this.restFlux);
  }

  tryAnchorPhase() {
    if (this.anchorCooldown > 0 || this.isAnchored || !this.alive) return false;
    for (const g of grassPatches) {
      const overlap = max(0, 1 - p5.Vector.dist(this.pos, g.pos) / (g.radius * 0.95));
      if (overlap > 0.72 && this.fear < 0.28 && (this.hunger > 0.45 || this.fatigue > 0.42) && g.nutrition > 0.18) {
        this.isAnchored = true; this.anchorType = 'grass'; this.anchorTarget = g; return true;
      }
    }
    for (const w of waterSources) {
      const overlap = max(0, 1 - p5.Vector.dist(this.pos, w.pos) / (w.radius * 0.95));
      if (overlap > 0.72 && this.fear < 0.32 && this.thirst > 0.38 && w.available > 0.15) {
        this.isAnchored = true; this.anchorType = 'water'; this.anchorTarget = w; return true;
      }
    }
    return false;
  }

  applyAnchoredFlows() {
    if (!this.alive) return;
    this.vel.set(0,0); this.acc.set(0,0);
    this.intakeFood = 0; this.intakeWater = 0; this.restFlux = 0;
    if (!this.anchorTarget) { this.clearAnchor(10); return; }

    if (this.anchorType === 'grass') {
      const g = this.anchorTarget;
      const overlap = max(0, 1 - p5.Vector.dist(this.pos, g.pos) / (g.radius * 0.95));
      const intake = overlap * (1 - this.fear);
      this.intakeFood = intake * g.nutrition * 0.012;
      this.restFlux = intake * g.stopEase * 0.006;
      const eaten = g.consume(min(this.intakeFood, 0.012));
      this.hunger = max(0, this.hunger - eaten * 0.9);
      this.fatigue = max(0, this.fatigue - this.restFlux);
      if (this.fear > 0.42 || g.nutrition < 0.08 || this.thirst > 0.68 || this.hunger < 0.16 || this.fatigue < 0.22 || this.H > 1.2) {
        this.releaseFromPatch(g, 70);
      }
      return;
    }

    if (this.anchorType === 'water') {
      const w = this.anchorTarget;
      const overlap = max(0, 1 - p5.Vector.dist(this.pos, w.pos) / (w.radius * 0.95));
      const intake = overlap * (1 - this.fear);
      this.intakeWater = intake * w.hydration * w.available * 0.015;
      this.restFlux = intake * w.stopEase * 0.004;
      const drank = w.drink(min(this.intakeWater, 0.015));
      this.thirst = max(0, this.thirst - drank * 1.3);
      this.fatigue = max(0, this.fatigue - this.restFlux);
      if (this.fear > 0.42 || w.available < 0.07 || this.thirst < 0.22 || this.H > 1.2) {
        this.releaseFromPatch(w, 70);
      }
      return;
    }
  }

  releaseFromPatch(patch, cooldown) {
    const away = p5.Vector.sub(this.pos, patch.pos);
    if (away.mag() < 0.001) away.set(random(-1,1), random(-1,1));
    this.vel = away.normalize().copy().mult(1.8); this.H *= 0.35;
    wrapPosition(this.pos); this.clearAnchor(cooldown);
  }

  clearAnchor(cooldown) {
    this.isAnchored = false; this.anchorType = null; this.anchorTarget = null; this.anchorCooldown = cooldown;
  }

  show() {
    if (!this.alive) {
      push(); translate(this.pos.x, this.pos.y); stroke(120);
      line(-8,-8,8,8); line(-8,8,8,-8); pop(); return;
    }
    drawVector(this.pos, this.lastForces.food, color(80, 220, 120), 180);
    drawVector(this.pos, this.lastForces.water, color(160, 120, 255), 180);
    drawVector(this.pos, this.lastForces.cover, color(80, 220, 255), 180);
    drawVector(this.pos, this.lastForces.danger, color(255, 80, 80), 230);
    push(); translate(this.pos.x, this.pos.y);
    noFill(); stroke(100, 220, 255, map(this.H, 0, 3, 20, 150, true)); circle(0, 0, 12 + this.H * 10);
    if (this.isAnchored) { stroke(255, 255, 180, 160); noFill(); circle(0, 0, 24); }
    noStroke();
    fill(lerpColor(color(210, 220, 235), color(255, 180, 140), this.fear));
    rotate(this.vel.heading()); ellipse(0, 0, 18, 12); ellipse(-7, -5, 5, 12); ellipse(-1, -6, 5, 12);
    pop();
  }
}

function distancePointToSegment(p, a, b) {
  const ab = p5.Vector.sub(b, a), ap = p5.Vector.sub(p, a);
  const abLenSq = ab.magSq();
  if (abLenSq === 0) return p5.Vector.dist(p, a);
  let t = constrain(ap.dot(ab) / abLenSq, 0, 1);
  return p5.Vector.dist(p, p5.Vector.add(a, p5.Vector.mult(ab, t)));
}

function drawVector(origin, vec, col, scale = 220) {
  const v = p5.Vector.mult(vec, scale);
  stroke(col); strokeWeight(2);
  line(origin.x, origin.y, origin.x + v.x, origin.y + v.y);
}

function wrapPosition(pos) {
  if (pos.x < 0) pos.x = width; if (pos.x > width) pos.x = 0;
  if (pos.y < 0) pos.y = height; if (pos.y > height) pos.y = 0;
}
