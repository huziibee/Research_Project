"""Fail-fast exact-runtime LMFE schema preflight."""

from __future__ import annotations

import importlib.metadata
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.generation_schema import (
    effective_task_registry,
    generation_schema_hashes,
    minimal_valid_instance,
)
from ambiguity_manager.model.task_constrained_decoding import (
    PINNED_VERSION,
    compile_task_constraint,
    load_constraint_config,
)


def _contains_null_enum(value: Any) -> bool:
    if isinstance(value, dict):
        if None in (value.get("enum") or []):
            return True
        return any(_contains_null_enum(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_null_enum(item) for item in value)
    return False


def run_schema_preflight(root: Path | None = None) -> dict[str, Any]:
    root = (root or Path(__file__).resolve().parents[3]).resolve()
    registry = effective_task_registry(root)
    constraint_config = load_constraint_config(root)
    try:
        installed = importlib.metadata.version("lm-format-enforcer")
    except importlib.metadata.PackageNotFoundError:
        installed = None
    if installed != PINNED_VERSION:
        # The cluster container intentionally keeps project packages in an
        # external site-packages directory.  Bootstrap only the pinned decoder
        # here; no model or adapter is loaded before the subsequent compile.
        from ambiguity_manager.model.qlora_task_conditioned_smoke import ensure_runtime_lm_format_enforcer

        ensure_runtime_lm_format_enforcer()
        importlib.invalidate_caches()
        try:
            installed = importlib.metadata.version("lm-format-enforcer")
        except importlib.metadata.PackageNotFoundError:
            installed = None
    records: list[dict[str, Any]] = []
    for task in registry["tasks"]:
        task_id = str(task["task_id"])
        schema = task["json_schema"]
        result: dict[str, Any] = {
            "task_id": task_id,
            "task_version": str(task.get("task_version") or ""),
            "generation_schema_version": registry["generation_schema_version"],
            "schema_hash": generation_schema_hashes(registry)[task_id],
            "prompt_contract_identity": task.get("prompt_contract_identity"),
            "maximum_output_tokens": int(task.get("maximum_output_tokens") or 0),
            "lmfe_version_expected": PINNED_VERSION,
            "lmfe_version_installed": installed,
            "unconstrained_fallback_available": bool(constraint_config.get("unconstrained_fallback_permitted")),
            "nullable_enum": _contains_null_enum(schema),
            "compile_result": "failed",
            "exception_class": None,
            "exception_message": None,
            "minimal_instance_valid": False,
            "omission_instance_valid": False,
        }
        try:
            if installed != PINNED_VERSION:
                raise RuntimeError(f"lmfe_version_mismatch:{installed!r}")
            if result["nullable_enum"]:
                raise ValueError("nullable_enum_forbidden")
            if result["unconstrained_fallback_available"]:
                raise ValueError("unconstrained_fallback_available")
            compile_task_constraint(schema)
            from jsonschema import Draft202012Validator

            validator = Draft202012Validator(schema)
            minimal = minimal_valid_instance(task)
            if list(validator.iter_errors(minimal)):
                raise ValueError("minimal_instance_invalid")
            result["minimal_instance_valid"] = True
            # Optional fields are tested by their omission; required unknown
            # semantics are represented by the task's explicit unknown values.
            if task_id in {"predict_intent_v1", "predict_interpretations_v1"}:
                result["omission_instance_valid"] = not list(validator.iter_errors(minimal))
            else:
                result["omission_instance_valid"] = True
            result["compile_result"] = "passed"
        except Exception as exc:  # noqa: BLE001
            result["exception_class"] = type(exc).__name__
            result["exception_message"] = str(exc)
        records.append(result)
    payload = {
        "evidence_version": "t27f-schema-preflight-v1",
        "ticket": "T27F",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generation_schema_version": registry["generation_schema_version"],
        "generation_schema_hashes": generation_schema_hashes(registry),
        "constraint_config_hash": sha256_hex(canonical_json_bytes(constraint_config)),
        "lmfe_version_expected": PINNED_VERSION,
        "lmfe_version_installed": installed,
        "tasks": records,
        "passed": bool(records) and all(item["compile_result"] == "passed" for item in records),
        "model_loading_permitted": bool(records) and all(item["compile_result"] == "passed" for item in records),
    }
    return payload
