"""Bounded, hash-locked full-data T28 training utilities.

The module keeps the data contract independent from optional GPU libraries so
that every refusal is testable before a model is loaded.  Tokenisation is
intentionally lazy; callers consume the train manifest one record at a time.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

from ambiguity_manager.model.t28 import T28Error, assert_train_only


class T28TrainerError(T28Error):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def build_emitted_target_manifest_entry(row: Mapping[str, Any], *, task: str, prompt: str, target: str, included: bool, reason: str | None = None) -> dict[str, Any]:
    return {
        "record_id": str(row.get("id", row.get("record_id", ""))),
        "group_id": row.get("group_key", row.get("group_id")),
        "split": row.get("split"),
        "task": task,
        "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest(),
        "target_hash": hashlib.sha256(target.encode()).hexdigest(),
        "source": row.get("source_dataset", row.get("source")),
        "eligibility_reason": reason or ("included" if included else "excluded"),
        "included": included,
    }


def _required_identity(identity: Mapping[str, Any]) -> None:
    required = ("canonical_sha256", "permitted_view_sha256", "train_manifest_sha256", "dev_manifest_sha256", "schema_registry_sha256", "run_id")
    missing = [key for key in required if not identity.get(key)]
    if missing:
        raise T28TrainerError("missing_identity:" + ",".join(missing))


def validate_full_data_contract(evidence: Mapping[str, Any]) -> None:
    if int(evidence.get("record_count", 0)) == 192 or evidence.get("smoke_subset"):
        raise T28TrainerError("smoke_subset_refused")
    if evidence.get("source_holdout_loaded", 0) or evidence.get("protected_records_loaded", 0):
        raise T28TrainerError("protected_or_holdout_data_refused")
    if int(evidence.get("record_count", 0)) != 11294:
        raise T28TrainerError("train_record_count_mismatch")
    if int(evidence.get("target_count", 0)) != 13058:
        raise T28TrainerError("target_count_mismatch")
    _required_identity(evidence)
    if evidence.get("base_revision") in (None, "", "latest", "main"):
        raise T28TrainerError("unpinned_base_revision")


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise T28TrainerError(f"invalid_jsonl:{path}:{number}") from exc


@dataclass(frozen=True)
class TrainExample:
    record_id: str
    task: str
    prompt: str
    target: str


class FullDataLoader:
    """Lazy source_train-only loader backed by the immutable manifest."""

    def __init__(self, view_path: Path, manifest_path: Path):
        self.view_path, self.manifest_path = view_path, manifest_path

    def __iter__(self) -> Iterator[TrainExample]:
        manifest = list(iter_jsonl(self.manifest_path))
        assert_train_only(manifest)
        allowed = {str(row["record_id"]): row for row in manifest}
        seen: set[str] = set()
        for row in iter_jsonl(self.view_path):
            if row.get("split") != "source_train":
                continue
            record_id = str(row.get("id", row.get("record_id")))
            if record_id not in allowed:
                continue
            seen.add(record_id)
            record = row.get("record", row)
            prompt = str(record.get("prompt", record.get("command", "")))
            target = json.dumps(record.get("target", {}), sort_keys=True, ensure_ascii=False)
            for task in allowed[record_id].get("task_ids", [allowed[record_id].get("task", "")]):
                if task:
                    yield TrainExample(record_id, str(task), prompt, target)
        missing = set(allowed) - seen
        if missing:
            raise T28TrainerError(f"manifest_records_missing_from_view:{len(missing)}")


class T28RunOrchestrator:
    def __init__(self, matrix_path: Path, output_root: Path):
        self.matrix_path, self.output_root = matrix_path, output_root
        self._matrix_hash = sha256_file(matrix_path)
        self.matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        if not self.matrix.get("frozen"):
            raise T28TrainerError("run_matrix_not_frozen")

    def verify_immutable(self) -> None:
        if sha256_file(self.matrix_path) != self._matrix_hash:
            raise T28TrainerError("run_matrix_changed")

    def run_ids(self) -> list[str]:
        self.verify_immutable()
        return [str(item["run_id"]) for item in self.matrix.get("runs", [])]

    def prepare_run_directory(self, run_id: str) -> Path:
        self.verify_immutable()
        path = self.output_root / run_id
        if path.exists() and any(path.iterdir()):
            raise T28TrainerError(f"output_directory_not_empty:{path}")
        path.mkdir(parents=True, exist_ok=True)
        (path / "run_matrix_sha256").write_text(self._matrix_hash + "\n", encoding="ascii", newline="\n")
        return path


def package_manifest(package_dir: Path, identity: Mapping[str, Any]) -> dict[str, Any]:
    files = {}
    for path in sorted(p for p in package_dir.rglob("*") if p.is_file() and p.name != "package_manifest.json"):
        files[str(path.relative_to(package_dir)).replace(os.sep, "/")] = sha256_file(path)
    return {"identity": dict(identity), "files": files, "immutable": True}


def verify_package_checksums(package_dir: Path, manifest: Mapping[str, Any]) -> bool:
    expected = dict(manifest.get("files", {}))
    actual = {str(p.relative_to(package_dir)).replace(os.sep, "/"): sha256_file(p) for p in package_dir.rglob("*") if p.is_file() and p.name != "package_manifest.json"}
    return actual == expected


def safe_copy_package(source: Path, destination: Path, identity: Mapping[str, Any]) -> dict[str, Any]:
    if destination.exists():
        raise T28TrainerError("package_destination_exists")
    shutil.copytree(source, destination)
    manifest = package_manifest(destination, identity)
    (destination / "package_manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest
