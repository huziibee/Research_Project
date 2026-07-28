"""Machine-enforced T28 train/dev, selection, and packaging contracts.

This module is deliberately independent of the GPU trainer.  It is used by
the local preflight and by the cluster runner so a run cannot silently cross
the T15 split boundary or replace a frozen plan.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from ambiguity_manager.governance.t28_r2 import training_allowed

BASE_MODEL = "Qwen/Qwen3-8B"
BASE_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
TRAIN_SPLIT = "source_train"
DEV_SPLIT = "source_dev"
FORBIDDEN_SPLITS = {"source_holdout", "manual_protected_challenge_set", "protected_test"}


class T28Error(RuntimeError):
    """A mandatory T28 contract was violated."""


def assert_dataset_training_permissions(register_path: Path, dataset_ids: Iterable[str]) -> None:
    """Stop T28 training unless the separate institutional internal-use gate passes."""
    register = json.loads(Path(register_path).read_text(encoding="utf-8"))
    entries = {entry["dataset_id"]: entry for entry in register.get("entries", [])}
    requested = tuple(dataset_ids)
    if set(requested).issubset({"ambik", "indirect_requests", "codraw_icr_v2", "vague", "clara"}):
        allowed, errors = training_allowed(register, repo_root=Path(register_path).resolve().parents[2])
        if allowed and set(requested) == {"ambik", "indirect_requests", "codraw_icr_v2", "vague", "clara"}:
            return
        if register.get("internal_academic_research_use_gate", {}).get("decision") in {"approved", "approved_with_conditions"}:
            raise T28Error("dataset_permission_gate_blocked:" + ",".join(errors))
    blocked = []
    for dataset_id in requested:
        entry = entries.get(dataset_id)
        if not entry or entry.get("verification_status") != "verified":
            blocked.append(dataset_id)
            continue
        if entry.get("training_permission") not in {"permitted", "permitted_with_attribution", "permitted_noncommercial_only", "permitted_research_only"}:
            blocked.append(dataset_id)
        if entry.get("development_evaluation_permission") not in {"permitted", "permitted_with_attribution", "permitted_noncommercial_only", "permitted_research_only"}:
            blocked.append(dataset_id)
        if entry.get("dependency_status") == "unresolved":
            blocked.append(dataset_id)
    if blocked:
        raise T28Error("dataset_permission_gate_blocked:" + ",".join(sorted(set(blocked))))


def _rows(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return list(rows)


def _assert_common(rows: list[Mapping[str, Any]], expected: str, label: str) -> None:
    for row in rows:
        split = str(row.get("split", row.get("original_split", "")))
        if split in FORBIDDEN_SPLITS or row.get("protected_data") is True:
            raise T28Error(f"{label}_protected_or_forbidden:{row.get('id', row.get('record_id', '?'))}")
        if split != expected:
            raise T28Error(f"{label}_wrong_split:{split}")


def assert_train_only(rows: Iterable[Mapping[str, Any]]) -> None:
    _assert_common(_rows(rows), TRAIN_SPLIT, "train")


def assert_dev_only(rows: Iterable[Mapping[str, Any]]) -> None:
    _assert_common(_rows(rows), DEV_SPLIT, "dev")


def assert_group_disjoint(train_rows: Iterable[Mapping[str, Any]], dev_rows: Iterable[Mapping[str, Any]]) -> None:
    train = {str(r.get("group_id", r.get("group_key", ""))) for r in train_rows}
    dev = {str(r.get("group_id", r.get("group_key", ""))) for r in dev_rows}
    overlap = train & dev
    if overlap:
        raise T28Error(f"train_dev_group_overlap:{','.join(sorted(overlap))}")


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def freeze_plan(path: Path, plan: Mapping[str, Any]) -> Path:
    """Write a plan once; a second write is allowed only byte-for-byte identically."""
    path = Path(path)
    payload = dict(plan)
    encoded = _canonical(payload)
    if path.exists():
        if path.read_bytes() != encoded:
            raise T28Error(f"frozen_plan_immutable:{path}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return path


def _step_number(name: str) -> int:
    match = re.search(r"(?:step|checkpoint)[-_]?(\d+)", name)
    return int(match.group(1)) if match else 10**12


def choose_checkpoint(candidates: Iterable[Mapping[str, Any]]) -> Mapping[str, Any]:
    eligible = [c for c in candidates if c.get("eligible") is True]
    if not eligible:
        raise T28Error("no_valid_supervised_checkpoint")
    # Frozen tie-break: primary metric, schema validity, safety margin, then
    # earliest checkpoint.  Lower risk/repair counts are safer tie-breaks.
    return sorted(
        eligible,
        key=lambda c: (
            -float(c.get("primary", float("-inf"))),
            -float(c.get("schema_validity", 0.0)),
            -float(c.get("safety_margin", 0.0)),
            int(c.get("repair_count", 0)),
            _step_number(str(c.get("checkpoint", ""))),
            str(c.get("checkpoint", "")),
        ),
    )[0]


def require_same_adapter(full_adapter: str, blind_adapter: str) -> None:
    if not full_adapter or not blind_adapter or "no_adapter" in {full_adapter, blind_adapter}:
        raise T28Error("proposed_manager_no_adapter_forbidden")
    if full_adapter != blind_adapter:
        raise T28Error("proposed_manager_adapter_mismatch")


def package_manifest(package_dir: Path, identity: Mapping[str, Any]) -> dict[str, Any]:
    package_dir = Path(package_dir)
    files: dict[str, str] = {}
    for path in sorted(p for p in package_dir.rglob("*") if p.is_file() and p.name != "package_manifest.json"):
        rel = path.relative_to(package_dir).as_posix()
        files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"package_version": "t28-adapter-package-v1", "identity": dict(identity), "files": files}


def verify_package(package_dir: Path, manifest: Mapping[str, Any]) -> None:
    package_dir = Path(package_dir)
    actual = package_manifest(package_dir, manifest.get("identity", {}))["files"]
    if actual != dict(manifest.get("files", {})):
        raise T28Error("adapter_package_checksum_mismatch")
