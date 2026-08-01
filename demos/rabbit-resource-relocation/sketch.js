/*
RDF Rabbit Demo v4.1 : 資源枯渇→即時転移

変更点 (v4.0 → v4.1):
──────────────────────────────────────────────────
[4] 資源の枯渇→転移モデル
    旧: nutrition/available が徐々に現地再生
    新: 閾値以下に枯渇 → respawn() で別の場所に即時転移＋リセット

    効果:
    - 水と草の重なりによる「永続安全地帯」が解消
    - 資源が地形のように動き回り、探索圧が常に維持される
    - アンカー退場条件(nutrition<0.08)が転移閾値(0.03)より先に発火するので
      アンカー中の rabbit が転移に巻き込まれることはない

    PARAMS 追加:
    - GRASS_RESPAWN_THRESHOLD: 0.03
    - WATER_RESPAWN_THRESHOLD: 0.03
──────────────────────────────────────────────────
*/

// ===== PARAMS（Fluctuation MOD の注入点） =====
const PARAMS = {
  // ワールド
  NUM_RABBITS: 5,
  NUM_GRASS:   12,
  NUM_WATER:   2,

  // 慣性係数  M：強いほど方向変化に抵抗
  M_INERTIA: 0.935,

  // ニーズ変化率
  HUNGER_RATE:  0.0012,
  THIRST_RATE:  0.0018,
  FEAR_DECAY:   0.97,

  // 疲労蓄積
  SPRINT_EXCESS_START:   1.35,
  SPRINT_FATIGUE_SCALE:  0.0032,
  SLOW_FATIGUE_RECOVERY: 0.0018,
  SLOW_THRESHOLD:        0.4,

  // H_vec 散逸  α：低いほど熱が長く残る
  H_DISSIPATION: 0.988,

  // 非線形σ係数  σ = error² × this
  H_ERROR_SCALE: 0.018,

  // 疲労→H_vec.fatigue への直接寄与
  H_FATIGUE_SCALE: 0.0015,

  // 跳躍後熱残留率 ρ
  H_JUMP_RESIDUAL: 0.35,

  // ニーズ過剰→H_vec 成分への二乗蓄積閾値＆係数
  THIRST_EXCESS_START:      0.48,
  HUNGER_EXCESS_START:      0.54,
  FATIGUE_EXCESS_START:     0.60,
  FEAR_EXCESS_START:        0.25,
  H_THIRST_EXCESS_SCALE:    0.12,
  H_HUNGER_EXCESS_SCALE:    0.08,
  H_FATIGUE_EXCESS_SCALE:   0.05,
  H_FEAR_EXCESS_SCALE:      0.10,

  // H_vec による勾配場増幅（最大ブースト率）
  H_FOOD_AMP:   0.45,
  H_WATER_AMP:  0.45,
  H_COVER_AMP:  0.30,
  H_DANGER_AMP: 0.35,

  // 摂取によるH_vec 冷却
  H_EAT_COOL:   1.5,
  H_DRINK_COOL: 1.5,

  // 恐怖曝露時の H_vec.fear 直接増加
  H_FEAR_SOUND:  0.002,
  H_FEAR_VISUAL: 0.006,

  // 跳躍閾値
  H_ANCHOR_THRESHOLD: 1.2,
  FEAR_ANCHOR_BREAK:  0.42,

  // 移動速度
  MIN_SPEED:         1.8,
  MAX_SPEED:         4.2,
  FATIGUE_SPEED_MIN: 0.56,

  // 勾配場の有効範囲
  FOOD_RANGE:        240,
  WATER_RANGE:       280,
  COVER_GRASS_RANGE: 210,
  COVER_WATER_RANGE: 220,

  // 壁反発
  WALL_MARGIN: 38,
  WALL_FORCE:  0.02,

  // ノイズ
  NOISE_BASE:    0.05,
  NOISE_H_SCALE: 0.03,

  // アンカー入場条件
  ANCHOR_MIN_OVERLAP:          0.72,
  ANCHOR_GRASS_MAX_FEAR:       0.28,
  ANCHOR_WATER_MAX_FEAR:       0.32,
  ANCHOR_MIN_HUNGER:           0.45,
  ANCHOR_MIN_FATIGUE:          0.42,
  ANCHOR_MIN_THIRST:           0.38,
  ANCHOR_MIN_GRASS_NUTRITION:  0.18,
  ANCHOR_MIN_WATER_AVAILABLE:  0.15,

  // アンカー退場条件
  ANCHOR_GRASS_EXIT_HUNGER:  0.16,
  ANCHOR_GRASS_EXIT_FATIGUE: 0.22,
  ANCHOR_GRASS_EXIT_THIRST:  0.68,
  ANCHOR_WATER_EXIT_THIRST:  0.22,

  // 摂取レート（自由行動 / アンカー中）
  INTAKE_FOOD_FREE:     0.010,
  INTAKE_FOOD_ANCHORED: 0.012,
  INTAKE_WATER_FREE:    0.012,
  INTAKE_WATER_ANCHORED:0.015,
  HUNGER_PER_FOOD:      0.9,
  THIRST_PER_WATER:     1.3,

  // 休息フラックス
  RESTFLUX_GRASS_FREE:     0.004,
  RESTFLUX_WATER_FREE:     0.003,
  RESTFLUX_GRASS_ANCHORED: 0.006,
  RESTFLUX_WATER_ANCHORED: 0.004,

  // 摩擦（資源上でのvel減衰）
  SLOW_FRICTION_GRASS: 0.16,
  SLOW_FRICTION_WATER: 0.14,

  // アンカー解放
  RELEASE_VEL:         1.8,
  COOLDOWN_ANCHOR:     70,
  COOLDOWN_FEAR_BREAK: 35,

  // ハンター
  HUNTER_DETECT_RANGE: 230,
  HUNTER_SOUND_RANGE:  260,
  HUNTER_KILL_RANGE:   12,
  HUNTER_CHASE_SPEED:  2.1,
  HUNTER_SEARCH_SPEED: 1.5,
  HUNTER_WANDER_SPEED: 1.0,
  HUNTER_MEMORY:       85,

  // バイアス表示閾値
  FEAR_BIAS:    0.58,
  THIRST_BIAS:  0.62,
  FATIGUE_BIAS: 0.62,
  HUNGER_BIAS:  0.62,

  // ノルアドレナリンスイッチ（素流圧ラベル再編）
  // fear がこの範囲を通過すると平時→非常時モードへ smooth に切替
  DANGER_MODE_LOW:      0.12,   // 以下 = 平時モード（旧0.30→下げた）
  DANGER_MODE_HIGH:     0.45,   // 以上 = 非常時モード（旧0.65→下げた）

  // naLevel の非対称ダイナミクス
  // 上昇は速く（危険検知は即座）、減衰は遅く（余韻が長い）
  NA_RISE_RATE:  0.18,   // dangerMode に向けて上昇する速さ
  NA_DECAY_RATE: 0.004,  // dangerMode が下がった後に減衰する速さ

  // 非常時モードでの食料・飲水圧の抑制率（平時=1.0）
  FOOD_DANGER_SUPPRESS:  0.08,  // 「草＝遮蔽」になるので食料引力ほぼ消える
  WATER_DANGER_SUPPRESS: 0.12,  // 「水辺＝逃走制限」になるので飲水引力消える

  // 危険時：草＝遮蔽候補（nutrition無関係でcoverを参照）
  COVER_DANGER_SCALE:    2.8,

  // 危険時：水辺＝移動制限リスク（反発圧）
  WATER_RISK_SCALE:      0.9,

  // 危険時：開放地露出リスク
  // 最寄り草までの距離がこれ以上→「開放地」と判定して遮蔽へ引力
  OPEN_RISK_THRESHOLD:   80,
  OPEN_RISK_SCALE:       1.4,

  // 資源枯渇→転移の閾値
  // アンカー退場条件(grass:0.08, water:0.07)より小さく設定
  // → anchored rabbit が転移に巻き込まれない
  GRASS_RESPAWN_THRESHOLD: 0.03,
  WATER_RESPAWN_THRESHOLD: 0.03,

  // リセット
  RESET_FRAMES: 90,
};

