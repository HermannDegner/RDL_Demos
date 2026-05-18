/*
RDF minimal world ver3
少数戦術モード + 水場追加
*/

let herbivores = [];
let carnivores = [];
let grassPatches = [];
let waterSources = [];

const NUM_HERBIVORES = 5;
const NUM_CARNIVORES = 1;
const NUM_GRASS = 14;
const NUM_WATER = 3;

let focusHerbivore = null;

function setup() {
  createCanvas(960, 640);

  for (let i = 0; i < NUM_GRASS; i++) {
    grassPatches.push(new GrassPatch(random(60, width - 60), random(80, height - 60)));
  }
  for (let i = 0; i < NUM_WATER; i++) {
    waterSources.push(new WaterSource(random(90, width - 90), random(110, height - 90)));
  }
  for (let i = 0; i < NUM_HERBIVORES; i++) {
    herbivores.push(new Herbivore(random(width), random(height), i));
  }
  for (let i = 0; i < NUM_CARNIVORES; i++) {
    carnivores.push(new Carnivore(random(width), random(height)));
  }

  focusHerbivore = herbivores[0] || null;
}

function draw() {
  background(12, 14, 18, 50);
  drawGrid();

  for (const g of grassPatches) { g.update(); g.show(); }
  for (const w of waterSources) { w.show(); }
  for (const c of carnivores) { if (c.alive) { c.update(); c.show(); } }
  for (const h of herbivores) { if (h.alive) { h.update(); h.show(); } }

  drawUI();
  drawFocusOverlay();
}

function drawGrid() {
  stroke(255, 255, 255, 10); strokeWeight(1);
  for (let x = 0; x < width; x += 40) line(x, 0, x, height);
  for (let y = 0; y < height; y += 40) line(0, y, width, y);
}

function drawUI() {
  noStroke(); fill(255); textSize(14);
  text('RDF minimal world ver3 / 少数戦術モード + 水場', 20, 24);
  text('predator: 1 / herbivore: 5 / extinction allowed / sensors: vision + sound', 20, 44);
  text('green patch: grass(food + cover) / blue pond: water / red line: predator', 20, 64);
  const aliveHerb = herbivores.filter(h => h.alive).length;
  const aliveCarn = carnivores.filter(c => c.alive).length;
  text(`alive herbivores: ${aliveHerb} / alive carnivores: ${aliveCarn}`, 20, 88);
}

function drawFocusOverlay() {
  if (!focusHerbivore || !focusHerbivore.alive) {
    focusHerbivore = herbivores.find(h => h.alive) || null;
  }
  if (!focusHerbivore) return;
  const x = 20, y = height - 100;
  noStroke(); fill(0, 0, 0, 120);
  rect(x - 10, y - 20, 320, 88, 8);
  fill(255); textSize(13);
  text(`focus herbivore #${focusHerbivore.id}`, x, y);
  text(`hunger: ${focusHerbivore.hunger.toFixed(2)}`, x, y + 18);
  text(`fear: ${focusHerbivore.fear.toFixed(2)}`, x + 110, y + 18);
  text(`norad: ${focusHerbivore.norad.toFixed(2)}`, x + 200, y + 18);
  text(`heat: ${focusHerbivore.H.toFixed(2)}`, x, y + 38);
  text(`thirst: ${focusHerbivore.thirst.toFixed(2)}`, x + 110, y + 38);
  text(`state: ${focusHerbivore.stateLabel()}`, x + 220, y + 38);
}

function lineBlockedByGrass(a, b) {
  for (const g of grassPatches) {
    if (distancePointToSegment(g.pos, a, b) < g.radius * 0.9) return true;
  }
  return false;
}

function distancePointToSegment(p, a, b) {
  const ab = p5.Vector.sub(b, a);
  const ap = p5.Vector.sub(p, a);
  const abLenSq = ab.magSq();
  if (abLenSq === 0) return p5.Vector.dist(p, a);
  let t = constrain(ap.dot(ab) / abLenSq, 0, 1);
  return p5.Vector.dist(p, p5.Vector.add(a, ab.mult(t)));
}

