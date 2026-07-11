"""Atomic shard output and manifest protocol for T12 cluster execution."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ambiguity_manager.model.cluster._config_loader import deterministic_json_dumps


class AtomicOutputError(ValueError):
    """Raised when atomic shard output validation or publication fails."""


@dataclass(frozen=True)
class AttemptRecord:
    attempt_number: int
    status: str
    start_timestamp: str
    end_timestamp: str
    failure_reasons: tuple[str, ...]
    output_record_count: int
    output_sha256: str
    prior_manifest_sha256: str
    backend_config_hash: str
    backend_identifier: str
    model_repository: str
    model_revision: str
    container_sha256: str
    parsed_output_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_number": self.attempt_number,
            "status": self.status,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "failure_reasons": list(self.failure_reasons),
            "output_record_count": self.output_record_count,
            "output_sha256": self.output_sha256,
            "prior_manifest_sha256": self.prior_manifest_sha256,
            "backend_config_hash": self.backend_config_hash,
            "backend_identifier": self.backend_identifier,
            "model_repository": self.model_repository,
            "model_revision": self.model_revision,
            "container_sha256": self.container_sha256,
            "parsed_output_path": self.parsed_output_path,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AttemptRecord:
        return cls(
            attempt_number=int(payload["attempt_number"]),
            status=str(payload["status"]),
            start_timestamp=str(payload["start_timestamp"]),
            end_timestamp=str(payload["end_timestamp"]),
            failure_reasons=tuple(str(item) for item in payload.get("failure_reasons", [])),
            output_record_count=int(payload["output_record_count"]),
            output_sha256=str(payload["output_sha256"]),
            prior_manifest_sha256=str(payload.get("prior_manifest_sha256", "")),
            backend_config_hash=str(payload["backend_config_hash"]),
            backend_identifier=str(payload["backend_identifier"]),
            model_repository=str(payload["model_repository"]),
            model_revision=str(payload["model_revision"]),
            container_sha256=str(payload["container_sha256"]),
            parsed_output_path=str(payload["parsed_output_path"]),
        )


@dataclass(frozen=True)
class ShardManifest:
    run_id: str
    shard_id: str
    input_plan_hash: str
    input_shard_hash: str
    expected_ids: tuple[str, ...]
    completed_ids: tuple[str, ...]
    failed_ids: tuple[str, ...]
    duplicate_ids: tuple[str, ...]
    output_record_count: int
    output_sha256: str
    raw_output_path: str
    parsed_output_path: str
    status: str
    start_timestamp: str
    end_timestamp: str
    backend_identifier: str
    backend_config_hash: str
    model_repository: str
    model_revision: str
    container_sha256: str
    retry_count: int
    failure_reasons: tuple[str, ...]
    attempt_history: tuple[AttemptRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "shard_id": self.shard_id,
            "input_plan_hash": self.input_plan_hash,
            "input_shard_hash": self.input_shard_hash,
            "expected_ids": list(self.expected_ids),
            "completed_ids": list(self.completed_ids),
            "failed_ids": list(self.failed_ids),
            "duplicate_ids": list(self.duplicate_ids),
            "output_record_count": self.output_record_count,
            "output_sha256": self.output_sha256,
            "raw_output_path": self.raw_output_path,
            "parsed_output_path": self.parsed_output_path,
            "status": self.status,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "backend_identifier": self.backend_identifier,
            "backend_config_hash": self.backend_config_hash,
            "model_repository": self.model_repository,
            "model_revision": self.model_revision,
            "container_sha256": self.container_sha256,
            "retry_count": self.retry_count,
            "failure_reasons": list(self.failure_reasons),
            "attempt_history": [item.to_dict() for item in self.attempt_history],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ShardManifest:
        history_payload = payload.get("attempt_history", [])
        return cls(
            run_id=str(payload["run_id"]),
            shard_id=str(payload["shard_id"]),
            input_plan_hash=str(payload["input_plan_hash"]),
            input_shard_hash=str(payload["input_shard_hash"]),
            expected_ids=tuple(str(item) for item in payload["expected_ids"]),
            completed_ids=tuple(str(item) for item in payload["completed_ids"]),
            failed_ids=tuple(str(item) for item in payload.get("failed_ids", [])),
            duplicate_ids=tuple(str(item) for item in payload.get("duplicate_ids", [])),
            output_record_count=int(payload["output_record_count"]),
            output_sha256=str(payload["output_sha256"]),
            raw_output_path=str(payload["raw_output_path"]),
            parsed_output_path=str(payload["parsed_output_path"]),
            status=str(payload["status"]),
            start_timestamp=str(payload["start_timestamp"]),
            end_timestamp=str(payload["end_timestamp"]),
            backend_identifier=str(payload.get("backend_identifier", "")),
            backend_config_hash=str(payload.get("backend_config_hash", "")),
            model_repository=str(payload.get("model_repository", "")),
            model_revision=str(payload["model_revision"]),
            container_sha256=str(payload["container_sha256"]),
            retry_count=int(payload.get("retry_count", 0)),
            failure_reasons=tuple(str(item) for item in payload.get("failure_reasons", [])),
            attempt_history=tuple(AttemptRecord.from_dict(item) for item in history_payload),
        )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_bytes(
    destination: Path,
    payload: bytes,
    *,
    validator: Callable[[Path], None] | None = None,
    allow_overwrite: bool = False,
) -> None:
    if destination.exists() and not allow_overwrite:
        raise AtomicOutputError(f"destination_exists:{destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=str(destination.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if validator is not None:
            validator(temp_path)
        os.replace(temp_path, destination)
    except Exception:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def atomic_write_text(
    destination: Path,
    text: str,
    *,
    validator: Callable[[Path], None] | None = None,
    allow_overwrite: bool = False,
) -> None:
    atomic_write_bytes(
        destination,
        text.encode("utf-8"),
        validator=validator,
        allow_overwrite=allow_overwrite,
    )


def validate_jsonl_output(path: Path, *, expected_ids: tuple[str, ...] | None = None) -> None:
    if not path.is_file():
        raise AtomicOutputError("output_missing")
    ids: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise AtomicOutputError(f"invalid_json_line:{line_number}") from exc
        if not isinstance(record, dict) or "record_id" not in record:
            raise AtomicOutputError(f"invalid_record_shape:{line_number}")
        ids.append(str(record["record_id"]))
    if expected_ids is not None and tuple(ids) != expected_ids:
        raise AtomicOutputError("output_ids_mismatch")


def _failure_reasons_for_manifest(
    manifest: ShardManifest,
    *,
    failure_reasons: tuple[str, ...],
) -> tuple[str, ...]:
    if failure_reasons:
        return failure_reasons
    if manifest.failure_reasons:
        return manifest.failure_reasons
    if manifest.failed_ids:
        return tuple(f"failed_id:{item}" for item in manifest.failed_ids)
    if manifest.status != "completed":
        return (f"status:{manifest.status}",)
    return ()


def _attempt_record_from_manifest(
    manifest: ShardManifest,
    *,
    attempt_number: int,
    prior_manifest_sha256: str,
    failure_reasons: tuple[str, ...] = (),
) -> AttemptRecord:
    return AttemptRecord(
        attempt_number=attempt_number,
        status=manifest.status,
        start_timestamp=manifest.start_timestamp,
        end_timestamp=manifest.end_timestamp,
        failure_reasons=_failure_reasons_for_manifest(manifest, failure_reasons=failure_reasons),
        output_record_count=manifest.output_record_count,
        output_sha256=manifest.output_sha256,
        prior_manifest_sha256=prior_manifest_sha256,
        backend_config_hash=manifest.backend_config_hash,
        backend_identifier=manifest.backend_identifier,
        model_repository=manifest.model_repository,
        model_revision=manifest.model_revision,
        container_sha256=manifest.container_sha256,
        parsed_output_path=manifest.parsed_output_path,
    )


def write_shard_outputs(
    *,
    output_dir: Path,
    run_id: str,
    shard_id: str,
    input_plan_hash: str,
    input_shard_hash: str,
    expected_ids: tuple[str, ...],
    output_records: list[dict[str, Any]],
    status: str,
    start_timestamp: str,
    end_timestamp: str,
    backend_identifier: str,
    backend_config_hash: str,
    model_repository: str,
    model_revision: str,
    container_sha256: str,
    failed_ids: tuple[str, ...] = (),
    duplicate_ids: tuple[str, ...] = (),
    failure_reasons: tuple[str, ...] = (),
    allow_overwrite: bool = False,
) -> ShardManifest:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / f"{shard_id}.raw.jsonl"
    parsed_path = output_dir / f"{shard_id}.parsed.jsonl"
    manifest_path = output_dir / f"{shard_id}.manifest.json"
    attempt_history: tuple[AttemptRecord, ...] = ()

    if manifest_path.exists():
        prior_text = manifest_path.read_text(encoding="utf-8")
        existing = ShardManifest.from_dict(json.loads(prior_text))
        if existing.status == "completed":
            raise AtomicOutputError("completed_shard_exists")
        if allow_overwrite:
            prior_manifest_sha256 = sha256_text(prior_text)
            prior_entry = _attempt_record_from_manifest(
                existing,
                attempt_number=len(existing.attempt_history) + 1,
                prior_manifest_sha256=prior_manifest_sha256,
                failure_reasons=_failure_reasons_for_manifest(existing, failure_reasons=()),
            )
            attempt_history = existing.attempt_history + (prior_entry,)
        elif existing.run_id != run_id or existing.input_plan_hash != input_plan_hash:
            raise AtomicOutputError("conflicting_run_or_plan")

    lines = []
    for record_id in expected_ids:
        match = next((item for item in output_records if str(item.get("record_id")) == record_id), None)
        if match is None:
            continue
        lines.append(json.dumps(match, sort_keys=True, separators=(",", ":")))
    output_text = "\n".join(lines) + ("\n" if lines else "")
    output_sha = sha256_text(output_text)

    def _validate_output(path: Path) -> None:
        validate_jsonl_output(path, expected_ids=expected_ids)

    atomic_write_text(parsed_path, output_text, validator=_validate_output, allow_overwrite=allow_overwrite)
    atomic_write_text(raw_path, output_text, validator=_validate_output, allow_overwrite=allow_overwrite)

    manifest = ShardManifest(
        run_id=run_id,
        shard_id=shard_id,
        input_plan_hash=input_plan_hash,
        input_shard_hash=input_shard_hash,
        expected_ids=expected_ids,
        completed_ids=tuple(item for item in expected_ids if item not in failed_ids),
        failed_ids=failed_ids,
        duplicate_ids=duplicate_ids,
        output_record_count=len(lines),
        output_sha256=output_sha,
        raw_output_path=str(raw_path),
        parsed_output_path=str(parsed_path),
        status=status,
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
        backend_identifier=backend_identifier,
        backend_config_hash=backend_config_hash,
        model_repository=model_repository,
        model_revision=model_revision,
        container_sha256=container_sha256,
        retry_count=len(attempt_history),
        failure_reasons=failure_reasons if status != "completed" else (),
        attempt_history=attempt_history,
    )

    manifest_payload = deterministic_json_dumps(manifest.to_dict()) + "\n"
    atomic_write_text(
        manifest_path,
        manifest_payload,
        validator=lambda path: _validate_manifest_matches_output(path, parsed_path, manifest),
        allow_overwrite=allow_overwrite,
    )
    return manifest


def _validate_manifest_matches_output(
    manifest_path: Path, parsed_path: Path, expected: ShardManifest
) -> None:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    loaded = ShardManifest.from_dict(payload)
    if loaded.output_sha256 != sha256_file(parsed_path):
        raise AtomicOutputError("manifest_output_hash_mismatch")


def is_temporary_output(path: Path) -> bool:
    name = path.name
    return ".tmp" in name or name.startswith(".")
