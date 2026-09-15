"""Finite-context canonical authority cutover for ``rdl_village``.

Village observation is explicitly finite and context-qualified (currently
place + band).  Authority therefore moves one finite context at a time instead
of turning one reconstructed slice into a global village truth.

A cutover requires:

1. an explicit retained :class:`VillageReconstructionProposal`;
2. multiple distinct stable shadow re-entry validations;
3. an installable Village-local runtime adapter declared by the candidate;
4. an explicit installer, basis and finite evidence references.

Inside an installed finite context the reconstructed evaluator / place-meaning
slice becomes authoritative and the historical ``LeapEngine`` is prevented
from authorizing reconstruction.  Outside that context the legacy runtime is
left untouched until that finite B is migrated separately.

Core xi is never numericized.  Legacy LocalLoadVector / ExplorationState values
remain compatibility diagnostics and are never used to authorize this cutover.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import MappingProxyType, MethodType
from typing import Any, Mapping, Optional, Sequence

from .v23_live_observer import (
    DEFAULT_OBSERVER_COEFFICIENTS,
    VILLAGE_OBSERVER_DIMENSIONS,
)
from .v23_mdelta_t1 import (
    VillageReconstructionProposal,
    VillageReentryValidation,
    request_village_mdelta,
)


EPSILON = 1e-12
INSTALL_KIND = "village-finite-context-model"
INSTALL_SCOPE = "prediction-field-place-meaning+observer-evaluator"
PLACE_FIELDS = (
    "comfort",
    "social_expectation",
    "resource_expectation",
    "danger_expectation",
)
PLACE_PATCH_KEYS = MappingProxyType(
    {
        "comfort": "comfort",
        "socialExpectation": "social_expectation",
        "resourceExpectation": "resource_expectation",
        "dangerExpectation": "danger_expectation",
    }
)
STABLE_REVIEW_STATUSES = {
    "zero-difference",
    "resolved-difference",
    "ordinary-temporal-change",
}


def _freeze(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


def _nonempty(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} must be non-empty")
    return text


def _nonempty_refs(values: Sequence[str], *, label: str) -> tuple[str, ...]:
    refs = tuple(str(item).strip() for item in values if str(item).strip())
    if not refs:
        raise ValueError(f"{label} must be non-empty")
    return refs


def _context_key_from_parts(
    boundary_id: str,
    purpose: str,
    dimensions: Sequence[str],
    conditions: Mapping[str, Any],
) -> tuple[Any, ...]:
    return (
        str(boundary_id),
        str(purpose),
        tuple(str(item) for item in dimensions),
        tuple(sorted(dict(conditions).items())),
    )


def _proposal_context_key(proposal: VillageReconstructionProposal) -> tuple[Any, ...]:
    return _context_key_from_parts(
        proposal.target_boundary_id,
        proposal.target_purpose,
        proposal.target_dimensions,
        proposal.target_conditions,
    )


def _live_context_key(agent_name: str, perception) -> tuple[Any, ...]:
    return _context_key_from_parts(
        f"village:{agent_name}:local-observation",
        "npc_local_interpretation",
        VILLAGE_OBSERVER_DIMENSIONS,
        {"place": perception.place_id, "band": perception.band},
    )


def _contains_numeric_xi(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key) in {"xi", "ξ"} and isinstance(nested, (int, float)):
                return True
            if _contains_numeric_xi(nested):
                return True
    elif isinstance(value, (list, tuple, set)):
        return any(_contains_numeric_xi(item) for item in value)
    return False


def _finite_coefficients(value: Mapping[str, Any]) -> Mapping[str, float]:
    expected = tuple(VILLAGE_OBSERVER_DIMENSIONS)
    if set(value) != set(expected):
        raise ValueError("authority candidate requires complete observer coefficients")
    result = {}
    for key in expected:
        numeric = float(value[key])
        if not math.isfinite(numeric):
            raise ValueError(f"observer coefficient must be finite: {key}")
        result[key] = numeric
    return MappingProxyType(result)


def _finite_place_patch(value: Mapping[str, Any]) -> Mapping[str, float]:
    if not value:
        raise ValueError("authority candidate requires a non-empty placeMeaningPatch")
    unknown = set(value) - set(PLACE_PATCH_KEYS)
    if unknown:
        raise ValueError(f"unknown placeMeaningPatch fields: {sorted(unknown)}")
    result = {}
    for public_key, raw in value.items():
        numeric = float(raw)
        if not math.isfinite(numeric):
            raise ValueError(f"place meaning patch must be finite: {public_key}")
        if public_key == "comfort":
            if not -1.0 <= numeric <= 1.0:
                raise ValueError("comfort patch must remain within [-1, 1]")
        elif not 0.0 <= numeric <= 1.0:
            raise ValueError(f"{public_key} patch must remain within [0, 1]")
        result[public_key] = numeric
    return MappingProxyType(result)


def _snapshot_place(meaning) -> dict[str, float]:
    return {field: float(getattr(meaning, field)) for field in PLACE_FIELDS}


def _restore_place(meaning, state: Mapping[str, float]) -> None:
    for field in PLACE_FIELDS:
        setattr(meaning, field, float(state[field]))


@dataclass(frozen=True)
class VillageAuthorityInstallAudit:
    proposal_ref: str
    model_ref: str
    agent_name: str
    context: Mapping[str, Any]
    installer: str
    basis: tuple[str, ...]
    shadow_validation_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    status: str = "M_B-prime-installed"
    authority: str = "canonical-v23-finite-context"
    xi_status: str = "unrecovered-relations-remain"
    reentry_required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "context", _freeze(self.context))
        object.__setattr__(
            self,
            "basis",
            tuple(str(item).strip() for item in self.basis if str(item).strip()),
        )
        if not self.basis:
            raise ValueError("authority install audit requires finite basis")


@dataclass
class _InstalledContextModel:
    proposal: VillageReconstructionProposal
    observer_coefficients: Mapping[str, float]
    place_id: str
    place_patch: Mapping[str, float]
    install_audit: VillageAuthorityInstallAudit
    reentry_required: int
    context_state: dict[str, float]
    reentry_status: str = "pending"
    clean_evidence: set[str] = field(default_factory=set)
    completion: Optional[Mapping[str, Any]] = None

    @property
    def context_key(self) -> tuple[Any, ...]:
        return _proposal_context_key(self.proposal)

    def snapshot(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "proposalRef": self.proposal.proposal_ref,
                "modelRef": self.proposal.candidate_model_ref,
                "context": MappingProxyType(
                    {
                        "boundaryId": self.proposal.target_boundary_id,
                        "purpose": self.proposal.target_purpose,
                        "dimensions": self.proposal.target_dimensions,
                        "conditions": MappingProxyType(dict(self.proposal.target_conditions)),
                    }
                ),
                "reentryStatus": self.reentry_status,
                "cleanComparisons": len(self.clean_evidence),
                "requiredComparisons": self.reentry_required,
                "completion": self.completion,
                "legacyLeapAuthority": False,
                "xiStatus": "unrecovered-relations-remain",
            }
        )


class VillageContextObserverView:
    """Context-local projection of one live observer for provenance-safe M_delta."""

    def __init__(self, observer, agent_name: str, context_key: tuple[Any, ...]):
        self.observer = observer
        self.agent_name = agent_name
        self.context_key = context_key

    def reviews_for(self, agent_name: str):
        if agent_name != self.agent_name:
            return ()
        return tuple(
            review
            for review in self.observer.reviews_for(agent_name)
            if review.mismatch.context_key == self.context_key
        )

    def review_candidates_for(self, agent_name: str):
        if agent_name != self.agent_name:
            return ()
        return tuple(
            candidate
            for candidate in self.observer.review_candidates_for(agent_name)
            if candidate.mismatch.context_key == self.context_key
        )

    def h_snapshot(self, agent_name: str):
        if agent_name != self.agent_name:
            raise ValueError("context observer view is bound to one agent")
        dimensions = tuple(self.context_key[2])
        values = {key: 0.0 for key in dimensions}
        for review in self.reviews_for(agent_name):
            if not review.eligible_for_h:
                continue
            for key, value in review.unresolved_values.items():
                values[key] += abs(float(value))
        magnitude = max(values.values(), default=0.0)
        theta = float(self.observer.theta)
        return {
            "H_vec": values,
            "H": magnitude,
            "theta": theta,
            "shouldReconstructDiagnostic": magnitude >= theta,
            "authority": "diagnostic-context-view",
        }


class VillageCanonicalAuthorityController:
    """One NPC's finite-context canonical reconstruction authority."""

    def __init__(
        self,
        *,
        agent,
        observer,
        required_shadow_validations: int = 2,
        reentry_validation_windows: int = 2,
    ) -> None:
        if required_shadow_validations < 1 or reentry_validation_windows < 1:
            raise ValueError("authority validation window counts must be positive")
        self.agent = agent
        self.observer = observer
        self.required_shadow_validations = int(required_shadow_validations)
        self.reentry_validation_windows = int(reentry_validation_windows)
        self.default_model_ref = str(observer.model_ref)
        self.default_coefficients = MappingProxyType(dict(observer.coefficients))
        self.models: dict[tuple[Any, ...], _InstalledContextModel] = {}
        self.base_place_states: dict[str, dict[str, float]] = {}
        self.loaded_place_slots: dict[str, Optional[tuple[Any, ...]]] = {}
        self.current_context_key: Optional[tuple[Any, ...]] = None
        self.current_model: Optional[_InstalledContextModel] = None
        self.installed = False
        self._original_integrate = None
        self._original_update_boundary = None
        self._original_leap_check = None
        self._original_leap_check_basal = None

    def install_hooks(self):
        if self.installed:
            return self
        field = self.agent.prediction_field
        self._original_integrate = field.integrate
        self._original_update_boundary = self.agent.update_boundary
        self._original_leap_check = self.agent.leap_engine.check
        self._original_leap_check_basal = self.agent.leap_engine.check_basal
        controller = self

        def integrated(field_self, perception, t, _original=self._original_integrate):
            controller.prepare_context(perception)
            return _original(perception, t)

        def updated(agent_self, perception, _original=self._original_update_boundary):
            result = _original(perception)
            controller.observe_after_capture(perception)
            return result

        def guarded_check(engine_self, *args, _original=self._original_leap_check, **kwargs):
            if controller.current_model is not None:
                return None
            return _original(*args, **kwargs)

        def guarded_check_basal(
            engine_self,
            *args,
            _original=self._original_leap_check_basal,
            **kwargs,
        ):
            if controller.current_model is not None:
                return None
            return _original(*args, **kwargs)

        field.integrate = MethodType(integrated, field)
        self.agent.update_boundary = MethodType(updated, self.agent)
        self.agent.leap_engine.check = MethodType(guarded_check, self.agent.leap_engine)
        self.agent.leap_engine.check_basal = MethodType(
            guarded_check_basal,
            self.agent.leap_engine,
        )
        self.agent.v23CanonicalAuthorityController = self
        self.installed = True
        return self

    def context_view(self, context_key: tuple[Any, ...]) -> VillageContextObserverView:
        return VillageContextObserverView(self.observer, self.agent.name, context_key)

    def request_mdelta(
        self,
        context_key: tuple[Any, ...],
        *,
        request_ref: str,
        requester: str,
        basis: Sequence[str],
    ):
        return request_village_mdelta(
            self.context_view(context_key),
            self.agent.name,
            request_ref=request_ref,
            requester=requester,
            basis=basis,
        )

    def _validate_proposal_scope(self, proposal: VillageReconstructionProposal):
        if proposal.target_boundary_id != f"village:{self.agent.name}:local-observation":
            raise ValueError("authority proposal target B does not match live Village agent boundary")
        if proposal.target_purpose != "npc_local_interpretation":
            raise ValueError("authority proposal target Purpose does not match live Village observer")
        if tuple(proposal.target_dimensions) != tuple(VILLAGE_OBSERVER_DIMENSIONS):
            raise ValueError("authority proposal dimensions exceed the supported live finite adapter")
        conditions = dict(proposal.target_conditions)
        if set(conditions) != {"place", "band"}:
            raise ValueError("authority proposal must target exactly one finite place/band context")
        if not conditions["place"] or not conditions["band"]:
            raise ValueError("authority proposal requires concrete place and band conditions")

    def _adapter_from(self, proposal: VillageReconstructionProposal):
        structure = dict(proposal.candidate_structure)
        if _contains_numeric_xi(structure):
            raise ValueError("authority candidate must not numericize Core xi")
        if structure.get("kind") != INSTALL_KIND:
            raise ValueError(f"authority candidate kind must be {INSTALL_KIND}")
        if structure.get("installScope") != INSTALL_SCOPE:
            raise ValueError(f"authority candidate installScope must be {INSTALL_SCOPE}")
        place_id = _nonempty(structure.get("placeId"), label="candidate placeId")
        if place_id != dict(proposal.target_conditions)["place"]:
            raise ValueError("candidate placeId must equal the finite target place")
        coefficients = _finite_coefficients(structure.get("observerCoefficients") or {})
        patch = _finite_place_patch(structure.get("placeMeaningPatch") or {})
        return place_id, coefficients, patch

    def _validate_shadow_reentry(
        self,
        proposal: VillageReconstructionProposal,
        validations: Sequence[VillageReentryValidation],
    ) -> tuple[str, ...]:
        finite = tuple(validations)
        if len(finite) < self.required_shadow_validations:
            raise ValueError("authority cutover requires more stable shadow re-entry validations")
        refs = []
        pairs = set()
        for validation in finite:
            if not isinstance(validation, VillageReentryValidation):
                raise TypeError("authority cutover requires VillageReentryValidation evidence")
            if validation.proposal_ref != proposal.proposal_ref:
                raise ValueError("shadow re-entry validation belongs to another proposal")
            if not validation.stable_for_shadow or validation.H_new != 0.0:
                raise ValueError("authority cutover requires stable shadow re-entry evidence")
            pair = (validation.current_section_ref, validation.later_section_ref)
            pairs.add(pair)
            refs.append(f"{validation.current_section_ref}->{validation.later_section_ref}")
        if len(pairs) < self.required_shadow_validations:
            raise ValueError("authority cutover requires distinct fresh shadow windows")
        return tuple(refs)

    def activate(
        self,
        proposal: VillageReconstructionProposal,
        validations: Sequence[VillageReentryValidation],
        *,
        installer: str,
        basis: Sequence[str],
        evidence_refs: Sequence[str],
    ) -> VillageAuthorityInstallAudit:
        if not isinstance(proposal, VillageReconstructionProposal):
            raise TypeError("authority activation requires VillageReconstructionProposal")
        self._validate_proposal_scope(proposal)
        place_id, coefficients, patch = self._adapter_from(proposal)
        shadow_refs = self._validate_shadow_reentry(proposal, validations)
        installer_id = _nonempty(installer, label="installer")
        finite_basis = tuple(str(item).strip() for item in basis if str(item).strip())
        if not finite_basis:
            raise ValueError("authority activation requires finite basis")
        refs = _nonempty_refs(evidence_refs, label="authority evidence refs")
        context_key = _proposal_context_key(proposal)
        if context_key in self.models:
            raise ValueError("finite context already has canonical reconstruction authority")

        meaning = self.agent.prediction_field.meaning(place_id)
        if place_id not in self.base_place_states:
            self.base_place_states[place_id] = _snapshot_place(meaning)
            self.loaded_place_slots[place_id] = None
        initial = dict(self.base_place_states[place_id])
        for public_key, numeric in patch.items():
            initial[PLACE_PATCH_KEYS[public_key]] = numeric

        audit = VillageAuthorityInstallAudit(
            proposal_ref=proposal.proposal_ref,
            model_ref=proposal.candidate_model_ref,
            agent_name=self.agent.name,
            context=MappingProxyType(
                {
                    "boundaryId": proposal.target_boundary_id,
                    "purpose": proposal.target_purpose,
                    "dimensions": proposal.target_dimensions,
                    "conditions": MappingProxyType(dict(proposal.target_conditions)),
                }
            ),
            installer=installer_id,
            basis=finite_basis,
            shadow_validation_refs=shadow_refs,
            evidence_refs=refs,
        )
        model = _InstalledContextModel(
            proposal=proposal,
            observer_coefficients=coefficients,
            place_id=place_id,
            place_patch=patch,
            install_audit=audit,
            reentry_required=self.reentry_validation_windows,
            context_state=initial,
        )
        self.models[context_key] = model
        self._reset_observer_context(context_key)
        return audit

    def _reset_observer_context(self, context_key: tuple[Any, ...]) -> None:
        name = self.agent.name
        self.observer._previous.pop(name, None)
        self.observer._local_baseline.pop(name, None)
        # Active H/review provenance belongs to the previous M_B epoch.  Keep
        # records/counters as audit history, but begin fresh active review state.
        self.observer._review_candidates[name].clear()
        self.observer._reviews[name].clear()
        self.observer._reviewed_candidate_ids[name].clear()
        self.observer._h.pop(name, None)
        self.observer._records[name].append(
            {
                "tick": None,
                "formed": False,
                "status": "canonical-model-epoch-started",
                "context": context_key,
            }
        )

    def _save_loaded_place_state(self, place_id: str, meaning) -> None:
        slot = self.loaded_place_slots.get(place_id)
        state = _snapshot_place(meaning)
        if slot is None:
            self.base_place_states[place_id] = state
        elif slot in self.models:
            self.models[slot].context_state = state

    def _load_place_slot(
        self,
        place_id: str,
        target_slot: Optional[tuple[Any, ...]],
    ) -> None:
        meaning = self.agent.prediction_field.meaning(place_id)
        if place_id not in self.base_place_states:
            self.base_place_states[place_id] = _snapshot_place(meaning)
            self.loaded_place_slots[place_id] = None
        current_slot = self.loaded_place_slots.get(place_id)
        if current_slot == target_slot:
            return
        self._save_loaded_place_state(place_id, meaning)
        if target_slot is None:
            target_state = self.base_place_states[place_id]
        else:
            target_state = self.models[target_slot].context_state
        _restore_place(meaning, target_state)
        self.loaded_place_slots[place_id] = target_slot

    def prepare_context(self, perception) -> None:
        context_key = _live_context_key(self.agent.name, perception)
        model = self.models.get(context_key)
        place_id = perception.place_id
        if place_id and place_id in self.base_place_states:
            self._load_place_slot(place_id, context_key if model else None)
        elif model is not None and place_id:
            self._load_place_slot(place_id, context_key)

        self.current_context_key = context_key
        self.current_model = model
        if model is None:
            self.observer.model_ref = self.default_model_ref
            self.observer.coefficients = self.default_coefficients
        else:
            self.observer.model_ref = model.proposal.candidate_model_ref
            self.observer.coefficients = model.observer_coefficients

    def observe_after_capture(self, perception) -> None:
        model = self.current_model
        if model is None or model.reentry_status != "pending":
            return
        records = self.observer.records_for(self.agent.name)
        if not records:
            return
        latest = records[-1]
        if latest.get("tick") != perception.t or not latest.get("formed"):
            return
        if latest.get("status") == "zero-difference":
            model.clean_evidence.add(f"live-zero:{perception.t}")

    def review(
        self,
        candidate_id: str,
        *,
        status: str,
        basis: Sequence[str],
        assessor: str,
        ordinary_temporal_change_excluded: bool = False,
        boundary_or_coverage_change_excluded: bool = False,
        unresolved_dimensions: Sequence[str] = (),
    ):
        candidate = next(
            (
                item
                for item in self.observer.review_candidates_for(self.agent.name)
                if item.candidate_id == candidate_id
            ),
            None,
        )
        if candidate is None:
            raise ValueError("unknown finite review candidate")
        assessment = self.observer.submit_review(
            self.agent.name,
            candidate_id,
            status=status,
            basis=basis,
            assessor=assessor,
            ordinary_temporal_change_excluded=ordinary_temporal_change_excluded,
            boundary_or_coverage_change_excluded=boundary_or_coverage_change_excluded,
            unresolved_dimensions=unresolved_dimensions,
        )
        model = self.models.get(candidate.mismatch.context_key)
        if model is not None and model.reentry_status == "pending":
            if assessment.eligible_for_h:
                model.clean_evidence.clear()
                view = self.context_view(model.context_key)
                if view.h_snapshot(self.agent.name)["shouldReconstructDiagnostic"]:
                    model.reentry_status = "m-delta-required"
            elif assessment.status in STABLE_REVIEW_STATUSES:
                model.clean_evidence.add(candidate.candidate_id)
        return assessment

    def finalize_reentry(
        self,
        context_key: tuple[Any, ...],
        *,
        basis: str,
        validator: str,
        evidence_refs: Sequence[str],
    ) -> Mapping[str, Any]:
        model = self.models.get(context_key)
        if model is None:
            raise ValueError("no canonical installed model exists for finite context")
        if model.reentry_status != "pending":
            raise ValueError("finite context has no pending re-entry validation")
        snapshot = self.context_view(context_key).h_snapshot(self.agent.name)
        if snapshot["H"] >= snapshot["theta"]:
            raise ValueError("cannot finalize re-entry while context-local H >= theta")
        if len(model.clean_evidence) < model.reentry_required:
            raise ValueError("re-entry requires more finite post-install comparisons")
        finite_basis = _nonempty(basis, label="re-entry basis")
        validator_id = _nonempty(validator, label="re-entry validator")
        refs = _nonempty_refs(evidence_refs, label="re-entry evidence refs")
        completion = MappingProxyType(
            {
                "status": "normal-operation-restored",
                "modelRef": model.proposal.candidate_model_ref,
                "context": model.install_audit.context,
                "basis": finite_basis,
                "validator": validator_id,
                "evidenceRefs": refs,
                "H": snapshot["H"],
                "theta": snapshot["theta"],
                "xiStatus": "unrecovered-relations-remain",
            }
        )
        model.reentry_status = "complete"
        model.completion = completion
        return completion

    def snapshot(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "agent": self.agent.name,
                "currentContext": self.current_context_key,
                "currentAuthority": (
                    "canonical-v23-finite-context"
                    if self.current_model is not None
                    else "legacy-local-outside-migrated-context"
                ),
                "legacyLeapAuthority": self.current_model is None,
                "models": tuple(model.snapshot() for model in self.models.values()),
                "legacyNumericXiIsCoreXi": False,
            }
        )


