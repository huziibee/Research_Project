"""T12 Slice 3A model candidate evidence validation."""

from __future__ import annotations

import re
from typing import Any

EVIDENCE_REL = "configs/model/evidence/historical/t12_model_candidates.json"
REGISTER_REL = "configs/licences/model_licence_register.json"

CUMULATIVE_DOWNLOAD_CAP_BYTES = 30 * 1024 * 1024 * 1024
MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES = 32212254720
CUMULATIVE_DOWNLOAD_CAP_DISPLAY = "30 GiB"
MANDATORY_CONTEXT_LIMIT = 4096
DECIMAL_30_GB_BYTES = 30_000_000_000
DOWNLOAD_SIZE_TOLERANCE_BYTES = 104_857_600
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
BRANCH_TAG_ONLY_PATTERN = re.compile(r"^(main|master|HEAD|v[\d.]+)$", re.IGNORECASE)
_ABSOLUTE_PATH_PATTERN = re.compile(r"^[A-Za-z]:[\\/]|^/home/|^/Users/|^\\\\")
_USERNAME_PATTERN = re.compile(r"\bhuzii\b", re.IGNORECASE)
_MODEL_WEIGHT_EXTENSIONS = frozenset(
    {".safetensors", ".bin", ".gguf", ".pt", ".pth", ".onnx", ".ckpt"}
)
_THIRD_PARTY_QUANT_AUTHORS = frozenset(
    {
        "TheBloke",
        "bartowski",
        "RichardErkhov",
    }
)

_ELIGIBILITY_GATES = (
    "public_ungated",
    "text_only_causal",
    "official_provider",
    "immutable_revision_sha",
    "official_licence",
    "local_inference_permitted",
    "academic_research_permitted",
    "adapter_training_permitted",
    "transformers_supported",
    "peft_compatible",
    "tokenizer_available",
    "no_lvlm_dependency",
    "download_under_cap",
    "quantised_inference_plausible",
    "authoritative_checkpoint",
    "context_limit",
)

_REQUIRED_ALLOWLIST_PATTERNS = (
    "*.safetensors",
    "config.json",
    "generation_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.json",
    "merges.txt",
    "*.model",
    "LICENSE*",
    "README.md",
)

_FORBIDDEN_ALLOWLIST_PATTERNS = (
    "pytorch_model*.bin",
    "tf_model*.h5",
    "flax_model*.msgpack",
    "onnx/**",
    "*.onnx",
    "*.gguf",
    "*.ggml",
    "*-gptq*",
    "*-awq*",
    "original/**",
)


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


