/*
RDF minimal world ver2.1
少数戦術モード

変更点:
- 少数戦術モードに変更（捕食1 / 被食5 / 全滅あり）
- センサーを視覚と音に限定
- 視覚は短距離・高精度・草で遮断
- 音は草を貫通するが、主に警戒スイッチを上げるだけで単独行動決定は弱い
- 草は食料 + 隠れ場の複合誘導源
- 捕食者は捕食中に停止し、危険接近で中断
*/

let herbivores = [];
let carnivores = [];
let grassPatches = [];

const NUM_HERBIVORES = 5;
const NUM_CARNIVORES = 1;
const NUM_GRASS = 14;
const STEALTH_TRIGGER = 0.62;
const GRASS_EDGE_BAND = 10;

let focusHerbivore = null;

function setup() {
  createCanvas(960, 640);

  for (let i = 0; i < NUM_GRASS; i++) {
    grassPatches.push(new GrassPatch(random(60, width - 60), random(80, height - 60)));
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

  for (const g of grassPatches) {
    g.update();
    g.show();
  }

  for (const c of carnivores) {
    if (c.alive) {
      c.update();
      c.show();
    }
  }

  for (const h of herbivores) {
    if (h.alive) {
      h.update();
      h.show();
    }
  }

  drawUI();
  drawFocusOverlay();
}

function drawGrid() {
  stroke(255, 255, 255, 10);
  strokeWeight(1);
  for (let x = 0; x < width; x += 40) line(x, 0, x, height);
  for (let y = 0; y < height; y += 40) line(0, y, width, y);
}

function drawUI() {
  noStroke();
  fill(255);
  textSize(14);
  text('RDF minimal world ver2.1 / 少数戦術モード', 20, 24);
  text('predator: 1 / herbivore: 5 / extinction allowed / sensors: vision + sound', 20, 44);
  text('green patch: grass(food + cover) / blue line: food / cyan line: cover / red line: predator', 20, 64);

  const aliveHerb = herbivores.filter(h => h.alive).length;
  const aliveCarn = carnivores.filter(c => c.alive).length;
  text(`alive herbivores: ${aliveHerb} / alive carnivores: ${aliveCarn}`, 20, 88);
}

function drawFocusOverlay() {
  if (!focusHerbivore || !focusHerbivore.alive) {
    focusHerbivore = herbivores.find(h => h.alive) || null;
  }
  if (!focusHerbivore) return;

  const x = 20;
  const y = height - 90;
  noStroke();
  fill(0, 0, 0, 120);
  rect(x - 10, y - 20, 280, 78, 8);

  fill(255);
  textSize(13);
  text(`focus herbivore #${focusHerbivore.id}`, x, y);
  text(`hunger: ${focusHerbivore.hunger.toFixed(2)}`, x, y + 18);
  text(`fear: ${focusHerbivore.fear.toFixed(2)}`, x + 110, y + 18);
  text(`norad: ${focusHerbivore.norad.toFixed(2)}`, x + 200, y + 18);
  text(`heat: ${focusHerbivore.H.toFixed(2)}`, x, y + 36);
  text(`state: ${focusHerbivore.stateLabel()}`, x + 110, y + 36);
}

function lineBlockedByGrass(a, b) {
  for (const g of grassPatches) {
    if (distancePointToSegment(g.pos, a, b) < g.radius * 0.9) {
      return true;
    }
  }
  return false;
}

function distancePointToSegment(p, a, b) {
  const ab = p5.Vector.sub(b, a);
  const ap = p5.Vector.sub(p, a);
  const abLenSq = ab.magSq();
  if (abLenSq === 0) return p5.Vector.dist(p, a);
  let t = ap.dot(ab) / abLenSq;
  t = constrain(t, 0, 1);
  const proj = p5.Vector.add(a, ab.mult(t));
  return p5.Vector.dist(p, proj);
}

class GrassPatch {
  constructor(x, y) {
    this.pos = createVector(x, y);
    this.radius = random(20, 34);
    this.nutrition = random(0.45, 1.0);
    this.cover = random(0.35, 1.0);
    this.growRate = random(0.0008, 0.0018);
  }

  update() {
    this.nutrition = min(1.0, this.nutrition + this.growRate);
  }

  consume(amount) {
    const eaten = min(this.nutrition, amount);
    this.nutrition -= eaten;
    return eaten;
  }

  show() {
    noStroke();
    const alpha = map(this.nutrition, 0, 1, 30, 130);
    fill(40, 170, 70, alpha);
    circle(this.pos.x, this.pos.y, this.radius * 2);
    fill(90, 220, 120, alpha * 0.9);
    circle(this.pos.x, this.pos.y, this.radius * 1.1);
  }
}

class Herbivore {
  constructor(x, y, id) {
    this.id = id;
    this.alive = true;
    this.pos = createVector(x, y);
    this.vel = p5.Vector.random2D().mult(random(0.6, 1.2));
    this.acc = createVector(0, 0);
    this.M = random(0.91, 0.965);
    this.H = 0;
    this.theta = random(2.0, 3.0);
    this.hunger = random(0.15, 0.7);
    this.fear = 0;
    this.norad = 0;
    this.stealthLevel = 0;
    this.wFood = random(0.7, 1.2);
    this.wPred = random(1.1, 1.9);
    this.wCover = random(0.55, 1.2);
    this.wSound = random(0.35, 0.7);
    this.isEating = false;
    this.eatTimer = 0;
    this.targetGrass = null;
    this.cooldown = 0;
    this.justLeaped = 0;
    this.lastForces = {
      food: createVector(0, 0),
      cover: createVector(0, 0),
      pred: createVector(0, 0),
      sound: createVector(0, 0),
    };
  }

  stateLabel() {
    if (!this.alive) return 'dead';
    if (this.isEating) return 'eating';
    if (this.fear > 0.55) return 'escape';
    if (this.norad > 0.35) return 'alert';
    return 'graze';
  }

  update() {
    if (!this.alive) return;
    this.acc.mult(0);
    this.hunger = constrain(this.hunger + 0.0018, 0, 1);
    this.fear *= 0.94;
    this.norad = constrain(this.norad * 0.93 + this.fear * 0.16, 0, 1);
    if (this.cooldown > 0) this.cooldown--;
    if (this.justLeaped > 0) this.justLeaped--;

    if (this.isEating) {
      this.updateEating();
      this.wrap();
      return;
    }

    const sensed = this.senseWorld();
    const inertialFlow = this.vel.copy().mult(this.M);
    this.stealthLevel = lerp(this.stealthLevel, sensed.bestPreyLikelihood || 0, 0.06);

    let totalForce = createVector(0, 0);
    totalForce.add(sensed.food.copy().mult(this.wFood));
    totalForce.add(sensed.cover.copy().mult(this.wCover));
    totalForce.add(sensed.pred.copy().mult(this.wPred));
    totalForce.add(sensed.sound.copy().mult(this.wSound));
    this.lastForces = sensed;

    const error = p5.Vector.sub(totalForce, inertialFlow).mag();
    this.H += error * 0.014;
    this.H *= 0.992;
    totalForce.add(p5.Vector.random2D().mult(this.H * 0.10));

    if (this.H > this.theta && this.cooldown === 0) this.leap();

    this.acc.add(totalForce);
    this.vel.add(this.acc);
    const maxSpeed = map(this.norad, 0, 1, 1.9, 4.2);
    this.vel.limit(maxSpeed);
    this.pos.add(this.vel);
    this.wrap();

    if (this.targetGrass) {
      const d = p5.Vector.dist(this.pos, this.targetGrass.pos);
      if (d < this.targetGrass.radius * 0.45 && this.targetGrass.nutrition > 0.08 && this.fear < 0.45) {
        this.isEating = true;
        this.eatTimer = int(random(26, 44));
        this.vel.mult(0);
      }
    }
  }

  updateEating() {
    this.vel.mult(0.55);
    if (this.vel.mag() < 0.03) this.vel.mult(0);
    if (this.targetGrass) {
      const eaten = this.targetGrass.consume(0.012);
      this.hunger = max(0, this.hunger - eaten * 0.9);
    }
    const nearestPred = this.nearestPredatorDistance();
    if (nearestPred < 90) {
      this.isEating = false;
      this.fear = min(1, this.fear + 0.5);
      this.norad = min(1, this.norad + 0.4);
      return;
    }
    this.eatTimer--;
    if (this.eatTimer <= 0 || !this.targetGrass || this.targetGrass.nutrition <= 0.03) {
      this.isEating = false;
    }
  }

  senseWorld() {
    let foodForce = createVector(0, 0);
    let coverForce = createVector(0, 0);
    let predForce = createVector(0, 0);
    let soundForce = createVector(0, 0);
    let bestFoodScore = -Infinity;
    this.targetGrass = null;

    for (const g of grassPatches) {
      const toGrass = p5.Vector.sub(g.pos, this.pos);
      const d = max(toGrass.mag(), 1);
      const dir = toGrass.copy().normalize();
      const foodWeight = this.hunger * (1.0 - this.norad);
      const coverWeight = this.norad * 1.5 + this.fear * 0.9;
      const foodStrength = (g.nutrition * foodWeight) / d;
      const coverStrength = (g.cover * coverWeight) / d;
      if (d < 220) foodForce.add(dir.copy().mult(foodStrength));
      if (d < 180) coverForce.add(dir.copy().mult(coverStrength));
      const score = foodStrength * 1.3 + coverStrength;
      if (score > bestFoodScore) { bestFoodScore = score; this.targetGrass = g; }
    }

    for (const c of carnivores) {
      if (!c.alive) continue;
      const toPred = p5.Vector.sub(c.pos, this.pos);
      const d = max(toPred.mag(), 1);
      if (d < 150 && !lineBlockedByGrass(this.pos, c.pos)) {
        const away = p5.Vector.sub(this.pos, c.pos).normalize();
        const strength = map(d, 0, 150, 3.0, 0, true);
        predForce.add(away.mult(strength));
        this.fear = min(1, this.fear + 0.12);
        this.norad = min(1, this.norad + 0.08);
      }
      if (d < 260) {
        const away = p5.Vector.sub(this.pos, c.pos).normalize();
        const strength = map(d, 0, 260, 0.8, 0, true);
        soundForce.add(away.mult(strength));
        this.fear = min(1, this.fear + 0.025);
        this.norad = min(1, this.norad + 0.02);
      }
    }

    return { food: foodForce, cover: coverForce, pred: predForce, sound: soundForce };
  }

  nearestPredatorDistance() {
    let best = Infinity;
    for (const c of carnivores) {
      if (!c.alive) continue;
      best = min(best, p5.Vector.dist(this.pos, c.pos));
    }
    return best;
  }

  leap() {
    this.wFood = constrain(this.wFood + random(-0.25, 0.35), 0.25, 1.8);
    this.wPred = constrain(this.wPred + random(-0.2, 0.3), 0.7, 2.4);
    this.wCover = constrain(this.wCover + random(-0.2, 0.35), 0.2, 1.8);
    this.wSound = constrain(this.wSound + random(-0.1, 0.15), 0.15, 1.0);
    this.theta = constrain(this.theta + random(-0.2, 0.2), 1.6, 4.0);
    this.vel.rotate(random(-PI / 2, PI / 2));
    this.H *= 0.28;
    this.cooldown = 50;
    this.justLeaped = 18;
  }

  die() { this.alive = false; }

  wrap() {
    if (this.pos.x < 0) this.pos.x = width;
    if (this.pos.x > width) this.pos.x = 0;
    if (this.pos.y < 0) this.pos.y = height;
    if (this.pos.y > height) this.pos.y = 0;
  }

  show() {
    if (!this.alive) return;
    push();
    translate(this.pos.x, this.pos.y);
    noFill();
    stroke(80, 220, 255, map(this.H, 0, 4, 20, 180, true));
    circle(0, 0, 10 + this.H * 10);
    if (this.justLeaped > 0) { stroke(255, 220, 80, 180); circle(0, 0, 22); }
    noStroke();
    const bodyColor = lerpColor(color(120, 180, 255), color(255, 160, 120), this.norad);
    fill(bodyColor);
    rotate(this.vel.heading());
    triangle(8, 0, -6, -5, -6, 5);
    if (this.isEating) { fill(255, 255, 255, 180); circle(0, -10, 4); }
    pop();

    if (this === focusHerbivore) {
      drawVector(this.pos, this.lastForces.food, color(80, 220, 120), 180);
      drawVector(this.pos, this.lastForces.cover, color(80, 220, 255), 180);
      drawVector(this.pos, this.lastForces.pred, color(255, 80, 80), 180);
    }
  }
}

class Carnivore {
  constructor(x, y) {
    this.alive = true;
    this.pos = createVector(x, y);
    this.vel = p5.Vector.random2D().mult(random(1.0, 1.4));
    this.acc = createVector(0, 0);
    this.M = random(0.91, 0.97);
    this.H = 0;
    this.theta = random(2.0, 3.0);
    this.hunger = random(0.25, 0.8);
    this.focus = random(0.25, 0.7);
    this.wPrey = random(0.9, 1.4);
    this.wCover = random(0.45, 1.0);
    this.wSound = random(0.15, 0.4);
    this.stealthLevel = 0;
    this.targetAmbushGrass = null;
    this.cooldown = 0;
    this.justLeaped = 0;
    this.targetPrey = null;
  }

  update() {
    if (!this.alive) return;
    this.acc.mult(0);
    this.hunger = constrain(this.hunger + 0.0012, 0, 1);
    this.focus *= 0.992;
    if (this.cooldown > 0) this.cooldown--;
    if (this.justLeaped > 0) this.justLeaped--;

    const sensed = this.senseWorld();
    const inertialFlow = this.vel.copy().mult(this.M);
    this.stealthLevel = lerp(this.stealthLevel, sensed.bestPreyLikelihood, 0.06);

    let totalForce = createVector(0, 0);
    totalForce.add(sensed.prey.copy().mult(this.wPrey));
    totalForce.add(sensed.cover.copy().mult(this.wCover));
    totalForce.add(sensed.sound.copy().mult(this.wSound));

    const error = p5.Vector.sub(totalForce, inertialFlow).mag();
    this.H += error * 0.012;
    this.H *= 0.993;
    totalForce.add(p5.Vector.random2D().mult(this.H * 0.08));
    if (this.H > this.theta && this.cooldown === 0) this.leap();

    this.acc.add(totalForce);
    this.vel.add(this.acc);
    const maxSpeed = (2.6 + this.focus * 1.4) - this.stealthLevel * 1.4;
    this.vel.limit(max(0.85, maxSpeed));

    if (this.stealthLevel > 0.45 && this.vel.mag() < 0.22) {
      if (this.targetAmbushGrass) {
        const toGrass = p5.Vector.sub(this.targetAmbushGrass.pos, this.pos).normalize();
        const tangent = createVector(-toGrass.y, toGrass.x).mult(0.28);
        this.vel.add(tangent);
      } else {
        this.vel.add(p5.Vector.random2D().mult(0.18));
      }
    }
    this.pos.add(this.vel);
    this.wrap();
    this.tryCatch();
  }

  senseWorld() {
    let preyForce = createVector(0, 0);
    let coverForce = createVector(0, 0);
    let soundForce = createVector(0, 0);
    let bestScore = -Infinity;
    let bestPreyLikelihood = 0;
    this.targetPrey = null;
    this.targetAmbushGrass = null;

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
        const soundStrength = map(d, 0, 240, 0.45, 0, true);
        soundForce.add(dir.mult(soundStrength));
      }
    }

    for (const g of grassPatches) {
      const toGrass = p5.Vector.sub(g.pos, this.pos);
      const d = max(toGrass.mag(), 1);
      if (d < 220) {
        const dir = toGrass.copy().normalize();
        const ambushWeight = this.hunger * 0.8 + this.focus * 0.7;
        const coverStrength = (g.cover * ambushWeight) / d;
        coverForce.add(dir.copy().mult(coverStrength));
        const preyLikelihood = g.nutrition * 0.75 + g.cover * 0.95;
        if (preyLikelihood > bestPreyLikelihood) { bestPreyLikelihood = preyLikelihood; this.targetAmbushGrass = g; }
        if (preyLikelihood > STEALTH_TRIGGER) {
          const edgeRadius = max(6, g.radius + GRASS_EDGE_BAND);
          const radialError = d - edgeRadius;
          const towardEdge = dir.copy().mult(constrain(radialError * 0.03, -0.9, 0.9));
          const tangent = createVector(-dir.y, dir.x).mult(0.18 + this.focus * 0.12);
          const stealthStrength = preyLikelihood * (0.45 + this.hunger * 0.55);
          coverForce.add(towardEdge.mult(stealthStrength));
          coverForce.add(tangent.mult(stealthStrength * 0.6));
        }
      }
    }

    return { prey: preyForce, cover: coverForce, sound: soundForce, bestPreyLikelihood };
  }

  tryCatch() {
    for (const h of herbivores) {
      if (!h.alive) continue;
      const d = p5.Vector.dist(this.pos, h.pos);
      if (d < 10) {
        h.die();
        this.hunger = max(0, this.hunger - 0.5);
        this.focus = min(1, this.focus + 0.35);
      }
    }
  }

  leap() {
    this.wPrey = constrain(this.wPrey + random(-0.2, 0.3), 0.3, 2.0);
    this.wCover = constrain(this.wCover + random(-0.2, 0.3), 0.1, 1.8);
    this.wSound = constrain(this.wSound + random(-0.08, 0.12), 0.05, 0.7);
    this.theta = constrain(this.theta + random(-0.2, 0.2), 1.6, 4.0);
    this.vel.rotate(random(-PI / 3, PI / 3));
    this.H *= 0.35;
    this.cooldown = 50;
    this.justLeaped = 18;
  }

  wrap() {
    if (this.pos.x < 0) this.pos.x = width;
    if (this.pos.x > width) this.pos.x = 0;
    if (this.pos.y < 0) this.pos.y = height;
    if (this.pos.y > height) this.pos.y = 0;
  }

  show() {
    if (!this.alive) return;
    push();
    translate(this.pos.x, this.pos.y);
    noFill();
    stroke(255, 120, 90, map(this.H, 0, 4, 18, 130, true));
    circle(0, 0, 12 + this.H * 8);
    if (this.justLeaped > 0) { stroke(255, 220, 80, 180); circle(0, 0, 24); }
    noStroke();
    fill(
      lerp(220, 255, this.stealthLevel * 0.15),
      lerp(70, 170, this.stealthLevel * 0.2),
      lerp(70, 120, this.stealthLevel * 0.15)
    );
    rotate(this.vel.heading());
    triangle(12, 0, -8, -6, -8, 6);
    if (this.stealthLevel > 0.35) {
      noFill(); stroke(180, 220, 180, 90 + this.stealthLevel * 60); circle(0, 0, 26);
    }
    pop();
  }
}

function drawVector(origin, vec, col, scale = 220) {
  const v = vec.copy().mult(scale);
  stroke(col);
  strokeWeight(2);
  line(origin.x, origin.y, origin.x + v.x, origin.y + v.y);
}
