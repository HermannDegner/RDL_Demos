/*
RDF minimal world ver2

変更点:
- 草が「食料 + 隠れ場」の複合誘導源に変更
- 捕食者は捕食中に停止
- 捕食者が草を待ち伏せ隠れ場として利用
- 覚醒 / ノルアドレナリンによって、同じ草の意味が変わる

メモ:
- これはゲームAIというよりRDFの最小デモ実装
- オブジェクトを直接追うのではなく、勾配の力学結果として流動する
*/

let herbivores = [];
let carnivores = [];
let grassPatches = [];

const NUM_HERBIVORES = 40;
const NUM_CARNIVORES = 3;
const NUM_GRASS = 80;

function setup() {
  createCanvas(960, 640);

  for (let i = 0; i < NUM_GRASS; i++) {
    grassPatches.push(new GrassPatch(random(width), random(height)));
  }

  for (let i = 0; i < NUM_HERBIVORES; i++) {
    herbivores.push(new Herbivore(random(width), random(height)));
  }

  for (let i = 0; i < NUM_CARNIVORES; i++) {
    carnivores.push(new Carnivore(random(width), random(height)));
  }
}

function draw() {
  background(12, 14, 18, 50);
  drawGrid();

  for (const g of grassPatches) {
    g.update();
    g.show();
  }

  for (const c of carnivores) {
    c.update();
    c.show();
  }

  for (const h of herbivores) {
    h.update();
    h.show();
  }

  drawUI();
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
  text('RDF minimal world ver2', 20, 24);
  text('green area: grass patch / herbivore = blue / carnivore = red', 20, 44);
  text('cyan ring: heat / yellow ring: leap / grass = food + cover', 20, 64);
}

