import test from 'node:test';
import assert from 'node:assert/strict';

import { RelationalAgent } from '../demos/relational-ecology-lab/core.mjs';
import '../demos/relational-ecology-lab/local_aliases.mjs';

function legacyAgentStub() {
  const agent = Object.create(RelationalAgent.prototype);
  agent.H = { resource: 0.2, danger: 0.5, motion: 0.1 };
  agent.xi = 0.4;
  agent.thetaBase = 0.9;
  return agent;
}

test('Living Field runtime exposes demo-local names without changing behaviour', () => {
  const agent = legacyAgentStub();

  assert.equal(agent.localLoad, agent.H);
  assert.equal(agent.adaptationPressure, agent.xi);
  assert.equal(agent.localLeapThreshold, agent.thetaEffective);
});

test('localLoad and adaptationPressure remain write-through compatibility aliases', () => {
  const agent = legacyAgentStub();
  const nextLoad = { resource: 0.7, danger: 0.1, motion: 0.3 };

  agent.localLoad = nextLoad;
  agent.adaptationPressure = 0.25;

  assert.equal(agent.H, nextLoad);
  assert.equal(agent.xi, 0.25);
  assert.equal(agent.localLoad, nextLoad);
  assert.equal(agent.adaptationPressure, 0.25);
});

test('localLeapThreshold is the historical local policy, not a Core xi rule', () => {
  const agent = legacyAgentStub();
  const expected = Math.max(0.5, Math.min(1.05, agent.thetaBase - agent.adaptationPressure * 0.26));

  assert.equal(agent.localLeapThreshold, expected);
  assert.equal(Object.hasOwn(agent, 'localLeapThreshold'), false);
});