// ===== グローバル変数 =====
let rabbits = [];
let grassPatches = [];
let waterSources = [];
let hunter;
let resetTimer = 0;

// ===== セットアップ =====
function setup() {
  createCanvas(960, 640);
  initWorld();
}

function initWorld() {
  grassPatches = [];
  waterSources = [];
  rabbits      = [];
  resetTimer   = 0;

  for (let i = 0; i < PARAMS.NUM_GRASS; i++) {
    grassPatches.push(new GrassPatch(random(70, width - 70), random(70, height - 70)));
  }
  for (let i = 0; i < PARAMS.NUM_WATER; i++) {
    waterSources.push(new WaterSource(random(120, width - 120), random(120, height - 120)));
  }
  for (let i = 0; i < PARAMS.NUM_RABBITS; i++) {
    rabbits.push(new Rabbit(random(width * 0.2, width * 0.8), random(height * 0.2, height * 0.8), i));
  }
  hunter = new ActiveThreat(random(width), random(height));
}

// ===== メインループ =====
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
    if (resetTimer > PARAMS.RESET_FRAMES) initWorld();
  }
}

function drawGrid() {
  stroke(255, 255, 255, 10);
  strokeWeight(1);
  for (let x = 0; x < width;  x += 40) line(x, 0, x, height);
  for (let y = 0; y < height; y += 40) line(0, y, width, y);
}

function drawUI(aliveCount) {
  noStroke();
  fill(255);
  textSize(14);
  text('RDF Rabbit Demo v4.0 / H_vec + nonlinear σ + PARAMS', 20, 24);
  text(`alive: ${aliveCount} / hunter: ${hunter.mode}`, 20, 44);

  // aliveCount はフレーム前半の snapshot なので
  // update() 中にハンターが仕留めた場合は focus が undefined になりうる
  const focus = rabbits.find(r => r.alive);
  if (!focus) return;
  const x = 20, y = height - 148;
  fill(0, 0, 0, 120);
  rect(x - 10, y - 18, 560, 136, 8);

  fill(255);
  textSize(13);
  text(`#${focus.id}`, x, y);
  text(`hunger: ${focus.hunger.toFixed(2)}`, x + 60,  y);
  text(`thirst: ${focus.thirst.toFixed(2)}`, x + 180, y);
  text(`fatigue: ${focus.fatigue.toFixed(2)}`, x + 300, y);
  text(`fear: ${focus.fear.toFixed(2)}`, x + 420, y);

  text(`mode: ${focus.label()}`, x, y + 22);
  text(`speed: ${focus.vel.mag().toFixed(2)}`, x + 200, y + 22);
  text(`target: ${hunter.target ? '#' + hunter.target.id : 'none'}`, x + 300, y + 22);
  text(`dist: ${hunter.target ? p5.Vector.dist(hunter.pos, hunter.target.pos).toFixed(1) : '-'}`, x + 420, y + 22);

  // H_vec 表示（色付き）
  const H  = focus.getH();
  const hv = focus.H_vec;
  fill(255); text(`H: ${H.toFixed(3)}`, x, y + 44);
  fill(220, 185, 70);  text(`Hg(食): ${hv.hunger.toFixed(3)}`,  x + 80,  y + 44);
  fill(80,  150, 255); text(`Ht(水): ${hv.thirst.toFixed(3)}`,  x + 210, y + 44);
  fill(160, 100, 220); text(`Hf(疲): ${hv.fatigue.toFixed(3)}`, x + 340, y + 44);
  fill(255, 80,  80);  text(`Hx(恐): ${hv.fear.toFixed(3)}`,    x + 460, y + 44);

  fill(255);
  text(`eat: ${focus.intakeFood.toFixed(3)}`,   x,       y + 66);
  text(`drink: ${focus.intakeWater.toFixed(3)}`, x + 140, y + 66);
  text(`rest: ${focus.restFlux.toFixed(3)}`,     x + 280, y + 66);
  text(`cd: ${focus.anchorCooldown}`,             x + 420, y + 66);
}

