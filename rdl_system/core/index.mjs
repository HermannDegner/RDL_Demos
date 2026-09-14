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

export class RIBSection {
  constructor({
    id,
    boundaryId,
    values,
    role = "observation",
    provenance = null,
  }) {
    if (!id) throw new Error("RIBSection requires an id");
    if (!boundaryId) throw new Error("RIBSection requires a boundaryId");
    if (!values || typeof values !== "object") {
      throw new Error("RIBSection requires finite values");
    }
    this.id = id;
    this.boundaryId = boundaryId;
    this.role = role;
    this.values = Object.freeze({ ...values });
    this.provenance = provenance;
    Object.freeze(this);
  }
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
    this.interpreter = interpreter;
  }

  section(values, {
    id = `${this.id}:section`,
    role = "observation",
    provenance = null,
  } = {}) {
    const selected = {};
    for (const dimension of this.dimensions) {
      if (Object.hasOwn(values ?? {}, dimension)) selected[dimension] = values[dimension];
    }
    return new RIBSection({
      id,
      boundaryId: this.id,
      values: selected,
      role,
      provenance,
    });
  }

  threshold() {
    return this.thetaBase;
  }

  interpret(mbNode, ribSection) {
    if (!(ribSection instanceof RIBSection)) {
      throw new Error("Boundary.interpret requires a RIBSection");
    }
    if (ribSection.boundaryId !== this.id) {
      throw new Error("RIBSection belongs to a different Boundary");
    }
    if (this.interpreter) return this.interpreter(mbNode, ribSection, this);
    return mbNode.interpret(ribSection);
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

  recordUnresolved(error) {
    for (const dimension of this.dimensions) {
      const value = Math.abs(error[dimension] ?? 0);
      this.values[dimension] = this.values[dimension] * this.decay[dimension]
        + value * this.gain[dimension];
    }
    return this.snapshot();
  }

  dissipateTick() {
    for (const dimension of this.dimensions) {
      this.values[dimension] *= this.decay[dimension];
    }
    return this.snapshot();
  }

  // Core v2.3 Standard Model: H = ||H_vec||.
  // This finite demo chooses the Euclidean (L2) norm as its concrete norm.
  norm() {
    return Math.sqrt(
      this.dimensions.reduce((sum, dimension) => {
        const value = this.values[dimension] ?? 0;
        return sum + value * value;
      }, 0),
    );
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
  constructor({ cooldownTicks = 10, handlers = {} } = {}) {
    this.cooldownTicks = cooldownTicks;
    this.handlers = { ...handlers };
  }

  maybeLeap(node, tick = 0) {
    if (node.leapCooldown > 0) return null;

    const H = node.h.norm();
    const [dimension, componentPressure] = node.h.strongest();
    const threshold = node.boundary.threshold();
    if (H < threshold) return null;

    const handler = this.handlers[dimension] ?? this.handlers.default;
    const result = handler
      ? handler({ node, dimension, H, componentPressure, pressure: H, threshold, tick })
      : { title: `Leap: ${dimension}`, detail: "M_B reconstruction candidate from unresolved H" };

    node.phase = "M_delta";
    const hVectorBeforeRetention = node.h.snapshot();
    node.h.retainAfterLeap();
    node.leapCount += 1;
    node.leapCooldown = this.cooldownTicks;
    node.events.unshift({
      tick,
      type: "leap",
      dimension,
      H,
      HVector: hVectorBeforeRetention,
      componentPressure,
      pressure: H,
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
    alignRate = 0.035,
    reliabilityMin = 0.18,
    reliabilityMax = 0.98,
    h = null,
    adaptationPressure = 0,
    adaptationPressureDecay = 0.94,
    adaptationPressureGain = 0.12,
    adaptationPressureMax = 1.2,
    leapEngine = new LeapEngine(),
  }) {
    if (!id) throw new Error("MBNode requires an id");
    if (!(boundary instanceof Boundary)) throw new Error("MBNode requires a Boundary");
    this.id = id;
    this.boundary = boundary;
    this.dimensions = [...boundary.dimensions];
    this.reliability = dimensionConfig(this.dimensions, reliability);
    this.alignRate = dimensionConfig(this.dimensions, alignRate);
    this.reliabilityMin = reliabilityMin;
    this.reliabilityMax = reliabilityMax;
    this.h = h ?? new HVector({ dimensions: this.dimensions });
    this.adaptationPressure = adaptationPressure;
    this.adaptationPressureDecay = adaptationPressureDecay;
    this.adaptationPressureGain = adaptationPressureGain;
    this.adaptationPressureMax = adaptationPressureMax;
    this.leapEngine = leapEngine;
    this.phase = "M_act";
    this.lastF = null;
    this.lastFPrime = null;
    this.lastError = dimensionState(this.dimensions);
    this.leapCount = 0;
    this.leapCooldown = 0;
    this.events = [];
  }

  beginTick() {
    this.adaptationPressure *= this.adaptationPressureDecay;
    if (this.leapCooldown > 0) this.leapCooldown -= 1;
    if (this.phase === "M_delta") this.phase = "M_act";
  }

  interpret(ribSection, reliability = this.reliability) {
    if (!(ribSection instanceof RIBSection)) {
      throw new Error("MBNode.interpret requires a RIBSection");
    }
    const f = {};
    for (const dimension of this.dimensions) {
      f[dimension] = clamp((ribSection.values[dimension] ?? 0) * reliability[dimension]);
    }
    return f;
  }

  compare(f, fPrime) {
    const error = {};
    for (const dimension of this.dimensions) {
      error[dimension] = Math.abs((fPrime[dimension] ?? 0) - (f[dimension] ?? 0));
    }
    return error;
  }

  updateReliability(error) {
    const previous = { ...this.reliability };
    for (const dimension of this.dimensions) {
      const target = 1 - clamp(error[dimension] ?? 0);
      const rate = this.alignRate[dimension];
      this.reliability[dimension] = clamp(
        previous[dimension] + (target - previous[dimension]) * rate,
        this.reliabilityMin,
        this.reliabilityMax,
      );
    }
    return {
      previous,
      current: { ...this.reliability },
    };
  }

  compareSections({
    currentSection,
    laterSection,
    unresolved = true,
    adapt = true,
    tick = 0,
  } = {}) {
    if (!(currentSection instanceof RIBSection) || !(laterSection instanceof RIBSection)) {
      throw new Error("compareSections requires currentSection and laterSection RIBSection values");
    }
    this.beginTick();

    // Freeze the self-side section for both interpretations. Any local adaptive
    // update happens only after F/F' and E have been established.
    const frozenReliability = { ...this.reliability };
    const F = this.interpret(currentSection, frozenReliability);
    const FPrime = this.interpret(laterSection, frozenReliability);
    const E = this.compare(F, FPrime);

    if (unresolved) this.h.recordUnresolved(E);
    else this.h.dissipateTick();

    const dMB = adapt
      ? this.updateReliability(E)
      : { previous: frozenReliability, current: { ...this.reliability } };

    const largestError = Math.max(0, ...Object.values(E));
    this.adaptationPressure = clamp(
      this.adaptationPressure + largestError * this.adaptationPressureGain,
      0,
      this.adaptationPressureMax,
    );

    this.lastF = { ...F };
    this.lastFPrime = { ...FPrime };
    this.lastError = { ...E };

    const leap = this.leapEngine.maybeLeap(this, tick);
    return {
      F: { ...F },
      FPrime: { ...FPrime },
      E: { ...E },
      H: this.h.norm(),
      HVector: this.h.snapshot(),
      unresolved,
      dMB,
      adaptationPressure: this.adaptationPressure,
      theta: this.boundary.threshold(),
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
      F: this.lastF ? { ...this.lastF } : null,
      FPrime: this.lastFPrime ? { ...this.lastFPrime } : null,
      E: { ...this.lastError },
      H: this.h.norm(),
      HVector: this.h.snapshot(),
      adaptationPressure: this.adaptationPressure,
      theta: this.boundary.threshold(),
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

  connect(from, to, { type = "relation", weight = 1, label = "" } = {}) {
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
