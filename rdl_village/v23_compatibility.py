"""Compatibility quarantine for historical Village Core-like names.

The historical Village runtime still exposes several public names and fields
that predate current RDL Core v2.3.  They are retained for snapshot/API
compatibility, but this module makes the role mapping explicit and provides a
local-role view that new operational code can use without treating those names
as Core semantics.

This is a compatibility boundary, not an ontology mapping:

- HVec / agent.h_vec -> LocalLoadVector, not Core H;
- XiPool / agent.xi -> ExplorationState, not Core xi;
- Boundary / agent.boundary -> ActionBoundary, not complete Core B;
- BasalHeat / agent.basal_heat -> BasalExplorationLoad, not Core H.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from .core import ActionBoundary, BasalExplorationLoad, ExplorationState, LocalLoadVector


@dataclass(frozen=True)
class VillageCompatibilityAlias:
    historical_name: str
    local_role_name: str
    runtime_field: str
    role: str
    core_identity: str = "none"
    authority: str = "compatibility-only"


ALIASES = (
    VillageCompatibilityAlias(
        historical_name="HVec",
        local_role_name="LocalLoadVector",
        runtime_field="h_vec",
        role="demo-local multi-channel load containing prediction residuals and direct motivations",
    ),
    VillageCompatibilityAlias(
        historical_name="XiPool",
        local_role_name="ExplorationState",
        runtime_field="xi",
        role="demo-local exploration pressure plus unresolved-outcome queue",
    ),
    VillageCompatibilityAlias(
        historical_name="Boundary",
        local_role_name="ActionBoundary",
        runtime_field="boundary",
        role="demo-local action/reconfiguration threshold policy",
    ),
    VillageCompatibilityAlias(
        historical_name="BasalHeat",
        local_role_name="BasalExplorationLoad",
        runtime_field="basal_heat",
        role="demo-local boredom/exploration motivation",
    ),
)

ALIAS_BY_HISTORICAL_NAME = MappingProxyType({item.historical_name: item for item in ALIASES})

# Modules in this tuple constitute the canonical v2.3 path.  Tests guard these
# modules against depending on compatibility state as H / xi / theta authority.
CANONICAL_V23_MODULES = (
    "v23_boundary.py",
    "v23_live_observer.py",
    "v23_review.py",
    "v23_mdelta_t1.py",
    "v23_authority.py",
    "v23_runtime.py",
    "v23_review_assist.py",
    "v23_operational.py",
)


def village_local_dynamics_view(agent) -> Mapping[str, Any]:
    """Expose historical runtime objects under their local role names.

    This function deliberately does not expose keys named H or xi.  It exists so
    new diagnostics can read compatibility state without inheriting historical
    Core-like vocabulary.
    """

    local_load = agent.h_vec
    exploration = agent.xi
    action_boundary = agent.boundary
    basal_exploration = agent.basal_heat

    if not isinstance(local_load, LocalLoadVector):
        raise TypeError("agent.h_vec is not the quarantined LocalLoadVector role")
    if not isinstance(exploration, ExplorationState):
        raise TypeError("agent.xi is not the quarantined ExplorationState role")
    if not isinstance(action_boundary, ActionBoundary):
        raise TypeError("agent.boundary is not the quarantined ActionBoundary role")
    if not isinstance(basal_exploration, BasalExplorationLoad):
        raise TypeError("agent.basal_heat is not the quarantined BasalExplorationLoad role")

    return MappingProxyType(
        {
            "localLoadVector": local_load,
            "explorationState": exploration,
            "actionBoundary": action_boundary,
            "basalExplorationLoad": basal_exploration,
            "legacyNumericXiIsCoreXi": False,
            "localLoadIsCoreH": False,
            "actionBoundaryIsCompleteCoreB": False,
        }
    )


def compatibility_snapshot() -> Mapping[str, Any]:
    return MappingProxyType(
        {
            "aliases": tuple(
                MappingProxyType(
                    {
                        "historicalName": item.historical_name,
                        "localRoleName": item.local_role_name,
                        "runtimeField": item.runtime_field,
                        "role": item.role,
                        "coreIdentity": item.core_identity,
                        "authority": item.authority,
                    }
                )
                for item in ALIASES
            ),
            "canonicalModules": CANONICAL_V23_MODULES,
            "policy": "legacy-names-quarantined-not-Core-semantics",
            "xiStatus": "unrecovered-relations-remain",
        }
    )