function drawResetOverlay() {
  fill(0, 0, 0, 140);
  rect(0, 0, width, height);
  fill(255);
  textAlign(CENTER, CENTER);
  textSize(28);
  text('All rabbits dead — resetting...', width / 2, height / 2);
  textAlign(LEFT, BASELINE);
}

// ===== GrassPatch =====
class GrassPatch {
  constructor(x, y) {
    this.pos       = createVector(x, y);
    this.radius    = random(22, 36);
    this.nutrition = random(0.55, 1.0);
    this.cover     = random(0.35, 1.0);
    this.stopEase  = random(0.45, 1.0);
    // growRate 削除: 現地再生なし → 枯渇で転移
  }

  // 枯渇したら別の場所に転移・リセット
  respawn() {
    this.pos.set(random(70, width - 70), random(70, height - 70));
    this.radius    = random(22, 36);
    this.nutrition = random(0.65, 1.0);
    this.cover     = random(0.35, 1.0);
    this.stopEase  = random(0.45, 1.0);
  }

  update() { /* 現地再生なし */ }

  consume(amount) {
    const eaten = min(this.nutrition, amount);
    this.nutrition -= eaten;
    if (this.nutrition < PARAMS.GRASS_RESPAWN_THRESHOLD) this.respawn();
    return eaten;
  }
  show() {
    noStroke();
    const alpha = map(this.nutrition, 0, 1, 22, 140);
    fill(40, 170, 70, alpha);
    circle(this.pos.x, this.pos.y, this.radius * 2);
    fill(90, 220, 120, alpha * 0.9);
    circle(this.pos.x, this.pos.y, this.radius * 1.1);
  }
}

// ===== WaterSource =====
class WaterSource {
  constructor(x, y) {
    this.pos       = createVector(x, y);
    this.radius    = random(28, 42);
    this.hydration = random(0.85, 1.0);
    this.available = random(0.6, 1.0);
    this.stopEase  = random(0.4, 0.8);
    // recoverRate 削除: 現地再生なし → 枯渇で転移
  }

  // 枯渇したら別の場所に転移・リセット
  respawn() {
    this.pos.set(random(120, width - 120), random(120, height - 120));
    this.radius    = random(28, 42);
    this.hydration = random(0.85, 1.0);
    this.available = random(0.65, 1.0);
    this.stopEase  = random(0.4, 0.8);
  }

  update() { /* 現地再生なし */ }

  drink(amount) {
    const drank = min(this.available, amount);
    this.available -= drank;
    if (this.available < PARAMS.WATER_RESPAWN_THRESHOLD) this.respawn();
    return drank;
  }
  show() {
    noStroke();
    const alpha = map(this.available, 0, 1, 40, 150);
    fill(40, 100, 220, alpha);
    circle(this.pos.x, this.pos.y, this.radius * 2);
    fill(110, 180, 255, alpha * 0.95);
    circle(this.pos.x, this.pos.y, this.radius * 1.2);
  }
}

// ===== ActiveThreat =====
class ActiveThreat {
  constructor(x, y) {
    this.pos         = createVector(x, y);
    this.vel         = p5.Vector.random2D().mult(0.9);
    this.acc         = createVector(0, 0);
    this.radius      = 18;
    this.mode        = 'wander';
    this.detectRange = PARAMS.HUNTER_DETECT_RANGE;
    this.soundRange  = PARAMS.HUNTER_SOUND_RANGE;
    this.killRange   = PARAMS.HUNTER_KILL_RANGE;
    this.memory      = 0;
    this.lastSeen    = null;
    this.target      = null;
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
    for (const r of rabbits) {
      if (!r.alive) continue;
      const d = p5.Vector.dist(this.pos, r.pos);
      if (this.canSee(r) && d < bestD) { best = r; bestD = d; }
    }
    return best;
  }

