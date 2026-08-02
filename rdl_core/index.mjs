export function clamp(value, min = 0, max = 1) {
  return Math.max(min, Math.min(max, value));
}

export function dimensionState(dimensions, initial = 0) {
  return Object.fromEntries(dimensions.map((dimension) => [dimension, initial]));
}

export function dimensionConfig(dimensions, value) {
  if (typeof value === "number") return dimensionState(dimensions, value);
  return { ...dimensionState(dimensions, 0), ...value };
}

export class Boundary {
  constructor({
    id = "B",
    dimensions,
    timeScale = 1,
    spaceScale = null,
    purpose = "observe relational dynamics",
    observer = "observer",
    evaluation = null,
    thetaBase = 1,
    thetaMin = 0.2,
    thetaMax = 2,
    xiThetaWeight = 0.26,
    interpreter = null,
  }) {
    if (!Array.isArray(dimensions) || dimensions.length === 0) {
      throw new Error("Boundary requires a non-empty dimensions array");
    }
    this.id = id;
    this.dimensions = [...dimensions];
    this.timeScale = timeScale;
    this.spaceScale = spaceScale;
    this.purpose = purpose;
    this.observer = observer;
    this.evaluation = evaluation;
    this.thetaBase = thetaBase;
    this.thetaMin = thetaMin;
    this.thetaMax = thetaMax;
    this.xiThetaWeight = xiThetaWeight;
    this.interpreter = interpreter;
  }

  thetaEffective(xi = 0) {
    return clamp(this.thetaBase - xi * this.xiThetaWeight, this.thetaMin, this.thetaMax);
  }

  interpret(mbNode, efp) {
    if (this.interpreter) return this.interpreter(mbNode, efp, this);
    return mbNode.interpret(efp);
  }
}

export class HVector {
  constructor({
    dimensions,
    decay = 0.9,
    gain = 1,
    initial = 0,
    residualAfterLeap = 0.28,
  }) {
    this.dimensions = [...dimensions];
    this.decay = dimensionConfig(dimensions, decay);
    this.gain = dimensionConfig(dimensions, gain);
    this.values = dimensionConfig(dimensions, initial);
    this.residualAfterLeap = residualAfterLeap;
  }

  record(error) {
    for (const dimension of this.dimensions) {
      const value = Math.abs(error[dimension] ?? 0);
      this.values[dimension] = this.values[dimension] * this.decay[dimension]
        + value * this.gain[dimension];
    }
    return this.snapshot();
  }

  strongest() {
    return Object.entries(this.values)
      .sort((left, right) => right[1] - left[1])[0];
  }

  dissipate(factor) {
    for (const dimension of this.dimensions) this.values[dimension] *= factor;
    return this.snapshot();
  }

  retainAfterLeap() {
    return this.dissipate(this.residualAfterLeap);
  }

  snapshot() {
    return { ...this.values };
  }
}

export class LeapEngine {
  constructor({ cooldownTicks = 0, handlers = {} } = {}) {
    this.cooldownTicks = cooldownTicks;
    this.handlers = { ...handlers };
  }

  maybeLeap(node, tick = 0) {
    if (node.leapCooldown > 0) return null;
    const [dimension, pressure] = node.h.strongest();
    const threshold = node.boundary.thetaEffective(node.xi);
    if (pressure < threshold) return null;

    const handler = this.handlers[dimension] ?? this.handlers.default;
    const result = handler
      ? handler({ node, dimension, pressure, threshold, tick })
      : { title: `Leap: ${dimension}`, detail: "M_B was reorganized by accumulated H" };

    node.phase = "M_delta";
    node.h.retainAfterLeap();
    node.leapCount += 1;
    node.leapCooldown = this.cooldownTicks;
    node.events.unshift({
      tick,
      type: "leap",
      dimension,
      pressure,
      threshold,
      ...result,
    });
    return node.events[0];
  }
}

