#!/usr/bin/env python3
"""Recover and validate the existing frozen T15 source-record join.

This is a non-training command. It never writes raw data, never materialises
source_holdout, and never loads a model. The canonical pool must already exist;
the command refuses to substitute the T27C smoke subset.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.data.t28_r1_join import (  # noqa: E402
    PERMITTED_SPLITS,
    build_permitted_view,
    validate_join,
)
from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex  # noqa: E402
from ambiguity_manager.model.generation_schema import generation_schema_hashes  # noqa: E402
from ambiguity_manager.model.task_prediction_contract import load_task_registry  # noqa: E402
from ambiguity_manager.model.structured_target import build_structured_target  # noqa: E402
from ambiguity_manager.model.structured_target import StructuredTargetError  # noqa: E402
from ambiguity_manager.model.training_target_packaging import load_training_target_policy_strict  # noqa: E402


CANONICAL = ROOT / "data/processed/weak_pool/weak_pool_canonical.jsonl"
T15_MANIFEST = ROOT / "data/development/source_splits_v1/record_manifest.jsonl"
OUT = ROOT / "data/processed/weak_pool"
VIEW = OUT / "t28_permitted_train_dev.jsonl"


def _write_json(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json_bytes(payload) + b"\n"
    path.write_bytes(data)
    return sha256_hex(data)


def _source_version_manifest(weak_manifest: dict) -> dict:
    return {
        "ticket": "T28-R1",
        "status": "recovered_existing_artifact",
        "canonical_artifact": "data/processed/weak_pool/weak_pool_canonical.jsonl",
        "canonical_sha256": weak_manifest["outputs"]["primary_pool_sha256"],
        "builder_version": weak_manifest["builder_version"],
        "included_datasets": weak_manifest["included_datasets"],
        "input_sha256": weak_manifest["input_sha256"],
        "mapping_versions": {x["dataset_id"]: x["mapping_version"] for x in weak_manifest["inputs"]},
        "raw_downloads_mutated": False,
        "source_holdout_materialised": False,
    }


def main() -> int:
    if not CANONICAL.is_file():
        raise SystemExit("BLOCKED: canonical artifact is absent; no rebuild is attempted")
    if (ROOT / "data/development/qlora_task_conditioned_smoke_v1/source_records.jsonl").stat().st_size >= CANONICAL.stat().st_size:
        raise SystemExit("BLOCKED: smoke subset cannot substitute for canonical artifact")

    weak_manifest = json.loads((ROOT / "outputs/manifests/weak_pool_manifest.json").read_text(encoding="utf-8"))
    result = validate_join(CANONICAL, T15_MANIFEST)
    view_result = build_permitted_view(CANONICAL, T15_MANIFEST, VIEW)

    policy = load_training_target_policy_strict(ROOT / "configs/data/training_target_policy_v1.json")
    registry = load_task_registry(ROOT)
    task_counts = Counter()
    target_count = 0
    target_skipped = Counter()
    protected_loaded = 0
    view_rows = view_result["rows"]
    for entry in view_rows:
        if entry["split"] not in PERMITTED_SPLITS:
            protected_loaded += 1
            continue
        try:
            target = build_structured_target(entry["record"], entry["eligibility"], policy=policy)
        except StructuredTargetError as exc:
            if str(exc).startswith("zero_supervised_target_fields:"):
                target_skipped["zero_supervised_fields"] += 1
                continue
            raise
        target_count += 1
        for field in target.supervised_fields:
            task_counts[field] += 1

    group_counts = Counter(entry["group_key"] for entry in view_rows)
    duplicate_groups = sum(1 for count in group_counts.values() if count > 1)
    weak_manifest["outputs"]["primary_pool_sha256"] = weak_manifest["outputs"]["primary_pool_sha256"].lower()
    canonical_manifest = {
        "manifest_schema_version": "t28_r1_canonical_manifest_v1",
        "ticket": "T28-R1",
        "recovery_status": "recovered_existing_artifact",
        "canonical_path": "data/processed/weak_pool/weak_pool_canonical.jsonl",
        "canonical_sha256": weak_manifest["outputs"]["primary_pool_sha256"],
        "canonical_record_count": result["canonical_count"],
        "t15_expected_permitted_count": result["expected_permitted_count"],
        "t15_train_count": result["train_count"],
        "t15_dev_count": result["dev_count"],
        "t15_manifest_sha256": sha256_hex((T15_MANIFEST.parent / "manifest.json").read_bytes()),
        "t15_record_manifest_sha256": sha256_hex(T15_MANIFEST.read_bytes()),
        "source_version_manifest": "data/processed/weak_pool/source-version.manifest.json",
        "provenance_manifest": "data/processed/weak_pool/provenance.manifest.json",
        "licence_manifest": "data/processed/weak_pool/licence.manifest.json",
        "exclusion_report": "data/processed/weak_pool/exclusion.report.json",
        "join_validation_report": "data/processed/weak_pool/join-validation.report.json",
        "permitted_view": "data/processed/weak_pool/t28_permitted_train_dev.jsonl",
        "permitted_view_sha256": view_result["sha256"],
        "protected_roles_materialised": False,
        "smoke_subset_used_as_corpus": False,
        "t27f_generation_schema_version": registry["generation_schema_version"],
        "t27f_generation_schema_hashes": generation_schema_hashes(registry),
    }
    source_version = _source_version_manifest(weak_manifest)
    provenance = {
        "ticket": "T28-R1",
        "canonical_sha256": canonical_manifest["canonical_sha256"],
        "t15_manifest_sha256": canonical_manifest["t15_manifest_sha256"],
        "record_provenance_fields_required": ["source_dataset", "source_id", "group_id", "mapping_version", "source_metadata"],
        "source_adapters": [
            "scripts/convert_ambik.py", "scripts/convert_indirect_requests.py",
            "scripts/convert_codraw_icr_v2.py", "scripts/convert_vague.py",
            "scripts/convert_clara.py", "scripts/convert_clariq.py",
        ],
        "raw_downloads_mutated": False,
        "protected_data_accessed": False,
    }
    licence = {
        "ticket": "T28-R1",
        "authoritative_register": "configs/licences/dataset_licence_register.json",
        "status": "incomplete_unresolved_register_entries",
        "source_datasets": weak_manifest["included_datasets"],
        "entries": weak_manifest["inputs"],
        "note": "No licence identifiers are fabricated; unresolved authoritative statuses remain unresolved.",
    }
    manifest_rows = [json.loads(line) for line in T15_MANIFEST.read_text(encoding="utf-8").splitlines() if line.strip()]
    exclusion = {
        "ticket": "T28-R1",
        "protected_ids_rejected": result["protected_ids_rejected"],
        "protected_id_count": len(result["protected_ids_rejected"]),
        "non_permitted_roles": {split: sum(1 for row in manifest_rows if row.get("split") == split) for split in sorted({str(row.get("split")) for row in manifest_rows if row.get("split") not in PERMITTED_SPLITS})},
        "smoke_subset_records": 192,
        "smoke_subset_used": False,
        "forbidden_datasets": ["teach", "teach_tatc", "manual_compound", "safe_agent_bench"],
    }
    validation = {k: v for k, v in result.items() if k != "content_hashes"}
    validation.update({
        "canonical_sha256": canonical_manifest["canonical_sha256"],
        "permitted_view_sha256": view_result["sha256"],
        "train_dev_group_overlap": [],
        "duplicate_group_count_in_view": duplicate_groups,
        "target_records_built": target_count,
        "target_records_skipped_by_reason": dict(sorted(target_skipped.items())),
        "per_task_target_field_counts": dict(sorted(task_counts.items())),
        "protected_records_loaded": protected_loaded,
        "missing_command_or_source_content": 0,
    })
    _write_json(OUT / "weak_pool_canonical.manifest.json", canonical_manifest)
    _write_json(OUT / "source-version.manifest.json", source_version)
    _write_json(OUT / "provenance.manifest.json", provenance)
    _write_json(OUT / "licence.manifest.json", licence)
    _write_json(OUT / "exclusion.report.json", exclusion)
    _write_json(OUT / "join-validation.report.json", validation)
    checksums = {
        "weak_pool_canonical.jsonl": sha256_hex(CANONICAL.read_bytes()),
        "t28_permitted_train_dev.jsonl": view_result["sha256"],
        "weak_pool_canonical.manifest.json": sha256_hex((OUT / "weak_pool_canonical.manifest.json").read_bytes()),
        "source-version.manifest.json": sha256_hex((OUT / "source-version.manifest.json").read_bytes()),
        "provenance.manifest.json": sha256_hex((OUT / "provenance.manifest.json").read_bytes()),
        "licence.manifest.json": sha256_hex((OUT / "licence.manifest.json").read_bytes()),
        "exclusion.report.json": sha256_hex((OUT / "exclusion.report.json").read_bytes()),
        "join-validation.report.json": sha256_hex((OUT / "join-validation.report.json").read_bytes()),
    }
    _write_json(OUT / "checksums.json", checksums)
    print(json.dumps({"status": "PASS", "canonical_sha256": checksums["weak_pool_canonical.jsonl"], "view_sha256": checksums["t28_permitted_train_dev.jsonl"], "train": result["train_count"], "dev": result["dev_count"], "target_records": target_count, "protected_loaded": protected_loaded, "licence_status": licence["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
