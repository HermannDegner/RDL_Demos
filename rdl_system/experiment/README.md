# rdl_system/experiment

`rdl_system/experiment/` is for coefficient search and durability checks around the finite demo models.

It keeps exploratory logic out of `rdl_system/core/`. The core exposes the current RDL v2.3 role separation, profiles provide local coefficient hypotheses, and experiments test whether those hypotheses survive a declared target Boundary.

## Tools

| File | Role |
|---|---|
| `durability_metrics.mjs` | Summarize leap rate, demo-local adaptation-pressure saturation, H silence, and reliability collapse |
| `parameter_search.mjs` | Run a deterministic grid search across parameter bundles and seeds |

`adaptationPressure` is a demo-local diagnostic quantity.

```text
adaptationPressure != Core ξ
adaptationPressure != Core H
```

Core `ξ` is not a parameter-search variable in this directory.

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
→ RIB_B / Function input を構成する
→ 係数を仮設する
→ 回す
→ F / F' / E / H と破断条件を見る
→ 適用範囲・未回収・来歴を残す
→ 必要なら引き直す
```

探索で良かった係数は、そのままCore定数や普遍則へ昇格しない。