class GrassPatch {
  constructor(x, y) {
    this.pos = createVector(x, y);
    this.radius = random(20, 34);
    this.nutrition = random(0.45, 1.0);
    this.cover = random(0.35, 1.0);
    this.growRate = random(0.0008, 0.0018);
  }
  update() { this.nutrition = min(1.0, this.nutrition + this.growRate); }
  consume(amount) { const eaten = min(this.nutrition, amount); this.nutrition -= eaten; return eaten; }
  show() {
    noStroke();
    const alpha = map(this.nutrition, 0, 1, 30, 130);
    fill(40, 170, 70, alpha); circle(this.pos.x, this.pos.y, this.radius * 2);
    fill(90, 220, 120, alpha * 0.9); circle(this.pos.x, this.pos.y, this.radius * 1.1);
  }
}

class WaterSource {
  constructor(x, y) {
    this.pos = createVector(x, y);
    this.radius = random(24, 38);
  }
  show() {
    noStroke();
    fill(40, 100, 220, 120); circle(this.pos.x, this.pos.y, this.radius * 2);
    fill(110, 180, 255, 150); circle(this.pos.x, this.pos.y, this.radius * 1.2);
  }
}

class Herbivore {
  constructor(x, y, id) {
    this.id = id; this.alive = true;
    this.pos = createVector(x, y);
    this.vel = p5.Vector.random2D().mult(random(0.6, 1.2));
    this.acc = createVector(0, 0);
    this.M = random(0.91, 0.965); this.H = 0; this.theta = random(2.0, 3.0);
    this.hunger = random(0.15, 0.7); this.thirst = random(0.1, 0.55);
    this.fear = 0; this.norad = 0;
    this.wFood = random(0.7, 1.2); this.wWater = random(0.9, 1.4);
    this.wPred = random(1.1, 1.9); this.wCover = random(0.55, 1.2); this.wSound = random(0.35, 0.7);
    this.isEating = false; this.eatTimer = 0; this.targetGrass = null;
    this.cooldown = 0; this.justLeaped = 0;
    this.lastForces = { food: createVector(0,0), water: createVector(0,0), cover: createVector(0,0), pred: createVector(0,0), sound: createVector(0,0) };
  }

  stateLabel() {
    if (!this.alive) return 'dead';
    if (this.isEating) return 'eating';
    if (this.thirst > 0.75) return 'drink';
    if (this.fear > 0.55) return 'escape';
    if (this.norad > 0.35) return 'alert';
    return 'graze';
  }

  update() {
    if (!this.alive) return;
    this.acc.mult(0);
    this.hunger = constrain(this.hunger + 0.0018, 0, 1);
    this.thirst = constrain(this.thirst + 0.0026, 0, 1);
    this.fear *= 0.94;
    this.norad = constrain(this.norad * 0.93 + this.fear * 0.16, 0, 1);
    if (this.cooldown > 0) this.cooldown--;
    if (this.justLeaped > 0) this.justLeaped--;

    if (this.isEating) { this.updateEating(); this.wrap(); return; }

    const sensed = this.senseWorld();
    const inertialFlow = this.vel.copy().mult(this.M);
    let totalForce = createVector(0, 0);
    totalForce.add(sensed.food.copy().mult(this.wFood));
    totalForce.add(sensed.water.copy().mult(this.wWater));
    totalForce.add(sensed.cover.copy().mult(this.wCover));
    totalForce.add(sensed.pred.copy().mult(this.wPred));
    totalForce.add(sensed.sound.copy().mult(this.wSound));
    this.lastForces = sensed;

    const error = p5.Vector.sub(totalForce, inertialFlow).mag();
    this.H += error * 0.014; this.H *= 0.992;
    totalForce.add(p5.Vector.random2D().mult(this.H * 0.10));
    if (this.H > this.theta && this.cooldown === 0) this.leap();

    this.acc.add(totalForce); this.vel.add(this.acc);
    this.vel.limit(map(this.norad, 0, 1, 1.9, 4.2));
    this.pos.add(this.vel); this.wrap();

    if (this.targetGrass) {
      const d = p5.Vector.dist(this.pos, this.targetGrass.pos);
      if (d < this.targetGrass.radius * 0.45 && this.targetGrass.nutrition > 0.08 && this.fear < 0.45 && this.thirst < 0.75) {
        this.isEating = true; this.eatTimer = int(random(26, 44)); this.vel.mult(0);
      }
    }
    this.tryDrink();
  }

