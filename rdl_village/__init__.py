"""RDL village simulation package.

The existing simulation keeps compatibility with the historical T4 drafts, but
current Core semantics follow RDL Core v2.3.  Canonical village-local state
names are exported alongside legacy aliases during migration.
"""

from .core import (
    ActionBoundary,
    BasalExplorationLoad,
    Boundary,
    ExplorationState,
    HVec,
    LeapEngine,
    LocalLoadVector,
    Phase,
    XiPool,
)
from .npc import VillageNPC
from .profiles import REFERENCE_PROFILE, VILLAGE_PROFILE, Profile
from .simulation import VillageObserver, VillageSimulation
from .v23_boundary import (
    VillageBoundary,
    VillageRIBSection,
    VillageInterpretation,
    VillageMismatch,
    VillageUnresolvedH,
)
from .world import PhysicalWorld, VillageClock

__all__ = [
    "ActionBoundary",
    "BasalExplorationLoad",
    "ExplorationState",
    "LocalLoadVector",
    "LeapEngine",
    "Phase",
    "VillageBoundary",
    "VillageRIBSection",
    "VillageInterpretation",
    "VillageMismatch",
    "VillageUnresolvedH",
    # Legacy compatibility names. These no longer define Core H/xi/B semantics.
    "Boundary",
    "HVec",
    "XiPool",
    "Profile",
    "REFERENCE_PROFILE",
    "VILLAGE_PROFILE",
    "PhysicalWorld",
    "VillageClock",
    "VillageNPC",
    "VillageSimulation",
    "VillageObserver",
]
