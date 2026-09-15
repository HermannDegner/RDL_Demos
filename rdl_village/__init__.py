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
from . import dialogue_local_aliases as _dialogue_local_aliases  # noqa: F401
from .npc import VillageNPC
from .profiles import REFERENCE_PROFILE, VILLAGE_PROFILE, Profile
from .simulation import VillageObserver, VillageSimulation
from .v23_boundary import (
    VillageBoundary,
    VillageBoundaryChange,
    VillageCoverageError,
    VillageDifferenceAssessment,
    VillageInterpretation,
    VillageMismatch,
    VillageRIBSection,
    VillageUnresolvedH,
    assess_village_mismatch,
)
from .v23_live_observer import VillageCanonicalObserver, attach_v23_observer
from .world import PhysicalWorld, VillageClock

__all__ = [
    "ActionBoundary",
    "BasalExplorationLoad",
    "ExplorationState",
    "LocalLoadVector",
    "LeapEngine",
    "Phase",
    "VillageBoundary",
    "VillageBoundaryChange",
    "VillageCoverageError",
    "VillageDifferenceAssessment",
    "VillageRIBSection",
    "VillageInterpretation",
    "VillageMismatch",
    "VillageUnresolvedH",
    "VillageCanonicalObserver",
    "assess_village_mismatch",
    "attach_v23_observer",
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
