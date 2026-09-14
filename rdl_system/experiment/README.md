# rdl_system/experiment

`rdl_system/experiment/` is for coefficient search and durability checks around the finite demo models.

It keeps exploratory logic out of `rdl_system/core/` and `rdl_system/functions/`. The core exposes the current RDL v2.3 role separation, functions expose T2 input/output contracts, profiles provide local coefficient hypotheses, and experiments test whether those hypotheses survive a declared target Boundary.

## Tools

| File | Role |
|---|---|
| `durability_metrics.mjs` | Summarize leap rate, demo-local adaptation-pressure saturation, scalar H silence, and reliability collapse |
| `parameter_search.mjs` | Run a deterministic grid search across parameter bundles and seeds |

`adaptationPressure` is a demo-local diagnostic quantity.

```text
adaptationPressure != Core ξ
adaptationPressure != Core H
```

Core `ξ` is not a parameter-search variable in this directory.

Core-facing snapshots distinguish:

```text
HVector = unresolved H_vec components
H       = ||HVector||
```

The current reference implementation uses an L2 norm as its finite demo concretization.

## Example Shape

```js
runParameterSearch({
  makeSimulation,
  parameterGrid: {
    adaptationPressureDecay: [0.88, 0.92, 0.96],
    cooldownTicks: [4, 10, 20],
  },
  seeds: [1, 2, 3],
  ticks: 600,
});
```

The intended cycle is:

```text
Purpose / B を仮設する
→ RIB_B または身分付き finite state を構成する
→ 必要なら Function_B の input_role / output_role 契約を通す
→ 係数を仮設する
→ 回す
→ F / F' / E / H と破断条件を見る
→ 適用範囲・unresolved・来歴を残す
→ 必要なら引き直す
```

探索で良かった係数は、そのままCore定数や普遍則へ昇格しない。
Functionの出力も、そのまま `M_B` や `RIB_B` と同一視せず、output_roleに従って次段へ接続する。
