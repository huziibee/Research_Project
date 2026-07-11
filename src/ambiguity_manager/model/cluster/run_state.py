"""Resume decisions and deterministic shard merge for T12 cluster execution."""

from __future__ import annotations

import json
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ResumeIdentity:
    run_id: str
    shard_id: str
    input_plan_hash: str
    input_shard_hash: str
    expected_record_ids: tuple[str, ...]
    output_record_count: int
    output_sha256: str
    model_repository: str
    model_revision: str
    container_sha256: str
    backend_config_hash: str


@dataclass(frozen=True)
class ResumeDecision:
    skip: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"skip": self.skip, "reason": self.reason}


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


def evaluate_resume(
    manifest: ShardManifest,
    *,
    identity: ResumeIdentity,
    parsed_output_path: Path,
) -> ResumeDecision:
    if manifest.status != "completed":
        return ResumeDecision(skip=False, reason="shard_not_completed")

    checks = (
        ("run_id", manifest.run_id, identity.run_id),
        ("shard_id", manifest.shard_id, identity.shard_id),
        ("input_plan_hash", manifest.input_plan_hash, identity.input_plan_hash),
        ("input_shard_hash", manifest.input_shard_hash, identity.input_shard_hash),
        ("expected_record_ids", manifest.expected_ids, identity.expected_record_ids),
        ("output_record_count", manifest.output_record_count, identity.output_record_count),
        ("output_sha256", manifest.output_sha256, identity.output_sha256),
        ("model_revision", manifest.model_revision, identity.model_revision),
        ("container_sha256", manifest.container_sha256, identity.container_sha256),
    )
    for field, observed, expected in checks:
        if observed != expected:
            return ResumeDecision(skip=False, reason=f"mismatch:{field}")

    if not parsed_output_path.is_file():
        return ResumeDecision(skip=False, reason="parsed_output_missing")

    observed_hash = sha256_file(parsed_output_path)
    if observed_hash != identity.output_sha256:
        return ResumeDecision(skip=False, reason="mismatch:output_file_sha256")

    return ResumeDecision(skip=True, reason="exact_completed_shard")


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
