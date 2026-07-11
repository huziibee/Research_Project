"""T12 Stage D generation and repair policy contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ambiguity_manager.model.parser import MAX_REPAIR_ROUNDS
from ambiguity_manager.model.prediction_contract import ACCEPTANCE_RULE_IDS

T19_ROUTING_DEFERRED = True
DEFAULT_POLICY_REL = Path("configs") / "model" / "t12_generation_policy.json"


@dataclass(frozen=True)
class GenerationPolicy:
    schema_version: str
    total_model_attempts: int
    initial_generation_attempts: int
    bounded_regeneration_attempts: int
    deterministic_local_json_repair_rounds: int
    unconstrained_fallback_permitted: bool
    retain_all_raw_attempts: bool
    structural_validity_separate_from_semantic_correctness: bool
    accept_schema_invalid_output: bool
    exhausted_attempts_end_in_explicit_rejection: bool
    silent_enum_coercion_permitted: bool
    field_invention_permitted: bool
    full_t19_routing_deferred: bool
    acceptance_rule_ids: tuple[str, ...]
    unsupported_silent_commitments_are_rejection_evidence: bool
    route_policy_logic_beyond_schema_deferred_to: str


def load_generation_policy(path: Path | None = None) -> GenerationPolicy:
    from ambiguity_manager.paths import repo_root

    target = path or (repo_root() / DEFAULT_POLICY_REL)
    payload = json.loads(target.read_text(encoding="utf-8"))
    return GenerationPolicy(
        schema_version=str(payload["schema_version"]),
        total_model_attempts=int(payload["total_model_attempts"]),
        initial_generation_attempts=int(payload["initial_generation_attempts"]),
        bounded_regeneration_attempts=int(payload["bounded_regeneration_attempts"]),
        deterministic_local_json_repair_rounds=int(payload["deterministic_local_json_repair_rounds"]),
        unconstrained_fallback_permitted=bool(payload["unconstrained_fallback_permitted"]),
        retain_all_raw_attempts=bool(payload["retain_all_raw_attempts"]),
        structural_validity_separate_from_semantic_correctness=bool(
            payload["structural_validity_separate_from_semantic_correctness"]
        ),
        accept_schema_invalid_output=bool(payload["accept_schema_invalid_output"]),
        exhausted_attempts_end_in_explicit_rejection=bool(
            payload["exhausted_attempts_end_in_explicit_rejection"]
        ),
        silent_enum_coercion_permitted=bool(payload["silent_enum_coercion_permitted"]),
        field_invention_permitted=bool(payload["field_invention_permitted"]),
        full_t19_routing_deferred=bool(payload["full_t19_routing_deferred"]),
        acceptance_rule_ids=tuple(payload["acceptance_rule_ids"]),
        unsupported_silent_commitments_are_rejection_evidence=bool(
            payload["unsupported_silent_commitments_are_rejection_evidence"]
        ),
        route_policy_logic_beyond_schema_deferred_to=str(
            payload["route_policy_logic_beyond_schema_deferred_to"]
        ),
    )


def default_generation_policy_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "total_model_attempts": 3,
        "initial_generation_attempts": 1,
        "bounded_regeneration_attempts": 2,
        "deterministic_local_json_repair_rounds": MAX_REPAIR_ROUNDS,
        "unconstrained_fallback_permitted": False,
        "retain_all_raw_attempts": True,
        "structural_validity_separate_from_semantic_correctness": True,
        "accept_schema_invalid_output": False,
        "exhausted_attempts_end_in_explicit_rejection": True,
        "silent_enum_coercion_permitted": False,
        "field_invention_permitted": False,
        "full_t19_routing_deferred": True,
        "acceptance_rule_ids": list(ACCEPTANCE_RULE_IDS),
        "unsupported_silent_commitments_are_rejection_evidence": True,
        "route_policy_logic_beyond_schema_deferred_to": "T19",
    }
