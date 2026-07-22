"""Frozen development base-model selection policy loader and applier."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ambiguity_manager.model.base_model_candidates import (
    ALLOWLISTED_CANDIDATE_IDS,
    BaseModelCandidateRegistry,
    BaseModelRegistryError,
    load_base_model_candidate_registry,
)
from ambiguity_manager.model.errors import ModelClientError
from ambiguity_manager.paths import ProjectPaths

POLICY_REL = "configs/model/base_model_selection_policy_v1.json"
ADAPTATION_POLICY_REL = "configs/model/adaptation_base_selection_policy_v1.json"
POLICY_VERSION = "1.0.0"
ADAPTATION_POLICY_VERSION = "1.0.0"

_PRIORITY_CRITERIA = (
    "safety_and_unsupported_commitments",
    "structured_output_reliability",
    "joint_intent_cpc_quality",
    "compound_ambiguity_quality",
    "context_use_and_blind_separation",
    "qlora_feasibility",
    "operational_cost_and_latency",
)

_HARD_REJECTION_IDS = (
    "stage1_transport_failure",
    "repeated_schema_collapse",
    "unsupported_or_unsafe_commitments",
    "runtime_incompatibility",
    "snapshot_or_licence_failure",
    "insufficient_context_length",
    "no_plausible_qlora_path",
)

_ADAPTATION_PRIORITY_CRITERIA = (
    "structured_output_reliability",
    "severity_weighted_safety",
    "semantic_validity_closeness",
    "joint_intent_cpc_quality",
    "compound_ambiguity_quality",
    "qlora_feasibility",
    "context_length",
    "runtime_stability",
    "vram_and_latency",
)

_ADAPTATION_HARD_REJECTION_IDS = (
    "incomplete_corrupt_snapshot",
    "unsupported_architecture",
    "tokenizer_load_failure",
    "no_valid_structured_output",
    "no_viable_4bit_training_path",
    "licence_incompatibility",
    "reproducibility_failure",
    "runtime_incompatibility",
    "insufficient_context_length",
    "fundamental_schema_runtime_incompatibility",
)


class BaseModelSelectionError(ModelClientError):
    """Raised when the selection policy payload or application is invalid."""


@dataclass(frozen=True)
class BaseModelSelectionPolicy:
    policy_version: str
    status: str
    frozen_before_stage_2: bool
    development_only: bool
    valid_for_official_use: bool
    selected_base_model: str | None
    selected_adapter: str | None
    selected_model_strategy: str | None
    ranking_mode: str
    priority_criteria: tuple[dict[str, Any], ...]
    hard_rejection_criteria: tuple[dict[str, Any], ...]
    unsafe_candidate_cannot_win_on_semantic_score: bool
    tie_break_order: tuple[str, ...]
    no_viable_candidate_status: str


@dataclass(frozen=True)
class CandidateBakeoffResult:
    candidate_id: str
    checkpoint_identity: str
    stage1_passed: bool
    hard_gate_failures: tuple[str, ...] = ()
    metrics: Mapping[str, float] = field(default_factory=dict)
    unsupported_commitments_on_accepted: int = 0
    unsafe_silent_commitments: int = 0
    invalid_final_schema_count: int = 0
    unrecorded_attempts: int = 0
    unconstrained_fallback_used: bool = False
    qlora_feasible: bool = True
    context_length_sufficient: bool = True
    runtime_compatible: bool = True
    snapshot_and_licence_verified: bool = True
    strict_structured_output_count: int = 0
    tokenizer_loads: bool = True
    runtime_loads: bool = True
    licence_compatible: bool = True
    reproducible_load: bool = True
    fundamental_incompatibility: bool = False


@dataclass(frozen=True)
class AdaptationBaseSelectionPolicy:
    policy_version: str
    policy_id: str
    status: str
    frozen_before_application: bool
    development_only: bool
    valid_for_official_use: bool
    requires_zero_shot_stage1_pass: bool
    selected_base_model: str | None
    selected_adapter: str | None
    selected_model_strategy: str | None
    ranking_mode: str
    priority_criteria: tuple[dict[str, Any], ...]
    hard_requirements: tuple[dict[str, Any], ...]
    hard_rejection_criteria: tuple[dict[str, Any], ...]
    unsafe_candidate_cannot_win_on_semantic_score: bool
    latency_must_not_override_safer_candidate: bool
    tie_break_order: tuple[str, ...]
    no_viable_candidate_status: str


@dataclass(frozen=True)
class SelectionOutcome:
    selected_base_model: str | None
    selected_adapter: str | None
    selected_model_strategy: str | None
    valid_for_official_use: bool
    status: str
    ranked_candidate_ids: tuple[str, ...]
    rejected_candidates: dict[str, tuple[str, ...]]
    winning_candidate_id: str | None
    tie_break_applied: bool

    def identity_update(self) -> dict[str, Any]:
        """Return identity fields for a caller to persist; does not write files."""
        return {
            "selected_base_model": self.selected_base_model,
            "selected_adapter": self.selected_adapter,
            "selected_model_strategy": self.selected_model_strategy,
            "valid_for_official_use": self.valid_for_official_use,
            "status": self.status,
        }


def _default_policy_path() -> Path:
    return ProjectPaths.from_repo_root().configs / "model" / "base_model_selection_policy_v1.json"


def _default_adaptation_policy_path() -> Path:
    return ProjectPaths.from_repo_root().configs / "model" / "adaptation_base_selection_policy_v1.json"


def validate_selection_policy_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if payload.get("policy_version") != POLICY_VERSION:
        errors.append(f"policy_version must be {POLICY_VERSION!r}")
    if payload.get("status") != "frozen_for_development_bakeoff":
        errors.append("status must be frozen_for_development_bakeoff")
    if payload.get("frozen_before_stage_2") is not True:
        errors.append("frozen_before_stage_2 must be true")
    if payload.get("development_only") is not True:
        errors.append("development_only must be true")
    if payload.get("valid_for_official_use") is not False:
        errors.append("valid_for_official_use must be false")
    for field in ("selected_base_model", "selected_adapter", "selected_model_strategy"):
        if payload.get(field) is not None:
            errors.append(f"{field} must remain null until bake-off pass")
    if payload.get("unsafe_candidate_cannot_win_on_semantic_score") is not True:
        errors.append("unsafe_candidate_cannot_win_on_semantic_score must be true")
    if payload.get("no_viable_candidate_status") != "no_viable_base_candidate":
        errors.append("no_viable_candidate_status must be no_viable_base_candidate")

    criteria = payload.get("priority_criteria")
    if not isinstance(criteria, list) or len(criteria) != len(_PRIORITY_CRITERIA):
        errors.append("priority_criteria must contain exactly seven frozen criteria")
    else:
        observed_ids = [str(item.get("criterion_id", "")) for item in criteria if isinstance(item, dict)]
        if observed_ids != list(_PRIORITY_CRITERIA):
            errors.append("priority_criteria order/ids must match frozen policy")
        for item in criteria:
            if not isinstance(item, dict):
                errors.append("each priority criterion must be an object")
                continue
            if "tune" in str(item.get("description", "")).lower():
                errors.append("priority criterion descriptions must not invite post-hoc tuning")

    hard = payload.get("hard_rejection_criteria")
    if not isinstance(hard, list):
        errors.append("hard_rejection_criteria must be a list")
    else:
        observed_hard = [str(item.get("criterion_id", "")) for item in hard if isinstance(item, dict)]
        if observed_hard != list(_HARD_REJECTION_IDS):
            errors.append("hard_rejection_criteria must match frozen section-18 list")

    tie_break = payload.get("tie_break_order")
    if tie_break != ["candidate_id_lexicographic_ascending"]:
        errors.append("tie_break_order must be candidate_id_lexicographic_ascending only")

    return errors


def load_base_model_selection_policy(path: Path | None = None) -> BaseModelSelectionPolicy:
    resolved = path or _default_policy_path()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BaseModelSelectionError("selection policy must be a JSON object")
    errors = validate_selection_policy_payload(payload)
    if errors:
        raise BaseModelSelectionError("invalid base-model selection policy:\n- " + "\n- ".join(errors))
    return BaseModelSelectionPolicy(
        policy_version=str(payload["policy_version"]),
        status=str(payload["status"]),
        frozen_before_stage_2=bool(payload["frozen_before_stage_2"]),
        development_only=bool(payload["development_only"]),
        valid_for_official_use=bool(payload["valid_for_official_use"]),
        selected_base_model=payload.get("selected_base_model"),
        selected_adapter=payload.get("selected_adapter"),
        selected_model_strategy=payload.get("selected_model_strategy"),
        ranking_mode=str(payload["ranking_mode"]),
        priority_criteria=tuple(dict(item) for item in payload["priority_criteria"]),
        hard_rejection_criteria=tuple(dict(item) for item in payload["hard_rejection_criteria"]),
        unsafe_candidate_cannot_win_on_semantic_score=bool(
            payload["unsafe_candidate_cannot_win_on_semantic_score"]
        ),
        tie_break_order=tuple(str(item) for item in payload["tie_break_order"]),
        no_viable_candidate_status=str(payload["no_viable_candidate_status"]),
    )


def _collect_hard_rejections(
    result: CandidateBakeoffResult,
    *,
    registry: BaseModelCandidateRegistry,
) -> list[str]:
    failures: list[str] = list(result.hard_gate_failures)
    thresholds = registry.development_bakeoff_thresholds

    if not result.stage1_passed:
        failures.append("stage1_transport_failure")
    if result.invalid_final_schema_count > int(thresholds["max_invalid_final_schema"]):
        failures.append("repeated_schema_collapse")
    if result.unrecorded_attempts > int(thresholds["max_unrecorded_attempts"]):
        failures.append("stage1_transport_failure")
    if result.unconstrained_fallback_used and not thresholds["unconstrained_fallback_permitted"]:
        failures.append("stage1_transport_failure")
    if result.unsupported_commitments_on_accepted > int(
        thresholds["max_unsupported_commitments_on_accepted"]
    ):
        failures.append("unsupported_or_unsafe_commitments")
    if result.unsafe_silent_commitments > int(thresholds["max_unsafe_silent_commitments"]):
        failures.append("unsupported_or_unsafe_commitments")
    if not result.runtime_compatible:
        failures.append("runtime_incompatibility")
    if not result.snapshot_and_licence_verified:
        failures.append("snapshot_or_licence_failure")
    if not result.context_length_sufficient:
        failures.append("insufficient_context_length")
    if not result.qlora_feasible:
        failures.append("no_plausible_qlora_path")

    return sorted(set(failures))


def _sort_key(result: CandidateBakeoffResult) -> tuple[float, ...]:
    key: list[float] = []
    for criterion_id in _PRIORITY_CRITERIA:
        value = float(result.metrics.get(criterion_id, 0.0))
        if criterion_id == "operational_cost_and_latency":
            key.append(value)
        else:
            key.append(-value)
    return tuple(key)


def apply_selection(
    results: Mapping[str, CandidateBakeoffResult],
    *,
    policy: BaseModelSelectionPolicy | None = None,
    registry: BaseModelCandidateRegistry | None = None,
) -> SelectionOutcome:
    """Apply the frozen policy to bake-off results without writing identity files."""
    resolved_policy = policy or load_base_model_selection_policy()
    resolved_registry = registry or load_base_model_candidate_registry()

    unknown = sorted(set(results) - ALLOWLISTED_CANDIDATE_IDS)
    if unknown:
        raise BaseModelSelectionError(f"results contain non-allowlisted candidate IDs: {unknown}")

    rejected: dict[str, tuple[str, ...]] = {}
    viable: list[CandidateBakeoffResult] = []
    for candidate_id in sorted(results):
        result = results[candidate_id]
        if result.candidate_id != candidate_id:
            raise BaseModelSelectionError(
                f"result key {candidate_id!r} does not match result.candidate_id {result.candidate_id!r}"
            )
        hard_failures = tuple(_collect_hard_rejections(result, registry=resolved_registry))
        if hard_failures:
            rejected[candidate_id] = hard_failures
            continue
        if resolved_policy.unsafe_candidate_cannot_win_on_semantic_score and (
            result.unsafe_silent_commitments > 0
            or result.unsupported_commitments_on_accepted
            > int(resolved_registry.development_bakeoff_thresholds["max_unsupported_commitments_on_accepted"])
        ):
            rejected[candidate_id] = ("unsupported_or_unsafe_commitments",)
            continue
        viable.append(result)

    if not viable:
        return SelectionOutcome(
            selected_base_model=None,
            selected_adapter=None,
            selected_model_strategy=None,
            valid_for_official_use=False,
            status=resolved_policy.no_viable_candidate_status,
            ranked_candidate_ids=tuple(),
            rejected_candidates=rejected,
            winning_candidate_id=None,
            tie_break_applied=False,
        )

    ranked = sorted(viable, key=lambda item: (*_sort_key(item), item.candidate_id))
    top_score = _sort_key(ranked[0])
    tied = [item for item in ranked if _sort_key(item) == top_score]
    tie_break_applied = len(tied) > 1
    winner = sorted(tied, key=lambda item: item.candidate_id)[0]

    return SelectionOutcome(
        selected_base_model=winner.checkpoint_identity,
        selected_adapter=None,
        selected_model_strategy=None,
        valid_for_official_use=False,
        status="development_base_selected",
        ranked_candidate_ids=tuple(item.candidate_id for item in ranked),
        rejected_candidates=rejected,
        winning_candidate_id=winner.candidate_id,
        tie_break_applied=tie_break_applied,
    )


def validate_adaptation_base_selection_policy_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if payload.get("policy_version") != ADAPTATION_POLICY_VERSION:
        errors.append(f"policy_version must be {ADAPTATION_POLICY_VERSION!r}")
    if payload.get("policy_id") != "adaptation_base_selection_policy_v1":
        errors.append("policy_id must be adaptation_base_selection_policy_v1")
    if payload.get("status") != "frozen_for_adaptation_base_selection":
        errors.append("status must be frozen_for_adaptation_base_selection")
    if payload.get("frozen_before_application") is not True:
        errors.append("frozen_before_application must be true")
    if payload.get("development_only") is not True:
        errors.append("development_only must be true")
    if payload.get("valid_for_official_use") is not False:
        errors.append("valid_for_official_use must be false")
    if payload.get("requires_zero_shot_stage1_pass") is not False:
        errors.append("requires_zero_shot_stage1_pass must be false")
    for field in ("selected_base_model", "selected_adapter", "selected_model_strategy"):
        if payload.get(field) is not None:
            errors.append(f"{field} must remain null until adaptation-base selection is applied")
    if payload.get("unsafe_candidate_cannot_win_on_semantic_score") is not True:
        errors.append("unsafe_candidate_cannot_win_on_semantic_score must be true")
    if payload.get("latency_must_not_override_safer_candidate") is not True:
        errors.append("latency_must_not_override_safer_candidate must be true")
    if payload.get("no_viable_candidate_status") != "no_viable_adaptation_base":
        errors.append("no_viable_candidate_status must be no_viable_adaptation_base")

    criteria = payload.get("priority_criteria")
    if not isinstance(criteria, list) or len(criteria) != len(_ADAPTATION_PRIORITY_CRITERIA):
        errors.append("priority_criteria must contain exactly nine frozen criteria")
    else:
        observed_ids = [str(item.get("criterion_id", "")) for item in criteria if isinstance(item, dict)]
        if observed_ids != list(_ADAPTATION_PRIORITY_CRITERIA):
            errors.append("priority_criteria order/ids must match frozen adaptation-base policy")
        for item in criteria:
            if not isinstance(item, dict):
                errors.append("each priority criterion must be an object")
                continue
            if "tune" in str(item.get("description", "")).lower():
                errors.append("priority criterion descriptions must not invite post-hoc tuning")

    hard = payload.get("hard_rejection_criteria")
    if not isinstance(hard, list):
        errors.append("hard_rejection_criteria must be a list")
    else:
        observed_hard = [str(item.get("criterion_id", "")) for item in hard if isinstance(item, dict)]
        if observed_hard != list(_ADAPTATION_HARD_REJECTION_IDS):
            errors.append("hard_rejection_criteria must match frozen adaptation-base list")

    requirements = payload.get("hard_requirements")
    if not isinstance(requirements, list) or len(requirements) < 10:
        errors.append("hard_requirements must list all adaptation-base hard requirements")

    tie_break = payload.get("tie_break_order")
    if tie_break != ["candidate_id_lexicographic_ascending"]:
        errors.append("tie_break_order must be candidate_id_lexicographic_ascending only")

    return errors


def load_adaptation_base_selection_policy(
    path: Path | None = None,
) -> AdaptationBaseSelectionPolicy:
    resolved = path or _default_adaptation_policy_path()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BaseModelSelectionError("adaptation-base selection policy must be a JSON object")
    errors = validate_adaptation_base_selection_policy_payload(payload)
    if errors:
        raise BaseModelSelectionError(
            "invalid adaptation-base selection policy:\n- " + "\n- ".join(errors)
        )
    return AdaptationBaseSelectionPolicy(
        policy_version=str(payload["policy_version"]),
        policy_id=str(payload["policy_id"]),
        status=str(payload["status"]),
        frozen_before_application=bool(payload["frozen_before_application"]),
        development_only=bool(payload["development_only"]),
        valid_for_official_use=bool(payload["valid_for_official_use"]),
        requires_zero_shot_stage1_pass=bool(payload["requires_zero_shot_stage1_pass"]),
        selected_base_model=payload.get("selected_base_model"),
        selected_adapter=payload.get("selected_adapter"),
        selected_model_strategy=payload.get("selected_model_strategy"),
        ranking_mode=str(payload["ranking_mode"]),
        priority_criteria=tuple(dict(item) for item in payload["priority_criteria"]),
        hard_requirements=tuple(dict(item) for item in payload["hard_requirements"]),
        hard_rejection_criteria=tuple(dict(item) for item in payload["hard_rejection_criteria"]),
        unsafe_candidate_cannot_win_on_semantic_score=bool(
            payload["unsafe_candidate_cannot_win_on_semantic_score"]
        ),
        latency_must_not_override_safer_candidate=bool(
            payload["latency_must_not_override_safer_candidate"]
        ),
        tie_break_order=tuple(str(item) for item in payload["tie_break_order"]),
        no_viable_candidate_status=str(payload["no_viable_candidate_status"]),
    )


def _collect_adaptation_hard_rejections(result: CandidateBakeoffResult) -> list[str]:
    failures: list[str] = list(result.hard_gate_failures)

    if not result.licence_compatible:
        failures.append("licence_incompatibility")
    if not result.snapshot_and_licence_verified:
        failures.append("incomplete_corrupt_snapshot")
    if not result.tokenizer_loads:
        failures.append("tokenizer_load_failure")
    if not result.runtime_loads or not result.runtime_compatible:
        failures.append("runtime_incompatibility")
    if not result.reproducible_load:
        failures.append("reproducibility_failure")
    if result.strict_structured_output_count < 1:
        failures.append("no_valid_structured_output")
    if result.fundamental_incompatibility:
        failures.append("fundamental_schema_runtime_incompatibility")
    if not result.context_length_sufficient:
        failures.append("insufficient_context_length")
    if not result.qlora_feasible:
        failures.append("no_viable_4bit_training_path")

    return sorted(set(failures))


def _adaptation_sort_key(result: CandidateBakeoffResult) -> tuple[float, ...]:
    key: list[float] = []
    for criterion_id in _ADAPTATION_PRIORITY_CRITERIA:
        value = float(result.metrics.get(criterion_id, 0.0))
        if criterion_id == "vram_and_latency":
            key.append(value)
        else:
            key.append(-value)
    return tuple(key)


def apply_adaptation_base_selection(
    results: Mapping[str, CandidateBakeoffResult],
    *,
    policy: AdaptationBaseSelectionPolicy | None = None,
    registry: BaseModelCandidateRegistry | None = None,
) -> SelectionOutcome:
    """Apply the frozen adaptation-base policy without requiring zero-shot 4/4 pass."""
    resolved_policy = policy or load_adaptation_base_selection_policy()
    resolved_registry = registry or load_base_model_candidate_registry()

    if resolved_policy.requires_zero_shot_stage1_pass:
        raise BaseModelSelectionError(
            "adaptation-base policy must not require zero-shot Stage-1 4/4 acceptance"
        )

    unknown = sorted(set(results) - ALLOWLISTED_CANDIDATE_IDS)
    if unknown:
        raise BaseModelSelectionError(f"results contain non-allowlisted candidate IDs: {unknown}")

    rejected: dict[str, tuple[str, ...]] = {}
    viable: list[CandidateBakeoffResult] = []
    for candidate_id in sorted(results):
        result = results[candidate_id]
        if result.candidate_id != candidate_id:
            raise BaseModelSelectionError(
                f"result key {candidate_id!r} does not match result.candidate_id {result.candidate_id!r}"
            )
        hard_failures = tuple(_collect_adaptation_hard_rejections(result))
        if hard_failures:
            rejected[candidate_id] = hard_failures
            continue
        # Safety severity is ranked (criterion #2), not a hard gate for adaptation-base
        # eligibility. zero-shot Stage-1 4/4 safety acceptance is intentionally not required.
        # unsafe_candidate_cannot_win_on_semantic_score is enforced by lexicographic ranking
        # with severity_weighted_safety before semantic/CPC criteria.
        viable.append(result)

    if not viable:
        return SelectionOutcome(
            selected_base_model=None,
            selected_adapter=None,
            selected_model_strategy=None,
            valid_for_official_use=False,
            status=resolved_policy.no_viable_candidate_status,
            ranked_candidate_ids=tuple(),
            rejected_candidates=rejected,
            winning_candidate_id=None,
            tie_break_applied=False,
        )

    ranked = sorted(viable, key=lambda item: (*_adaptation_sort_key(item), item.candidate_id))
    top_score = _adaptation_sort_key(ranked[0])
    tied = [item for item in ranked if _adaptation_sort_key(item) == top_score]
    tie_break_applied = len(tied) > 1
    winner = sorted(tied, key=lambda item: item.candidate_id)[0]

    return SelectionOutcome(
        selected_base_model=winner.checkpoint_identity,
        selected_adapter=None,
        selected_model_strategy=None,
        valid_for_official_use=False,
        status="adaptation_base_selected_for_qlora_development",
        ranked_candidate_ids=tuple(item.candidate_id for item in ranked),
        rejected_candidates=rejected,
        winning_candidate_id=winner.candidate_id,
        tie_break_applied=tie_break_applied,
    )
