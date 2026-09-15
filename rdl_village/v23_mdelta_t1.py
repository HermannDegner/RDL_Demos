"""Village Core v2.3 M_delta -> T1 shadow handoff.

This module starts only after explicit reviewed unresolved H reaches an explicit
theta.  It preserves the T0/T1 responsibility boundary:

T0 side:
    reviewed unresolved provenance -> H_vec -> H >= theta -> M_delta request

T1 side:
    bind current M_B as SILN_SELF -> finite Probe evidence -> Selection
    (retain/reject/defer) -> explicit reconstruction proposal -> fresh re-entry
    validation.

The historical Village ``LeapEngine`` remains authoritative.  Nothing in this
module mutates an NPC policy model or installs M_B'.  H is an entry condition,
not a parameter-update vector.  Core xi is never numericized here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence

from .v23_boundary import (
    VillageBoundary,
    VillageDifferenceAssessment,
    VillageRIBSection,
    assess_village_mismatch,
    compare_village_interpretations,
    interpret_village_section,
)


EPSILON = 1e-12
SELECTION_DECISIONS = ("retain", "reject", "defer")
BOUNDARY_MODES = ("maintain", "adjust")
STABLE_REENTRY_STATUSES = (
    "zero-difference",
    "resolved-difference",
    "ordinary-temporal-change",
)


def _freeze(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


def _finite_mapping(value: Mapping[str, float], *, label: str) -> Mapping[str, float]:
    frozen: dict[str, float] = {}
    for key, raw in value.items():
        numeric = float(raw)
        if not math.isfinite(numeric):
            raise ValueError(f"{label} contains non-finite value: {key}")
        frozen[str(key)] = numeric
    return MappingProxyType(frozen)


def _nonempty_tuple(values: Sequence[str], *, label: str) -> tuple[str, ...]:
    result = tuple(str(item) for item in values if str(item).strip())
    if not result:
        raise ValueError(f"{label} must be non-empty")
    return result


def _context_from_mismatch(mismatch) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            "boundaryId": mismatch.boundary_id,
            "purpose": mismatch.purpose,
            "dimensions": mismatch.dimensions,
            "conditions": MappingProxyType(dict(mismatch.conditions)),
        }
    )


def _context_key(context: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        context["boundaryId"],
        context["purpose"],
        tuple(context["dimensions"]),
        tuple(sorted(dict(context["conditions"]).items())),
    )


def _same_float_mapping(left: Mapping[str, float], right: Mapping[str, float]) -> bool:
    keys = set(left) | set(right)
    return all(abs(float(left.get(key, 0.0)) - float(right.get(key, 0.0))) <= EPSILON for key in keys)


@dataclass(frozen=True)
class VillageMDeltaRequest:
    request_ref: str
    agent_name: str
    requester: str
    basis: tuple[str, ...]
    context: Mapping[str, Any]
    H_vector: Mapping[str, float]
    H: float
    theta: float
    norm_ref: str
    review_refs: tuple[str, ...]
    review_provenance: tuple[Mapping[str, Any], ...]
    status: str = "m-delta-requested"
    authority: str = "handoff-only"
    next_layer: str = "T1"
    subject_ref: None = None
    reconstructed_model_ref: None = None
    xi_status: str = "unrecovered-relations-remain"

    def __post_init__(self) -> None:
        if not self.request_ref or not self.agent_name or not self.requester:
            raise ValueError("M_delta request requires request_ref, agent_name and requester")
        object.__setattr__(self, "basis", _nonempty_tuple(self.basis, label="M_delta basis"))
        object.__setattr__(self, "context", _freeze(self.context))
        object.__setattr__(self, "H_vector", _finite_mapping(self.H_vector, label="H_vector"))
        object.__setattr__(self, "review_refs", _nonempty_tuple(self.review_refs, label="review refs"))
        if not math.isfinite(self.H) or not math.isfinite(self.theta):
            raise ValueError("H and theta must be finite")
        if self.H < self.theta:
            raise ValueError("M_delta request requires H >= theta")


@dataclass(frozen=True)
class VillageMDeltaT1Handoff:
    request: VillageMDeltaRequest
    subject_ref: str
    subject_slice: Mapping[str, Any]
    basis: tuple[str, ...]
    binder: str
    subject_role: str = "SILN_SELF-current-M_B"
    slice_role: str = "finite-subject-slice-not-whole-M_B"
    authority: str = "T1-handoff-only"
    reconstruction_target_ref: None = None
    reconstructed_model_ref: None = None
    selection_status: str = "not-performed"

    def __post_init__(self) -> None:
        if not self.subject_ref or not self.binder:
            raise ValueError("T1 handoff requires explicit subject_ref and binder")
        object.__setattr__(self, "subject_slice", _freeze(self.subject_slice))
        object.__setattr__(self, "basis", _nonempty_tuple(self.basis, label="subject binding basis"))
        if not self.subject_slice:
            raise ValueError("T1 handoff requires an explicit finite subject slice")


@dataclass(frozen=True)
class VillageProbeEvidence:
    probe_ref: str
    request_ref: str
    subject_ref: str
    condition_ref: str
    rib_section_ref: str
    boundary_id: str
    purpose: str
    dimensions: tuple[str, ...]
    observed_values: Mapping[str, float]
    interpreted_values: Mapping[str, float]
    evidence_refs: tuple[str, ...]
    basis: tuple[str, ...]
    authority: str = "probe-evidence-only"

    def __post_init__(self) -> None:
        if not all((self.probe_ref, self.request_ref, self.subject_ref, self.condition_ref, self.rib_section_ref)):
            raise ValueError("Probe evidence requires explicit refs")
        dimensions = tuple(str(item) for item in self.dimensions)
        object.__setattr__(self, "dimensions", dimensions)
        observed = _finite_mapping(self.observed_values, label="probe observed values")
        interpreted = _finite_mapping(self.interpreted_values, label="probe interpreted values")
        if set(observed) != set(dimensions) or set(interpreted) != set(dimensions):
            raise ValueError("Probe evidence requires complete selected dimensions")
        object.__setattr__(self, "observed_values", observed)
        object.__setattr__(self, "interpreted_values", interpreted)
        object.__setattr__(self, "evidence_refs", _nonempty_tuple(self.evidence_refs, label="probe evidence refs"))
        object.__setattr__(self, "basis", _nonempty_tuple(self.basis, label="probe basis"))


@dataclass(frozen=True)
class VillageSelectionResult:
    selection_ref: str
    request_ref: str
    subject_ref: str
    candidate_ref: str
    decision: str
    probe_refs: tuple[str, ...]
    criteria: tuple[str, ...]
    basis: tuple[str, ...]
    retained_relations: tuple[str, ...] = ()
    valid_conditions: tuple[str, ...] = ()
    break_conditions: tuple[str, ...] = ()
    unresolved_items: tuple[str, ...] = ()
    authority: str = "selection-only"

    def __post_init__(self) -> None:
        if not all((self.selection_ref, self.request_ref, self.subject_ref, self.candidate_ref)):
            raise ValueError("Selection requires explicit refs")
        if self.decision not in SELECTION_DECISIONS:
            raise ValueError(f"unknown Selection decision: {self.decision}")
        object.__setattr__(self, "probe_refs", _nonempty_tuple(self.probe_refs, label="Selection probe refs"))
        object.__setattr__(self, "criteria", _nonempty_tuple(self.criteria, label="Selection criteria"))
        object.__setattr__(self, "basis", _nonempty_tuple(self.basis, label="Selection basis"))
        object.__setattr__(self, "retained_relations", tuple(str(x) for x in self.retained_relations if str(x).strip()))
        object.__setattr__(self, "valid_conditions", tuple(str(x) for x in self.valid_conditions if str(x).strip()))
        object.__setattr__(self, "break_conditions", tuple(str(x) for x in self.break_conditions if str(x).strip()))
        object.__setattr__(self, "unresolved_items", tuple(str(x) for x in self.unresolved_items if str(x).strip()))
        if self.decision == "retain" and not self.retained_relations:
            raise ValueError("retain requires explicit retained relations")
        if self.decision == "defer" and not self.unresolved_items:
            raise ValueError("defer requires explicit unresolved items")


@dataclass(frozen=True)
class VillageReconstructionProposal:
    proposal_ref: str
    request_ref: str
    subject_ref: str
    candidate_model_ref: str
    candidate_structure: Mapping[str, Any]
    selection_ref: str
    retained_relations: tuple[str, ...]
    valid_conditions: tuple[str, ...]
    break_conditions: tuple[str, ...]
    unresolved_items: tuple[str, ...]
    boundary_mode: str
    target_boundary_id: str
    target_purpose: str
    target_dimensions: tuple[str, ...]
    target_conditions: Mapping[str, Any]
    basis: tuple[str, ...]
    builder: str
    status: str = "m-b-prime-proposal"
    authority: str = "shadow-proposal-only"
    xi_status: str = "unrecovered-relations-remain"
    installed: bool = False

    def __post_init__(self) -> None:
        if not all((self.proposal_ref, self.request_ref, self.subject_ref, self.candidate_model_ref, self.selection_ref, self.builder)):
            raise ValueError("reconstruction proposal requires explicit refs and builder")
        if self.boundary_mode not in BOUNDARY_MODES:
            raise ValueError(f"unknown boundary mode: {self.boundary_mode}")
        structure = dict(self.candidate_structure)
        if not structure:
            raise ValueError("M_B' proposal requires an explicit candidate structure")
        if "xi" in structure or "ξ" in structure:
            raise ValueError("Core xi must not be numericized inside the reconstruction proposal")
        object.__setattr__(self, "candidate_structure", MappingProxyType(structure))
        object.__setattr__(self, "retained_relations", _nonempty_tuple(self.retained_relations, label="retained relations"))
        object.__setattr__(self, "target_dimensions", _nonempty_tuple(self.target_dimensions, label="target dimensions"))
        object.__setattr__(self, "target_conditions", _freeze(self.target_conditions))
        object.__setattr__(self, "basis", _nonempty_tuple(self.basis, label="reconstruction basis"))
        object.__setattr__(self, "valid_conditions", tuple(str(x) for x in self.valid_conditions if str(x).strip()))
        object.__setattr__(self, "break_conditions", tuple(str(x) for x in self.break_conditions if str(x).strip()))
        object.__setattr__(self, "unresolved_items", tuple(str(x) for x in self.unresolved_items if str(x).strip()))
        if not self.target_boundary_id or not self.target_purpose:
            raise ValueError("reconstruction proposal requires target finite B and Purpose")


@dataclass(frozen=True)
class VillageReentryValidation:
    proposal_ref: str
    current_section_ref: str
    later_section_ref: str
    E: Mapping[str, float]
    assessment: VillageDifferenceAssessment
    H_new: Optional[float]
    status: str
    stable_for_shadow: bool
    authority: str = "validation-only"

    def __post_init__(self) -> None:
        object.__setattr__(self, "E", _finite_mapping(self.E, label="re-entry E"))


def request_village_mdelta(
    observer,
    agent_name: str,
    *,
    request_ref: str,
    requester: str,
    basis: Sequence[str],
) -> VillageMDeltaRequest:
    """Form M_delta only when current H can be reproduced from finite reviews."""

    snapshot = observer.h_snapshot(agent_name)
    if not snapshot.get("shouldReconstructDiagnostic"):
        raise ValueError("M_delta request requires H >= theta")

    reviews = tuple(
        review for review in observer.reviews_for(agent_name) if review.eligible_for_h
    )
    if not reviews:
        raise ValueError("M_delta request requires reviewed unresolved provenance")

    contexts = {review.mismatch.context_key for review in reviews}
    if len(contexts) != 1:
        raise ValueError("M_delta request refuses H mixed across finite contexts")

    context = _context_from_mismatch(reviews[0].mismatch)
    dimensions = tuple(context["dimensions"])
    recomputed = {dimension: 0.0 for dimension in dimensions}
    provenance = []
    review_refs = []
    candidates = observer.review_candidates_for(agent_name)

    for review in reviews:
        candidate = next(
            (
                item
                for item in candidates
                if item.mismatch.later_section_id == review.mismatch.later_section_id
                and item.mismatch.context_key == review.mismatch.context_key
            ),
            None,
        )
        if candidate is None:
            raise ValueError("unresolved review is missing its finite review candidate provenance")
        review_refs.append(candidate.candidate_id)
        for key, value in review.unresolved_values.items():
            recomputed[key] += abs(float(value))
        provenance.append(
            MappingProxyType(
                {
                    "candidateRef": candidate.candidate_id,
                    "reviewer": review.assessor,
                    "basis": review.basis,
                    "unresolvedDimensions": review.unresolved_dimensions,
                    "evidenceRefs": candidate.evidence_refs,
                }
            )
        )

    if not _same_float_mapping(recomputed, snapshot["H_vec"]):
        raise ValueError("current H_vector cannot be reproduced from supplied finite review provenance")

    return VillageMDeltaRequest(
        request_ref=request_ref,
        agent_name=agent_name,
        requester=requester,
        basis=tuple(basis),
        context=context,
        H_vector=recomputed,
        H=float(snapshot["H"]),
        theta=float(snapshot["theta"]),
        norm_ref="max-demo-local-v1",
        review_refs=tuple(review_refs),
        review_provenance=tuple(provenance),
    )


def snapshot_village_subject_slice(agent, *, place_id: str) -> Mapping[str, Any]:
    """Snapshot one explicit finite local slice of current M_B for T1 inspection.

    This is deliberately labelled a slice.  The place model is not asserted to
    equal the whole NPC M_B.
    """

    meaning = agent.prediction_field.places.get(place_id)
    if meaning is None:
        raise ValueError("current finite subject slice is not available for place")
    return MappingProxyType(
        {
            "sliceRole": "prediction-field-place-meaning",
            "placeId": place_id,
            "comfort": float(meaning.comfort),
            "socialExpectation": float(meaning.social_expectation),
            "resourceExpectation": float(meaning.resource_expectation),
            "dangerExpectation": float(meaning.danger_expectation),
            "familiarity": float(meaning.familiarity),
        }
    )


def bind_village_mdelta_subject(
    request: VillageMDeltaRequest,
    *,
    subject_ref: str,
    subject_slice: Mapping[str, Any],
    basis: Sequence[str],
    binder: str,
) -> VillageMDeltaT1Handoff:
    return VillageMDeltaT1Handoff(
        request=request,
        subject_ref=subject_ref,
        subject_slice=subject_slice,
        basis=tuple(basis),
        binder=binder,
    )


def record_village_probe(
    handoff: VillageMDeltaT1Handoff,
    *,
    probe_ref: str,
    condition_ref: str,
    rib_section_ref: str,
    observed_values: Mapping[str, float],
    interpreted_values: Mapping[str, float],
    evidence_refs: Sequence[str],
    basis: Sequence[str],
) -> VillageProbeEvidence:
    context = handoff.request.context
    return VillageProbeEvidence(
        probe_ref=probe_ref,
        request_ref=handoff.request.request_ref,
        subject_ref=handoff.subject_ref,
        condition_ref=condition_ref,
        rib_section_ref=rib_section_ref,
        boundary_id=context["boundaryId"],
        purpose=context["purpose"],
        dimensions=tuple(context["dimensions"]),
        observed_values=observed_values,
        interpreted_values=interpreted_values,
        evidence_refs=tuple(evidence_refs),
        basis=tuple(basis),
    )


def select_village_candidate(
    handoff: VillageMDeltaT1Handoff,
    probes: Sequence[VillageProbeEvidence],
    *,
    selection_ref: str,
    candidate_ref: str,
    decision: str,
    criteria: Sequence[str],
    basis: Sequence[str],
    retained_relations: Sequence[str] = (),
    valid_conditions: Sequence[str] = (),
    break_conditions: Sequence[str] = (),
    unresolved_items: Sequence[str] = (),
) -> VillageSelectionResult:
    finite_probes = tuple(probes)
    if not finite_probes:
        raise ValueError("Selection requires at least one finite Probe result")
    for probe in finite_probes:
        if probe.request_ref != handoff.request.request_ref or probe.subject_ref != handoff.subject_ref:
            raise ValueError("Selection probe provenance does not match T1 handoff")
        if (
            probe.boundary_id != handoff.request.context["boundaryId"]
            or probe.purpose != handoff.request.context["purpose"]
            or probe.dimensions != tuple(handoff.request.context["dimensions"])
        ):
            raise ValueError("Selection probe escaped the finite T1 context")

    return VillageSelectionResult(
        selection_ref=selection_ref,
        request_ref=handoff.request.request_ref,
        subject_ref=handoff.subject_ref,
        candidate_ref=candidate_ref,
        decision=decision,
        probe_refs=tuple(probe.probe_ref for probe in finite_probes),
        criteria=tuple(criteria),
        basis=tuple(basis),
        retained_relations=tuple(retained_relations),
        valid_conditions=tuple(valid_conditions),
        break_conditions=tuple(break_conditions),
        unresolved_items=tuple(unresolved_items),
    )


def propose_village_reconstruction(
    handoff: VillageMDeltaT1Handoff,
    selection: VillageSelectionResult,
    *,
    proposal_ref: str,
    candidate_model_ref: str,
    candidate_structure: Mapping[str, Any],
    boundary_mode: str,
    basis: Sequence[str],
    builder: str,
    target_boundary_id: Optional[str] = None,
    target_purpose: Optional[str] = None,
    target_dimensions: Optional[Sequence[str]] = None,
    target_conditions: Optional[Mapping[str, Any]] = None,
) -> VillageReconstructionProposal:
    if selection.request_ref != handoff.request.request_ref or selection.subject_ref != handoff.subject_ref:
        raise ValueError("Selection provenance does not match T1 handoff")
    if selection.decision != "retain":
        raise ValueError("only retained Selection may form an M_B' proposal")

    current = handoff.request.context
    if boundary_mode == "maintain":
        target_boundary_id = current["boundaryId"]
        target_purpose = current["purpose"]
        target_dimensions = tuple(current["dimensions"])
        target_conditions = dict(current["conditions"])
    elif boundary_mode == "adjust":
        if not target_boundary_id or not target_purpose or not target_dimensions or target_conditions is None:
            raise ValueError("adjusted boundary requires explicit target B / Purpose / dimensions / conditions")
    else:
        raise ValueError(f"unknown boundary mode: {boundary_mode}")

    return VillageReconstructionProposal(
        proposal_ref=proposal_ref,
        request_ref=handoff.request.request_ref,
        subject_ref=handoff.subject_ref,
        candidate_model_ref=candidate_model_ref,
        candidate_structure=candidate_structure,
        selection_ref=selection.selection_ref,
        retained_relations=selection.retained_relations,
        valid_conditions=selection.valid_conditions,
        break_conditions=selection.break_conditions,
        unresolved_items=selection.unresolved_items,
        boundary_mode=boundary_mode,
        target_boundary_id=str(target_boundary_id),
        target_purpose=str(target_purpose),
        target_dimensions=tuple(target_dimensions or ()),
        target_conditions=dict(target_conditions or {}),
        basis=tuple(basis),
        builder=builder,
    )


def validate_village_reentry(
    proposal: VillageReconstructionProposal,
    current_section: VillageRIBSection,
    later_section: VillageRIBSection,
    *,
    coefficients: Mapping[str, float],
    assessment_status: Optional[str] = None,
    basis: Sequence[str] = (),
    assessor: Optional[str] = None,
) -> VillageReentryValidation:
    """Validate a proposed M_B' on fresh finite sections without installing it.

    A non-zero fresh E is not treated as H_new.  Stable re-entry requires an
    explicit resolved/ordinary-temporal assessment.  If fresh E remains pending,
    H_new is deliberately left unformed.  If unresolved is suspected, the fresh
    result must go back through the full absorption/review cycle rather than
    bypassing it here.
    """

    expected_context = (
        proposal.target_boundary_id,
        proposal.target_purpose,
        proposal.target_dimensions,
        tuple(sorted(dict(proposal.target_conditions).items())),
    )
    if current_section.boundary.context_key != expected_context:
        raise ValueError("fresh current RIB_B does not match proposed target finite context")
    if later_section.boundary.context_key != expected_context:
        raise ValueError("fresh later RIB_B does not match proposed target finite context")

    current = interpret_village_section(
        current_section,
        model_ref=proposal.candidate_model_ref,
        coefficients=coefficients,
    )
    later = interpret_village_section(
        later_section,
        model_ref=proposal.candidate_model_ref,
        coefficients=coefficients,
    )
    mismatch = compare_village_interpretations(current, later)

    if assessment_status == "unresolved-mismatch":
        raise ValueError("fresh unresolved re-entry must return through the full finite review gate")
    assessment = assess_village_mismatch(
        mismatch,
        status=assessment_status,
        basis=tuple(basis),
        assessor=assessor,
    )

    stable = assessment.status in STABLE_REENTRY_STATUSES
    if stable:
        H_new: Optional[float] = 0.0
        status = "stable-for-shadow-reentry"
    else:
        H_new = None
        status = "pending-reentry-assessment"

    return VillageReentryValidation(
        proposal_ref=proposal.proposal_ref,
        current_section_ref=current_section.section_id,
        later_section_ref=later_section.section_id,
        E=dict(mismatch.values),
        assessment=assessment,
        H_new=H_new,
        status=status,
        stable_for_shadow=stable,
    )