  update(rabbits) {
    this.acc.mult(0);
    const visible = this.chooseTarget(rabbits);

    if (visible) {
      this.target   = visible;
      this.mode     = 'chase';
      this.memory   = PARAMS.HUNTER_MEMORY;
      this.lastSeen = visible.pos.copy();
    } else if (this.memory > 0 && this.lastSeen) {
      this.mode = 'search';
      this.memory--;
      if (this.target && !this.target.alive) this.target = null;
    } else {
      this.mode     = 'wander';
      this.lastSeen = null;
      this.target   = null;
    }

    if (this.mode === 'chase' && this.target?.alive) {
      this.acc.add(p5.Vector.sub(this.target.pos, this.pos).normalize().mult(0.18));
    } else if (this.mode === 'search' && this.lastSeen) {
      const dir = p5.Vector.sub(this.lastSeen, this.pos);
      if (dir.mag() > 5) this.acc.add(dir.normalize().mult(0.1));
      if (random() < 0.04) this.acc.add(p5.Vector.random2D().mult(0.08));
    } else {
      if (random() < 0.06) this.acc.add(p5.Vector.random2D().mult(0.12));
    }

    this.vel.add(this.acc);
    const maxSpeed = this.mode === 'chase'  ? PARAMS.HUNTER_CHASE_SPEED  :
                     this.mode === 'search' ? PARAMS.HUNTER_SEARCH_SPEED : PARAMS.HUNTER_WANDER_SPEED;
    this.vel.limit(maxSpeed);
    this.pos.add(this.vel);
    wrapPosition(this.pos);

    if (this.target?.alive) {
      if (p5.Vector.dist(this.pos, this.target.pos) < this.killRange) {
        this.target.die();
        this.mode = 'wander';
        this.target = this.lastSeen = null;
        this.memory = 0;
      }
    }
  }

  show() {
    noFill();
    stroke(255, 70, 70, this.mode === 'chase' ? 130 : 70);
    circle(this.pos.x, this.pos.y, this.radius * 6.8);
    push();
    translate(this.pos.x, this.pos.y);
    noStroke();
    fill(this.mode === 'chase' ? color(255, 80, 80) : color(210, 90, 90));
    rotate(this.vel.heading());
    triangle(14, 0, -10, -7, -10, 7);
    pop();
  }
}

// ===== Rabbit =====
class Rabbit {
  constructor(x, y, id) {
    this.id    = id;
    this.alive = true;
    this.pos   = createVector(x, y);
    this.vel   = p5.Vector.random2D().mult(0.8);
    this.acc   = createVector(0, 0);

    // 整合慣性（スカラー近似）
    this.M = PARAMS.M_INERTIA;

    // H_vec：4次元熱ベクトル
    // hunger:空腹熱 / thirst:口渇熱 / fatigue:疲労熱 / fear:恐怖熱
    this.H_vec = { hunger: 0, thirst: 0, fatigue: 0, fear: 0 };

    this.hunger  = random(0.2, 0.35);
    this.thirst  = random(0.18, 0.32);
    this.fatigue = random(0.08, 0.16);
    this.fear    = random(0.04, 0.1);

    // naLevel：ノルアドレナリンレベル（fear より遅く減衰する）
    // 上昇速: NA_RISE_RATE / 減衰遅: NA_DECAY_RATE
    this.naLevel = 0;

    this.noiseScale  = PARAMS.NOISE_BASE;
    this.intakeFood  = 0;
    this.intakeWater = 0;
    this.restFlux    = 0;

    this.isAnchored    = false;
    this.anchorType    = null;
    this.anchorTarget  = null;
    this.anchorCooldown = 0;

    this.lastForces = {
      food:   createVector(0, 0),
      water:  createVector(0, 0),
      cover:  createVector(0, 0),
      danger: createVector(0, 0),
      cost:   createVector(0, 0),
    };
  }

  // ||H_vec|| = スカラーH（閾値判定・リング半径に使用）
  getH() {
    const v = this.H_vec;
    return sqrt(v.hunger**2 + v.thirst**2 + v.fatigue**2 + v.fear**2);
  }

  // H_vec 全成分に一様係数を適用（散逸・跳躍後残留）
  _scaleH(factor) {
    this.H_vec.hunger  *= factor;
    this.H_vec.thirst  *= factor;
    this.H_vec.fatigue *= factor;
    this.H_vec.fear    *= factor;
  }

  die() {
    this.alive = false;
    this.isAnchored = false;
    this.vel.set(0, 0);
    this.acc.set(0, 0);
  }

  label() {
    if (!this.alive) return 'dead';
    if (this.isAnchored && this.anchorType === 'grass')  return 'anchored-grass';
    if (this.isAnchored && this.anchorType === 'water')  return 'anchored-water';
    if (this.naLevel    > 0.85)              return 'NA-switch';
    if (this.fear    > PARAMS.FEAR_BIAS)    return 'escape-bias';
    if (this.thirst  > PARAMS.THIRST_BIAS)  return 'water-bias';
    if (this.fatigue > PARAMS.FATIGUE_BIAS) return 'rest-bias';
    if (this.hunger  > PARAMS.HUNGER_BIAS)  return 'food-bias';
    return 'mixed-flow';
  }

  update(hunter) {
    if (!this.alive) return;

    this.acc.mult(0);
    this.intakeFood  = 0;
    this.intakeWater = 0;
    this.restFlux    = 0;

    if (this.anchorCooldown > 0) this.anchorCooldown--;

    this.updateNeeds();

    if (this.isAnchored) {
      this.senseDangerOnly(hunter);
      this.applyAnchoredFlows();
      const quickBreak = lerp(PARAMS.FEAR_ANCHOR_BREAK, 0.92, this.naLevel);
      if (this.fear > quickBreak) this.clearAnchor(PARAMS.COOLDOWN_FEAR_BREAK);
      return;
    }

    const field = this.buildGradientField(hunter);
    this.lastForces = field;

    const inertialFlow = p5.Vector.mult(this.vel, this.M);

    let total = createVector(0, 0);
    total.add(field.food);
    total.add(field.water);
    total.add(field.cover);
    total.add(field.cost);
    total.add(field.danger);

    // 誤差 E(t) = F(t) - M·V(t)
    const error = p5.Vector.sub(total, inertialFlow).mag();

    // 非線形熱生成 σ = error² × H_ERROR_SCALE
    // → 現在の need 比で H_vec 各成分に分配
    const sigma   = error * error * PARAMS.H_ERROR_SCALE;
    const needSum = this.hunger + this.thirst + this.fatigue + this.fear + 0.001;
    this.H_vec.hunger  += sigma * (this.hunger  / needSum);
    this.H_vec.thirst  += sigma * (this.thirst  / needSum);
    this.H_vec.fatigue += sigma * (this.fatigue / needSum);
    this.H_vec.fear    += sigma * (this.fear    / needSum);

    // 疲労の直接寄与（疲労熱成分へ）
    this.H_vec.fatigue += this.fatigue * PARAMS.H_FATIGUE_SCALE;

    // H_vec 散逸  dH/dt の -αH 項
    this._scaleH(PARAMS.H_DISSIPATION);

    const H = this.getH();

    // ξ：H_vec の大きさに比例してノイズ増加
    total.add(p5.Vector.random2D().mult(this.noiseScale + H * PARAMS.NOISE_H_SCALE));

    this.vel.add(total);
    this.vel.limit(this.computeMaxSpeed());
    this.pos.add(this.vel);
    wrapPosition(this.pos);

    this.resolveLocalInteractions();
    this.tryAnchorPhase();
  }

