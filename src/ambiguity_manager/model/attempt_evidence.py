"""Immutable attempt evidence ledger for T12 Stage D1C1 generation pipeline."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ambiguity_manager.governance.hashing import canonical_json_bytes


class AttemptKind(StrEnum):
    INITIAL = "initial"
    REGENERATION = "regeneration"


class AttemptDisposition(StrEnum):
    ACCEPTED = "accepted"
    REPAIRABLE_REJECTED = "repairable_rejected"
    NON_RETRYABLE_REJECTED = "non_retryable_rejected"
    SKIPPED_PRE_GENERATION = "skipped_pre_generation"


@dataclass(frozen=True)
class AttemptEvidenceEntry:
    caller_request_id: str
    attempt_index: int
    attempt_kind: str
    prompt_message_hash: str | None
    rendered_prompt_hash: str | None
    repair_prompt_hash: str | None
    response_mode_identity: str | None
    response_mode_status: str | None
    structured_decode_contract_hash: str | None
    semantic_schema_hash: str | None
    backend_identifier: str | None
    backend_configuration_hash: str | None
    model_repository: str | None
    model_revision: str | None
    container_sha: str | None
    raw_generated_text: str | None
    generation_status: str | None
    generation_error_type: str | None
    generation_error_message: str | None
    engine_request_id: str | None
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    json_extraction_status: str | None
    local_repair_operations: tuple[str, ...] = ()
    extracted_json_text: str | None = None
    json_parse_status: str | None = None
    semantic_schema_validation_status: str | None = None
    semantic_schema_validation_errors: tuple[str, ...] = ()
    canonical_assembly_status: str | None = None
    canonical_assembly_errors: tuple[str, ...] = ()
    unsupported_commitment_count: int | None = None
    unsupported_commitment_details: tuple[str, ...] = ()
    structural_validity_status: str | None = None
    semantic_correctness_status: str | None = None
    integrity_context_hash: str | None = None
    final_attempt_disposition: str | None = None
    failure_categories: tuple[str, ...] = ()
    failure_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "caller_request_id": self.caller_request_id,
            "attempt_index": self.attempt_index,
            "attempt_kind": self.attempt_kind,
            "prompt_message_hash": self.prompt_message_hash,
            "rendered_prompt_hash": self.rendered_prompt_hash,
            "repair_prompt_hash": self.repair_prompt_hash,
            "response_mode_identity": self.response_mode_identity,
            "response_mode_status": self.response_mode_status,
            "structured_decode_contract_hash": self.structured_decode_contract_hash,
            "semantic_schema_hash": self.semantic_schema_hash,
            "backend_identifier": self.backend_identifier,
            "backend_configuration_hash": self.backend_configuration_hash,
            "model_repository": self.model_repository,
            "model_revision": self.model_revision,
            "container_sha": self.container_sha,
            "raw_generated_text": self.raw_generated_text,
            "generation_status": self.generation_status,
            "generation_error_type": self.generation_error_type,
            "generation_error_message": self.generation_error_message,
            "engine_request_id": self.engine_request_id,
            "finish_reason": self.finish_reason,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "json_extraction_status": self.json_extraction_status,
            "local_repair_operations": list(self.local_repair_operations),
            "extracted_json_text": self.extracted_json_text,
            "json_parse_status": self.json_parse_status,
            "semantic_schema_validation_status": self.semantic_schema_validation_status,
            "semantic_schema_validation_errors": list(self.semantic_schema_validation_errors),
            "canonical_assembly_status": self.canonical_assembly_status,
            "canonical_assembly_errors": list(self.canonical_assembly_errors),
            "unsupported_commitment_count": self.unsupported_commitment_count,
            "unsupported_commitment_details": list(self.unsupported_commitment_details),
            "structural_validity_status": self.structural_validity_status,
            "semantic_correctness_status": self.semantic_correctness_status,
            "integrity_context_hash": self.integrity_context_hash,
            "final_attempt_disposition": self.final_attempt_disposition,
            "failure_categories": list(self.failure_categories),
            "failure_reasons": list(self.failure_reasons),
        }


@dataclass
class AttemptEvidenceLedger:
    entries: list[AttemptEvidenceEntry] = field(default_factory=list)

    def append(self, entry: AttemptEvidenceEntry) -> None:
        self.entries.append(entry)

    def to_dict(self) -> dict[str, Any]:
        return {"entries": [entry.to_dict() for entry in self.entries]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=2)


def attempt_evidence_json_bytes(ledger: AttemptEvidenceLedger) -> bytes:
    return canonical_json_bytes(ledger.to_dict())


def defensive_copy_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        return {}
    return copy.deepcopy(metadata)
