// Runtime naming bridge plus browser-only canonical Living Field bootstrap.
//
// Historical storage names remain in core.mjs for regression compatibility:
//   H              -> localLoad
//   xi             -> adaptationPressure
//   thetaEffective -> localLeapThreshold
//
// Under the complete canonical browser runtime, localLoad/localLeapThreshold
// read from the v2.3 H sidecars instead. adaptationPressure remains the demo-
// local historical scalar and is never promoted to Core ξ.
import { RelationalAgent, Simulation } from './core.mjs';
import { installLiveCanonicalLivingFieldRuntime } from './v23_live_runtime.mjs';

function defineAlias(name, descriptor) {
  if (Object.getOwnPropertyDescriptor(RelationalAgent.prototype, name)) return;
  Object.defineProperty(RelationalAgent.prototype, name, {
    configurable: true,
    enumerable: false,
    ...descriptor,
  });
}

function canonicalLoad(agent) {
  const general = agent.v23CanonicalController?.sidecar?.snapshot?.().HVector ?? null;
  const attack = agent.v23AttackCanonicalController?.sidecar?.snapshot?.().HVector ?? null;
  if (!general && !attack) return null;
  return {
    ...(general ?? {}),
    ...(attack ?? {}),
  };
}

defineAlias('localLoad', {
  get() {
    return canonicalLoad(this) ?? this.H;
  },
  set(value) {
    this.H = value;
  },
});

defineAlias('adaptationPressure', {
  get() {
    return this.xi;
  },
  set(value) {
    this.xi = value;
  },
});

defineAlias('localLeapThreshold', {
  get() {
    return this.v23CanonicalController?.theta ?? this.thetaEffective;
  },
});

function finiteQueryNumber(query, name, fallback) {
  const raw = query.get(name);
  if (raw == null || raw === '') return fallback;
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 ? value : fallback;
}

function finiteQueryInteger(query, name, fallback, minimum = 1) {
  const raw = query.get(name);
  if (raw == null || raw === '') return fallback;
  const value = Number.parseInt(raw, 10);
  return Number.isInteger(value) && value >= minimum ? value : fallback;
}

// app.mjs constructs Simulation directly. Because this module is evaluated
// before app.mjs body execution, the browser-only prototype bridge can ensure
// v2.3 observation is present from episode creation and install the complete
// canonical runtime before the first physical tick. Node imports remain
// untouched because `window` is absent there.
if (typeof window !== 'undefined' && !Simulation.prototype.__rdlV23BrowserBootstrap) {
  const query = new URLSearchParams(window.location.search);
  const options = Object.freeze({
    theta: finiteQueryNumber(query, 'theta', 1),
    attackTheta: finiteQueryNumber(query, 'attackTheta', 1),
    reviewWindows: finiteQueryInteger(query, 'reviewWindows', 2, 2),
    attackReviewWindows: finiteQueryInteger(query, 'attackReviewWindows', 2, 2),
    probeWindows: finiteQueryInteger(query, 'probeWindows', 2, 1),
    attackProbeWindows: finiteQueryInteger(query, 'attackProbeWindows', 2, 1),
    reentryValidationWindows: finiteQueryInteger(query, 'reentryWindows', 2, 1),
    attackReentryValidationWindows: finiteQueryInteger(query, 'attackReentryWindows', 2, 1),
  });
  const originalCreateEpisode = Simulation.prototype.createEpisode;
  const originalStepOnce = Simulation.prototype.stepOnce;

  Simulation.prototype.createEpisode = function canonicalEpisodeBootstrap(...args) {
    this.observeV23 = true;
    return originalCreateEpisode.apply(this, args);
  };

  Simulation.prototype.stepOnce = function canonicalStepBootstrap(...args) {
    if (!this.v23LiveCanonicalRuntime) {
      installLiveCanonicalLivingFieldRuntime(this, options);
    }
    return originalStepOnce.apply(this, args);
  };

  Object.defineProperty(Simulation.prototype, '__rdlV23BrowserBootstrap', {
    configurable: false,
    enumerable: false,
    value: Object.freeze({
      authority: 'complete-canonical-v23',
      options,
      legacyNumericXiIsCoreXi: false,
    }),
  });
}
