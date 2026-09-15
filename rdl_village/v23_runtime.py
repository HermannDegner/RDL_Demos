"""Stateful explicit runtime driver for the Village v2.3 canonical path.

This driver removes test-harness plumbing without weakening review boundaries.
It never auto-classifies a mismatch as unresolved and never fabricates a T1
candidate.  The caller must still provide the finite review, Probe evidence,
Selection criteria, candidate structure, and re-entry evidence.

The driver only carries those explicit objects through the already constrained
path:

review -> context-local H -> M_delta -> SILN_SELF -> Probe -> Selection
       -> M_B' shadow proposal -> shadow validation -> finite-context install
       -> live re-entry validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence

from .v23_authority import (
    VillageCanonicalAuthority,
    install_village_canonical_authority,
)
from .v23_live_observer import attach_v23_observer
from .v23_mdelta_t1 import (
    VillageProbeEvidence,
    VillageReconstructionProposal,
    VillageReentryValidation,
    VillageSelectionResult,
    bind_village_mdelta_subject,
    propose_village_reconstruction,
    record_village_probe,
    select_village_candidate,
    snapshot_village_subject_slice,
    validate_village_reentry,
)


@dataclass
class VillageCanonicalRuntimeSession:
    agent_name: str
    context_key: tuple[Any, ...]
    request: Any
    handoff: Any
    cycle: int
    probes: list[VillageProbeEvidence] = field(default_factory=list)
    selection: Optional[VillageSelectionResult] = None
    proposal: Optional[VillageReconstructionProposal] = None
    shadow_validations: list[VillageReentryValidation] = field(default_factory=list)
    install_audit: Any = None
    reentry_completion: Any = None
    status: str = "M_delta-awaiting-probe"

    def snapshot(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "agent": self.agent_name,
                "context": self.context_key,
                "cycle": self.cycle,
                "requestRef": self.request.request_ref,
                "subjectRef": self.handoff.subject_ref,
                "probeRefs": tuple(probe.probe_ref for probe in self.probes),
                "selection": self.selection,
                "proposal": self.proposal,
                "shadowValidations": len(self.shadow_validations),
                "installAudit": self.install_audit,
                "reentryCompletion": self.reentry_completion,
                "status": self.status,
                "authority": "explicit-canonical-runtime-driver",
            }
        )


class VillageCanonicalRuntimeDriver:
    """Explicit state machine over the Village canonical migration modules."""

    def __init__(self, simulation, observer, authority: VillageCanonicalAuthority) -> None:
        self.simulation = simulation
        self.observer = observer
        self.authority = authority
        self.sessions: dict[tuple[str, tuple[Any, ...]], VillageCanonicalRuntimeSession] = {}
        self.cycles: dict[tuple[str, tuple[Any, ...]], int] = {}
        simulation.v23CanonicalRuntime = self

    def _agent(self, agent_name: str):
        agent = next((item for item in self.simulation.agents if item.name == agent_name), None)
        if agent is None:
            raise ValueError(f"unknown Village runtime agent: {agent_name}")
        return agent

    def _session_key(self, agent_name: str, context_key: tuple[Any, ...]):
        return agent_name, context_key

    def session(self, agent_name: str, context_key: tuple[Any, ...]):
        return self.sessions.get(self._session_key(agent_name, context_key))

    def review(
        self,
        agent_name: str,
        candidate_id: str,
        *,
        status: str,
        basis: Sequence[str],
        assessor: str,
        ordinary_temporal_change_excluded: bool = False,
        boundary_or_coverage_change_excluded: bool = False,
        unresolved_dimensions: Sequence[str] = (),
    ):
        candidates = self.observer.review_candidates_for(agent_name)
        candidate = next((item for item in candidates if item.candidate_id == candidate_id), None)
        if candidate is None:
            raise ValueError("unknown finite review candidate")
        assessment = self.authority.review(
            agent_name,
            candidate_id,
            status=status,
            basis=basis,
            assessor=assessor,
            ordinary_temporal_change_excluded=ordinary_temporal_change_excluded,
            boundary_or_coverage_change_excluded=boundary_or_coverage_change_excluded,
            unresolved_dimensions=unresolved_dimensions,
        )
        if assessment.eligible_for_h:
            context_key = candidate.mismatch.context_key
            snapshot = self.authority.controller(agent_name).context_view(context_key).h_snapshot(
                agent_name
            )
            if snapshot["shouldReconstructDiagnostic"] and self.session(agent_name, context_key) is None:
                self.begin_cycle(agent_name, context_key)
        return assessment

    def begin_cycle(self, agent_name: str, context_key: tuple[Any, ...]):
        key = self._session_key(agent_name, context_key)
        existing = self.sessions.get(key)
        if existing is not None and existing.status not in {
            "selection-rejected",
            "selection-deferred",
            "reentry-complete",
        }:
            raise ValueError("finite context already has an active canonical runtime cycle")

        controller = self.authority.controller(agent_name)
        cycle = self.cycles.get(key, 0) + 1
        self.cycles[key] = cycle
        request = controller.request_mdelta(
            context_key,
            request_ref=f"village:{agent_name}:m-delta:{cycle}",
            requester="village-canonical-runtime-driver",
            basis=("explicit reviewed context-local unresolved H reached theta",),
        )
        conditions = dict(request.context["conditions"])
        place_id = conditions.get("place")
        if not place_id:
            raise ValueError("Village T1 runtime requires a finite place in the request context")
        agent = self._agent(agent_name)
        handoff = bind_village_mdelta_subject(
            request,
            subject_ref=f"M_B:{agent_name}:{place_id}:{conditions.get('band')}:{cycle}",
            subject_slice=snapshot_village_subject_slice(agent, place_id=place_id),
            basis=("bind current finite place-meaning slice as SILN_SELF inspection subject",),
            binder="village-canonical-runtime-driver",
        )
        session = VillageCanonicalRuntimeSession(
            agent_name=agent_name,
            context_key=context_key,
            request=request,
            handoff=handoff,
            cycle=cycle,
        )
        self.sessions[key] = session
        return session

    def record_probe(
        self,
        agent_name: str,
        context_key: tuple[Any, ...],
        *,
        probe_ref: str,
        condition_ref: str,
        rib_section_ref: str,
        observed_values: Mapping[str, float],
        interpreted_values: Mapping[str, float],
        evidence_refs: Sequence[str],
        basis: Sequence[str],
    ) -> VillageProbeEvidence:
        session = self.session(agent_name, context_key)
        if session is None:
            raise ValueError("finite context has no active M_delta runtime session")
        if session.selection is not None:
            raise ValueError("cannot add Probe evidence after Selection")
        probe = record_village_probe(
            session.handoff,
            probe_ref=probe_ref,
            condition_ref=condition_ref,
            rib_section_ref=rib_section_ref,
            observed_values=observed_values,
            interpreted_values=interpreted_values,
            evidence_refs=evidence_refs,
            basis=basis,
        )
        session.probes.append(probe)
        session.status = "M_delta-probing"
        return probe

    def select(
        self,
        agent_name: str,
        context_key: tuple[Any, ...],
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
        session = self.session(agent_name, context_key)
        if session is None:
            raise ValueError("finite context has no active M_delta runtime session")
        selection = select_village_candidate(
            session.handoff,
            tuple(session.probes),
            selection_ref=selection_ref,
            candidate_ref=candidate_ref,
            decision=decision,
            criteria=criteria,
            basis=basis,
            retained_relations=retained_relations,
            valid_conditions=valid_conditions,
            break_conditions=break_conditions,
            unresolved_items=unresolved_items,
        )
        session.selection = selection
        if decision == "retain":
            session.status = "selection-retained-awaiting-proposal"
        elif decision == "reject":
            session.status = "selection-rejected"
        else:
            session.status = "selection-deferred"
        return selection

    def propose(
        self,
        agent_name: str,
        context_key: tuple[Any, ...],
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
        session = self.session(agent_name, context_key)
        if session is None or session.selection is None:
            raise ValueError("reconstruction proposal requires an explicit Selection")
        proposal = propose_village_reconstruction(
            session.handoff,
            session.selection,
            proposal_ref=proposal_ref,
            candidate_model_ref=candidate_model_ref,
            candidate_structure=candidate_structure,
            boundary_mode=boundary_mode,
            basis=basis,
            builder=builder,
            target_boundary_id=target_boundary_id,
            target_purpose=target_purpose,
            target_dimensions=target_dimensions,
            target_conditions=target_conditions,
        )
        session.proposal = proposal
        session.status = "shadow-proposal-awaiting-validation"
        return proposal

    def validate_shadow(
        self,
        agent_name: str,
        context_key: tuple[Any, ...],
        current_section,
        later_section,
        *,
        coefficients: Mapping[str, float],
        assessment_status: Optional[str] = None,
        basis: Sequence[str] = (),
        assessor: Optional[str] = None,
    ) -> VillageReentryValidation:
        session = self.session(agent_name, context_key)
        if session is None or session.proposal is None:
            raise ValueError("shadow validation requires a reconstruction proposal")
        validation = validate_village_reentry(
            session.proposal,
            current_section,
            later_section,
            coefficients=coefficients,
            assessment_status=assessment_status,
            basis=basis,
            assessor=assessor,
        )
        session.shadow_validations.append(validation)
        session.status = (
            "shadow-validation-stable"
            if validation.stable_for_shadow
            else "shadow-validation-pending"
        )
        return validation

    def install_proposal(
        self,
        agent_name: str,
        context_key: tuple[Any, ...],
        *,
        installer: str,
        basis: Sequence[str],
        evidence_refs: Sequence[str],
    ):
        session = self.session(agent_name, context_key)
        if session is None or session.proposal is None:
            raise ValueError("authority install requires a reconstruction proposal")
        audit = self.authority.activate(
            agent_name,
            session.proposal,
            tuple(session.shadow_validations),
            installer=installer,
            basis=basis,
            evidence_refs=evidence_refs,
        )
        session.install_audit = audit
        session.status = "installed-reentry-pending"
        return audit

    def finalize_reentry(
        self,
        agent_name: str,
        context_key: tuple[Any, ...],
        *,
        basis: str,
        validator: str,
        evidence_refs: Sequence[str],
    ):
        session = self.session(agent_name, context_key)
        if session is None or session.install_audit is None:
            raise ValueError("re-entry completion requires an installed reconstruction")
        completion = self.authority.finalize_reentry(
            agent_name,
            context_key,
            basis=basis,
            validator=validator,
            evidence_refs=evidence_refs,
        )
        session.reentry_completion = completion
        session.status = "reentry-complete"
        return completion

    def snapshot(self):
        return MappingProxyType(
            {
                "authority": self.authority.snapshot(),
                "sessions": tuple(session.snapshot() for session in self.sessions.values()),
                "reviewPolicy": "explicit-only-no-automatic-unresolved-promotion",
            }
        )


def install_village_canonical_runtime(
    simulation,
    *,
    theta: float,
    coefficients: Optional[Mapping[str, float]] = None,
    required_shadow_validations: int = 2,
    reentry_validation_windows: int = 2,
) -> VillageCanonicalRuntimeDriver:
    """Install observer + finite-context authority + explicit runtime driver.

    If an observer already exists, its explicit theta must match the requested
    runtime theta.  The function does not change any policy authority until a
    reconstruction proposal passes the separate ``install_proposal`` gate.
    """

    observer = getattr(simulation, "v23_observer", None)
    if observer is None:
        observer = attach_v23_observer(simulation, coefficients=coefficients, theta=theta)
    elif abs(float(observer.theta) - float(theta)) > 1e-12:
        raise ValueError("existing Village observer theta does not match runtime theta")

    authority = getattr(simulation, "v23CanonicalAuthority", None)
    if authority is None:
        authority = install_village_canonical_authority(
            simulation,
            required_shadow_validations=required_shadow_validations,
            reentry_validation_windows=reentry_validation_windows,
        )
    if getattr(simulation, "v23CanonicalRuntime", None) is not None:
        raise ValueError("Village canonical runtime is already installed")
    return VillageCanonicalRuntimeDriver(simulation, observer, authority)
