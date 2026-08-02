# rdl_experiment

`rdl_experiment/` is for coefficient search and durability checks.

It keeps exploratory logic out of `rdl_core/`. The core executes RDL dynamics,
profiles provide coefficient hypotheses, and experiments test whether those
hypotheses survive a target B.

## Tools

| File | Role |
|---|---|
| `durability_metrics.mjs` | Summarize leap rate, xi saturation, H silence, and reliability collapse |
| `parameter_search.mjs` | Run a deterministic grid search across parameter bundles and seeds |

## Example Shape

```js
runParameterSearch({
  makeSimulation,
  parameterGrid: {
    xiDecay: [0.88, 0.92, 0.96],
    cooldownTicks: [4, 10, 20],
  },
  seeds: [1, 2, 3],
  ticks: 600,
});
```

The intended cycle is:

```text
Bを仮設する -> 係数を仮設する -> 回す -> 破断を見る -> 引き直す
```
