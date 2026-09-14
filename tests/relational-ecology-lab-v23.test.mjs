import test from 'node:test';
import assert from 'node:assert/strict';

import {
  BoundaryContext,
  CoverageState,
  InteractionSection,
  UnresolvedMismatchState,
  acquireInteractionSection,
  compareInterpretations,
  interpretSection,
} from '../demos/relational-ecology-lab/v23_state.mjs';

function context() {
  return new BoundaryContext({
    boundaryId: 'living-field:test',
    purpose: 'compare one agent interaction section across time',
    question: 'what changed under the same finite interpretive model?',
    conditions: { species: 'rabbit' },
  });
}

function interpreter(section) {
  return {
    resource: Number(section.payload.resource ?? 0),
    danger: Number(section.payload.danger ?? 0),
    motion: Number(section.payload.motion ?? 0),
  };
}

test('raw ecology data and RIB_B section remain distinct', () => {
  const raw = { resource: 0.2, danger: 0.1, motion: 0.7 };
  const section = acquireInteractionSection({
    sectionId: 't0',
    context: context(),
    payload: raw,
    provenance: { source: 'living-field-simulation', tick: 10 },
  });

  assert.ok(section instanceof InteractionSection);
  assert.notEqual(section, raw);
  assert.deepEqual(section.payload, raw);
  assert.equal(section.provenance.source, 'living-field-simulation');
});

test("same pre-update model forms F, F' and canonical E", () => {
  const currentSection = acquireInteractionSection({
    sectionId: 't0', context: context(), payload: { resource: 0.2, danger: 0.1, motion: 0.7 },
  });
  const laterSection = acquireInteractionSection({
    sectionId: 't1', context: context(), payload: { resource: 0.6, danger: 0.25, motion: 0.4 },
  });

  const current = interpretSection(currentSection, { modelRef: 'M_B:pre-update:1', interpreter });
  const later = interpretSection(laterSection, { modelRef: 'M_B:pre-update:1', interpreter });
  const mismatch = compareInterpretations(current, later);

  assert.deepEqual(mismatch.values, { resource: 0.4, danger: 0.15, motion: 0.29999999999999993 });
  assert.equal(mismatch.magnitude, 0.4);
  assert.deepEqual(mismatch.reasons, ['danger', 'motion', 'resource']);
});

test('model drift is rejected before E is formed', () => {
  const section = acquireInteractionSection({
    sectionId: 't0', context: context(), payload: { resource: 0.2 },
  });
  const current = interpretSection(section, { modelRef: 'M_B:1', interpreter });
  const later = interpretSection(section, { modelRef: 'M_B:2', interpreter });

  assert.throws(() => compareInterpretations(current, later), /same pre-update modelRef/);
});

test('resolved canonical mismatch does not enter H', () => {
  const state = new UnresolvedMismatchState({ theta: 0.3, decay: 1 });
  const current = interpretSection(
    acquireInteractionSection({ sectionId: 't0', context: context(), payload: { resource: 0.1 } }),
    { modelRef: 'M_B:1', interpreter },
  );
  const later = interpretSection(
    acquireInteractionSection({ sectionId: 't1', context: context(), payload: { resource: 0.8 } }),
    { modelRef: 'M_B:1', interpreter },
  );
  const mismatch = compareInterpretations(current, later);

  state.observe(mismatch, { unresolved: false });
  assert.equal(state.magnitude, 0);
  assert.equal(state.shouldReconstruct, false);
});

test('unresolved canonical mismatch can drive fixed theta', () => {
  const state = new UnresolvedMismatchState({ theta: 0.3, decay: 1 });
  const current = interpretSection(
    acquireInteractionSection({ sectionId: 't0', context: context(), payload: { danger: 0.1 } }),
    { modelRef: 'M_B:1', interpreter },
  );
  const later = interpretSection(
    acquireInteractionSection({ sectionId: 't1', context: context(), payload: { danger: 0.5 } }),
    { modelRef: 'M_B:1', interpreter },
  );

  state.observe(compareInterpretations(current, later), { unresolved: true });
  assert.equal(state.magnitude, 0.4);
  assert.equal(state.shouldReconstruct, true);
  assert.equal(state.theta, 0.3);
});

test('coverage remains separate from H and Core xi', () => {
  const coverage = new CoverageState();
  const state = new UnresolvedMismatchState({ theta: 0.2 });

  coverage.recordMissing(2);
  coverage.recordUnknownRelation();
  coverage.recordRejected();

  assert.deepEqual(coverage.snapshot(), {
    missingObservation: 2,
    unknownRelation: 1,
    rejectedObservation: 1,
  });
  assert.equal(state.magnitude, 0);
  assert.equal(state.theta, 0.2);
  assert.equal('xi' in coverage, false);
});
