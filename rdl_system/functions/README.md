# rdl_system/functions

`Aporapeiron/RDL_Functions` の Core v2.3 同期後の Function 契約を、デモ用の最小コードで確認する T2 参照層。

規範定義はこのディレクトリではなく、`Aporapeiron/RDL_Functions` の `02_Function_Design/01_RDL_Functionと局所M_B.md` にある。

## 境界

```text
Function != M_B
Function != SILN
Function != RIB_B
```

ここでの `FunctionModule` は、有限な `B_f` のもとで身分付き入力へ局所拘束を作用させ、身分付き出力を返す演算モジュールである。

最小契約:

```text
FunctionSpec
├ id / version
├ Purpose
├ B_f
├ input_role
├ local constraints / transform
├ output_role
├ failure conditions
├ unresolved
├ provenance
└ compatibility
```

`ξ` は Function の数値出力へ変換しない。`UNKNOWN / NOT_OBSERVED / UNRESOLVED` は `unresolved` として値から分離して保持する。

## 例

```js
import { Boundary } from "../core/index.mjs";
import { FunctionModule } from "./index.mjs";

const boundary = new Boundary({
  id: "B-resource",
  dimensions: ["resource", "danger"],
});

const section = boundary.section(
  { resource: 0.8, danger: 0.3 },
  { id: "resource-section", provenance: "demo sensor" },
);

const scoreResource = new FunctionModule({
  id: "resource-score",
  version: "0.1.0",
  purpose: "rank resource opportunity",
  boundaryId: boundary.id,
  inputRole: "RIB_B",
  outputRole: "state",
  provenance: "RDL_Demos reference",
  constraints: { dangerWeight: 0.5 },
  transform: (ribSection, { functionSpec }) => ({
    value: ribSection.values.resource
      - ribSection.values.danger * functionSpec.constraints.dangerWeight,
    unresolved: ribSection.values.resource == null ? ["resource:not-observed"] : [],
    coverage: 1,
  }),
});

const result = scoreResource.run(section);
console.log(result.value, result.outputRole, result.unresolved);
```

## Composition

Function の出力身分と次の Function の入力身分が一致しない場合、そのまま接続しない。

```text
Function_A output_role = F
Function_B input_role  = RIB_B

F
↓ adapter / action / environment interaction
RIB
↓ B_B
RIB_B
↓ Function_B
```

`FunctionRegistry` は `Purpose / B / input_role / output_role` で候補を検索するためのデモ実装であり、Core primitiveではない。
