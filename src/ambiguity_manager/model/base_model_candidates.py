"""Base-model candidate registry loader and validator."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ambiguity_manager.annotation.canonical import sha256_json
from ambiguity_manager.model.errors import ModelClientError
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.systems.model_identities import checkpoint_identity

REGISTRY_REL = "configs/model/base_model_candidates_v1.json"
REGISTRY_VERSION = "1.0.0"
ALLOWLISTED_CANDIDATE_IDS = frozenset({"qwen3_8b", "phi4_14b", "mistral_small_24b_2501"})
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_REQUIRED_REGISTRY_FIELDS = (
    "registry_version",
    "status",
    "development_only",
    "valid_for_official_use",
    "canonical_hash",
    "selected_base_model",
    "selected_adapter",
    "selected_model_strategy",
    "candidates",
    "screened_out",
    "development_bakeoff_thresholds",
    "official_source_references",
)

_REQUIRED_CANDIDATE_FIELDS = (
    "candidate_id",
    "repository",
    "revision",
    "tokenizer_repository",
    "tokenizer_revision",
    "parameter_count_display",
    "architecture_class",
    "architecture_type",
    "context_length",
    "licence_identifier",
    "licence_evidence_url",
    "gated",
    "private",
    "selection_rationale",
    "official_source_references",
)

_REQUIRED_THRESHOLDS = (
    "transport_accepted_records_min",
    "transport_records_required",
    "max_invalid_final_schema",
    "max_unrecorded_attempts",
    "max_unsupported_commitments_on_accepted",
    "max_unsafe_silent_commitments",
    "unconstrained_fallback_permitted",
)


class BaseModelRegistryError(ModelClientError):
    """Raised when the base-model candidate registry is invalid."""


@dataclass(frozen=True)
class BaseModelCandidate:
    candidate_id: str
    repository: str
    revision: str
    tokenizer_repository: str
    tokenizer_revision: str
    parameter_count_display: str
    architecture_class: str
    architecture_type: str
    context_length: int
    licence_identifier: str
    licence_evidence_url: str
    gated: bool
    private: bool
    gated_access_authorised: bool
    selection_rationale: str
    official_source_references: tuple[str, ...]
    register_entry_id: str | None = None
    parameter_count: int | None = None
    estimated_snapshot_bytes: int | None = None
    estimated_bf16_vram_bytes: int | None = None
    estimated_qlora_4bit_vram_bytes: int | None = None
    vllm_compatibility_evidence: str | None = None
    structured_output_compatibility_evidence: str | None = None
    qlora_compatibility_evidence: str | None = None
    known_caveats: tuple[str, ...] = ()

    @property
    def checkpoint_identity(self) -> str:
        return checkpoint_identity(self.repository, self.revision)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "repository": self.repository,
            "revision": self.revision,
            "tokenizer_repository": self.tokenizer_repository,
            "tokenizer_revision": self.tokenizer_revision,
            "checkpoint_identity": self.checkpoint_identity,
            "parameter_count_display": self.parameter_count_display,
            "architecture_class": self.architecture_class,
            "architecture_type": self.architecture_type,
            "context_length": self.context_length,
            "licence_identifier": self.licence_identifier,
            "licence_evidence_url": self.licence_evidence_url,
            "gated": self.gated,
            "private": self.private,
            "gated_access_authorised": self.gated_access_authorised,
            "selection_rationale": self.selection_rationale,
            "official_source_references": list(self.official_source_references),
            "register_entry_id": self.register_entry_id,
            "parameter_count": self.parameter_count,
            "estimated_snapshot_bytes": self.estimated_snapshot_bytes,
            "estimated_bf16_vram_bytes": self.estimated_bf16_vram_bytes,
            "estimated_qlora_4bit_vram_bytes": self.estimated_qlora_4bit_vram_bytes,
            "vllm_compatibility_evidence": self.vllm_compatibility_evidence,
            "structured_output_compatibility_evidence": self.structured_output_compatibility_evidence,
            "qlora_compatibility_evidence": self.qlora_compatibility_evidence,
            "known_caveats": list(self.known_caveats),
        }


@dataclass(frozen=True)
class BaseModelCandidateRegistry:
    registry_version: str
    status: str
    development_only: bool
    valid_for_official_use: bool
    canonical_hash: str
    selected_base_model: str | None
    selected_adapter: str | None
    selected_model_strategy: str | None
    candidates: tuple[BaseModelCandidate, ...]
    screened_out: tuple[dict[str, Any], ...]
    development_bakeoff_thresholds: dict[str, Any]
    official_source_references: dict[str, Any]

    @property
    def candidate_ids(self) -> frozenset[str]:
        return frozenset(candidate.candidate_id for candidate in self.candidates)

    def get_candidate(self, candidate_id: str) -> BaseModelCandidate:
        for candidate in self.candidates:
            if candidate.candidate_id == candidate_id:
                return candidate
        raise BaseModelRegistryError(f"unknown candidate_id: {candidate_id!r}")

    def assert_null_selection(self) -> None:
        if self.selected_base_model is not None:
            raise BaseModelRegistryError("selected_base_model must remain null until bake-off pass")
        if self.selected_adapter is not None:
            raise BaseModelRegistryError("selected_adapter must remain null")
        if self.selected_model_strategy is not None:
            raise BaseModelRegistryError("selected_model_strategy must remain null")


def _default_path() -> Path:
    return ProjectPaths.from_repo_root().configs / "model" / "base_model_candidates_v1.json"


def registry_canonical_hash(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "canonical_hash"}
    return sha256_json(body)


def _validate_sha(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not SHA_PATTERN.match(value):
        errors.append(f"{path} must be a 40-character lowercase hex commit SHA")


def _candidate_from_dict(raw: dict[str, Any]) -> BaseModelCandidate:
    known_caveats = raw.get("known_caveats") or []
    official_refs = raw.get("official_source_references") or []
    return BaseModelCandidate(
        candidate_id=str(raw["candidate_id"]),
        repository=str(raw["repository"]),
        revision=str(raw["revision"]),
        tokenizer_repository=str(raw["tokenizer_repository"]),
        tokenizer_revision=str(raw["tokenizer_revision"]),
        parameter_count_display=str(raw["parameter_count_display"]),
        architecture_class=str(raw["architecture_class"]),
        architecture_type=str(raw["architecture_type"]),
        context_length=int(raw["context_length"]),
        licence_identifier=str(raw["licence_identifier"]),
        licence_evidence_url=str(raw["licence_evidence_url"]),
        gated=bool(raw["gated"]),
        private=bool(raw["private"]),
        gated_access_authorised=bool(raw.get("gated_access_authorised", False)),
        selection_rationale=str(raw["selection_rationale"]),
        official_source_references=tuple(str(item) for item in official_refs),
        register_entry_id=raw.get("register_entry_id"),
        parameter_count=raw.get("parameter_count"),
        estimated_snapshot_bytes=raw.get("estimated_snapshot_bytes"),
        estimated_bf16_vram_bytes=raw.get("estimated_bf16_vram_bytes"),
        estimated_qlora_4bit_vram_bytes=raw.get("estimated_qlora_4bit_vram_bytes"),
        vllm_compatibility_evidence=raw.get("vllm_compatibility_evidence"),
        structured_output_compatibility_evidence=raw.get("structured_output_compatibility_evidence"),
        qlora_compatibility_evidence=raw.get("qlora_compatibility_evidence"),
        known_caveats=tuple(str(item) for item in known_caveats),
    )


def validate_registry_payload(payload: dict[str, Any], *, verify_hash: bool = True) -> list[str]:
    errors: list[str] = []

    for field in _REQUIRED_REGISTRY_FIELDS:
        if field not in payload:
            errors.append(f"missing required field: {field}")

    if payload.get("registry_version") != REGISTRY_VERSION:
        errors.append(f"registry_version must be {REGISTRY_VERSION!r}")
    if payload.get("status") != "development_shortlist":
        errors.append("status must be development_shortlist")
    if payload.get("development_only") is not True:
        errors.append("development_only must be true")
    if payload.get("valid_for_official_use") is not False:
        errors.append("valid_for_official_use must be false")

    for field in ("selected_base_model", "selected_adapter", "selected_model_strategy"):
        if payload.get(field) is not None:
            errors.append(f"{field} must be null before bake-off pass")

    thresholds = payload.get("development_bakeoff_thresholds")
    if not isinstance(thresholds, dict):
        errors.append("development_bakeoff_thresholds must be an object")
    else:
        for key in _REQUIRED_THRESHOLDS:
            if key not in thresholds:
                errors.append(f"development_bakeoff_thresholds missing {key}")
        if thresholds.get("transport_accepted_records_min") != 4:
            errors.append("transport_accepted_records_min must be 4")
        if thresholds.get("transport_records_required") != 4:
            errors.append("transport_records_required must be 4")
        if thresholds.get("max_invalid_final_schema") != 0:
            errors.append("max_invalid_final_schema must be 0")
        if thresholds.get("max_unrecorded_attempts") != 0:
            errors.append("max_unrecorded_attempts must be 0")
        if thresholds.get("max_unsupported_commitments_on_accepted") != 0:
            errors.append("max_unsupported_commitments_on_accepted must be 0")
        if thresholds.get("max_unsafe_silent_commitments") != 0:
            errors.append("max_unsafe_silent_commitments must be 0")
        if thresholds.get("unconstrained_fallback_permitted") is not False:
            errors.append("unconstrained_fallback_permitted must be false")

    runtime = (payload.get("official_source_references") or {}).get("pinned_runtime")
    if not isinstance(runtime, dict):
        errors.append("official_source_references.pinned_runtime must be an object")
    else:
        if runtime.get("container_filename") != "vllm-openai-v0.20.1.sif":
            errors.append("pinned_runtime.container_filename mismatch")
        sha = runtime.get("container_sha256")
        if not isinstance(sha, str) or not SHA256_PATTERN.match(sha):
            errors.append("pinned_runtime.container_sha256 must be a 64-char hex SHA-256")
        elif sha != "d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1":
            errors.append("pinned_runtime.container_sha256 mismatch")

    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        errors.append("candidates must be a non-empty list")
    else:
        seen_ids: set[str] = set()
        for index, raw in enumerate(candidates):
            prefix = f"candidates[{index}]"
            if not isinstance(raw, dict):
                errors.append(f"{prefix} must be an object")
                continue
            for field in _REQUIRED_CANDIDATE_FIELDS:
                if field not in raw:
                    errors.append(f"{prefix} missing {field}")
            candidate_id = str(raw.get("candidate_id", ""))
            if candidate_id not in ALLOWLISTED_CANDIDATE_IDS:
                errors.append(f"{prefix}.candidate_id {candidate_id!r} is not allowlisted")
            if candidate_id in seen_ids:
                errors.append(f"duplicate candidate_id: {candidate_id}")
            seen_ids.add(candidate_id)
            _validate_sha(raw.get("revision"), f"{prefix}.revision", errors)
            _validate_sha(raw.get("tokenizer_revision"), f"{prefix}.tokenizer_revision", errors)
            if not raw.get("licence_evidence_url"):
                errors.append(f"{prefix}.licence_evidence_url is required")
            refs = raw.get("official_source_references")
            if not isinstance(refs, list) or len(refs) < 2:
                errors.append(f"{prefix}.official_source_references must include model card and config.json URLs")
            gated = raw.get("gated") is True
            private = raw.get("private") is True
            authorised = raw.get("gated_access_authorised") is True
            if (gated or private) and not authorised:
                errors.append(f"{prefix} gated/private candidate rejected unless gated_access_authorised is true")

        if seen_ids != ALLOWLISTED_CANDIDATE_IDS:
            errors.append("candidates must include exactly the allowlisted candidate IDs")

    screened_out = payload.get("screened_out")
    if not isinstance(screened_out, list) or not screened_out:
        errors.append("screened_out must be a non-empty list")
    else:
        for index, entry in enumerate(screened_out):
            if not isinstance(entry, dict):
                errors.append(f"screened_out[{index}] must be an object")
            elif not entry.get("rejection_reason"):
                errors.append(f"screened_out[{index}] missing rejection_reason")

    if verify_hash:
        stored = payload.get("canonical_hash")
        if not isinstance(stored, str) or not stored:
            errors.append("canonical_hash must be a non-empty string")
        else:
            recomputed = registry_canonical_hash(payload)
            if stored != recomputed:
                errors.append("canonical_hash mismatch")

    return errors


def load_base_model_candidate_registry(path: Path | None = None, *, verify_hash: bool = True) -> BaseModelCandidateRegistry:
    resolved = path or _default_path()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BaseModelRegistryError("registry must be a JSON object")
    errors = validate_registry_payload(payload, verify_hash=verify_hash)
    if errors:
        raise BaseModelRegistryError("invalid base-model candidate registry:\n- " + "\n- ".join(errors))

    candidates = tuple(_candidate_from_dict(item) for item in payload["candidates"])
    registry = BaseModelCandidateRegistry(
        registry_version=str(payload["registry_version"]),
        status=str(payload["status"]),
        development_only=bool(payload["development_only"]),
        valid_for_official_use=bool(payload["valid_for_official_use"]),
        canonical_hash=str(payload["canonical_hash"]),
        selected_base_model=payload.get("selected_base_model"),
        selected_adapter=payload.get("selected_adapter"),
        selected_model_strategy=payload.get("selected_model_strategy"),
        candidates=candidates,
        screened_out=tuple(dict(item) for item in payload["screened_out"]),
        development_bakeoff_thresholds=dict(payload["development_bakeoff_thresholds"]),
        official_source_references=dict(payload["official_source_references"]),
    )
    registry.assert_null_selection()
    return registry


def get_candidate_by_id(
    candidate_id: str,
    *,
    registry: BaseModelCandidateRegistry | None = None,
    path: Path | None = None,
) -> BaseModelCandidate:
    resolved = registry or load_base_model_candidate_registry(path)
    return resolved.get_candidate(candidate_id)
