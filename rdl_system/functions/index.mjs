import { RIBSection } from "../core/index.mjs";

const KNOWN_INPUT_ROLES = new Set([
  "RIB_B",
  "F",
  "state",
  "profile",
  "function_output",
]);

function asArray(value) {
  if (value == null) return [];
  return Array.isArray(value) ? [...value] : [value];
}

export class FunctionContractError extends Error {
  constructor(message) {
    super(message);
    this.name = "FunctionContractError";
  }
}

export class FunctionModule {
  constructor({
    id,
    version = "0.1.0",
    purpose,
    boundaryId,
    inputRole,
    outputRole,
    transform,
    inputValidator = null,
    outputValidator = null,
    constraints = {},
    failureConditions = [],
    provenance = null,
    compatibility = null,
    scale = null,
    timeScope = null,
  }) {
    if (!id) throw new FunctionContractError("FunctionModule requires id");
    if (!purpose) throw new FunctionContractError("FunctionModule requires purpose");
    if (!boundaryId) throw new FunctionContractError("FunctionModule requires boundaryId (B_f)");
    if (!inputRole) throw new FunctionContractError("FunctionModule requires inputRole");
    if (!outputRole) throw new FunctionContractError("FunctionModule requires outputRole");
    if (typeof transform !== "function") {
      throw new FunctionContractError("FunctionModule requires a transform function");
    }

    this.id = id;
    this.version = version;
    this.purpose = purpose;
    this.boundaryId = boundaryId;
    this.inputRole = inputRole;
    this.outputRole = outputRole;
    this.transform = transform;
    this.inputValidator = inputValidator;
    this.outputValidator = outputValidator;
    this.constraints = Object.freeze({ ...constraints });
    this.failureConditions = Object.freeze([...failureConditions]);
    this.provenance = provenance;
    this.compatibility = compatibility;
    this.scale = scale;
    this.timeScope = timeScope;
  }

  spec() {
    return Object.freeze({
      id: this.id,
      version: this.version,
      purpose: this.purpose,
      boundaryId: this.boundaryId,
      inputRole: this.inputRole,
      outputRole: this.outputRole,
      constraints: this.constraints,
      failureConditions: this.failureConditions,
      provenance: this.provenance,
      compatibility: this.compatibility,
      scale: this.scale,
      timeScope: this.timeScope,
    });
  }

  validateInput(input) {
    if (this.inputRole === "RIB_B") {
      if (!(input instanceof RIBSection)) {
        throw new FunctionContractError(`${this.id} expects inputRole=RIB_B`);
      }
      if (input.boundaryId !== this.boundaryId) {
        throw new FunctionContractError(
          `${this.id} boundary mismatch: ${input.boundaryId} != ${this.boundaryId}`,
        );
      }
    }

    if (this.inputValidator && !this.inputValidator(input, this.spec())) {
      throw new FunctionContractError(`${this.id} input contract rejected the value`);
    }
  }

  validateOutput(value) {
    if (this.outputValidator && !this.outputValidator(value, this.spec())) {
      throw new FunctionContractError(`${this.id} output contract rejected the value`);
    }
  }

  run(input, context = {}) {
    this.validateInput(input);

    const raw = this.transform(input, {
      ...context,
      functionSpec: this.spec(),
    });

    const structured = raw && typeof raw === "object" && Object.hasOwn(raw, "value")
      ? raw
      : { value: raw };

    this.validateOutput(structured.value);

    const result = {
      functionId: this.id,
      functionVersion: this.version,
      boundaryId: this.boundaryId,
      inputRole: this.inputRole,
      outputRole: this.outputRole,
      value: structured.value,
      coverage: structured.coverage ?? null,
      unresolved: Object.freeze(asArray(structured.unresolved)),
      failureFlags: Object.freeze(asArray(structured.failureFlags)),
      provenance: structured.provenance ?? this.provenance,
    };

    // Core ξ is deliberately not converted into a scalar/result field here.
    // Finite-B open relations remain a condition on the Function contract.
    return Object.freeze(result);
  }
}

export class FunctionRegistry {
  constructor() {
    this.modules = new Map();
  }

  register(module) {
    if (!(module instanceof FunctionModule)) {
      throw new FunctionContractError("FunctionRegistry.register requires FunctionModule");
    }
    const key = `${module.id}@${module.version}`;
    this.modules.set(key, module);
    return module;
  }

  find({ purpose = null, boundaryId = null, inputRole = null, outputRole = null } = {}) {
    return [...this.modules.values()].filter((module) => (
      (purpose === null || module.purpose === purpose)
      && (boundaryId === null || module.boundaryId === boundaryId)
      && (inputRole === null || module.inputRole === inputRole)
      && (outputRole === null || module.outputRole === outputRole)
    ));
  }
}

export function isKnownInputRole(role) {
  return KNOWN_INPUT_ROLES.has(role);
}
