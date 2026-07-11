"""Immutable T12 cluster model and container identities."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

IMMUTABLE_SELECTION_REL = "configs/model/immutable_selection.json"

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MODEL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")

_REQUIRED_FIELDS = (
    "schema_version",
    "candidate_entry_id",
    "candidate_status",
    "model_repository",
    "model_revision",
    "tokenizer_repository",
    "tokenizer_revision",
    "licence",
    "gated",
    "private",
    "container_filename",
    "container_sha256",
    "container_size_bytes",
    "authoritative_runtime",
    "selected_model_register_must_remain_null_until_stage",
)

_EXPECTED = {
    "schema_version": "1.0.0",
    "candidate_entry_id": "t12-cand-qwen3-8b",
    "candidate_status": "provisionally_selected_for_cluster_validation",
    "model_repository": "Qwen/Qwen3-8B",
    "model_revision": "b968826d9c46dd6066d109eabc6255188de91218",
    "tokenizer_repository": "Qwen/Qwen3-8B",
    "tokenizer_revision": "b968826d9c46dd6066d109eabc6255188de91218",
    "licence": "apache-2.0",
    "gated": False,
    "private": False,
    "container_filename": "vllm-openai-v0.20.1.sif",
    "container_sha256": "d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1",
    "container_size_bytes": 7657443328,
    "authoritative_runtime": "wits_slurm_cluster",
    "selected_model_register_must_remain_null_until_stage": "I",
}


@dataclass(frozen=True)
class ImmutableSelection:
    schema_version: str
    candidate_entry_id: str
    candidate_status: str
    model_repository: str
    model_revision: str
    tokenizer_repository: str
    tokenizer_revision: str
    licence: str
    gated: bool
    private: bool
    container_filename: str
    container_sha256: str
    container_size_bytes: int
    authoritative_runtime: str
    selected_model_register_must_remain_null_until_stage: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> ImmutableSelection:
        errors = validate_immutable_selection(data)
        if errors:
            raise ValueError("; ".join(errors))
        return cls(
            schema_version=str(data["schema_version"]),
            candidate_entry_id=str(data["candidate_entry_id"]),
            candidate_status=str(data["candidate_status"]),
            model_repository=str(data["model_repository"]),
            model_revision=str(data["model_revision"]),
            tokenizer_repository=str(data["tokenizer_repository"]),
            tokenizer_revision=str(data["tokenizer_revision"]),
            licence=str(data["licence"]),
            gated=bool(data["gated"]),
            private=bool(data["private"]),
            container_filename=str(data["container_filename"]),
            container_sha256=str(data["container_sha256"]),
            container_size_bytes=int(data["container_size_bytes"]),
            authoritative_runtime=str(data["authoritative_runtime"]),
            selected_model_register_must_remain_null_until_stage=str(
                data["selected_model_register_must_remain_null_until_stage"]
            ),
        )


def validate_immutable_selection(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in _REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"immutable_selection.{field} is required")
    if errors:
        return errors

    for field, expected in _EXPECTED.items():
        if data.get(field) != expected:
            errors.append(f"immutable_selection.{field} must equal canonical value")

    if not isinstance(data["container_size_bytes"], int):
        errors.append("immutable_selection.container_size_bytes must be an integer")

    if not _SHA256_PATTERN.match(str(data["container_sha256"])):
        errors.append("immutable_selection.container_sha256 must be a 64-character lowercase hex SHA-256")
    for field in ("model_revision", "tokenizer_revision"):
        if not _MODEL_SHA_PATTERN.match(str(data[field])):
            errors.append(f"immutable_selection.{field} must be a 40-character lowercase hex commit SHA")

    return errors


def load_immutable_selection(repo_root: Path | None = None) -> ImmutableSelection:
    root = repo_root or Path.cwd()
    path = root / IMMUTABLE_SELECTION_REL
    data = json.loads(path.read_text(encoding="utf-8"))
    return ImmutableSelection.from_mapping(data)