class GrassPatch {
  constructor(x, y) {
    this.pos = createVector(x, y);
    this.radius = random(18, 34);
    this.nutrition = random(0.45, 1.0);
    this.cover = random(0.25, 1.0);
    this.growRate = random(0.0008, 0.0022);
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
  constructor(x, y) {
    this.pos = createVector(x, y);
    this.vel = p5.Vector.random2D().mult(random(0.6, 1.4));
    this.acc = createVector(0, 0);

    this.M = random(0.90, 0.965);
    this.H = 0;
    this.theta = random(2.0, 3.2);

    this.hunger = random(0.15, 0.7);
    this.fear = 0;
    this.norad = 0;

    this.wFood = random(0.7, 1.25);
    this.wPred = random(1.0, 1.8);
    this.wCover = random(0.5, 1.1);

    this.isEating = false;
    this.eatTimer = 0;
    this.targetGrass = null;
    this.cooldown = 0;
    this.justLeaped = 0;
  }

  update() {
    this.acc.mult(0);

    this.hunger = constrain(this.hunger + 0.0018, 0, 1);
    this.fear *= 0.94;
    this.norad = constrain(this.norad * 0.92 + this.fear * 0.15, 0, 1);

    if (this.cooldown > 0) this.cooldown--;
    if (this.justLeaped > 0) this.justLeaped--;

    if (this.isEating) {
      this.updateEating();
      this.wrap();
      return;
    }

    const sensed = this.senseWorld();
    const inertialFlow = this.vel.copy().mult(this.M);

    let totalForce = createVector(0, 0);
    totalForce.add(sensed.food.copy().mult(this.wFood));
    totalForce.add(sensed.cover.copy().mult(this.wCover));
    totalForce.add(sensed.pred.copy().mult(this.wPred));

    const error = p5.Vector.sub(totalForce, inertialFlow).mag();
    this.H += error * 0.014;
    this.H *= 0.992;

    const noise = p5.Vector.random2D().mult(this.H * 0.12);
    totalForce.add(noise);

    if (this.H > this.theta && this.cooldown === 0) {
      this.leap();
    }

    this.acc.add(totalForce);
    this.vel.add(this.acc);

    const maxSpeed = map(this.norad, 0, 1, 2.0, 4.3);
    this.vel.limit(maxSpeed);
    this.pos.add(this.vel);
    this.wrap();

    if (this.targetGrass) {
      const d = p5.Vector.dist(this.pos, this.targetGrass.pos);
      if (d < this.targetGrass.radius * 0.45 && this.targetGrass.nutrition > 0.08) {
        this.isEating = true;
        this.eatTimer = int(random(24, 44));
        this.vel.mult(0);
      }
    }
  }

  updateEating() {
    this.vel.mult(0.6);
    if (this.vel.mag() < 0.03) this.vel.mult(0);

    if (this.targetGrass) {
      const eaten = this.targetGrass.consume(0.012);
      this.hunger = max(0, this.hunger - eaten * 0.9);
    }

    const nearestPred = this.nearestPredatorDistance();
    if (nearestPred < 80) {
      this.isEating = false;
      this.fear = min(1, this.fear + 0.45);
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

    let bestFoodScore = -Infinity;
    this.targetGrass = null;

    for (const g of grassPatches) {
      const toGrass = p5.Vector.sub(g.pos, this.pos);
      const d = max(toGrass.mag(), 1);
      const dir = toGrass.copy().normalize();

      const foodWeight = this.hunger * (1.0 - this.norad);
      const coverWeight = this.norad * 1.4 + this.fear * 0.9;

      const foodStrength = (g.nutrition * foodWeight) / d;
      const coverStrength = (g.cover * coverWeight) / d;

      if (d < 220) foodForce.add(dir.copy().mult(foodStrength));
      if (d < 180) coverForce.add(dir.copy().mult(coverStrength));

      const score = foodStrength * 1.3 + coverStrength;
      if (score > bestFoodScore) {
        bestFoodScore = score;
        this.targetGrass = g;
      }
    }

    for (const c of carnivores) {
      const away = p5.Vector.sub(this.pos, c.pos);
      const d = away.mag();
      if (d < 180) {
        away.normalize();
        const strength = map(d, 0, 180, 2.8, 0, true);
        predForce.add(away.mult(strength));
        this.fear = min(1, this.fear + 0.08);
      }
    }

    return { food: foodForce, cover: coverForce, pred: predForce };
  }

  nearestPredatorDistance() {
    let best = Infinity;
    for (const c of carnivores) {
      best = min(best, p5.Vector.dist(this.pos, c.pos));
    }
    return best;
  }

  leap() {
    this.wFood = constrain(this.wFood + random(-0.25, 0.35), 0.25, 1.8);
    this.wPred = constrain(this.wPred + random(-0.2, 0.3), 0.7, 2.4);
    this.wCover = constrain(this.wCover + random(-0.2, 0.35), 0.2, 1.8);
    this.theta = constrain(this.theta + random(-0.2, 0.2), 1.6, 4.0);

    this.vel.rotate(random(-PI / 2, PI / 2));
    this.H *= 0.28;
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
    push();
    translate(this.pos.x, this.pos.y);

    noFill();
    stroke(80, 220, 255, map(this.H, 0, 4, 20, 180, true));
    circle(0, 0, 10 + this.H * 10);

    if (this.justLeaped > 0) {
      stroke(255, 220, 80, 180);
      circle(0, 0, 22);
    }

    noStroke();
    const bodyColor = lerpColor(color(120, 180, 255), color(255, 160, 120), this.norad);
    fill(bodyColor);
    rotate(this.vel.heading());
    triangle(8, 0, -6, -5, -6, 5);

    if (this.isEating) {
      fill(255, 255, 255, 180);
      circle(0, -10, 4);
    }

    pop();
  }
}

class Carnivore {
  constructor(x, y) {
    this.pos = createVector(x, y);
    this.vel = p5.Vector.random2D().mult(random(1.0, 1.6));
    this.acc = createVector(0, 0);

    this.M = random(0.91, 0.97);
    this.H = 0;
    this.theta = random(2.0, 3.0);

    this.hunger = random(0.2, 0.8);
    this.focus = random(0.2, 0.7);

    this.wPrey = random(0.8, 1.4);
    this.wCover = random(0.4, 1.0);

    this.cooldown = 0;
    this.justLeaped = 0;
    this.targetPrey = null;
  }

  update() {
    this.acc.mult(0);
    this.hunger = constrain(this.hunger + 0.0012, 0, 1);
    this.focus *= 0.992;

    if (this.cooldown > 0) this.cooldown--;
    if (this.justLeaped > 0) this.justLeaped--;

    const sensed = this.senseWorld();
    const inertialFlow = this.vel.copy().mult(this.M);

    let totalForce = createVector(0, 0);
    totalForce.add(sensed.prey.copy().mult(this.wPrey));
    totalForce.add(sensed.cover.copy().mult(this.wCover));

    const error = p5.Vector.sub(totalForce, inertialFlow).mag();
    this.H += error * 0.012;
    this.H *= 0.993;

    totalForce.add(p5.Vector.random2D().mult(this.H * 0.08));

    if (this.H > this.theta && this.cooldown === 0) {
      this.leap();
    }

    this.acc.add(totalForce);
    this.vel.add(this.acc);
    this.vel.limit(3.0 + this.focus * 1.8);
    this.pos.add(this.vel);
    this.wrap();

    this.tryCatch();
  }

  senseWorld() {
    let preyForce = createVector(0, 0);
    let coverForce = createVector(0, 0);

    let bestScore = -Infinity;
    this.targetPrey = null;

    for (const h of herbivores) {
      const toPrey = p5.Vector.sub(h.pos, this.pos);
      const d = max(toPrey.mag(), 1);
      if (d < 260) {
        const dir = toPrey.copy().normalize();
        const preyStrength = (this.hunger * 1.8 + 0.3) / d;
        preyForce.add(dir.mult(preyStrength));

        if (preyStrength > bestScore) {
          bestScore = preyStrength;
          this.targetPrey = h;
        }
      }
    }

    for (const g of grassPatches) {
      const toGrass = p5.Vector.sub(g.pos, this.pos);
      const d = max(toGrass.mag(), 1);
      if (d < 180) {
        const dir = toGrass.copy().normalize();
        const ambushWeight = this.hunger * 0.8 + this.focus * 0.7;
        const coverStrength = (g.cover * ambushWeight) / d;
        coverForce.add(dir.mult(coverStrength));
      }
    }

    return { prey: preyForce, cover: coverForce };
  }

  tryCatch() {
    for (const h of herbivores) {
      const d = p5.Vector.dist(this.pos, h.pos);
      if (d < 10) {
        h.pos = createVector(random(width), random(height));
        h.vel = p5.Vector.random2D().mult(random(0.6, 1.4));
        h.hunger = random(0.15, 0.5);
        h.fear = 0.8;
        h.norad = 1.0;
        h.isEating = false;

        this.hunger = max(0, this.hunger - 0.45);
        this.focus = min(1, this.focus + 0.3);
      }
    }
  }

  leap() {
    this.wPrey = constrain(this.wPrey + random(-0.2, 0.3), 0.3, 2.0);
    this.wCover = constrain(this.wCover + random(-0.2, 0.3), 0.1, 1.8);
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
    push();
    translate(this.pos.x, this.pos.y);

    noFill();
    stroke(255, 120, 90, map(this.H, 0, 4, 18, 130, true));
    circle(0, 0, 12 + this.H * 8);

    if (this.justLeaped > 0) {
      stroke(255, 220, 80, 180);
      circle(0, 0, 24);
    }

    noStroke();
    fill(220, 70, 70);
    rotate(this.vel.heading());
    triangle(12, 0, -8, -6, -8, 6);

    pop();
  }
}