  updateEating() {
    this.vel.mult(0.55);
    if (this.vel.mag() < 0.03) this.vel.mult(0);
    if (this.targetGrass) { const eaten = this.targetGrass.consume(0.012); this.hunger = max(0, this.hunger - eaten * 0.9); }
    this.tryDrink();
    const nearestPred = this.nearestPredatorDistance();
    if (nearestPred < 90) { this.isEating = false; this.fear = min(1, this.fear + 0.5); this.norad = min(1, this.norad + 0.4); return; }
    this.eatTimer--;
    if (this.eatTimer <= 0 || !this.targetGrass || this.targetGrass.nutrition <= 0.03) this.isEating = false;
  }

  senseWorld() {
    let foodForce = createVector(0,0), waterForce = createVector(0,0);
    let coverForce = createVector(0,0), predForce = createVector(0,0), soundForce = createVector(0,0);
    let bestFoodScore = -Infinity; this.targetGrass = null;

    for (const g of grassPatches) {
      const toGrass = p5.Vector.sub(g.pos, this.pos);
      const d = max(toGrass.mag(), 1); const dir = toGrass.copy().normalize();
      const foodWeight = this.hunger * (1.0 - this.norad);
      const coverWeight = this.norad * 1.5 + this.fear * 0.9;
      const foodStrength = (g.nutrition * foodWeight) / d;
      const coverStrength = (g.cover * coverWeight) / d;
      if (d < 220) foodForce.add(dir.copy().mult(foodStrength));
      if (d < 180) coverForce.add(dir.copy().mult(coverStrength));
      const score = foodStrength * 1.3 + coverStrength;
      if (score > bestFoodScore) { bestFoodScore = score; this.targetGrass = g; }
    }

    for (const w of waterSources) {
      const toWater = p5.Vector.sub(w.pos, this.pos);
      const d = max(toWater.mag(), 1); const dir = toWater.copy().normalize();
      if (d < 260) waterForce.add(dir.mult((this.thirst * 1.7) / d));
    }

    for (const c of carnivores) {
      if (!c.alive) continue;
      const d = max(p5.Vector.dist(this.pos, c.pos), 1);
      if (d < 150 && !lineBlockedByGrass(this.pos, c.pos)) {
        const away = p5.Vector.sub(this.pos, c.pos).normalize();
        predForce.add(away.mult(map(d, 0, 150, 3.0, 0, true)));
        this.fear = min(1, this.fear + 0.12); this.norad = min(1, this.norad + 0.08);
      }
      if (d < 260) {
        const away = p5.Vector.sub(this.pos, c.pos).normalize();
        soundForce.add(away.mult(map(d, 0, 260, 0.8, 0, true)));
        this.fear = min(1, this.fear + 0.025); this.norad = min(1, this.norad + 0.02);
      }
    }

    return { food: foodForce, water: waterForce, cover: coverForce, pred: predForce, sound: soundForce };
  }

  tryDrink() {
    for (const w of waterSources) {
      if (p5.Vector.dist(this.pos, w.pos) < w.radius * 0.8) this.thirst = max(0, this.thirst - 0.02);
    }
  }

  nearestPredatorDistance() {
    let best = Infinity;
    for (const c of carnivores) { if (!c.alive) continue; best = min(best, p5.Vector.dist(this.pos, c.pos)); }
    return best;
  }

