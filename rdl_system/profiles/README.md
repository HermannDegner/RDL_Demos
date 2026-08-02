# rdl_system/profiles

`rdl_system/profiles/` keeps B-dependent coefficient hypotheses out of `rdl_system/core/`.

`rdl_system/core/` provides the executable grammar: `Boundary`, `MBNode`, `HVector`,
`LeapEngine`, and `MBGraph`. Profiles provide coefficient bundles for a specific
boundary, demo, or experiment.

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
`rdl_experiment/` outputs for each target B.