export class MBNode {
  constructor({
    id,
    boundary,
    reliability = 0.7,
    h = null,
    xi = 0,
    xiDecay = 0.9985,
    xiGain = 0.12,
    leapEngine = new LeapEngine(),
    projection = null,
  }) {
    if (!id) throw new Error("MBNode requires an id");
    if (!(boundary instanceof Boundary)) throw new Error("MBNode requires a Boundary");
    this.id = id;
    this.boundary = boundary;
    this.dimensions = [...boundary.dimensions];
    this.reliability = dimensionConfig(this.dimensions, reliability);
    this.h = h ?? new HVector({ dimensions: this.dimensions });
    this.xi = xi;
    this.xiDecay = xiDecay;
    this.xiGain = xiGain;
    this.leapEngine = leapEngine;
    this.projection = projection;
    this.phase = "M_act";
    this.lastF = dimensionState(this.dimensions);
    this.lastError = dimensionState(this.dimensions);
    this.leapCount = 0;
    this.leapCooldown = 0;
    this.events = [];
  }

  beginTick() {
    this.xi *= this.xiDecay;
    if (this.leapCooldown > 0) this.leapCooldown -= 1;
    if (this.phase === "M_delta") this.phase = "M_act";
  }

  interpret(efp) {
    const f = {};
    for (const dimension of this.dimensions) {
      f[dimension] = clamp((efp[dimension] ?? 0) * this.reliability[dimension]);
    }
    return f;
  }

  project(previousF = this.lastF) {
    if (this.projection) return this.projection(this, previousF);
    const projected = {};
    for (const dimension of this.dimensions) {
      projected[dimension] = clamp((previousF[dimension] ?? 0) * this.reliability[dimension]);
    }
    return projected;
  }

  compare(predictedF, actualF) {
    const error = {};
    for (const dimension of this.dimensions) {
      error[dimension] = Math.abs((actualF[dimension] ?? 0) - (predictedF[dimension] ?? 0));
    }
    return error;
  }

  update({ efp = null, actualF = null, predictedF = null, tick = 0 } = {}) {
    this.beginTick();
    const interpretedF = efp ? this.boundary.interpret(this, efp) : null;
    const nextF = actualF ?? interpretedF;
    if (!nextF) throw new Error("MBNode.update requires efp or actualF");

    const prediction = predictedF ?? this.project(this.lastF);
    const error = this.compare(prediction, nextF);
    this.lastF = { ...nextF };
    this.lastError = error;
    this.h.record(error);

    const largestError = Math.max(...Object.values(error));
    this.xi = clamp(this.xi + largestError * this.xiGain, 0, 2);

    const leap = this.leapEngine.maybeLeap(this, tick);
    return {
      F: { ...nextF },
      predictedF: prediction,
      E: error,
      H: this.h.snapshot(),
      xi: this.xi,
      thetaEffective: this.boundary.thetaEffective(this.xi),
      phase: this.phase,
      leap,
    };
  }

  snapshot() {
    return {
      id: this.id,
      boundary: this.boundary.id,
      phase: this.phase,
      reliability: { ...this.reliability },
      F: { ...this.lastF },
      E: { ...this.lastError },
      H: this.h.snapshot(),
      xi: this.xi,
      thetaEffective: this.boundary.thetaEffective(this.xi),
      leapCount: this.leapCount,
    };
  }
}

export class MBGraph {
  constructor() {
    this.nodes = new Map();
    this.edges = new Map();
  }

  add(node) {
    if (!(node instanceof MBNode)) throw new Error("MBGraph.add requires an MBNode");
    this.nodes.set(node.id, node);
    if (!this.edges.has(node.id)) this.edges.set(node.id, []);
    return node;
  }

  connect(from, to, { type = "W_ij", weight = 1, label = "" } = {}) {
    if (!this.nodes.has(from) || !this.nodes.has(to)) {
      throw new Error("MBGraph.connect requires existing node ids");
    }
    this.edges.get(from).push({ from, to, type, weight, label });
  }

  neighbors(id, type = null) {
    const edges = this.edges.get(id) ?? [];
    return edges
      .filter((edge) => type === null || edge.type === type)
      .map((edge) => ({ edge, node: this.nodes.get(edge.to) }));
  }

  snapshot() {
    return {
      nodes: [...this.nodes.values()].map((node) => node.snapshot()),
      edges: [...this.edges.values()].flat(),
    };
  }
}