  leap() {
    this.wFood = constrain(this.wFood + random(-0.25, 0.35), 0.25, 1.8);
    this.wWater = constrain(this.wWater + random(-0.2, 0.25), 0.4, 2.0);
    this.wPred = constrain(this.wPred + random(-0.2, 0.3), 0.7, 2.4);
    this.wCover = constrain(this.wCover + random(-0.2, 0.35), 0.2, 1.8);
    this.wSound = constrain(this.wSound + random(-0.1, 0.15), 0.15, 1.0);
    this.theta = constrain(this.theta + random(-0.2, 0.2), 1.6, 4.0);
    this.vel.rotate(random(-PI / 2, PI / 2)); this.H *= 0.28; this.cooldown = 50; this.justLeaped = 18;
  }

  die() { this.alive = false; }

  wrap() {
    if (this.pos.x < 0) this.pos.x = width; if (this.pos.x > width) this.pos.x = 0;
    if (this.pos.y < 0) this.pos.y = height; if (this.pos.y > height) this.pos.y = 0;
  }

  show() {
    if (!this.alive) return;
    push(); translate(this.pos.x, this.pos.y);
    noFill(); stroke(80, 220, 255, map(this.H, 0, 4, 20, 180, true)); circle(0, 0, 10 + this.H * 10);
    if (this.justLeaped > 0) { stroke(255, 220, 80, 180); circle(0, 0, 22); }
    noStroke();
    fill(lerpColor(color(120, 180, 255), color(255, 160, 120), this.norad));
    rotate(this.vel.heading()); triangle(8, 0, -6, -5, -6, 5);
    if (this.isEating) { fill(255, 255, 255, 180); circle(0, -10, 4); }
    pop();
    if (this === focusHerbivore) {
      drawVector(this.pos, this.lastForces.food, color(80, 220, 120), 180);
      drawVector(this.pos, this.lastForces.water, color(160, 120, 255), 180);
      drawVector(this.pos, this.lastForces.cover, color(80, 220, 255), 180);
      drawVector(this.pos, this.lastForces.pred, color(255, 80, 80), 180);
    }
  }
}

class Carnivore {
  constructor(x, y) {
    this.alive = true;
    this.pos = createVector(x, y); this.vel = p5.Vector.random2D().mult(random(1.0, 1.4));
    this.acc = createVector(0, 0);
    this.M = random(0.91, 0.97); this.H = 0; this.theta = random(2.0, 3.0);
    this.hunger = random(0.25, 0.8); this.thirst = random(0.1, 0.55); this.focus = random(0.25, 0.7);
    this.wPrey = random(0.9, 1.4); this.wWater = random(0.85, 1.35);
    this.wCover = random(0.45, 1.0); this.wSound = random(0.15, 0.4);
    this.targetPrey = null; this.cooldown = 0; this.justLeaped = 0;
  }

  update() {
    if (!this.alive) return;
    this.acc.mult(0);
    this.hunger = constrain(this.hunger + 0.0012, 0, 1);
    this.thirst = constrain(this.thirst + 0.0022, 0, 1);
    this.focus *= 0.992;
    if (this.cooldown > 0) this.cooldown--;
    if (this.justLeaped > 0) this.justLeaped--;

    const sensed = this.senseWorld();
    const inertialFlow = this.vel.copy().mult(this.M);
    let totalForce = createVector(0, 0);
    totalForce.add(sensed.prey.copy().mult(this.wPrey));
    totalForce.add(sensed.water.copy().mult(this.wWater));
    totalForce.add(sensed.cover.copy().mult(this.wCover));
    totalForce.add(sensed.sound.copy().mult(this.wSound));

    const error = p5.Vector.sub(totalForce, inertialFlow).mag();
    this.H += error * 0.012; this.H *= 0.993;
    totalForce.add(p5.Vector.random2D().mult(this.H * 0.08));
    if (this.H > this.theta && this.cooldown === 0) this.leap();

    this.acc.add(totalForce); this.vel.add(this.acc); this.vel.limit(3.2);
    this.pos.add(this.vel); this.wrap(); this.tryCatch(); this.tryDrink();
  }

