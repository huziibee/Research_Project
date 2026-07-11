"""T12 Slice 4 controlled synthetic fixture evaluation."""

from __future__ import annotations

import json
import os
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ambiguity_manager.governance.hashing import sha256_hex
from ambiguity_manager.governance.model_licence import MANDATORY_CONTEXT_LIMIT
from ambiguity_manager.model.checkpoint_download import (
    AUTHORIZED_CANDIDATE_ENTRY_ID,
    AUTHORIZED_REPOSITORY_ID,
    AUTHORIZED_REVISION_SHA,
    AUTHORIZED_TOKENIZER_REVISION_SHA,
    EVIDENCE_REL as DOWNLOAD_EVIDENCE_REL,
    REGISTER_REL,
)
from ambiguity_manager.model.checkpoint_load import (
    BACKEND_ID,
    DEFAULT_TIMEOUT_S,
    LOAD_EVIDENCE_REL,
    REQUIRED_OFFLINE_ENV,
    build_runtime_spec,
    detect_lingering_probe_processes,
    gpu_free_vram_mib,
    validate_checkpoint_load_evidence,
    validate_download_evidence_for_load,
    validate_offline_flags,
    validate_register_for_load,
    validate_wsl_cache_policy,
)
from ambiguity_manager.model.context_budget import DEFAULT_SAFETY_MARGIN
from ambiguity_manager.model.environment import INFERENCE_ENV_REL
from ambiguity_manager.model.integrity import count_unsupported_commitments, load_synthetic_fixtures
from ambiguity_manager.model.parser import MAX_REPAIR_OPERATIONS, extract_and_repair_json
from ambiguity_manager.model.prompt_builder import build_messages_from_fixture
from ambiguity_manager.model.protocol import GenerateJsonRequest, GenerateJsonResult
from ambiguity_manager.schema.v2.json_schema import build_prediction_json_schema
from ambiguity_manager.schema.v2.validation import validate_canonical_record_v2

FIXTURE_REL = "tests/fixtures/schema_v2/t12_synthetic_inputs.jsonl"
EVIDENCE_REL = "configs/model/evidence/t12_synthetic_evaluation.json"
REPORT_REL = "docs/reports/ticket_T12_synthetic_evaluation.md"
RAW_OUTPUT_DIR_REL = "outputs/model_runs/synthetic_evaluation/raw"
RUN_LOG_DIR_REL = "outputs/model_runs/synthetic_evaluation"

AUTHORISED_FIXTURE_COUNT = 10
REQUESTED_MAX_NEW_TOKENS = 512
GENERATION_SEED = 0

FORBIDDEN_FIXTURE_SUBSTRINGS = (
    "data/interim",
    "data/processed",
    "weak_pool",
    "ambik:",
    "clara:",
    "protected",
)

OUTCOME_VALUES = frozenset(
    {
        "continue_to_repeatability",
        "prompt_contract_remediation_required",
        "fallback_candidate_probe_required",
        "blocked_by_runtime",
        "threshold_not_frozen",
    }
)

# Explicit fixture annotations only; do not invent expected labels.
ANNOTATED_FIELD_SOURCES: dict[str, tuple[str, str]] = {
    "route": ("support_declarations.expected_route_pressure", "recommended_strategy"),
}

_ABSOLUTE_PATH_PATTERN = re.compile(r"^[A-Za-z]:[\\/]|^/home/|^/Users/|^\\\\")
_USERNAME_PATTERN = re.compile(r"\bhuzii\b", re.IGNORECASE)


class SyntheticEvaluationError(Exception):
    """Raised when synthetic evaluation preconditions fail."""


@dataclass(frozen=True)
class FixtureManifest:
    fixture_file_sha256: str
    fixtures: list[dict[str, Any]]
    fixture_ids: list[str]
    fixture_input_shas: dict[str, str]


def utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _scan_forbidden_identifiers(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, str):
        if _ABSOLUTE_PATH_PATTERN.search(value):
            errors.append(f"{path} contains absolute path")
        if _USERNAME_PATTERN.search(value):
            errors.append(f"{path} contains username")
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            _scan_forbidden_identifiers(nested, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _scan_forbidden_identifiers(nested, f"{path}[{index}]", errors)


def canonical_fixture_line(fixture: dict[str, Any]) -> str:
    return json.dumps(fixture, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fixture_input_sha256(fixture: dict[str, Any]) -> str:
    return sha256_hex(canonical_fixture_line(fixture).encode("utf-8"))


def load_fixture_manifest(fixture_path: Path, *, expected_sha256: str | None = None) -> FixtureManifest:
    if not fixture_path.is_file():
        raise SyntheticEvaluationError(f"fixture file not found: {FIXTURE_REL}")

    raw_bytes = fixture_path.read_text(encoding="utf-8")
    lowered = raw_bytes.lower()
    for forbidden in FORBIDDEN_FIXTURE_SUBSTRINGS:
        if forbidden in lowered:
            raise SyntheticEvaluationError(f"fixture file contains forbidden reference: {forbidden}")

    digest = sha256_hex(raw_bytes.encode("utf-8"))
    if expected_sha256 is not None and digest != expected_sha256:
        raise SyntheticEvaluationError(
            f"fixture file SHA-256 mismatch: expected {expected_sha256}, got {digest}"
        )

    fixtures = load_synthetic_fixtures(fixture_path)
    if len(fixtures) != AUTHORISED_FIXTURE_COUNT:
        raise SyntheticEvaluationError(
            f"authorised fixture count must be {AUTHORISED_FIXTURE_COUNT}, got {len(fixtures)}"
        )

    seen: set[str] = set()
    fixture_ids: list[str] = []
    input_shas: dict[str, str] = {}
    for fixture in fixtures:
        fixture_id = fixture.get("fixture_id")
        if not isinstance(fixture_id, str) or not fixture_id:
            raise SyntheticEvaluationError("fixture_id required on every record")
        if fixture_id in seen:
            raise SyntheticEvaluationError(f"duplicate fixture_id: {fixture_id}")
        seen.add(fixture_id)
        fixture_ids.append(fixture_id)
        input_shas[fixture_id] = fixture_input_sha256(fixture)

    return FixtureManifest(
        fixture_file_sha256=digest,
        fixtures=fixtures,
        fixture_ids=fixture_ids,
        fixture_input_shas=input_shas,
    )


def prompt_sha256(messages: list[dict[str, str]]) -> str:
    payload = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_hex(payload.encode("utf-8"))


def raw_output_relpath(fixture_id: str) -> str:
    return f"{RAW_OUTPUT_DIR_REL}/t12_{fixture_id}.txt"


def extract_expected_annotations(fixture: dict[str, Any]) -> dict[str, Any]:
    """Return only explicitly annotated expected values from the fixture."""
    annotations: dict[str, Any] = {}
    declarations = fixture.get("support_declarations")
    if isinstance(declarations, dict):
        route_pressure = declarations.get("expected_route_pressure")
        if route_pressure is not None:
            annotations["route"] = route_pressure
    return annotations


def _predicted_field_value(prediction: dict[str, Any] | None, field: str) -> Any:
    if not isinstance(prediction, dict):
        return None
    return prediction.get(field)


def score_annotated_fields(
    fixture: dict[str, Any],
    prediction: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Score only fields explicitly annotated by the fixture."""
    expected = extract_expected_annotations(fixture)
    scores: list[dict[str, Any]] = []
    for metric_name, (source_path, prediction_field) in ANNOTATED_FIELD_SOURCES.items():
        if metric_name not in expected:
            continue
        expected_value = expected[metric_name]
        predicted_value = _predicted_field_value(prediction, prediction_field)
        exact_match = predicted_value == expected_value
        missing_prediction = predicted_value is None
        invalid_prediction = (
            not missing_prediction
            and not isinstance(predicted_value, str)
        )
        scores.append(
            {
                "field": metric_name,
                "source_path": source_path,
                "prediction_field": prediction_field,
                "expected_value": expected_value,
                "predicted_value": predicted_value,
                "exact_match": exact_match,
                "partial_or_set_match": None,
                "missing_prediction": missing_prediction,
                "invalid_prediction": invalid_prediction,
            }
        )
    return scores


def evaluate_silent_resolution_gate(
    *,
    prediction: dict[str, Any] | None,
    unsupported_commitment_count: int,
) -> dict[str, Any]:
    recommended = None
    if isinstance(prediction, dict):
        recommended = prediction.get("recommended_strategy")
    claims_silent = recommended == "silently_resolve"
    eligible = claims_silent and unsupported_commitment_count == 0
    return {
        "recommended_strategy": recommended,
        "claims_silent_resolution": claims_silent,
        "unsupported_commitment_count": unsupported_commitment_count,
        "silent_resolution_eligible": eligible,
        "false_silent_resolution_eligibility": claims_silent and unsupported_commitment_count > 0,
    }


def _context_budget_result(
    *,
    generation_status: str,
    effective_max_new_tokens: int | None,
    requested_max_new_tokens: int,
    prompt_tokens: int | None,
) -> str:
    if generation_status in {"timeout", "backend_error", "oom"}:
        return generation_status
    if prompt_tokens is None or effective_max_new_tokens is None:
        return "unknown"
    available = MANDATORY_CONTEXT_LIMIT - prompt_tokens - DEFAULT_SAFETY_MARGIN
    if available <= 0:
        return "context_overflow"
    if effective_max_new_tokens < requested_max_new_tokens:
        return "clamped"
    return "within_budget"


def _generation_status_from_result(result: GenerateJsonResult) -> str:
    if result.final_status == "timeout":
        return "timeout"
    if result.final_status == "backend_error":
        return "backend_error"
    if result.final_status == "empty_output":
        return "empty_output"
    return "completed"


def _is_oom_error(error_text: str | None) -> bool:
    if not error_text:
        return False
    lowered = error_text.lower()
    return "out of memory" in lowered or "cuda oom" in lowered or "oom" in lowered


def build_per_fixture_result(
    *,
    fixture: dict[str, Any],
    result: GenerateJsonResult,
    raw_output_relpath_value: str,
    raw_output_sha256_value: str,
    parse_result: Any | None = None,
) -> dict[str, Any]:
    fixture_id = fixture["fixture_id"]
    messages = build_messages_from_fixture(fixture, json_schema=build_prediction_json_schema())
    parsed = parse_result or extract_and_repair_json(result.raw_output)

    schema_valid = False
    schema_errors: list[str] = list(result.schema_errors)
    if parsed.parsed_object is not None:
        try:
            validate_canonical_record_v2(parsed.parsed_object)
            schema_valid = True
            schema_errors = []
        except Exception as exc:  # noqa: BLE001
            schema_valid = False
            schema_errors = [str(exc)]

    prediction = parsed.parsed_object
    unsupported_count = count_unsupported_commitments(fixture, prediction) if prediction else 0
    silent_gate = evaluate_silent_resolution_gate(
        prediction=prediction,
        unsupported_commitment_count=unsupported_count,
    )
    annotated_scores = score_annotated_fields(fixture, prediction)

    runtime_meta = dict(result.runtime_metadata or {})
    worker_error = runtime_meta.get("error")
    generation_status = _generation_status_from_result(result)
    oom_status = _is_oom_error(worker_error if isinstance(worker_error, str) else None)
    if oom_status:
        generation_status = "oom"

    prompt_tokens = result.prompt_tokens
    completion_tokens = result.completion_tokens
    total_tokens = None
    if prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens

    effective_max = runtime_meta.get("effective_max_new_tokens")
    context_budget = _context_budget_result(
        generation_status=generation_status,
        effective_max_new_tokens=effective_max if isinstance(effective_max, int) else None,
        requested_max_new_tokens=REQUESTED_MAX_NEW_TOKENS,
        prompt_tokens=prompt_tokens,
    )

    parser_status = "parse_success" if parsed.parsed_object is not None else "parse_failed"
    if not result.raw_output.strip():
        parser_status = "empty_output"

    route_score = next((s for s in annotated_scores if s["field"] == "route"), None)

    return {
        "fixture_id": fixture_id,
        "fixture_input_sha256": fixture_input_sha256(fixture),
        "immutable_revision_sha": AUTHORIZED_REVISION_SHA,
        "tokenizer_revision_sha": AUTHORIZED_TOKENIZER_REVISION_SHA,
        "prompt_sha256": prompt_sha256(messages),
        "prompt_token_count": prompt_tokens,
        "requested_max_new_tokens": REQUESTED_MAX_NEW_TOKENS,
        "effective_max_new_tokens": effective_max,
        "completion_token_count": completion_tokens,
        "total_token_count": total_tokens,
        "context_budget_result": context_budget,
        "generation_status": generation_status,
        "timeout_status": generation_status == "timeout",
        "oom_status": oom_status,
        "backend_error_status": generation_status == "backend_error",
        "raw_output_relpath": raw_output_relpath_value,
        "raw_output_sha256": raw_output_sha256_value,
        "raw_output_nonempty": bool(result.raw_output.strip()),
        "parser_status": parser_status,
        "bounded_repair_operations": list(parsed.repair_log),
        "bounded_repair_count": parsed.repair_attempts,
        "parsed_object_present": parsed.parsed_object is not None,
        "schema_validation_status": "schema_valid" if schema_valid else "schema_invalid",
        "schema_errors": schema_errors,
        "unsupported_commitment_count": unsupported_count,
        "silent_resolution_gate": silent_gate,
        "annotated_field_scores": annotated_scores,
        "route_result": route_score,
        "ambiguity_type_result": None,
        "risk_result": None,
        "unresolved_slot_result": None,
        "latency_ms": result.latency_ms,
        "peak_allocated_vram_mib": result.peak_vram_mib,
        "peak_reserved_vram_mib": None,
        "worker_process_exit_completed": bool(runtime_meta.get("worker_process_exit_completed")),
        "worker_exit_code": runtime_meta.get("worker_exit_code"),
        "cleanup_status": "completed" if runtime_meta.get("worker_process_exit_completed") else "incomplete",
        "final_status": result.final_status,
        "repair_bounded": parsed.repair_attempts <= MAX_REPAIR_OPERATIONS,
    }


def _distribution(values: list[float | int]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
        }
    numeric = [float(v) for v in values]
    return {
        "count": len(numeric),
        "min": round(min(numeric), 3),
        "max": round(max(numeric), 3),
        "mean": round(statistics.mean(numeric), 3),
        "median": round(statistics.median(numeric), 3),
    }


def compute_aggregate_metrics(per_fixture: list[dict[str, Any]]) -> dict[str, Any]:
    attempted = len(per_fixture)
    completed = sum(1 for item in per_fixture if item.get("generation_status") == "completed")
    nonempty = sum(1 for item in per_fixture if item.get("raw_output_nonempty"))
    parse_success = sum(1 for item in per_fixture if item.get("parser_status") == "parse_success")
    schema_valid = sum(
        1 for item in per_fixture if item.get("schema_validation_status") == "schema_valid"
    )
    schema_invalid = sum(
        1 for item in per_fixture if item.get("schema_validation_status") == "schema_invalid"
    )
    parser_failure = sum(1 for item in per_fixture if item.get("parser_status") == "parse_failed")
    timeout_count = sum(1 for item in per_fixture if item.get("timeout_status"))
    oom_count = sum(1 for item in per_fixture if item.get("oom_status"))
    backend_error_count = sum(1 for item in per_fixture if item.get("backend_error_status"))
    unsupported_total = sum(int(item.get("unsupported_commitment_count", 0)) for item in per_fixture)
    fixtures_with_unsupported = sum(
        1 for item in per_fixture if int(item.get("unsupported_commitment_count", 0)) > 0
    )
    false_silent = sum(
        1
        for item in per_fixture
        if isinstance(item.get("silent_resolution_gate"), dict)
        and item["silent_resolution_gate"].get("false_silent_resolution_eligibility")
    )
    context_overflow = sum(
        1 for item in per_fixture if item.get("context_budget_result") == "context_overflow"
    )
    worker_cleanup_failures = sum(
        1 for item in per_fixture if not item.get("worker_process_exit_completed")
    )

    repair_distribution: dict[str, int] = {}
    for item in per_fixture:
        count = int(item.get("bounded_repair_count", 0))
        repair_distribution[str(count)] = repair_distribution.get(str(count), 0) + 1
    repair_success = sum(
        1
        for item in per_fixture
        if int(item.get("bounded_repair_count", 0)) > 0
        and item.get("parser_status") == "parse_success"
    )

    route_scores = [
        score
        for item in per_fixture
        for score in item.get("annotated_field_scores", [])
        if score.get("field") == "route"
    ]
    route_exact = sum(1 for score in route_scores if score.get("exact_match"))
    route_attempted = len(route_scores)

    def _rate(numerator: int, denominator: int) -> float | None:
        if denominator == 0:
            return None
        return round(numerator / denominator, 4)

    latencies = [item["latency_ms"] for item in per_fixture if isinstance(item.get("latency_ms"), (int, float))]
    prompt_tokens = [
        item["prompt_token_count"]
        for item in per_fixture
        if isinstance(item.get("prompt_token_count"), int)
    ]
    completion_tokens = [
        item["completion_token_count"]
        for item in per_fixture
        if isinstance(item.get("completion_token_count"), int)
    ]
    peak_vram = [
        item["peak_allocated_vram_mib"]
        for item in per_fixture
        if isinstance(item.get("peak_allocated_vram_mib"), (int, float))
    ]

    return {
        "authorised_fixture_count": AUTHORISED_FIXTURE_COUNT,
        "attempted_count": attempted,
        "completed_generation_count": completed,
        "completed_generation_rate": _rate(completed, attempted),
        "non_empty_raw_output_count": nonempty,
        "non_empty_raw_output_rate": _rate(nonempty, attempted),
        "parse_success_count": parse_success,
        "parse_success_rate": _rate(parse_success, attempted),
        "schema_valid_count": schema_valid,
        "schema_valid_rate": _rate(schema_valid, attempted),
        "schema_invalid_count": schema_invalid,
        "parser_failure_count": parser_failure,
        "repair_attempt_distribution": repair_distribution,
        "repair_success_count": repair_success,
        "timeout_count": timeout_count,
        "oom_count": oom_count,
        "backend_error_count": backend_error_count,
        "unsupported_commitment_total": unsupported_total,
        "fixtures_with_unsupported_commitments": fixtures_with_unsupported,
        "false_silent_resolution_eligibility_count": false_silent,
        "route_accuracy": {
            "annotated_count": route_attempted,
            "exact_match_count": route_exact,
            "exact_match_rate": _rate(route_exact, route_attempted),
        },
        "ambiguity_type_accuracy": None,
        "risk_accuracy": None,
        "unresolved_slot_accuracy": None,
        "latency_ms_distribution": _distribution(latencies),
        "prompt_token_distribution": _distribution(prompt_tokens),
        "completion_token_distribution": _distribution(completion_tokens),
        "peak_vram_mib_distribution": _distribution(peak_vram),
        "context_overflow_count": context_overflow,
        "worker_cleanup_failures": worker_cleanup_failures,
    }


def reconcile_aggregate_metrics(
    per_fixture: list[dict[str, Any]],
    aggregate: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    recomputed = compute_aggregate_metrics(per_fixture)
    for key, expected in recomputed.items():
        actual = aggregate.get(key)
        if actual != expected:
            errors.append(f"aggregate.{key} mismatch: expected {expected!r}, got {actual!r}")
    if aggregate.get("attempted_count") != len(per_fixture):
        errors.append("attempted_count must equal per-fixture result count")
    if aggregate.get("authorised_fixture_count") != AUTHORISED_FIXTURE_COUNT:
        errors.append("authorised_fixture_count mismatch")
    return errors


def classify_outcome(
    aggregate: dict[str, Any],
    *,
    run_complete: bool,
) -> str:
    if not run_complete:
        return "blocked_by_runtime"
    attempted = int(aggregate.get("attempted_count", 0))
    authorised = int(aggregate.get("authorised_fixture_count", AUTHORISED_FIXTURE_COUNT))
    if attempted < authorised:
        return "blocked_by_runtime"
    if aggregate.get("timeout_count", 0) > 0 or aggregate.get("oom_count", 0) > 0:
        return "blocked_by_runtime"
    if aggregate.get("backend_error_count", 0) > 0:
        return "blocked_by_runtime"
    # Authoritative T12 plan does not freeze numeric quality thresholds for Slice 4.
    return "threshold_not_frozen"


def recommend_fallback_probe(aggregate: dict[str, Any]) -> bool:
    """Record-only recommendation; does not trigger download."""
    completed_rate = aggregate.get("completed_generation_rate")
    schema_rate = aggregate.get("schema_valid_rate")
    if completed_rate is not None and completed_rate < 1.0:
        return True
    if schema_rate is not None and schema_rate == 0.0:
        return True
    if aggregate.get("backend_error_count", 0) > 0:
        return True
    return False


def build_evidence_scaffold(*, fixture_file_sha256: str) -> dict[str, Any]:
    return {
        "manifest_schema_version": "1.0.0",
        "ticket": "T12",
        "slice": "4",
        "candidate_entry_id": AUTHORIZED_CANDIDATE_ENTRY_ID,
        "official_repository_id": AUTHORIZED_REPOSITORY_ID,
        "immutable_revision_sha": AUTHORIZED_REVISION_SHA,
        "tokenizer_revision_sha": AUTHORIZED_TOKENIZER_REVISION_SHA,
        "fixture_file_relpath": FIXTURE_REL,
        "fixture_file_sha256": fixture_file_sha256,
        "authorised_fixture_count": AUTHORISED_FIXTURE_COUNT,
        "checkpoint_load_evidence_sha256": None,
        "inference_environment_manifest_sha256": None,
        "inference_lockfile_sha256": None,
        "offline_flags": {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
        "local_files_only": True,
        "trust_remote_code": False,
        "decoding_configuration": {
            "backend": BACKEND_ID,
            "load_in_4bit": True,
            "quant_type": "nf4",
            "double_quant": True,
            "compute_dtype": "bfloat16",
            "device": "cuda:0",
            "attention": "eager",
            "context_limit": MANDATORY_CONTEXT_LIMIT,
            "safety_margin_tokens": DEFAULT_SAFETY_MARGIN,
            "do_sample": False,
            "seed": GENERATION_SEED,
            "requested_max_new_tokens": REQUESTED_MAX_NEW_TOKENS,
            "timeout_s": DEFAULT_TIMEOUT_S,
        },
        "authorised_data_boundary_confirmed": True,
        "no_research_data_access": True,
        "no_adapter_attached": True,
        "no_optimiser_step": True,
        "no_model_selection": True,
        "no_network_access": True,
        "no_fallback_download": True,
        "selected_model": None,
        "run_status": "pending",
        "per_fixture_results": [],
        "aggregate_metrics": None,
        "outcome_classification": None,
        "fallback_probe_recommended": None,
        "aggregate_reconciliation": None,
    }


def validate_pre_run_gates(
    *,
    download_evidence: dict[str, Any],
    register: dict[str, Any],
    load_evidence: dict[str, Any],
    local_files_only: bool = True,
    trust_remote_code: bool = False,
    cache_dir: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_download_evidence_for_load(download_evidence))
    errors.extend(validate_register_for_load(register))
    errors.extend(validate_offline_flags(local_files_only=local_files_only, trust_remote_code=trust_remote_code))
    if load_evidence.get("overall_status") != "PASS":
        errors.append("checkpoint load evidence overall_status must be PASS")
    load_errors = validate_checkpoint_load_evidence(
        load_evidence,
        download_evidence=download_evidence,
        register=register,
    )
    errors.extend(load_errors)
    if cache_dir is not None:
        errors.extend(validate_wsl_cache_policy(cache_dir))
    if register.get("selected_model") is not None:
        errors.append("selected_model must remain null")
    entry = next(
        (item for item in register.get("entries", []) if item.get("entry_id") == AUTHORIZED_CANDIDATE_ENTRY_ID),
        None,
    )
    if not isinstance(entry, dict):
        errors.append("candidate entry t12-cand-001 not found")
    elif entry.get("verification_status") != "candidate_evaluated":
        errors.append("candidate must remain candidate_evaluated")
    return errors


def validate_runtime_identity(evidence: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field, expected in (
        ("immutable_revision_sha", AUTHORIZED_REVISION_SHA),
        ("tokenizer_revision_sha", AUTHORIZED_TOKENIZER_REVISION_SHA),
        ("official_repository_id", AUTHORIZED_REPOSITORY_ID),
        ("candidate_entry_id", AUTHORIZED_CANDIDATE_ENTRY_ID),
    ):
        if evidence.get(field) != expected:
            errors.append(f"{field} mismatch")
    decoding = evidence.get("decoding_configuration")
    if isinstance(decoding, dict):
        if decoding.get("backend") != BACKEND_ID:
            errors.append("decoding_configuration.backend mismatch")
        if decoding.get("timeout_s") != DEFAULT_TIMEOUT_S:
            errors.append("decoding_configuration.timeout_s mismatch")
    return errors


def validate_synthetic_evaluation_evidence(
    evidence: dict[str, Any],
    *,
    register: dict[str, Any] | None = None,
    expected_fixture_sha256: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if evidence.get("manifest_schema_version") != "1.0.0":
        errors.append("manifest_schema_version must be 1.0.0")
    if evidence.get("ticket") != "T12":
        errors.append("ticket must be T12")
    if evidence.get("slice") != "4":
        errors.append("slice must be 4")

    errors.extend(validate_runtime_identity(evidence))

    fixture_sha = evidence.get("fixture_file_sha256")
    if not isinstance(fixture_sha, str):
        errors.append("fixture_file_sha256 required")
    elif expected_fixture_sha256 is not None and fixture_sha != expected_fixture_sha256:
        errors.append("fixture_file_sha256 mismatch")

    if evidence.get("local_files_only") is not True:
        errors.append("local_files_only must be true")
    if evidence.get("trust_remote_code") is not False:
        errors.append("trust_remote_code must be false")
    if evidence.get("selected_model") is not None:
        errors.append("selected_model must remain null")
    if evidence.get("no_research_data_access") is not True:
        errors.append("no_research_data_access must be true")
    if evidence.get("no_adapter_attached") is not True:
        errors.append("no_adapter_attached must be true")
    if evidence.get("no_optimiser_step") is not True:
        errors.append("no_optimiser_step must be true")
    if evidence.get("no_model_selection") is not True:
        errors.append("no_model_selection must be true")
    if evidence.get("no_fallback_download") is not True:
        errors.append("no_fallback_download must be true")

    offline = evidence.get("offline_flags")
    if not isinstance(offline, dict):
        errors.append("offline_flags required")
    else:
        for var in REQUIRED_OFFLINE_ENV:
            if offline.get(var) != "1":
                errors.append(f"offline_flags.{var} must be 1")

    per_fixture = evidence.get("per_fixture_results")
    if not isinstance(per_fixture, list):
        errors.append("per_fixture_results must be a list")
        return errors

    seen_ids: set[str] = set()
    for index, item in enumerate(per_fixture):
        prefix = f"per_fixture_results[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        fixture_id = item.get("fixture_id")
        if not isinstance(fixture_id, str):
            errors.append(f"{prefix}.fixture_id required")
            continue
        if fixture_id in seen_ids:
            errors.append(f"duplicate fixture_id in evidence: {fixture_id}")
        seen_ids.add(fixture_id)
        for required in ("raw_output_relpath", "raw_output_sha256"):
            if not isinstance(item.get(required), str):
                errors.append(f"{prefix}.{required} required")
        if item.get("raw_output_nonempty") is False and item.get("generation_status") == "completed":
            errors.append(f"{prefix} completed generation must have non-empty raw output")
        repair_count = item.get("bounded_repair_count")
        if isinstance(repair_count, int) and repair_count > MAX_REPAIR_OPERATIONS:
            errors.append(f"{prefix}.bounded_repair_count exceeds bound")
        gate = item.get("silent_resolution_gate")
        if isinstance(gate, dict) and gate.get("false_silent_resolution_eligibility"):
            if int(item.get("unsupported_commitment_count", 0)) == 0:
                errors.append(f"{prefix} false silent-resolution gate inconsistent")

    if evidence.get("run_status") == "completed":
        expected_ids = {f"syn-{index:03d}" for index in range(1, AUTHORISED_FIXTURE_COUNT + 1)}
        if seen_ids != expected_ids:
            errors.append(f"missing fixture IDs in completed run: {sorted(expected_ids - seen_ids)}")

        aggregate = evidence.get("aggregate_metrics")
        if not isinstance(aggregate, dict):
            errors.append("aggregate_metrics required when run_status is completed")
        else:
            errors.extend(reconcile_aggregate_metrics(per_fixture, aggregate))

        outcome = evidence.get("outcome_classification")
        if outcome not in OUTCOME_VALUES:
            errors.append("outcome_classification invalid")

    if register is not None:
        errors.extend(validate_register_for_load(register))

    _scan_forbidden_identifiers(evidence, "evidence", errors)
    return errors


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp_path.replace(path)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_evaluation_paths(repo_root: Path) -> dict[str, Path]:
    return {
        "repo_root": repo_root.resolve(),
        "fixture_path": (repo_root / FIXTURE_REL).resolve(),
        "evidence_path": (repo_root / EVIDENCE_REL).resolve(),
        "report_path": (repo_root / REPORT_REL).resolve(),
        "raw_output_dir": (repo_root / RAW_OUTPUT_DIR_REL).resolve(),
        "run_log_dir": (repo_root / RUN_LOG_DIR_REL).resolve(),
        "download_evidence": (repo_root / DOWNLOAD_EVIDENCE_REL).resolve(),
        "load_evidence": (repo_root / LOAD_EVIDENCE_REL).resolve(),
        "register": (repo_root / REGISTER_REL).resolve(),
        "inference_manifest": (repo_root / INFERENCE_ENV_REL).resolve(),
    }


def refresh_evidence_hashes(ctx: dict[str, Any]) -> None:
    paths = ctx["paths"]
    evidence = ctx["evidence"]
    evidence["checkpoint_load_evidence_sha256"] = sha256_hex(
        paths["load_evidence"].read_bytes()
    )
    evidence["inference_environment_manifest_sha256"] = sha256_hex(
        paths["inference_manifest"].read_bytes()
    )
    manifest = load_json(paths["inference_manifest"])
    lock_path = paths["repo_root"] / manifest["lockfile_relpath"]
    evidence["inference_lockfile_sha256"] = sha256_hex(lock_path.read_bytes())


def _fixture_result_complete(item: dict[str, Any], *, expected_input_sha: str) -> bool:
    return (
        item.get("fixture_input_sha256") == expected_input_sha
        and item.get("immutable_revision_sha") == AUTHORIZED_REVISION_SHA
        and isinstance(item.get("raw_output_sha256"), str)
        and item.get("generation_status") in {"completed", "timeout", "backend_error", "oom", "empty_output"}
    )


def run_fixtures(
    *,
    repo_root: Path,
    manifest: FixtureManifest,
    evidence: dict[str, Any],
    regenerate: bool = False,
    generate_fn: Callable[[dict[str, Any]], GenerateJsonResult] | None = None,
) -> dict[str, Any]:
    from ambiguity_manager.model.factory import create_model_client

    paths = resolve_evaluation_paths(repo_root)
    paths["raw_output_dir"].mkdir(parents=True, exist_ok=True)

    runtime = build_runtime_spec(environment_id="t12-inference-wsl2")
    client = None if generate_fn is not None else create_model_client(runtime)
    schema = build_prediction_json_schema()

    existing: dict[str, dict[str, Any]] = {
        item["fixture_id"]: item
        for item in evidence.get("per_fixture_results", [])
        if isinstance(item, dict) and isinstance(item.get("fixture_id"), str)
    }

    per_fixture: list[dict[str, Any]] = []
    for fixture in manifest.fixtures:
        fixture_id = fixture["fixture_id"]
        expected_input_sha = manifest.fixture_input_shas[fixture_id]

        if not regenerate:
            prior = existing.get(fixture_id)
            if prior and _fixture_result_complete(prior, expected_input_sha=expected_input_sha):
                per_fixture.append(prior)
                continue

        messages = build_messages_from_fixture(fixture, json_schema=schema)
        request = GenerateJsonRequest(
            messages=messages,
            json_schema=schema,
            seed=GENERATION_SEED,
            temperature=0.0,
            top_p=1.0,
            requested_max_new_tokens=REQUESTED_MAX_NEW_TOKENS,
            timeout_s=DEFAULT_TIMEOUT_S,
            fixture_id=fixture_id,
            run_id=f"t12-synthetic-{fixture_id}",
        )
        if generate_fn is not None:
            result = generate_fn(fixture)
        else:
            assert client is not None
            result = client.generate_json(request)

        raw_path = paths["raw_output_dir"] / f"t12_{fixture_id}.txt"
        if raw_path.exists() and not regenerate:
            existing_raw = raw_path.read_text(encoding="utf-8")
            if existing_raw != result.raw_output:
                raise SyntheticEvaluationError(
                    f"raw output hash mismatch for {fixture_id}; use regenerate to overwrite"
                )
        else:
            raw_path.write_text(result.raw_output, encoding="utf-8")

        raw_relpath = raw_output_relpath(fixture_id)
        raw_digest = sha256_hex(raw_path.read_bytes())
        fixture_result = build_per_fixture_result(
            fixture=fixture,
            result=result,
            raw_output_relpath_value=raw_relpath,
            raw_output_sha256_value=raw_digest,
        )
        per_fixture.append(fixture_result)

    evidence["per_fixture_results"] = per_fixture
    aggregate = compute_aggregate_metrics(per_fixture)
    evidence["aggregate_metrics"] = aggregate
    reconciliation_errors = reconcile_aggregate_metrics(per_fixture, aggregate)
    evidence["aggregate_reconciliation"] = {
        "reconciled": not reconciliation_errors,
        "errors": reconciliation_errors,
    }
    run_complete = len(per_fixture) == AUTHORISED_FIXTURE_COUNT
    evidence["run_status"] = "completed" if run_complete else "partial"
    evidence["outcome_classification"] = classify_outcome(aggregate, run_complete=run_complete)
    evidence["fallback_probe_recommended"] = recommend_fallback_probe(aggregate)
    evidence["completed_at"] = utc_now_iso()
    evidence["post_run_free_vram_mib"] = gpu_free_vram_mib()
    evidence["lingering_probe_processes_detected"] = bool(detect_lingering_probe_processes())
    return evidence


def render_report_markdown(evidence: dict[str, Any]) -> str:
    aggregate = evidence.get("aggregate_metrics") or {}
    lines = [
        "# T12 Slice 4 — Synthetic evaluation report",
        "",
        f"- Ticket: T12",
        f"- Slice: 4",
        f"- Candidate: {evidence.get('candidate_entry_id')}",
        f"- Model: {evidence.get('official_repository_id')}",
        f"- Revision: {evidence.get('immutable_revision_sha')}",
        f"- Fixture file SHA-256: `{evidence.get('fixture_file_sha256')}`",
        f"- Run status: {evidence.get('run_status')}",
        f"- Outcome classification: {evidence.get('outcome_classification')}",
        f"- Fallback probe recommended: {evidence.get('fallback_probe_recommended')}",
        "",
        "## Aggregate metrics",
        "",
        "```json",
        json.dumps(aggregate, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Per-fixture summary",
        "",
        "| Fixture | Generation | Parse | Schema | Route match | Unsupported | Silent gate | Latency ms |",
        "|---|---|---|---|---|---:|---|---:|",
    ]
    for item in evidence.get("per_fixture_results", []):
        route = item.get("route_result") or {}
        gate = item.get("silent_resolution_gate") or {}
        lines.append(
            "| {fixture_id} | {generation_status} | {parser_status} | {schema_validation_status} | "
            "{route_match} | {unsupported} | {silent} | {latency} |".format(
                fixture_id=item.get("fixture_id"),
                generation_status=item.get("generation_status"),
                parser_status=item.get("parser_status"),
                schema_validation_status=item.get("schema_validation_status"),
                route_match=route.get("exact_match"),
                unsupported=item.get("unsupported_commitment_count"),
                silent=gate.get("silent_resolution_eligible"),
                latency=round(float(item.get("latency_ms", 0)), 1),
            )
        )
    lines.extend(
        [
            "",
            "## Governance confirmations",
            "",
            f"- selected_model: {evidence.get('selected_model')}",
            f"- no_model_selection: {evidence.get('no_model_selection')}",
            f"- no_adapter_attached: {evidence.get('no_adapter_attached')}",
            f"- no_optimiser_step: {evidence.get('no_optimiser_step')}",
            f"- no_research_data_access: {evidence.get('no_research_data_access')}",
            f"- no_fallback_download: {evidence.get('no_fallback_download')}",
            "",
        ]
    )
    return "\n".join(lines)
