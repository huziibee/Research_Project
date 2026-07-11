"""Model licence register validation."""

from __future__ import annotations

import re
from typing import Any

REGISTER_SCHEMA_VERSION = "1.1.0"
CUMULATIVE_DOWNLOAD_CAP_BYTES = 30 * 1024 * 1024 * 1024
MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES = 32212254720
CUMULATIVE_DOWNLOAD_CAP_DISPLAY = "30 GiB"
MANDATORY_CONTEXT_LIMIT = 4096
DECIMAL_30_GB_BYTES = 30_000_000_000

PERMISSION_FIELDS = (
    "local_inference_permitted",
    "academic_research_permitted",
    "adapter_training_permitted",
)

CHECKPOINT_FIELDS = ("model_id", "immutable_revision_sha", "tokenizer_revision_sha")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
BRANCH_TAG_ONLY_PATTERN = re.compile(r"^(main|master|HEAD|v[\d.]+)$", re.IGNORECASE)


def _validate_sha(value: Any, path: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, str) or not SHA_PATTERN.match(value):
        errors.append(f"{path} must be a 40-character lowercase hex commit SHA")
    elif BRANCH_TAG_ONLY_PATTERN.match(value):
        errors.append(f"{path} must not be a branch or tag alias alone")
    return errors


def _validate_checkpoint_ref(ref: Any, path: str, *, allow_null_sha: bool = False) -> list[str]:
    errors: list[str] = []
    if not isinstance(ref, dict):
        return [f"{path} must be an object"]
    for field in CHECKPOINT_FIELDS:
        if not ref.get(field) and not (allow_null_sha and field.endswith("_sha")):
            errors.append(f"{path}.{field} is required")
    if allow_null_sha:
        for field in ("immutable_revision_sha", "tokenizer_revision_sha"):
            value = ref.get(field)
            if value is not None:
                errors.extend(_validate_sha(value, f"{path}.{field}"))
    else:
        errors.extend(_validate_sha(ref.get("immutable_revision_sha"), f"{path}.immutable_revision_sha"))
        errors.extend(_validate_sha(ref.get("tokenizer_revision_sha"), f"{path}.tokenizer_revision_sha"))
    return errors


