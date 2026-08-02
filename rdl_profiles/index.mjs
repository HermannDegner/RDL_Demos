import {
  Boundary,
  HVector,
  LeapEngine,
  MBNode,
} from "../rdl_core/index.mjs";

export const referenceProfile = Object.freeze({
  id: "reference",
  description: "Safe fallback coefficients for small reference simulations.",
  boundary: Object.freeze({
    thetaBase: 0.8,
    thetaMin: 0.28,
    thetaMax: 2,
    xiThetaWeight: 0.26,
  }),
  node: Object.freeze({
    reliability: 0.7,
    alignRate: 0.035,
    reliabilityMin: 0.18,
    reliabilityMax: 0.98,
    xiDecay: 0.94,
    xiGain: 0.12,
    xiMax: 1.2,
  }),
  h: Object.freeze({
    decay: 0.9,
    gain: 1,
    residualAfterLeap: 0.28,
  }),
  leap: Object.freeze({
    cooldownTicks: 10,
  }),
});

export const livingFieldProfile = Object.freeze({
  ...referenceProfile,
  id: "living-field",
  description: "Starting coefficients matching RDL Living Field style dynamics.",
});

export const botProfile = Object.freeze({
  ...referenceProfile,
  id: "rdl-bot",
  description: "Conservative turn-based coefficients for conversation graph experiments.",
  boundary: Object.freeze({
    ...referenceProfile.boundary,
    thetaBase: 2,
    thetaMin: 1.2,
    xiThetaWeight: 0.18,
  }),
  node: Object.freeze({
    ...referenceProfile.node,
    alignRate: 0.02,
    xiDecay: 0.88,
    xiGain: 0.08,
    xiMax: 1,
  }),
  h: Object.freeze({
    ...referenceProfile.h,
    decay: 0.82,
    gain: 1,
  }),
  leap: Object.freeze({
    cooldownTicks: 4,
  }),
});

export const causalScaleProfile = Object.freeze({
  ...referenceProfile,
  id: "causal-scale",
  description: "Placeholder profile for coefficients derived from B-local causal scale.",
});

export function mergeProfile(profile = referenceProfile, overrides = {}) {
  return {
    ...profile,
    ...overrides,
    boundary: { ...(profile.boundary ?? {}), ...(overrides.boundary ?? {}) },
    node: { ...(profile.node ?? {}), ...(overrides.node ?? {}) },
    h: { ...(profile.h ?? {}), ...(overrides.h ?? {}) },
    leap: { ...(profile.leap ?? {}), ...(overrides.leap ?? {}) },
  };
}

export function boundaryConfig(profile, overrides = {}) {
  return { ...(profile.boundary ?? {}), ...overrides };
}

export function nodeConfig(profile, overrides = {}) {
  return { ...(profile.node ?? {}), ...overrides };
}

export function hConfig(profile, overrides = {}) {
  return { ...(profile.h ?? {}), ...overrides };
}

export function leapConfig(profile, overrides = {}) {
  return { ...(profile.leap ?? {}), ...overrides };
}

export function createProfiledNode({
  id,
  dimensions,
  profile = referenceProfile,
  boundary = {},
  node = {},
  h = {},
  leap = {},
} = {}) {
  const resolved = mergeProfile(profile);
  const boundaryInstance = new Boundary({
    id: boundary.id ?? `${id ?? "node"}-B`,
    dimensions,
    ...boundaryConfig(resolved, boundary),
  });
  const hVector = new HVector({
    dimensions,
    ...hConfig(resolved, h),
  });
  const leapEngine = new LeapEngine(leapConfig(resolved, leap));
  return new MBNode({
    id,
    boundary: boundaryInstance,
    h: hVector,
    leapEngine,
    ...nodeConfig(resolved, node),
  });
}
