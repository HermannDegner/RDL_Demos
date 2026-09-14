import test from "node:test";
import assert from "node:assert/strict";

import { Boundary, MBNode } from "../rdl_system/core/index.mjs";
import {
  FunctionContractError,
  FunctionModule,
  FunctionRegistry,
} from "../rdl_system/functions/index.mjs";

test("FunctionModule は M_B と同一視せず、B と input/output role を契約として持つ", () => {
  const boundary = new Boundary({
    id: "B-resource",
    dimensions: ["resource", "danger"],
  });
  const mb = new MBNode({ id: "agent-model", boundary });
  const fn = new FunctionModule({
    id: "resource-score",
    purpose: "rank resource opportunity",
    boundaryId: boundary.id,
    inputRole: "RIB_B",
    outputRole: "state",
    transform: (section) => ({
      value: (section.values.resource ?? 0) - (section.values.danger ?? 0),
    }),
  });

  assert.ok(fn instanceof FunctionModule);
  assert.ok(mb instanceof MBNode);
  assert.notEqual(fn, mb);
  assert.equal(fn.spec().boundaryId, "B-resource");
  assert.equal(fn.spec().inputRole, "RIB_B");
  assert.equal(fn.spec().outputRole, "state");
});

test("RIB_B input contract は別Bの section を拒否する", () => {
  const b1 = new Boundary({ id: "B-1", dimensions: ["x"] });
  const b2 = new Boundary({ id: "B-2", dimensions: ["x"] });
  const fn = new FunctionModule({
    id: "bounded-transform",
    purpose: "test boundary contract",
    boundaryId: b1.id,
    inputRole: "RIB_B",
    outputRole: "state",
    transform: (section) => ({ value: section.values.x ?? 0 }),
  });

  assert.throws(
    () => fn.run(b2.section({ x: 1 }, { id: "wrong-B" })),
    FunctionContractError,
  );
});

test("unresolved と provenance は値から分離され、Core ξ の数値欄は生成しない", () => {
  const boundary = new Boundary({ id: "B-observation", dimensions: ["x"] });
  const fn = new FunctionModule({
    id: "partial-observation",
    version: "0.2.0",
    purpose: "retain partial observation status",
    boundaryId: boundary.id,
    inputRole: "RIB_B",
    outputRole: "state",
    provenance: "fixture:function",
    transform: () => ({
      value: 0,
      coverage: 0.5,
      unresolved: ["x:not-observed"],
      failureFlags: ["partial-input"],
    }),
  });

  const result = fn.run(boundary.section({}, { id: "partial" }));

  assert.equal(result.value, 0);
  assert.equal(result.coverage, 0.5);
  assert.deepEqual(result.unresolved, ["x:not-observed"]);
  assert.deepEqual(result.failureFlags, ["partial-input"]);
  assert.equal(result.provenance, "fixture:function");
  assert.equal(Object.hasOwn(result, "xi"), false);
  assert.equal(Object.hasOwn(result, "ξ"), false);
});

test("FunctionRegistry は Purpose / B / input/output role で候補を絞れる", () => {
  const registry = new FunctionRegistry();
  registry.register(new FunctionModule({
    id: "a",
    purpose: "compare",
    boundaryId: "B-a",
    inputRole: "state",
    outputRole: "state",
    transform: (value) => value,
  }));
  registry.register(new FunctionModule({
    id: "b",
    purpose: "compare",
    boundaryId: "B-b",
    inputRole: "F",
    outputRole: "state",
    transform: (value) => value,
  }));

  const found = registry.find({
    purpose: "compare",
    boundaryId: "B-b",
    inputRole: "F",
    outputRole: "state",
  });

  assert.equal(found.length, 1);
  assert.equal(found[0].id, "b");
});