def _validate_entry(entry: Any, index: int) -> list[str]:
    errors: list[str] = []
    prefix = f"entries[{index}]"
    if not isinstance(entry, dict):
        return [f"{prefix} must be an object"]

    entry_id = entry.get("entry_id")
    if not entry_id:
        errors.append(f"{prefix}.entry_id is required")

    status = entry.get("verification_status")
    if status not in {"candidate_evaluated", "selected", "rejected"}:
        errors.append(f"{prefix}.verification_status invalid")

    third_party_quant = entry.get("third_party_quantised_repository") is True
    allow_null_sha = status == "rejected" and third_party_quant

    for field in ("model_id", "licence_identifier"):
        if not entry.get(field):
            errors.append(f"{prefix}.{field} is required")

    for field in ("immutable_revision_sha", "tokenizer_revision_sha"):
        if not entry.get(field) and not allow_null_sha:
            errors.append(f"{prefix}.{field} is required")
        elif entry.get(field):
            errors.extend(_validate_sha(entry.get(field), f"{prefix}.{field}"))

    if not entry.get("licence_evidence_url") and not entry.get("licence_file_relpath"):
        errors.append(f"{prefix} requires licence_evidence_url or licence_file_relpath")

    if status in {"candidate_evaluated", "selected"}:
        for field in (
            "estimated_download_bytes",
            "parameter_count",
            "architecture",
            "context_limit",
            "verification_date",
            "verifier",
        ):
            if entry.get(field) in (None, ""):
                errors.append(f"{prefix}.{field} is required for {status} entries")
        download_bytes = entry.get("estimated_download_bytes")
        if isinstance(download_bytes, int) and download_bytes > CUMULATIVE_DOWNLOAD_CAP_BYTES:
            errors.append(f"{prefix}.estimated_download_bytes exceeds 30 GiB cap")
        context_limit = entry.get("context_limit")
        if isinstance(context_limit, int) and context_limit < MANDATORY_CONTEXT_LIMIT:
            errors.append(
                f"{prefix}.context_limit must be at least {MANDATORY_CONTEXT_LIMIT} for {status} entries"
            )
        for restriction in (
            "redistribution_restrictions",
            "adapter_release_restrictions",
            "acceptable_use_restrictions",
        ):
            if not entry.get(restriction):
                errors.append(f"{prefix}.{restriction} is required for {status} entries")

    for field in PERMISSION_FIELDS:
        value = entry.get(field)
        if status == "selected" and value is not True:
            errors.append(f"{prefix}.{field} must be true for selected entries")
        if status == "selected" and value is None:
            errors.append(f"{prefix}.{field} must not be null for selected entries")

    if entry.get("gated_access") is True and status != "rejected":
        errors.append(f"{prefix}.gated_access must be false or entry rejected during T12")

    if third_party_quant and status != "rejected":
        errors.append(f"{prefix}.third_party_quantised_repository requires rejected status")
    if third_party_quant and entry.get("authoritative_checkpoint") is not False:
        errors.append(f"{prefix}.authoritative_checkpoint must be false for third-party quant repos")

    errors.extend(
        _validate_checkpoint_ref(
            entry.get("inference_checkpoint_ref"),
            f"{prefix}.inference_checkpoint_ref",
            allow_null_sha=allow_null_sha,
        )
    )
    errors.extend(
        _validate_checkpoint_ref(
            entry.get("training_checkpoint_ref"),
            f"{prefix}.training_checkpoint_ref",
            allow_null_sha=allow_null_sha,
        )
    )

    inference_ref = entry.get("inference_checkpoint_ref")
    training_ref = entry.get("training_checkpoint_ref")
    if isinstance(inference_ref, dict) and isinstance(training_ref, dict):
        if inference_ref != training_ref:
            errors.append(f"{prefix} inference_checkpoint_ref must equal training_checkpoint_ref")
        if not allow_null_sha:
            if entry.get("immutable_revision_sha") != inference_ref.get("immutable_revision_sha"):
                errors.append(f"{prefix}.immutable_revision_sha must match inference_checkpoint_ref")
            if entry.get("tokenizer_revision_sha") != inference_ref.get("tokenizer_revision_sha"):
                errors.append(f"{prefix}.tokenizer_revision_sha must match inference_checkpoint_ref")

    if status == "rejected" and not entry.get("rejection_reason"):
        errors.append(f"{prefix}.rejection_reason is required for rejected entries")

    return errors


def validate_model_licence_register(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if data.get("register_schema_version") != REGISTER_SCHEMA_VERSION:
        errors.append(f"register_schema_version must be {REGISTER_SCHEMA_VERSION}")

    entries = data.get("entries")
    if entries is None:
        errors.append("entries is required")
    elif not isinstance(entries, list):
        errors.append("entries must be a list")
    else:
        entry_ids: list[str] = []
        for index, entry in enumerate(entries):
            errors.extend(_validate_entry(entry, index))
            if isinstance(entry, dict) and entry.get("entry_id"):
                entry_ids.append(str(entry["entry_id"]))

    selected_model = data.get("selected_model")
    if selected_model is not None:
        if not isinstance(entries, list):
            errors.append("selected_model requires entries list")
        else:
            selected_entries = [
                entry
                for entry in entries
                if isinstance(entry, dict) and entry.get("entry_id") == selected_model
            ]
            if not selected_entries:
                errors.append("selected_model must reference an existing entry_id")
            else:
                selected_entry = selected_entries[0]
                if selected_entry.get("verification_status") != "selected":
                    errors.append("selected_model entry must have verification_status selected")
                if sum(1 for entry in entries if entry.get("verification_status") == "selected") != 1:
                    errors.append("exactly one selected entry is required when selected_model is set")

    return errors
