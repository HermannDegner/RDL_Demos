# rdl_system/profiles

`rdl_system/profiles/` keeps B-dependent coefficient hypotheses out of `rdl_system/core/`.

`rdl_system/core/` provides the executable grammar: `Boundary`, `MBNode`, `HVector`,
`LeapEngine`, and `MBGraph`. `HVector` stores unresolved `H_vec`; scalar `H` is formed as `||H_vec||` before the `θ` decision. Profiles provide coefficient bundles for a specific boundary, demo, or experiment.

T2 Function contracts live separately in `rdl_system/functions/`; profile coefficients are not Functions and are not `M_B` by themselves.

## Included Profiles

| Profile | Role |
|---|---|
| `referenceProfile` | Safe fallback for small reference simulations |
| `livingFieldProfile` | Starting point for browser ecology demos |
| `botProfile` | Conservative turn-based conversation graph starting point |
| `causalScaleProfile` | Placeholder for coefficients derived from B-local causal scale |

## Example

```js
import { createProfiledNode, livingFieldProfile } from "./index.mjs";

const node = createProfiledNode({
  id: "rabbit-1",
  dimensions: ["resource", "danger", "motion"],
  profile: livingFieldProfile,
});
```

Profiles are hypotheses. They are expected to be tested, broken, and replaced by
`rdl_system/experiment/` outputs for each target B.
