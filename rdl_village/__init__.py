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
from .v23_authority import (
    INSTALL_KIND,
    INSTALL_SCOPE,
    VillageAuthorityInstallAudit,
    VillageCanonicalAuthority,
    VillageCanonicalAuthorityController,
    VillageContextObserverView,
    install_village_canonical_authority,
)
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
from .v23_mdelta_t1 import (
    VillageMDeltaRequest,
    VillageMDeltaT1Handoff,
    VillageProbeEvidence,
    VillageReconstructionProposal,
    VillageReentryValidation,
    VillageSelectionResult,
    bind_village_mdelta_subject,
    propose_village_reconstruction,
    record_village_probe,
    request_village_mdelta,
    select_village_candidate,
    snapshot_village_subject_slice,
    validate_village_reentry,
)
from .v23_operational import VillageOperationalCoverage, install_village_operational_coverage
from .v23_review import (
    VillageLocalAbsorptionEvidence,
    VillageUnresolvedReviewCandidate,
    review_village_candidate,
)
from .v23_review_assist import VillageReviewAdvisor, VillageReviewRecommendation
from .v23_runtime import (
    VillageCanonicalRuntimeDriver,
    VillageCanonicalRuntimeSession,
    install_village_canonical_runtime,
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
    "VillageBoundaryChange",
    "VillageCoverageError",
    "VillageDifferenceAssessment",
    "VillageRIBSection",
    "VillageInterpretation",
    "VillageMismatch",
    "VillageUnresolvedH",
    "VillageCanonicalObserver",
    "VillageLocalAbsorptionEvidence",
    "VillageUnresolvedReviewCandidate",
    "VillageReviewRecommendation",
    "VillageReviewAdvisor",
    "VillageMDeltaRequest",
    "VillageMDeltaT1Handoff",
    "VillageProbeEvidence",
    "VillageSelectionResult",
    "VillageReconstructionProposal",
    "VillageReentryValidation",
    "VillageAuthorityInstallAudit",
    "VillageCanonicalAuthority",
    "VillageCanonicalAuthorityController",
    "VillageContextObserverView",
    "VillageCanonicalRuntimeDriver",
    "VillageCanonicalRuntimeSession",
    "VillageOperationalCoverage",
    "INSTALL_KIND",
    "INSTALL_SCOPE",
    "assess_village_mismatch",
    "attach_v23_observer",
    "review_village_candidate",
    "request_village_mdelta",
    "bind_village_mdelta_subject",
    "snapshot_village_subject_slice",
    "record_village_probe",
    "select_village_candidate",
    "propose_village_reconstruction",
    "validate_village_reentry",
    "install_village_canonical_authority",
    "install_village_canonical_runtime",
    "install_village_operational_coverage",
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
