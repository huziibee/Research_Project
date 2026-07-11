"""Resume decisions and deterministic shard merge for T12 cluster execution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from ambiguity_manager.model.cluster._config_loader import deterministic_json_dumps
from ambiguity_manager.model.cluster.atomic_outputs import (
    AtomicOutputError,
    ShardManifest,
    atomic_write_text,
    sha256_file,
    sha256_text,
)


class ResumeDecisionError(ValueError):
    """Raised when resume identity validation fails."""


class MergeValidationError(ValueError):
    """Raised when shard merge validation fails."""


class ShardRunDecision(StrEnum):
    SKIP_EXACT_COMPLETED = "skip_exact_completed"
    RUN_NEW = "run_new"
    RETRY_FAILED = "retry_failed"
    RETRY_INCOMPLETE = "retry_incomplete"
    BLOCK_COMPLETED_CONFLICT = "block_completed_conflict"
    BLOCK_CORRUPTED_COMPLETION = "block_corrupted_completion"
    BLOCK_IDENTITY_MISMATCH = "block_identity_mismatch"


_BACKEND_START_DECISIONS = frozenset(
    {
        ShardRunDecision.RUN_NEW,
        ShardRunDecision.RETRY_FAILED,
        ShardRunDecision.RETRY_INCOMPLETE,
    }
)

_OVERWRITE_DECISIONS = frozenset(
    {
        ShardRunDecision.RETRY_FAILED,
        ShardRunDecision.RETRY_INCOMPLETE,
    }
)

_COMPLETED_IDENTITY_FIELDS = (
    "run_id",
    "shard_id",
    "input_plan_hash",
    "input_shard_hash",
    "expected_record_ids",
    "output_record_count",
    "output_sha256",
    "backend_identifier",
    "backend_config_hash",
    "model_repository",
    "model_revision",
    "container_sha256",
)

_RETRY_IDENTITY_FIELDS = (
    "run_id",
    "shard_id",
    "input_plan_hash",
    "input_shard_hash",
    "expected_record_ids",
    "backend_identifier",
    "backend_config_hash",
    "model_repository",
    "model_revision",
    "container_sha256",
)

_REQUIRED_MANIFEST_IDENTITY_FIELDS = (
    "backend_identifier",
    "backend_config_hash",
    "model_repository",
)


@dataclass(frozen=True)
class ResumeIdentity:
    run_id: str
    shard_id: str
    input_plan_hash: str
    input_shard_hash: str
    expected_record_ids: tuple[str, ...]
    output_record_count: int
    output_sha256: str
    backend_identifier: str
    backend_config_hash: str
    model_repository: str
    model_revision: str
    container_sha256: str


@dataclass(frozen=True)
class ResumeDecision:
    decision: ShardRunDecision
    reason: str

    @property
    def skip(self) -> bool:
        return self.decision == ShardRunDecision.SKIP_EXACT_COMPLETED

    @property
    def starts_backend(self) -> bool:
        return self.decision in _BACKEND_START_DECISIONS

    @property
    def allow_overwrite(self) -> bool:
        return self.decision in _OVERWRITE_DECISIONS

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "skip": self.skip,
            "reason": self.reason,
        }


def _manifest_identity_value(manifest: ShardManifest, field: str) -> Any:
    if field == "expected_record_ids":
        return manifest.expected_ids
    return getattr(manifest, field)


def _missing_manifest_identity(
    manifest: ShardManifest,
    *,
    for_completed: bool,
) -> ResumeDecision | None:
    for field in _REQUIRED_MANIFEST_IDENTITY_FIELDS:
        value = getattr(manifest, field, "")
        if not value:
            return ResumeDecision(
                decision=ShardRunDecision.BLOCK_CORRUPTED_COMPLETION
                if for_completed
                else ShardRunDecision.BLOCK_IDENTITY_MISMATCH,
                reason=(
                    f"corrupted_completion:missing_{field}"
                    if for_completed
                    else f"identity_mismatch:missing_{field}"
                ),
            )
    return None


def _identity_mismatch(
    manifest: ShardManifest,
    *,
    identity: ResumeIdentity,
    fields: tuple[str, ...],
    prefix: str,
) -> ResumeDecision | None:
    for field in fields:
        observed = _manifest_identity_value(manifest, field)
        expected = getattr(identity, field)
        if observed != expected:
            return ResumeDecision(
                decision=ShardRunDecision.BLOCK_COMPLETED_CONFLICT
                if prefix == "completed_conflict"
                else ShardRunDecision.BLOCK_IDENTITY_MISMATCH,
                reason=f"{prefix}:{field}",
            )
    return None


def evaluate_resume(
    manifest: ShardManifest,
    *,
    identity: ResumeIdentity,
    parsed_output_path: Path,
) -> ResumeDecision:
    if manifest.status == "completed":
        missing = _missing_manifest_identity(manifest, for_completed=True)
        if missing is not None:
            return missing

        conflict = _identity_mismatch(
            manifest,
            identity=identity,
            fields=_COMPLETED_IDENTITY_FIELDS,
            prefix="completed_conflict",
        )
        if conflict is not None:
            return conflict

        if not parsed_output_path.is_file():
            return ResumeDecision(
                decision=ShardRunDecision.BLOCK_CORRUPTED_COMPLETION,
                reason="corrupted_completion:parsed_output_missing",
            )

        observed_hash = sha256_file(parsed_output_path)
        if observed_hash != manifest.output_sha256:
            return ResumeDecision(
                decision=ShardRunDecision.BLOCK_CORRUPTED_COMPLETION,
                reason="corrupted_completion:output_file_sha256",
            )
        if observed_hash != identity.output_sha256:
            return ResumeDecision(
                decision=ShardRunDecision.BLOCK_CORRUPTED_COMPLETION,
                reason="corrupted_completion:output_sha256",
            )

        return ResumeDecision(
            decision=ShardRunDecision.SKIP_EXACT_COMPLETED,
            reason="exact_completed_shard",
        )

    missing = _missing_manifest_identity(manifest, for_completed=False)
    if missing is not None:
        return missing

    mismatch = _identity_mismatch(
        manifest,
        identity=identity,
        fields=_RETRY_IDENTITY_FIELDS,
        prefix="identity_mismatch",
    )
    if mismatch is not None:
        return mismatch

    if manifest.status == "failed":
        return ResumeDecision(decision=ShardRunDecision.RETRY_FAILED, reason="retry_failed_shard")

    return ResumeDecision(decision=ShardRunDecision.RETRY_INCOMPLETE, reason="retry_incomplete_shard")


@dataclass(frozen=True)
class MergeResult:
    status: str
    merged_sha256: str
    record_count: int
    input_shard_hashes: tuple[str, ...]
    output_path: str
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "merged_sha256": self.merged_sha256,
            "record_count": self.record_count,
            "input_shard_hashes": list(self.input_shard_hashes),
            "output_path": self.output_path,
            "rejection_reasons": list(self.rejection_reasons),
        }


def load_manifest(path: Path) -> ShardManifest:
    return ShardManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def merge_completed_shards(
    *,
    shard_manifests: list[ShardManifest],
    parsed_output_paths: list[Path],
    plan_record_order: tuple[str, ...],
    output_path: Path,
    run_id: str,
    backend_config_hash: str,
    model_revision: str,
    container_sha256: str,
    allow_overwrite: bool = False,
) -> MergeResult:
    rejections: list[str] = []
    if len(shard_manifests) != len(parsed_output_paths):
        rejections.append("manifest_output_path_count_mismatch")
        return MergeResult("fail", "", 0, (), str(output_path), tuple(rejections))

    run_ids = {manifest.run_id for manifest in shard_manifests}
    if len(run_ids) != 1 or run_id not in run_ids:
        rejections.append("mixed_run_ids")

    for manifest in shard_manifests:
        if manifest.status != "completed":
            rejections.append(f"shard_not_completed:{manifest.shard_id}")
        if manifest.model_revision != model_revision:
            rejections.append(f"model_revision_mismatch:{manifest.shard_id}")
        if manifest.container_sha256 != container_sha256:
            rejections.append(f"container_sha_mismatch:{manifest.shard_id}")

    merged_records: dict[str, dict[str, Any]] = {}
    shard_hashes: list[str] = []
    for manifest, parsed_path in zip(shard_manifests, parsed_output_paths, strict=True):
        shard_hashes.append(manifest.input_shard_hash)
        if sha256_file(parsed_path) != manifest.output_sha256:
            rejections.append(f"output_hash_mismatch:{manifest.shard_id}")
        for line in parsed_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            record = json.loads(stripped)
            record_id = str(record["record_id"])
            if record_id in merged_records:
                rejections.append(f"duplicate_record_id:{record_id}")
            merged_records[record_id] = record

    expected_ids = set(plan_record_order)
    observed_ids = set(merged_records)
    for missing in sorted(expected_ids - observed_ids):
        rejections.append(f"missing_record_id:{missing}")
    for unexpected in sorted(observed_ids - expected_ids):
        rejections.append(f"unexpected_record_id:{unexpected}")

    if rejections:
        return MergeResult("fail", "", len(merged_records), tuple(shard_hashes), str(output_path), tuple(rejections))

    ordered_lines = []
    for record_id in plan_record_order:
        ordered_lines.append(
            json.dumps(merged_records[record_id], sort_keys=True, separators=(",", ":"))
        )
    merged_text = "\n".join(ordered_lines) + "\n"
    merged_sha = sha256_text(merged_text)

    def _validate(path: Path) -> None:
        if sha256_file(path) != merged_sha:
            raise AtomicOutputError("merged_hash_mismatch")

    atomic_write_text(output_path, merged_text, validator=_validate, allow_overwrite=allow_overwrite)
    return MergeResult(
        status="pass",
        merged_sha256=merged_sha,
        record_count=len(plan_record_order),
        input_shard_hashes=tuple(shard_hashes),
        output_path=str(output_path),
        rejection_reasons=(),
    )


def merge_result_canonical_json(result: MergeResult) -> str:
    return deterministic_json_dumps(result.to_dict())