def _validate_sha(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not SHA_PATTERN.match(value):
        errors.append(f"{path} must be a 40-character lowercase hex commit SHA")
    elif BRANCH_TAG_ONLY_PATTERN.match(value):
        errors.append(f"{path} must not be a branch or tag alias alone")


def _is_third_party_quant_repo(model_id: str) -> bool:
    if not isinstance(model_id, str):
        return False
    author = model_id.split("/", 1)[0] if "/" in model_id else ""
    if author in _THIRD_PARTY_QUANT_AUTHORS:
        return True
    lowered = model_id.lower()
    return any(marker in lowered for marker in ("-gptq", "-awq", "-gguf", "-bnb-4bit"))


def _validate_eligibility_gates(gates: Any, prefix: str, errors: list[str]) -> None:
    if not isinstance(gates, dict):
        errors.append(f"{prefix}.eligibility_gates must be an object")
        return
    for gate in _ELIGIBILITY_GATES:
        if gate not in gates:
            errors.append(f"{prefix}.eligibility_gates missing {gate}")


def _validate_candidate(
    candidate: Any,
    index: int,
    *,
    register_entry_ids: set[str],
    errors: list[str],
) -> None:
    prefix = f"candidates[{index}]"
    if not isinstance(candidate, dict):
        errors.append(f"{prefix} must be an object")
        return

    status = candidate.get("verification_status")

    register_entry_id = candidate.get("register_entry_id")
    if not register_entry_id:
        errors.append(f"{prefix}.register_entry_id is required")
    elif register_entry_id not in register_entry_ids:
        errors.append(f"{prefix}.register_entry_id must reference licence register entry")

    if candidate.get("revision_alias_only"):
        errors.append(f"{prefix} must not use branch/tag alias as authoritative revision")

    third_party_rejected = status == "rejected" and (
        candidate.get("third_party_quantised_repository") is True
        or candidate.get("authoritative_checkpoint") is False
    )
    if not third_party_rejected:
        _validate_sha(candidate.get("immutable_revision_sha"), f"{prefix}.immutable_revision_sha", errors)
        _validate_sha(candidate.get("tokenizer_revision_sha"), f"{prefix}.tokenizer_revision_sha", errors)
    else:
        for field in ("immutable_revision_sha", "tokenizer_revision_sha"):
            value = candidate.get(field)
            if value is not None:
                _validate_sha(value, f"{prefix}.{field}", errors)

    model_id = candidate.get("model_id")
    if not model_id:
        errors.append(f"{prefix}.model_id is required")

    authoritative = candidate.get("authoritative_checkpoint_ref")
    if not isinstance(authoritative, dict):
        errors.append(f"{prefix}.authoritative_checkpoint_ref is required")
    else:
        if authoritative.get("model_id") != model_id:
            errors.append(f"{prefix}.authoritative_checkpoint_ref.model_id must match model_id")
        if _is_third_party_quant_repo(str(authoritative.get("model_id", ""))):
            if status != "rejected":
                errors.append(f"{prefix}.authoritative_checkpoint_ref must not be a third-party quant repo")

    if model_id and _is_third_party_quant_repo(str(model_id)):
        if candidate.get("verification_status") != "rejected":
            errors.append(f"{prefix} third-party quant repo must be rejected")

    evidence_refs = candidate.get("official_evidence_references")
    if not isinstance(evidence_refs, list) or not evidence_refs:
        errors.append(f"{prefix}.official_evidence_references must be a non-empty list")

    download_bytes = candidate.get("estimated_checkpoint_download_bytes")
    if download_bytes is None:
        if status != "rejected" or register_entry_id:
            errors.append(f"{prefix}.estimated_checkpoint_download_bytes is required")
    elif not isinstance(download_bytes, int) or download_bytes < 0:
        errors.append(f"{prefix}.estimated_checkpoint_download_bytes must be a non-negative integer")
    elif download_bytes > CUMULATIVE_DOWNLOAD_CAP_BYTES:
        errors.append(f"{prefix}.estimated_checkpoint_download_bytes exceeds 30 GiB cap")

    if status == "candidate_evaluated":
        context_limit = candidate.get("context_limit")
        if not isinstance(context_limit, int) or context_limit < MANDATORY_CONTEXT_LIMIT:
            errors.append(
                f"{prefix}.context_limit must be at least {MANDATORY_CONTEXT_LIMIT} for eligible candidates"
            )

    if status not in {"candidate_evaluated", "rejected"}:
        errors.append(f"{prefix}.verification_status invalid for Slice 3A")
    if status == "selected":
        errors.append(f"{prefix}.verification_status must not be selected in Slice 3A")

    if candidate.get("gated_access") is True and status != "rejected":
        errors.append(f"{prefix}.gated_access must be false or entry rejected")

    if status == "candidate_evaluated":
        for field in (
            "local_inference_permitted",
            "academic_research_permitted",
            "adapter_training_permitted",
        ):
            if candidate.get(field) is not True:
                errors.append(f"{prefix}.{field} must be true for eligible candidates")
        gates = candidate.get("eligibility_gates", {})
        if isinstance(gates, dict):
            for gate, passed in gates.items():
                if gate in _ELIGIBILITY_GATES and passed is not True:
                    errors.append(f"{prefix}.eligibility_gates.{gate} must be true for eligible candidates")

    if status == "rejected" and not candidate.get("rejection_reason"):
        errors.append(f"{prefix}.rejection_reason is required for rejected candidates")

    _validate_eligibility_gates(candidate.get("eligibility_gates"), prefix, errors)


def validate_candidate_evidence(
    data: dict[str, Any],
    *,
    register: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []

    if data.get("manifest_schema_version") != "1.0.0":
        errors.append("manifest_schema_version must be 1.0.0")
    if data.get("ticket") != "T12":
        errors.append("ticket must be T12")
    if data.get("slice") != "3A":
        errors.append("slice must be 3A")
    if data.get("no_model_download") is not True:
        errors.append("no_model_download must be true")
    if data.get("no_model_execution") is not True:
        errors.append("no_model_execution must be true")
    if data.get("no_absolute_paths") is not True:
        errors.append("no_absolute_paths must be true")

    if data.get("maximum_cumulative_download_bytes") != MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES:
        errors.append("maximum_cumulative_download_bytes must be 32212254720")
    if data.get("cumulative_download_cap_display") != CUMULATIVE_DOWNLOAD_CAP_DISPLAY:
        errors.append("cumulative_download_cap_display must be 30 GiB")
    if data.get("cumulative_download_cap_bytes") == DECIMAL_30_GB_BYTES:
        errors.append("cumulative_download_cap_bytes must not use decimal 30 GB")

    register_entry_ids: set[str] = set()
    eligible_entry_ids: set[str] = set()
    if register is not None:
        for entry in register.get("entries", []):
            if isinstance(entry, dict) and entry.get("entry_id"):
                register_entry_ids.add(str(entry["entry_id"]))
                if entry.get("verification_status") == "candidate_evaluated":
                    eligible_entry_ids.add(str(entry["entry_id"]))

    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        errors.append("candidates must be a non-empty list")
    else:
        cumulative = 0
        for index, candidate in enumerate(candidates):
            _validate_candidate(
                candidate,
                index,
                register_entry_ids=register_entry_ids,
                errors=errors,
            )
            if isinstance(candidate, dict):
                download = candidate.get("estimated_checkpoint_download_bytes")
                if isinstance(download, int):
                    cumulative = max(cumulative, download)
        cap = data.get("cumulative_download_cap_bytes", CUMULATIVE_DOWNLOAD_CAP_BYTES)
        if cap != MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES:
            errors.append("cumulative_download_cap_bytes must equal 32212254720 bytes (30 GiB)")
        max_download = data.get("max_single_candidate_download_bytes")
        if isinstance(max_download, int) and max_download > MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES:
            errors.append("max_single_candidate_download_bytes exceeds 30 GiB cap")

        evidence_ids = {
            str(candidate.get("register_entry_id"))
            for candidate in candidates
            if isinstance(candidate, dict) and candidate.get("register_entry_id")
        }
        if register is not None and not evidence_ids.issubset(register_entry_ids):
            errors.append("every evaluated candidate must have a licence-register entry")

    primary = data.get("recommended_first_probe_candidate")
    fallback = data.get("recommended_fallback_candidate")
    if not primary:
        errors.append("recommended_first_probe_candidate is required")
    elif register is not None and primary not in eligible_entry_ids:
        errors.append("recommended_first_probe_candidate must reference eligible register entry")
    if not fallback:
        errors.append("recommended_fallback_candidate is required")
    elif primary and fallback == primary:
        errors.append("recommended_fallback_candidate must differ from primary")
    elif register is not None and fallback not in eligible_entry_ids:
        errors.append("recommended_fallback_candidate must reference eligible register entry")

    if "recommended_smaller_fallback_candidate" in data:
        errors.append("recommended_smaller_fallback_candidate must not be set after TinyLlama rejection")

    primary_download = data.get("recommended_first_probe_download_bytes")
    headroom = data.get("remaining_headroom_bytes")
    if primary_download != 3098955668:
        errors.append("recommended_first_probe_download_bytes must be 3098955668")
    if headroom != 29113299052:
        errors.append("remaining_headroom_bytes must be 29113299052")
    if isinstance(primary_download, int) and isinstance(headroom, int):
        if primary_download + headroom != MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES:
            errors.append("headroom arithmetic must equal maximum_cumulative_download_bytes")

    download_plan = data.get("download_plan")
    if not isinstance(download_plan, dict):
        errors.append("download_plan must be an object")
    else:
        if download_plan.get("execute_in_slice") != "3B":
            errors.append("download_plan.execute_in_slice must be 3B")
        if download_plan.get("stop_before_checkpoint_load") is not True:
            errors.append("download_plan.stop_before_checkpoint_load must be true")
        if download_plan.get("maximum_cumulative_download_bytes") != MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES:
            errors.append("download_plan.maximum_cumulative_download_bytes must be 32212254720")
        if download_plan.get("cumulative_download_cap_display") != CUMULATIVE_DOWNLOAD_CAP_DISPLAY:
            errors.append("download_plan.cumulative_download_cap_display must be 30 GiB")
        allowlist = download_plan.get("allowlist")
        if not isinstance(allowlist, dict):
            errors.append("download_plan.allowlist must be an object")
        else:
            include_patterns = allowlist.get("include_patterns")
            exclude_patterns = allowlist.get("exclude_patterns")
            if not isinstance(include_patterns, list) or not isinstance(exclude_patterns, list):
                errors.append("download_plan.allowlist patterns must be lists")
            else:
                for pattern in _REQUIRED_ALLOWLIST_PATTERNS:
                    if pattern not in include_patterns:
                        errors.append(f"download_plan.allowlist missing include pattern {pattern}")
                for pattern in _FORBIDDEN_ALLOWLIST_PATTERNS:
                    if pattern not in exclude_patterns:
                        errors.append(f"download_plan.allowlist missing exclude pattern {pattern}")
        tolerance = download_plan.get("size_tolerance_bytes")
        if tolerance != DOWNLOAD_SIZE_TOLERANCE_BYTES:
            errors.append("download_plan.size_tolerance_bytes must be documented")

    repo_text = str(data)
    for ext in _MODEL_WEIGHT_EXTENSIONS:
        if ext in repo_text and "no_model_weight_files_in_repository" not in data:
            pass

    _scan_forbidden_identifiers(data, "evidence", errors)
    return errors