  senseWorld() {
    let preyForce = createVector(0,0), waterForce = createVector(0,0);
    let coverForce = createVector(0,0), soundForce = createVector(0,0);
    let bestScore = -Infinity; this.targetPrey = null;

    for (const h of herbivores) {
      if (!h.alive) continue;
      const d = max(p5.Vector.dist(this.pos, h.pos), 1);
      if (d < 170 && !lineBlockedByGrass(this.pos, h.pos)) {
        const dir = p5.Vector.sub(h.pos, this.pos).normalize();
        const preyStrength = (this.hunger * 2.0 + 0.3) / d;
        preyForce.add(dir.mult(preyStrength));
        if (preyStrength > bestScore) { bestScore = preyStrength; this.targetPrey = h; }
      }
      if (d < 240) {
        const dir = p5.Vector.sub(h.pos, this.pos).normalize();
        soundForce.add(dir.mult(map(d, 0, 240, 0.45, 0, true)));
      }
    }

    for (const w of waterSources) {
      const toWater = p5.Vector.sub(w.pos, this.pos);
      const d = max(toWater.mag(), 1);
      if (d < 260) waterForce.add(toWater.copy().normalize().mult((this.thirst * 1.6) / d));
    }

    for (const g of grassPatches) {
      const toGrass = p5.Vector.sub(g.pos, this.pos);
      const d = max(toGrass.mag(), 1);
      if (d < 180) coverForce.add(toGrass.copy().normalize().mult((g.cover * (this.hunger * 0.35 + 0.2)) / d));
    }

    return { prey: preyForce, water: waterForce, cover: coverForce, sound: soundForce };
  }

  tryCatch() {
    for (const h of herbivores) {
      if (!h.alive) continue;
      if (p5.Vector.dist(this.pos, h.pos) < 10) {
        h.die(); this.hunger = max(0, this.hunger - 0.5);
        this.thirst = max(0, this.thirst - 0.08); this.focus = min(1, this.focus + 0.35);
      }
    }
  }

  tryDrink() {
    for (const w of waterSources) {
      if (p5.Vector.dist(this.pos, w.pos) < w.radius * 0.8) this.thirst = max(0, this.thirst - 0.018);
    }
  }

  leap() {
    this.wPrey = constrain(this.wPrey + random(-0.2, 0.3), 0.3, 2.0);
    this.wWater = constrain(this.wWater + random(-0.15, 0.2), 0.4, 1.9);
    this.wCover = constrain(this.wCover + random(-0.1, 0.18), 0.1, 1.4);
    this.wSound = constrain(this.wSound + random(-0.08, 0.12), 0.05, 0.7);
    this.theta = constrain(this.theta + random(-0.2, 0.2), 1.6, 4.0);
    this.vel.rotate(random(-PI / 3, PI / 3)); this.H *= 0.35; this.cooldown = 50; this.justLeaped = 18;
  }

  wrap() {
    if (this.pos.x < 0) this.pos.x = width; if (this.pos.x > width) this.pos.x = 0;
    if (this.pos.y < 0) this.pos.y = height; if (this.pos.y > height) this.pos.y = 0;
  }

  show() {
    if (!this.alive) return;
    push(); translate(this.pos.x, this.pos.y);
    noFill(); stroke(255, 120, 90, map(this.H, 0, 4, 18, 130, true)); circle(0, 0, 12 + this.H * 8);
    if (this.justLeaped > 0) { stroke(255, 220, 80, 180); circle(0, 0, 24); }
    noStroke(); fill(220, 70, 70); rotate(this.vel.heading()); triangle(12, 0, -8, -6, -8, 6);
    pop();
  }
}

function drawVector(origin, vec, col, scale = 220) {
  const v = vec.copy().mult(scale);
  stroke(col); strokeWeight(2);
  line(origin.x, origin.y, origin.x + v.x, origin.y + v.y);
}
