"""T28-R1 recovery and guarded materialisation of the frozen T15 join.

This module is CPU-only. It joins by frozen record ID and never reads any
protected role. The canonical weak pool is treated as an existing source
artifact; this code does not regenerate labels or alter the canonical pool.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex

PERMITTED_SPLITS = {"source_train", "source_dev"}
PROTECTED_SPLITS = {"source_holdout", "protected_test", "manual_protected_challenge_set"}
FORBIDDEN_DATASETS = {"teach", "teach_tatc", "manual_compound", "safe_agent_bench"}
REQUIRED_RECORD_FIELDS = ("id", "source_dataset", "source_id", "command", "source_license", "mapping_version")


class T28R1JoinError(RuntimeError):
    """Raised when the frozen join cannot be proven safe and complete."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise T28R1JoinError(f"blank_jsonl_line:{path}:{line_no}")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise T28R1JoinError(f"invalid_json:{path}:{line_no}") from exc
        if not isinstance(row, dict):
            raise T28R1JoinError(f"json_object_required:{path}:{line_no}")
        rows.append(row)
    return rows


def _by_unique_id(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for row in rows:
        rid = str(row.get("id") or "")
        if not rid:
            raise T28R1JoinError(f"missing_id:{label}")
        if rid in result:
            duplicates.append(rid)
        result[rid] = row
    if duplicates:
        raise T28R1JoinError(f"duplicate_ids:{label}:{sorted(set(duplicates))[:10]}")
    return result


def _content_hash(record: dict[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(record))


def _group_matches(record: dict[str, Any], manifest_row: dict[str, Any]) -> bool:
    group_key = str(manifest_row.get("group_key") or "")
    group_id = record.get("group_id")
    if group_id is None:
        return not group_key.startswith("group:")
    return group_key == f"group:{group_id}" or group_key == str(group_id)


def validate_join(canonical_path: Path, manifest_path: Path) -> dict[str, Any]:
    """Validate the full canonical pool against the frozen T15 manifest."""
    canonical = _read_jsonl(canonical_path)
    manifest = _read_jsonl(manifest_path)
    canonical_by_id = _by_unique_id(canonical, "canonical")
    manifest_by_id = _by_unique_id(manifest, "t15_manifest")
    expected = [r for r in manifest if r.get("split") in PERMITTED_SPLITS and r.get("pool") == "primary"]
    expected_ids = {str(r["id"]) for r in expected}
    recovered_ids = set(canonical_by_id)
    missing = sorted(expected_ids - recovered_ids)
    unexpected = sorted(recovered_ids - set(manifest_by_id))
    protected_recovered = sorted(
        rid for rid, row in manifest_by_id.items()
        if row.get("split") in PROTECTED_SPLITS and rid in recovered_ids
    )
    if missing or unexpected:
        raise T28R1JoinError(f"join_id_failure:missing={missing[:10]}:unexpected={unexpected[:10]}")
    for rid in sorted(expected_ids):
        record = canonical_by_id[rid]
        row = manifest_by_id[rid]
        missing_fields = [name for name in REQUIRED_RECORD_FIELDS if record.get(name) in (None, "")]
        if missing_fields:
            raise T28R1JoinError(f"required_source_content_missing:{rid}:{missing_fields}")
        if record.get("source_dataset") != row.get("source_dataset") or record.get("source_id") != row.get("source_id"):
            raise T28R1JoinError(f"source_identity_mismatch:{rid}")
        if not _group_matches(record, row):
            raise T28R1JoinError(f"group_id_mismatch:{rid}")
        if row.get("source_dataset") in FORBIDDEN_DATASETS:
            raise T28R1JoinError(f"forbidden_dataset:{rid}:{row.get('source_dataset')}")
        if not isinstance(row.get("eligibility"), dict):
            raise T28R1JoinError(f"eligibility_missing:{rid}")
    train = [r for r in expected if r["split"] == "source_train"]
    dev = [r for r in expected if r["split"] == "source_dev"]
    train_groups = {str(r["group_key"]) for r in train}
    dev_groups = {str(r["group_key"]) for r in dev}
    if train_groups & dev_groups:
        raise T28R1JoinError(f"train_dev_group_overlap:{sorted(train_groups & dev_groups)[:10]}")
    return {
        "canonical_count": len(canonical),
        "expected_permitted_count": len(expected),
        "train_count": len(train),
        "dev_count": len(dev),
        "missing_ids": missing,
        "duplicate_ids": [],
        "unexpected_ids": unexpected,
        "protected_ids_rejected": sorted(
            rid for rid, row in manifest_by_id.items() if row.get("split") in PROTECTED_SPLITS
        ),
        "train_dev_group_overlap": [],
        "content_hashes": {rid: _content_hash(canonical_by_id[rid]) for rid in sorted(expected_ids)},
    }


def build_permitted_view(canonical_path: Path, manifest_path: Path, output_path: Path) -> dict[str, Any]:
    """Materialise only primary source_train/source_dev records with frozen metadata."""
    validation = validate_join(canonical_path, manifest_path)
    canonical_by_id = _by_unique_id(_read_jsonl(canonical_path), "canonical")
    manifest = _read_jsonl(manifest_path)
    rows: list[dict[str, Any]] = []
    for frozen in manifest:
        if frozen.get("pool") != "primary" or frozen.get("split") not in PERMITTED_SPLITS:
            continue
        record = canonical_by_id[str(frozen["id"])]
        rows.append({
            "id": str(frozen["id"]),
            "group_key": frozen["group_key"],
            "source_dataset": frozen["source_dataset"],
            "source_id": frozen["source_id"],
            "split": frozen["split"],
            "eligibility": frozen["eligibility"],
            "content_hash": _content_hash(record),
            "record": record,
        })
    rows.sort(key=lambda row: str(row["id"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(canonical_json_bytes(row).decode("utf-8") + "\n" for row in rows), encoding="utf-8"
    )
    return {**validation, "rows": rows, "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest()}