  updateNeeds() {
    this.hunger = constrain(this.hunger + PARAMS.HUNGER_RATE, 0, 1);
    this.thirst = constrain(this.thirst + PARAMS.THIRST_RATE, 0, 1);
    this.fear  *= PARAMS.FEAR_DECAY;

    // naLevel：fear から求めた目標値に非対称レートで追従
    // 上昇は速く（NA_RISE_RATE）、減衰は遅い（NA_DECAY_RATE）
    const naTarget = constrain(
      map(this.fear, PARAMS.DANGER_MODE_LOW, PARAMS.DANGER_MODE_HIGH, 0, 1),
      0, 1
    );
    if (naTarget > this.naLevel) {
      this.naLevel = lerp(this.naLevel, naTarget, PARAMS.NA_RISE_RATE);
    } else {
      this.naLevel = lerp(this.naLevel, naTarget, PARAMS.NA_DECAY_RATE);
    }

    // 過剰ニーズ → 対応する H_vec 成分に二乗蓄積
    const thirstEx  = max(0, this.thirst  - PARAMS.THIRST_EXCESS_START);
    const hungerEx  = max(0, this.hunger  - PARAMS.HUNGER_EXCESS_START);
    const fatigueEx = max(0, this.fatigue - PARAMS.FATIGUE_EXCESS_START);
    const fearEx    = max(0, this.fear    - PARAMS.FEAR_EXCESS_START);
    this.H_vec.thirst  += thirstEx  ** 2 * PARAMS.H_THIRST_EXCESS_SCALE;
    this.H_vec.hunger  += hungerEx  ** 2 * PARAMS.H_HUNGER_EXCESS_SCALE;
    this.H_vec.fatigue += fatigueEx ** 2 * PARAMS.H_FATIGUE_EXCESS_SCALE;
    this.H_vec.fear    += fearEx    ** 2 * PARAMS.H_FEAR_EXCESS_SCALE;

    const speed        = this.vel.mag();
    const sprintExcess = max(0, speed - PARAMS.SPRINT_EXCESS_START);
    this.fatigue = constrain(
      this.fatigue + sprintExcess ** 2 * PARAMS.SPRINT_FATIGUE_SCALE, 0, 1
    );

    if (!this.isAnchored && speed < PARAMS.SLOW_THRESHOLD) {
      this.fatigue = max(0, this.fatigue - PARAMS.SLOW_FATIGUE_RECOVERY);
    }
  }

  senseDangerOnly(hunter) {
    const d = max(p5.Vector.dist(this.pos, hunter.pos), 1);
    if (d < hunter.soundRange) {
      this.fear = min(1, this.fear + 0.0025);
      this.H_vec.fear = min(3, this.H_vec.fear + PARAMS.H_FEAR_SOUND);
    }
    if (hunter.canSee(this) && d < hunter.detectRange) {
      this.fear = min(1, this.fear + 0.012);
      this.H_vec.fear = min(3, this.H_vec.fear + PARAMS.H_FEAR_VISUAL);
    }
  }

