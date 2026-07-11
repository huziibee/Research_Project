"""Model licence register validation."""

from __future__ import annotations

from typing import Any

REGISTER_SCHEMA_VERSION = "1.1.0"

PERMISSION_FIELDS = (
    "local_inference_permitted",
    "academic_research_permitted",
    "adapter_training_permitted",
)

CHECKPOINT_FIELDS = ("model_id", "immutable_revision_sha", "tokenizer_revision_sha")


def _validate_checkpoint_ref(ref: Any, path: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(ref, dict):
        return [f"{path} must be an object"]
    for field in CHECKPOINT_FIELDS:
        if not ref.get(field):
            errors.append(f"{path}.{field} is required")
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

    for field in (
        "model_id",
        "immutable_revision_sha",
        "tokenizer_revision_sha",
        "licence_identifier",
    ):
        if not entry.get(field):
            errors.append(f"{prefix}.{field} is required")

    if not entry.get("licence_evidence_url") and not entry.get("licence_file_relpath"):
        errors.append(f"{prefix} requires licence_evidence_url or licence_file_relpath")

    for field in PERMISSION_FIELDS:
        value = entry.get(field)
        if status == "selected" and value is not True:
            errors.append(f"{prefix}.{field} must be true for selected entries")
        if status == "selected" and value is None:
            errors.append(f"{prefix}.{field} must not be null for selected entries")

    if entry.get("gated_access") is True and status != "rejected":
        errors.append(f"{prefix}.gated_access must be false or entry rejected during T12")

    errors.extend(_validate_checkpoint_ref(entry.get("inference_checkpoint_ref"), f"{prefix}.inference_checkpoint_ref"))
    errors.extend(_validate_checkpoint_ref(entry.get("training_checkpoint_ref"), f"{prefix}.training_checkpoint_ref"))

    inference_ref = entry.get("inference_checkpoint_ref")
    training_ref = entry.get("training_checkpoint_ref")
    if isinstance(inference_ref, dict) and isinstance(training_ref, dict):
        if inference_ref != training_ref:
            errors.append(f"{prefix} inference_checkpoint_ref must equal training_checkpoint_ref")
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
