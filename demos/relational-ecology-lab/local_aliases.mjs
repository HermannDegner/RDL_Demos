// Staged runtime naming bridge for the Living Field migration.
//
// Historical storage names remain in core.mjs so seeded behaviour stays
// unchanged during the cutover.  These aliases expose what those fields
// actually are in the current model:
//
//   H              -> localLoad
//   xi             -> adaptationPressure
//   thetaEffective -> localLeapThreshold
//
// None of these aliases promotes the historical fields into Core H / xi / theta.

import { RelationalAgent } from './core.mjs';

function defineAlias(name, descriptor) {
  if (Object.getOwnPropertyDescriptor(RelationalAgent.prototype, name)) return;
  Object.defineProperty(RelationalAgent.prototype, name, {
    configurable: true,
    enumerable: false,
    ...descriptor,
  });
}

defineAlias('localLoad', {
  get() {
    return this.H;
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
    return this.thetaEffective;
  },
});