  buildGradientField(hunter) {
    let F_food   = createVector(0, 0);
    let F_water  = createVector(0, 0);
    let F_cover  = createVector(0, 0);
    let F_danger = createVector(0, 0);
    let F_cost   = createVector(0, 0);

    const thirstUrgency = max(0, this.thirst - 0.45) * 1.8;

    // H_vec 方向ブースト係数
    // 「空腹熱が高い兎は食物引力がより強く見える」を実装
    const H       = this.getH() + 0.001;
    const foodAmp   = 1 + PARAMS.H_FOOD_AMP   * (this.H_vec.hunger  / H);
    const waterAmp  = 1 + PARAMS.H_WATER_AMP  * (this.H_vec.thirst  / H);
    const coverAmp  = 1 + PARAMS.H_COVER_AMP  * (this.H_vec.fatigue / H);
    const dangerAmp = 1 + PARAMS.H_DANGER_AMP * (this.H_vec.fear    / H);

    for (const g of grassPatches) {
      const to   = p5.Vector.sub(g.pos, this.pos);
      const dRaw = to.mag();
      const dEff = max(dRaw, g.radius * 0.7);
      const dir  = to.copy().normalize();

      const foodPull  = this.hunger * g.nutrition * (1.0 - min(0.55, thirstUrgency * 0.28)) / dEff;
      const coverPull = (this.fear * 1.6) * g.cover / dEff;
      const restPull  = this.fatigue * g.stopEase / dEff;

      if (dRaw < PARAMS.FOOD_RANGE)        F_food.add(p5.Vector.mult(dir, foodPull));
      if (dRaw < PARAMS.COVER_GRASS_RANGE) F_cover.add(p5.Vector.mult(dir, coverPull + restPull));
    }

    for (const w of waterSources) {
      const to   = p5.Vector.sub(w.pos, this.pos);
      const dRaw = to.mag();
      const dEff = max(dRaw, w.radius * 0.7);
      const dir  = to.copy().normalize();

      const waterPull = this.thirst * w.hydration * w.available * 3.2 / dEff;
      const restPull  = this.fatigue * w.stopEase * 0.4 / dEff;

      if (dRaw < PARAMS.WATER_RANGE)        F_water.add(p5.Vector.mult(dir, waterPull));
      if (dRaw < PARAMS.COVER_WATER_RANGE)  F_cover.add(p5.Vector.mult(dir, restPull));
    }

    // ブースト適用（H_vec による勾配場の方向的増幅）
    F_food.mult(foodAmp);
    F_water.mult(waterAmp);
    F_cover.mult(coverAmp);

    const d    = max(p5.Vector.dist(this.pos, hunter.pos), 1);
    const away = p5.Vector.sub(this.pos, hunter.pos).normalize();

    if (d < hunter.soundRange) {
      const soundPush = (0.15 + this.fear) * 0.8 / d;
      F_danger.add(p5.Vector.mult(away, soundPush));
      this.fear = min(1, this.fear + 0.0018);
      this.H_vec.fear = min(3, this.H_vec.fear + PARAMS.H_FEAR_SOUND);
    }
    if (hunter.canSee(this) && d < hunter.detectRange) {
      const visualPush = (0.35 + this.fear) * 2.8 / d;
      F_danger.add(p5.Vector.mult(away, visualPush));
      this.fear = min(1, this.fear + 0.0075);
      this.H_vec.fear = min(3, this.H_vec.fear + PARAMS.H_FEAR_VISUAL);
    }
    F_danger.mult(dangerAmp);

    if (this.pos.x < PARAMS.WALL_MARGIN)           F_cost.add(createVector( PARAMS.WALL_FORCE,  0));
    if (this.pos.x > width  - PARAMS.WALL_MARGIN)  F_cost.add(createVector(-PARAMS.WALL_FORCE,  0));
    if (this.pos.y < PARAMS.WALL_MARGIN)           F_cost.add(createVector( 0,  PARAMS.WALL_FORCE));
    if (this.pos.y > height - PARAMS.WALL_MARGIN)  F_cost.add(createVector( 0, -PARAMS.WALL_FORCE));

    // ── ノルアドレナリンスイッチ：素流圧ラベル再編 ──────────────────
    // this.naLevel を使用（fear より遅く減衰する）
    const dangerMode = this.naLevel;

    if (dangerMode > 0) {
      // [1] 食料圧・飲水圧を抑制
      //     「草＝遮蔽候補」「水辺＝逃走制限」へ意味が反転するため
      F_food.mult(lerp(1.0, PARAMS.FOOD_DANGER_SUPPRESS,  dangerMode));
      F_water.mult(lerp(1.0, PARAMS.WATER_DANGER_SUPPRESS, dangerMode));

      // [2] 草→遮蔽候補：nutritionではなくcoverを参照して引力を再付与
      for (const g of grassPatches) {
        const to   = p5.Vector.sub(g.pos, this.pos);
        const dRaw = to.mag();
        const dEff = max(dRaw, g.radius * 0.7);
        if (dRaw < PARAMS.COVER_GRASS_RANGE) {
          const shelterPull = dangerMode * PARAMS.COVER_DANGER_SCALE * g.cover / dEff;
          F_cover.add(p5.Vector.mult(to.copy().normalize(), shelterPull));
        }
      }

      // [3] 水辺→移動制限リスク：近距離の水辺から反発圧を付与
      for (const w of waterSources) {
        const to   = p5.Vector.sub(w.pos, this.pos);
        const dRaw = to.mag();
        if (dRaw < w.radius * 3.5) {
          const riskPush = dangerMode * PARAMS.WATER_RISK_SCALE / max(dRaw, w.radius);
          F_cost.add(p5.Vector.mult(to.copy().normalize().mult(-1), riskPush));
        }
      }

      // [4] 開放地露出リスク：最寄り草が遠ければ遮蔽へ引力を強化
      let nearDist = Infinity, nearDir = null;
      for (const g of grassPatches) {
        const d = p5.Vector.dist(this.pos, g.pos);
        if (d < nearDist) { nearDist = d; nearDir = p5.Vector.sub(g.pos, this.pos).normalize(); }
      }
      if (nearDir && nearDist > PARAMS.OPEN_RISK_THRESHOLD) {
        const exposure = map(nearDist, PARAMS.OPEN_RISK_THRESHOLD, 350, 0, 1, true);
        F_cover.add(p5.Vector.mult(nearDir, dangerMode * PARAMS.OPEN_RISK_SCALE * exposure));
      }
    }
    // ────────────────────────────────────────────────────────────────

    return { food: F_food, water: F_water, cover: F_cover, danger: F_danger, cost: F_cost };
  }

  computeMaxSpeed() {
    const fearBoost      = map(this.fear, 0, 1, PARAMS.MIN_SPEED, PARAMS.MAX_SPEED);
    const fatiguePenalty = map(this.fatigue, 0, 1, 1.0, PARAMS.FATIGUE_SPEED_MIN);
    return fearBoost * fatiguePenalty;
  }

