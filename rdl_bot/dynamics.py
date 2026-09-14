"""rdl_bot legacy-local dynamics coefficients.

These parameters keep the historical CLI behaviour reproducible while the bot
migrates to Core v2.3.  They are implementation / Standard-Model candidates,
not mandatory Core laws.

In particular:

- ``xi_*`` keys are legacy configuration names for unresolved-input pressure;
  that pressure is not Core xi;
- ``theta_eff`` adjustment is a bot-local compatibility policy, not a Core
  ``xi -> theta`` rule;
- ``kappa_*`` and dissipation coefficients are implementation hypotheses;
- alignment/reinforcement coefficients do not define the unique Core update
  law for M_B.

Canonical semantic comparison lives in ``v23_state.py``.
"""

import json
from dataclasses import dataclass, asdict, fields
from typing import Optional


@dataclass
class DynamicsConfig:
    # --- Legacy CLI threshold policy ---
    theta_initial: float = 2.0
    theta_max: float = 5.0
    theta_raise_on_leap: float = 1.05
    theta_relax: float = 0.97

    # Historical xi_* keys. Semantically these configure the local
    # unresolved-input/coverage pressure path, NOT Core xi.
    xi_saturation: float = 10.0
    xi_drop_ratio: float = 0.25
    xi_jitter_ratio: float = 0.10

    # --- Demo-local alignment / reinforcement policy ---
    align_rate_exact: float = 0.04
    align_rate_partial: float = 0.02
    alignment_ceiling: float = 0.9

    # --- Optional implementation inertia / self-modification policy ---
    kappa_m0: float = 5.0
    kappa_hitl_threshold: float = 0.15
    inertia_usage_weight: float = 0.3
    inertia_approval_weight: float = 0.5

    # --- Demo-local load dissipation policy ---
    dissipation_gamma: float = 0.01
    dissipation_cap: float = 0.15

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DynamicsConfig":
        known = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in known})


CONFIG = DynamicsConfig()


def configure(config: DynamicsConfig) -> None:
    """Replace the current legacy-local coefficient bundle."""
    global CONFIG
    CONFIG = config


def load_dynamics_config(path: str) -> DynamicsConfig:
    """Load optional local coefficients; fall back to defaults on missing/invalid JSON."""
    try:
        with open(path, encoding="utf-8") as file:
            return DynamicsConfig.from_dict(json.load(file))
    except FileNotFoundError:
        return DynamicsConfig()
    except json.JSONDecodeError:
        print(f"  [ERROR] 動態係数のJSONが壊れています ({path})。既定値を使います。")
        return DynamicsConfig()


def resolve(value: Optional[float], field_name: str) -> float:
    """Resolve an optional parameter against the current local coefficient bundle."""
    return getattr(CONFIG, field_name) if value is None else value
