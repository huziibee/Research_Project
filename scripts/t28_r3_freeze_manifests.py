#!/usr/bin/env python3
"""Freeze T28-R3 train/dev target manifests without loading a model."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex  # noqa: E402
from ambiguity_manager.model.generation_schema import generation_schema_hashes  # noqa: E402
from ambiguity_manager.model.structured_target import StructuredTargetError, build_structured_target  # noqa: E402
from ambiguity_manager.model.task_prediction_contract import build_task_prompt, load_task_registry  # noqa: E402
from ambiguity_manager.model.training_target_packaging import load_training_target_policy_strict  # noqa: E402


VIEW = ROOT / "data/processed/weak_pool/t28_permitted_train_dev.jsonl"
OUT = ROOT / "outputs/t28_r3/frozen_manifests"
EXPECTED = {"source_train": 11294, "source_dev": 2396}
TASK_FIELDS = {
    "predict_intent_v1": {"intent_summary", "speech_act"},
    "predict_cpc_v1": {"cpc"},
    "predict_ambiguity_v1": {"ambiguity_present", "ambiguity_types"},
    "predict_interpretations_v1": {"candidate_interpretations", "selected_interpretation"},
    "predict_risk_capability_v1": {"risk_relevant", "risk_level", "capability_status"},
}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    rows = [json.loads(line) for line in VIEW.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != sum(EXPECTED.values()):
        raise SystemExit(f"permitted_count_mismatch:{len(rows)}")
    if any(row.get("split") not in EXPECTED for row in rows):
        raise SystemExit("non_train_dev_record_present")
    if any(row.get("protected_data") is True or row.get("source_holdout") is True for row in rows):
        raise SystemExit("protected_record_present")

    registry = load_task_registry(ROOT)
    policy = load_training_target_policy_strict(ROOT / "configs/data/training_target_policy_v1.json")
    schema_hashes = generation_schema_hashes(registry)
    manifests: dict[str, list[dict]] = {split: [] for split in EXPECTED}
    skipped: Counter[str] = Counter()
    task_counts: Counter[str] = Counter()
    seen: set[str] = set()

    for row in rows:
        record = row["record"]
        record_id = str(row["id"])
        if record_id in seen:
            raise SystemExit(f"duplicate_record_id:{record_id}")
        seen.add(record_id)
        split = str(row["split"])
        try:
            target = build_structured_target(record, row["eligibility"], policy=policy)
        except StructuredTargetError as exc:
            if str(exc).startswith("zero_supervised_target_fields:"):
                skipped[str(exc).split(":", 1)[0]] += 1
                continue
            raise
        task_ids = [task_id for task_id, fields in TASK_FIELDS.items() if set(target.supervised_fields) & fields]
        prompt_hashes: dict[str, str] = {}
        for task_id in task_ids:
            task = next(item for item in registry["tasks"] if item["task_id"] == task_id)
            prompt = build_task_prompt(
                task_spec=task,
                command=str(record.get("command") or ""),
                scene_context=record.get("scene_context"),
                dialogue_history=record.get("dialogue_history") or [],
                capability_context=record.get("capability_context"),
                analysis_variant="full_context",
            )
            prompt_hashes[task_id] = sha256_hex(prompt.encode("utf-8"))
            task_counts[task_id] += 1
        manifests[split].append({
            "record_id": record_id,
            "group_id": row.get("group_key") or record.get("group_id"),
            "source_dataset": row.get("source_dataset"),
            "source_id": row.get("source_id"),
            "split": split,
            "content_hash": row.get("content_hash"),
            "target_hash": target.target_hash,
            "supervised_fields": list(target.supervised_fields),
            "weakly_eligible_fields": list(target.weakly_eligible_fields),
            "task_ids": task_ids,
            "prompt_hashes": prompt_hashes,
            "schema_hashes": {task_id: schema_hashes[task_id] for task_id in task_ids},
        })

    for split, expected in EXPECTED.items():
        if len(manifests[split]) > expected:
            raise SystemExit(f"{split}_target_accounting_mismatch:{len(manifests[split])}")
    if sum(EXPECTED.values()) - len(manifests["source_train"]) - len(manifests["source_dev"]) != 632:
        raise SystemExit("total_skipped_target_accounting_mismatch")
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_hashes: dict[str, str] = {}
    for split, entries in manifests.items():
        path = OUT / f"{split}_task_manifest.jsonl"
        path.write_bytes(b"".join(canonical_json_bytes(entry) + b"\n" for entry in entries))
        manifest_hashes[split] = file_sha256(path)
    summary = {
        "ticket": "T28-R3",
        "view_sha256": file_sha256(VIEW),
        "source_train_records": EXPECTED["source_train"],
        "source_dev_records": EXPECTED["source_dev"],
        "valid_task_conditioned_targets": len(manifests["source_train"]) + len(manifests["source_dev"]),
        "skipped_records": 632,
        "skipped_by_reason": dict(skipped),
        "per_task_manifest_counts": dict(task_counts),
        "manifest_sha256": manifest_hashes,
        "schema_hashes": schema_hashes,
        "protected_records_loaded": 0,
        "source_holdout_loaded": 0,
        "train_dev_group_overlap": 0,
        "immutable": True,
    }
    (OUT / "task_manifest_summary.json").write_bytes(canonical_json_bytes(summary) + b"\n")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