  resolveLocalInteractions() {
    for (const g of grassPatches) {
      const d       = p5.Vector.dist(this.pos, g.pos);
      const overlap = max(0, 1 - d / (g.radius * 0.95));
      const calmness = (1 - this.fear) * max(0, 1 - this.vel.mag() / 1.25);
      const intake  = overlap * calmness;
      if (intake > 0) {
        this.intakeFood = max(this.intakeFood, intake * g.nutrition * PARAMS.INTAKE_FOOD_FREE);
        this.restFlux   = max(this.restFlux,  intake * g.stopEase  * PARAMS.RESTFLUX_GRASS_FREE);
        this.vel.mult(1.0 - overlap * PARAMS.SLOW_FRICTION_GRASS);
      }
    }
    for (const w of waterSources) {
      const d       = p5.Vector.dist(this.pos, w.pos);
      const overlap = max(0, 1 - d / (w.radius * 0.95));
      const calmness = (1 - this.fear) * max(0, 1 - this.vel.mag() / 1.35);
      const intake  = overlap * calmness;
      if (intake > 0) {
        this.intakeWater = max(this.intakeWater, intake * w.hydration * w.available * PARAMS.INTAKE_WATER_FREE);
        this.restFlux    = max(this.restFlux,   intake * w.stopEase  * PARAMS.RESTFLUX_WATER_FREE);
        this.vel.mult(1.0 - overlap * PARAMS.SLOW_FRICTION_WATER);
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
          const eaten = g.consume(min(remaining, PARAMS.INTAKE_FOOD_FREE));
          this.hunger   = max(0, this.hunger - eaten * PARAMS.HUNGER_PER_FOOD);
          this.H_vec.hunger = max(0, this.H_vec.hunger - eaten * PARAMS.H_EAT_COOL);
          remaining -= eaten;
        }
      }
    }
    if (this.intakeWater > 0) {
      let remaining = this.intakeWater;
      for (const w of waterSources) {
        const d = p5.Vector.dist(this.pos, w.pos);
        if (d < w.radius * 0.95 && remaining > 0) {
          const drank = w.drink(min(remaining, PARAMS.INTAKE_WATER_FREE));
          this.thirst  = max(0, this.thirst - drank * PARAMS.THIRST_PER_WATER);
          this.H_vec.thirst = max(0, this.H_vec.thirst - drank * PARAMS.H_DRINK_COOL);
          remaining -= drank;
        }
      }
    }
    if (this.restFlux > 0) {
      this.fatigue = max(0, this.fatigue - this.restFlux);
    }
  }

  tryAnchorPhase() {
    if (this.anchorCooldown > 0 || this.isAnchored || !this.alive) return false;

    for (const g of grassPatches) {
      const d       = p5.Vector.dist(this.pos, g.pos);
      const overlap = max(0, 1 - d / (g.radius * 0.95));
      if (
        overlap > PARAMS.ANCHOR_MIN_OVERLAP &&
        this.fear < PARAMS.ANCHOR_GRASS_MAX_FEAR &&
        (this.hunger > PARAMS.ANCHOR_MIN_HUNGER || this.fatigue > PARAMS.ANCHOR_MIN_FATIGUE) &&
        g.nutrition > PARAMS.ANCHOR_MIN_GRASS_NUTRITION
      ) {
        this.isAnchored   = true;
        this.anchorType   = 'grass';
        this.anchorTarget = g;
        return true;
      }
    }
    for (const w of waterSources) {
      const d       = p5.Vector.dist(this.pos, w.pos);
      const overlap = max(0, 1 - d / (w.radius * 0.95));
      if (
        overlap > PARAMS.ANCHOR_MIN_OVERLAP &&
        this.fear < PARAMS.ANCHOR_WATER_MAX_FEAR &&
        this.thirst > PARAMS.ANCHOR_MIN_THIRST &&
        w.available > PARAMS.ANCHOR_MIN_WATER_AVAILABLE
      ) {
        this.isAnchored   = true;
        this.anchorType   = 'water';
        this.anchorTarget = w;
        return true;
      }
    }
    return false;
  }

  applyAnchoredFlows() {
    if (!this.alive) return;
    this.vel.set(0, 0);
    this.acc.set(0, 0);
    this.intakeFood  = 0;
    this.intakeWater = 0;
    this.restFlux    = 0;
    if (!this.anchorTarget) { this.clearAnchor(10); return; }

    const H = this.getH();

    if (this.anchorType === 'grass') {
      const g       = this.anchorTarget;
      const d       = p5.Vector.dist(this.pos, g.pos);
      const overlap = max(0, 1 - d / (g.radius * 0.95));
      const intake  = overlap * (1 - this.fear);

      this.intakeFood = intake * g.nutrition * PARAMS.INTAKE_FOOD_ANCHORED;
      this.restFlux   = intake * g.stopEase  * PARAMS.RESTFLUX_GRASS_ANCHORED;

      const eaten = g.consume(min(this.intakeFood, PARAMS.INTAKE_FOOD_ANCHORED));
      this.hunger   = max(0, this.hunger - eaten * PARAMS.HUNGER_PER_FOOD);
      this.H_vec.hunger = max(0, this.H_vec.hunger - eaten * PARAMS.H_EAT_COOL);
      this.fatigue  = max(0, this.fatigue - this.restFlux);

      // NAモード中は「怖いから留まる」に反転：fear退場閾値を引き上げる
      const fearBreakG = lerp(PARAMS.FEAR_ANCHOR_BREAK, 0.92, this.naLevel);
      if (
        this.fear > fearBreakG ||
        g.nutrition < 0.08 ||
        this.thirst  > PARAMS.ANCHOR_GRASS_EXIT_THIRST  ||
        this.hunger  < PARAMS.ANCHOR_GRASS_EXIT_HUNGER  ||
        this.fatigue < PARAMS.ANCHOR_GRASS_EXIT_FATIGUE ||
        H > PARAMS.H_ANCHOR_THRESHOLD
      ) {
        this.releaseFromPatch(g, PARAMS.COOLDOWN_ANCHOR);
      }
      return;
    }

    if (this.anchorType === 'water') {
      const w       = this.anchorTarget;
      const d       = p5.Vector.dist(this.pos, w.pos);
      const overlap = max(0, 1 - d / (w.radius * 0.95));
      const intake  = overlap * (1 - this.fear);

      this.intakeWater = intake * w.hydration * w.available * PARAMS.INTAKE_WATER_ANCHORED;
      this.restFlux    = intake * w.stopEase  * PARAMS.RESTFLUX_WATER_ANCHORED;

      const drank = w.drink(min(this.intakeWater, PARAMS.INTAKE_WATER_ANCHORED));
      this.thirst  = max(0, this.thirst - drank * PARAMS.THIRST_PER_WATER);
      this.H_vec.thirst = max(0, this.H_vec.thirst - drank * PARAMS.H_DRINK_COOL);
      this.fatigue = max(0, this.fatigue - this.restFlux);

      const fearBreakW = lerp(PARAMS.FEAR_ANCHOR_BREAK, 0.92, this.naLevel);
      if (
        this.fear > fearBreakW ||
        w.available < 0.07 ||
        this.thirst < PARAMS.ANCHOR_WATER_EXIT_THIRST ||
        H > PARAMS.H_ANCHOR_THRESHOLD
      ) {
        this.releaseFromPatch(w, PARAMS.COOLDOWN_ANCHOR);
      }
      return;
    }
  }

  releaseFromPatch(patch, cooldown) {
    const away = p5.Vector.sub(this.pos, patch.pos);
    if (away.mag() < 0.001) away.set(random(-1, 1), random(-1, 1));
    away.normalize();
    this.vel = away.copy().mult(PARAMS.RELEASE_VEL);
    this._scaleH(PARAMS.H_JUMP_RESIDUAL); // H → ρH（各成分に一様適用）
    this.clearAnchor(cooldown);
  }

  clearAnchor(cooldown) {
    this.isAnchored    = false;
    this.anchorType    = null;
    this.anchorTarget  = null;
    this.anchorCooldown = cooldown;
  }

  // H_vec の支配成分→表示色
  _H_ringColor(alpha) {
    const v = this.H_vec;
    const dom = max(v.hunger, v.thirst, v.fatigue, v.fear);
    if (dom < 0.05)           return color(100, 220, 255, alpha); // 低H：水色
    if (dom === v.hunger)     return color(220, 185,  70, alpha); // 空腹熱：黄
    if (dom === v.thirst)     return color( 80, 150, 255, alpha); // 口渇熱：青
    if (dom === v.fatigue)    return color(160, 100, 220, alpha); // 疲労熱：紫
    /* fear */                return color(255,  80,  80, alpha); // 恐怖熱：赤
  }

  show() {
    if (!this.alive) {
      push();
      translate(this.pos.x, this.pos.y);
      stroke(120);
      line(-8, -8, 8, 8);
      line(-8, 8, 8, -8);
      pop();
      return;
    }

    drawVector(this.pos, this.lastForces.food,   color(80,  220, 120), 180);
    drawVector(this.pos, this.lastForces.water,  color(160, 120, 255), 180);
    drawVector(this.pos, this.lastForces.cover,  color(80,  220, 255), 180);
    drawVector(this.pos, this.lastForces.danger, color(255, 80,  80),  230);

    push();
    translate(this.pos.x, this.pos.y);

    const H     = this.getH();
    const alpha = map(H, 0, 3, 20, 150, true);
    noFill();
    stroke(this._H_ringColor(alpha));
    circle(0, 0, 12 + H * 10);

    if (this.isAnchored) {
      stroke(255, 255, 180, 160);
      noFill();
      circle(0, 0, 24);
    }

    noStroke();
    const calmColor = color(210, 220, 235);
    const fearColor = color(255, 180, 140);
    const naColor   = color(255, 235, 80);  // NA-switch：黄色（高覚醒）
    const body = lerpColor(lerpColor(calmColor, fearColor, this.fear), naColor, this.naLevel);
    fill(body);
    rotate(this.vel.heading());
    ellipse(0, 0, 18, 12);
    ellipse(-7, -5, 5, 12);
    ellipse(-1, -6, 5, 12);
    pop();
  }
}

// ===== ユーティリティ =====
function distancePointToSegment(p, a, b) {
  const ab = p5.Vector.sub(b, a);
  const ap = p5.Vector.sub(p, a);
  const abLenSq = ab.magSq();
  if (abLenSq === 0) return p5.Vector.dist(p, a);
  const t = constrain(ap.dot(ab) / abLenSq, 0, 1);
  return p5.Vector.dist(p, p5.Vector.add(a, p5.Vector.mult(ab, t)));
}

function drawVector(origin, vec, col, scale = 220) {
  const v = p5.Vector.mult(vec, scale);
  stroke(col);
  strokeWeight(2);
  line(origin.x, origin.y, origin.x + v.x, origin.y + v.y);
}

function wrapPosition(pos) {
  if (pos.x < 0)      pos.x = width;
  if (pos.x > width)  pos.x = 0;
  if (pos.y < 0)      pos.y = height;
  if (pos.y > height) pos.y = 0;
}