class VillageCanonicalAuthority:
    """Opt-in finite-context authority manager for a live VillageSimulation."""

    def __init__(
        self,
        simulation,
        *,
        required_shadow_validations: int = 2,
        reentry_validation_windows: int = 2,
    ) -> None:
        observer = getattr(simulation, "v23_observer", None)
        if observer is None:
            raise ValueError("Village canonical authority requires attach_v23_observer(simulation) first")
        self.simulation = simulation
        self.observer = observer
        self.controllers = {
            agent.name: VillageCanonicalAuthorityController(
                agent=agent,
                observer=observer,
                required_shadow_validations=required_shadow_validations,
                reentry_validation_windows=reentry_validation_windows,
            ).install_hooks()
            for agent in simulation.agents
        }
        simulation.v23CanonicalAuthority = self

    def controller(self, agent_name: str) -> VillageCanonicalAuthorityController:
        if agent_name not in self.controllers:
            raise ValueError(f"unknown Village canonical authority agent: {agent_name}")
        return self.controllers[agent_name]

    def activate(self, agent_name: str, proposal, validations, **kwargs):
        return self.controller(agent_name).activate(proposal, validations, **kwargs)

    def review(self, agent_name: str, candidate_id: str, **kwargs):
        return self.controller(agent_name).review(candidate_id, **kwargs)

    def request_mdelta(self, agent_name: str, context_key, **kwargs):
        return self.controller(agent_name).request_mdelta(context_key, **kwargs)

    def finalize_reentry(self, agent_name: str, context_key, **kwargs):
        return self.controller(agent_name).finalize_reentry(context_key, **kwargs)

    def snapshot(self):
        return MappingProxyType(
            {
                "authority": "canonical-v23-finite-context-manager",
                "agents": tuple(controller.snapshot() for controller in self.controllers.values()),
            }
        )


def install_village_canonical_authority(
    simulation,
    *,
    required_shadow_validations: int = 2,
    reentry_validation_windows: int = 2,
) -> VillageCanonicalAuthority:
    if getattr(simulation, "v23CanonicalAuthority", None) is not None:
        raise ValueError("Village canonical authority is already installed")
    return VillageCanonicalAuthority(
        simulation,
        required_shadow_validations=required_shadow_validations,
        reentry_validation_windows=reentry_validation_windows,
    )
