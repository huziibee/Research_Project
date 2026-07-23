"""Task-aligned QLoRA smoke dataset v2 + frozen held-out validation set (T27).

Uses only ``source_train`` for the 64-record training subset and only
``source_dev`` for the 4-record held-out technical validation set.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ambiguity_manager.data.model_selection_set import CALIBRATION_ID_RE, FUTURE_MANUAL_ID_RES
from ambiguity_manager.data.source_splits import (
    FORBIDDEN_DATASETS,
    PRIMARY_ALLOWED_DATASETS,
    load_training_target_policy,
)
from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.io_guard import resolve_writable_path
from ambiguity_manager.model.qlora_smoke_data import (
    CATEGORY_SPECS,
    categorize_entry,
    load_primary_pool_by_id,
    load_record_manifest_rows,
)
from ambiguity_manager.model.training_example_contract import build_training_example
from ambiguity_manager.model.training_target_packaging import load_training_target_policy_strict
from ambiguity_manager.paths import ProjectPaths

PROGRAMME_ID = "qlora_task_aligned_smoke_data_v2"
PROGRAMME_VERSION = "2.0.0"

OUTPUT_DIR_REL = "data/development/qlora_task_aligned_smoke_v2"
VAL_DIR_REL = "data/development/qlora_task_aligned_smoke_val_v2"

TARGET_TRAIN_COUNT = 64
TARGET_VAL_COUNT = 4
REQUIRED_TRAIN_SPLIT = "source_train"
REQUIRED_VAL_SPLIT = "source_dev"
STRUCTURED_TARGET_TASK = "structured_training_target"
STRUCTURED_TARGET_STRONG = ("eligible", "weakly_eligible")

MODEL_SELECTION_SET_REL = "data/development/model_selection_v1/record_ids.json"


class TaskAlignedSmokeDataError(RuntimeError):
    """Raised when the task-aligned smoke dataset cannot be built safely."""


def _root(root: Path | None) -> Path:
    return root if root is not None else ProjectPaths.from_repo_root().root


def dataset_paths(root: Path | None = None) -> dict[str, Path]:
    base = _root(root) / OUTPUT_DIR_REL
    return {
        "dataset_dir": base,
        "records": base / "records.jsonl",
        "training_examples": base / "training_examples.jsonl",
        "manifest": base / "manifest.json",
        "source_lineage": base / "source_lineage.json",
        "field_eligibility_summary": base / "field_eligibility_summary.json",
        "loss_mask_summary": base / "loss_mask_summary.json",
        "leakage_report": base / "leakage_report.json",
        "hashes": base / "hashes.json",
    }


def validation_paths(root: Path | None = None) -> dict[str, Path]:
    base = _root(root) / VAL_DIR_REL
    return {
        "dataset_dir": base,
        "records": base / "records.jsonl",
        "manifest": base / "manifest.json",
        "hashes": base / "hashes.json",
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    target = resolve_writable_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [canonical_json_bytes(row).decode("utf-8") for row in rows]
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    target = resolve_writable_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json_bytes(payload).decode("utf-8") + "\n", encoding="utf-8")


def _digest(seed: int, key: str) -> str:
    return hashlib.sha256(f"{seed}:{key}".encode("utf-8")).hexdigest()


def _assert_no_leakage_id(record_id: str) -> None:
    if CALIBRATION_ID_RE.match(record_id):
        raise TaskAlignedSmokeDataError(f"calibration_id_forbidden:{record_id}")
    if any(pattern.match(record_id) for pattern in FUTURE_MANUAL_ID_RES):
        raise TaskAlignedSmokeDataError(f"future_manual_id_forbidden:{record_id}")


def _load_model_selection_ids(root: Path) -> set[str]:
    path = root / MODEL_SELECTION_SET_REL
    if not path.is_file():
        # Fall back to scanning known bake-off evidence ids file if present.
        alt = root / "data/development/model_selection_v1/manifest.json"
        if alt.is_file():
            payload = json.loads(alt.read_text(encoding="utf-8"))
            ids = payload.get("record_ids") or payload.get("ids") or []
            return {str(x) for x in ids}
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {str(x) for x in payload}
    ids = payload.get("record_ids") or payload.get("ids") or []
    return {str(x) for x in ids}


def _supervised_field_count(record: dict[str, Any], eligibility: dict[str, str], policy: dict[str, Any]) -> int:
    from ambiguity_manager.model.structured_target import StructuredTargetError, build_structured_target

    try:
        target = build_structured_target(record, eligibility, policy=policy)
        return len(target.supervised_fields)
    except StructuredTargetError:
        return 0
    except Exception:
        return 0


def build_split_pool(root: Path, *, split: str) -> list[dict[str, Any]]:
    manifest_rows = load_record_manifest_rows(root)
    pool_by_id = load_primary_pool_by_id(root)
    joined: list[dict[str, Any]] = []
    for row in manifest_rows:
        if row["split"] != split:
            continue
        record_id = str(row["id"])
        _assert_no_leakage_id(record_id)
        dataset = row["source_dataset"]
        if dataset in FORBIDDEN_DATASETS:
            raise TaskAlignedSmokeDataError(f"forbidden_dataset:{dataset}:{record_id}")
        if dataset not in PRIMARY_ALLOWED_DATASETS and split == REQUIRED_TRAIN_SPLIT:
            # auxiliary datasets are not used for this smoke train subset
            continue
        if dataset not in PRIMARY_ALLOWED_DATASETS and split == REQUIRED_VAL_SPLIT:
            continue
        eligibility = row["eligibility"]
        if eligibility.get(STRUCTURED_TARGET_TASK) not in STRUCTURED_TARGET_STRONG:
            continue
        full = pool_by_id.get(record_id)
        if full is None:
            raise TaskAlignedSmokeDataError(f"missing_pool_record:{record_id}")
        joined.append(
            {
                "id": record_id,
                "group_key": row["group_key"],
                "source_dataset": dataset,
                "eligibility": eligibility,
                "record": full,
                "split": split,
            }
        )
    if not joined:
        raise TaskAlignedSmokeDataError(f"empty_pool_for_split:{split}")
    return joined


def select_train_entries(
    pool: list[dict[str, Any]],
    *,
    seed: int,
    policy: dict[str, Any],
    target_count: int = TARGET_TRAIN_COUNT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    scored: list[tuple[int, int, str, dict[str, Any]]] = []
    for entry in pool:
        tokens = _supervised_field_count(entry["record"], entry["eligibility"], policy)
        if tokens <= 0:
            continue
        entry = dict(entry)
        entry["_categories"] = categorize_entry(entry)
        entry["_supervised_tokens"] = tokens
        entry["_digest"] = _digest(seed, str(entry["id"]))
        # Prefer more supervised tokens, then eligible over weakly, then digest.
        tier = 0 if entry["eligibility"][STRUCTURED_TARGET_TASK] == "eligible" else 1
        scored.append((-tokens, tier, entry["_digest"], entry))
    scored.sort()
    ordered = [item[3] for item in scored]

    datasets = sorted({e["source_dataset"] for e in ordered})
    selected_ids: list[str] = []
    selected_set: set[str] = set()
    # Category coverage first.
    for spec in CATEGORY_SPECS:
        for dataset in datasets:
            if len(selected_ids) >= target_count:
                break
            for entry in ordered:
                rid = str(entry["id"])
                if rid in selected_set:
                    continue
                if entry["source_dataset"] != dataset:
                    continue
                if spec.category_id not in entry["_categories"]:
                    continue
                selected_ids.append(rid)
                selected_set.add(rid)
                break
    for entry in ordered:
        if len(selected_ids) >= target_count:
            break
        rid = str(entry["id"])
        if rid in selected_set:
            continue
        selected_ids.append(rid)
        selected_set.add(rid)

    if len(selected_ids) < target_count:
        raise TaskAlignedSmokeDataError(
            f"insufficient_supervised_train_records:{len(selected_ids)}<{target_count}"
        )
    by_id = {str(e["id"]): e for e in ordered}
    selected = [by_id[rid] for rid in selected_ids]
    coverage = {
        "selected_count": len(selected),
        "datasets": sorted({e["source_dataset"] for e in selected}),
        "category_counts": {
            spec.category_id: sum(1 for e in selected if spec.category_id in e["_categories"])
            for spec in CATEGORY_SPECS
        },
    }
    return selected, coverage


def select_validation_entries(
    pool: list[dict[str, Any]],
    *,
    seed: int,
    train_group_keys: set[str],
    train_ids: set[str],
    policy: dict[str, Any],
    target_count: int = TARGET_VAL_COUNT,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for entry in pool:
        rid = str(entry["id"])
        if rid in train_ids:
            continue
        if entry["group_key"] in train_group_keys:
            continue
        tokens = _supervised_field_count(entry["record"], entry["eligibility"], policy)
        if tokens <= 0:
            continue
        entry = dict(entry)
        entry["_categories"] = categorize_entry(entry)
        entry["_digest"] = _digest(seed + 17, rid)
        candidates.append(entry)
    candidates.sort(key=lambda e: (e["_digest"], e["id"]))

    picks: list[dict[str, Any]] = []
    need = {
        "clear": lambda e: e["record"].get("ambiguity_present") is False,
        "ambiguous": lambda e: e["record"].get("ambiguity_present") is True,
        "compound_or_context": lambda e: bool(e["record"].get("compound_ambiguity"))
        or ("contextual" in (e["record"].get("ambiguity_types") or []))
        or ("spatial" in (e["record"].get("ambiguity_types") or [])),
        "capability_or_safety": lambda e: e["eligibility"].get("capability")
        in ("eligible", "weakly_eligible")
        or e["eligibility"].get("risk") in ("eligible", "weakly_eligible")
        or e["record"].get("capability_status") is not None,
    }
    used: set[str] = set()
    for _label, pred in need.items():
        for entry in candidates:
            rid = str(entry["id"])
            if rid in used:
                continue
            if pred(entry):
                picks.append(entry)
                used.add(rid)
                break
    for entry in candidates:
        if len(picks) >= target_count:
            break
        rid = str(entry["id"])
        if rid in used:
            continue
        picks.append(entry)
        used.add(rid)
    if len(picks) < target_count:
        raise TaskAlignedSmokeDataError(f"insufficient_validation_records:{len(picks)}")
    return picks[:target_count]


def build_task_aligned_smoke_dataset(root: Path | None = None, *, publish: bool = True) -> dict[str, Any]:
    effective = _root(root)
    seed = int((load_training_target_policy(effective).get("qlora_smoke_subset") or {}).get("seed", 20260722))
    policy = load_training_target_policy_strict(effective / "configs/data/training_target_policy_v1.json")
    model_selection_ids = _load_model_selection_ids(effective)

    train_pool = build_split_pool(effective, split=REQUIRED_TRAIN_SPLIT)
    train_pool = [e for e in train_pool if str(e["id"]) not in model_selection_ids]
    selected, coverage = select_train_entries(train_pool, seed=seed, policy=policy)

    train_ids = {str(e["id"]) for e in selected}
    train_groups = {str(e["group_key"]) for e in selected}

    # Leakage checks against source_dev / source_holdout groups.
    all_manifest = load_record_manifest_rows(effective)
    dev_groups = {str(r["group_key"]) for r in all_manifest if r["split"] == "source_dev"}
    holdout_groups = {str(r["group_key"]) for r in all_manifest if r["split"] == "source_holdout"}
    leaked_dev = sorted(train_groups & dev_groups)
    leaked_holdout = sorted(train_groups & holdout_groups)
    if leaked_dev or leaked_holdout:
        raise TaskAlignedSmokeDataError(
            f"group_leakage_detected:dev={leaked_dev[:5]} holdout={leaked_holdout[:5]}"
        )

    val_pool = build_split_pool(effective, split=REQUIRED_VAL_SPLIT)
    val_pool = [e for e in val_pool if str(e["id"]) not in model_selection_ids]
    # Prefer validation groups disjoint from train (already enforced) and from holdout.
    val_selected = select_validation_entries(
        val_pool,
        seed=seed,
        train_group_keys=train_groups,
        train_ids=train_ids,
        policy=policy,
    )
    val_ids = {str(e["id"]) for e in val_selected}
    val_groups = {str(e["group_key"]) for e in val_selected}
    if train_ids & val_ids:
        raise TaskAlignedSmokeDataError("train_val_record_overlap")
    if train_groups & val_groups:
        raise TaskAlignedSmokeDataError("train_val_group_overlap")

    record_rows: list[dict[str, Any]] = []
    example_rows: list[dict[str, Any]] = []
    field_elig_summary: dict[str, dict[str, int]] = {}
    loss_summaries: list[dict[str, Any]] = []
    for entry in sorted(selected, key=lambda e: str(e["id"])):
        example = build_training_example(
            record=entry["record"],
            eligibility=entry["eligibility"],
            source_dataset=entry["source_dataset"],
            group_key=entry["group_key"],
            policy=policy,
            attach_masks=True,
            max_seq_len=1024,
        )
        record_rows.append(
            {
                "id": entry["id"],
                "group_key": entry["group_key"],
                "source_dataset": entry["source_dataset"],
                "split": REQUIRED_TRAIN_SPLIT,
                "eligibility": entry["eligibility"],
                "category_tags": sorted(entry["_categories"]),
                "record": entry["record"],
            }
        )
        example_rows.append(example.to_dict())
        loss_summaries.append(dict(example.masked_sequence.diagnostics) if example.masked_sequence else {})
        for field_name, status in example.per_field_supervision_status.items():
            bucket = field_elig_summary.setdefault(field_name, {"supervised": 0, "weakly_supervised": 0, "unavailable_masked": 0})
            bucket[status] = bucket.get(status, 0) + 1

    val_rows: list[dict[str, Any]] = []
    for entry in sorted(val_selected, key=lambda e: str(e["id"])):
        val_rows.append(
            {
                "id": entry["id"],
                "group_key": entry["group_key"],
                "source_dataset": entry["source_dataset"],
                "split": REQUIRED_VAL_SPLIT,
                "eligibility": entry["eligibility"],
                "category_tags": sorted(entry.get("_categories") or categorize_entry(entry)),
                "record": entry["record"],
            }
        )

    leakage_report = {
        "train_record_count": len(record_rows),
        "val_record_count": len(val_rows),
        "train_ids": sorted(train_ids),
        "val_ids": sorted(val_ids),
        "group_overlap_train_dev": [],
        "group_overlap_train_holdout": [],
        "group_overlap_train_val": [],
        "model_selection_overlap": sorted(train_ids & model_selection_ids),
        "calibration_overlap": [],
        "future_manual_overlap": [],
        "source_holdout_records_in_train": 0,
        "passed": True,
    }

    paths = dataset_paths(effective)
    vpaths = validation_paths(effective)
    source_lineage = {
        "programme_id": PROGRAMME_ID,
        "programme_version": PROGRAMME_VERSION,
        "train_split": REQUIRED_TRAIN_SPLIT,
        "val_split": REQUIRED_VAL_SPLIT,
        "seed": seed,
        "coverage": coverage,
        "datasets_in_train": sorted({r["source_dataset"] for r in record_rows}),
        "datasets_in_val": sorted({r["source_dataset"] for r in val_rows}),
    }
    loss_mask_summary = {
        "example_count": len(example_rows),
        "examples_with_supervised_tokens": sum(
            1 for item in loss_summaries if int(item.get("target_supervised_tokens") or 0) > 0
        ),
        "mean_supervised_token_percentage": round(
            sum(float(item.get("supervised_token_percentage") or 0.0) for item in loss_summaries)
            / max(1, len(loss_summaries)),
            4,
        ),
        "per_example": loss_summaries,
    }

    manifest = {
        "programme_id": PROGRAMME_ID,
        "programme_version": PROGRAMME_VERSION,
        "ticket": "T27",
        "source_split_used": REQUIRED_TRAIN_SPLIT,
        "validation_split_used": REQUIRED_VAL_SPLIT,
        "record_count": len(record_rows),
        "training_example_count": len(example_rows),
        "validation_record_count": len(val_rows),
        "record_ids": [row["id"] for row in record_rows],
        "validation_record_ids": [row["id"] for row in val_rows],
        "development_only": True,
        "valid_for_official_use": False,
        "technical_smoke_only": True,
        "seed": seed,
        "excluded_sources": [
            "source_holdout",
            "model_selection_development_set_v1",
            "t13_calibration",
            "future_manual_namespace",
            "protected_data",
        ],
        "paths": {
            "records": f"{OUTPUT_DIR_REL}/records.jsonl",
            "training_examples": f"{OUTPUT_DIR_REL}/training_examples.jsonl",
            "validation_records": f"{VAL_DIR_REL}/records.jsonl",
        },
    }

    if publish:
        paths["dataset_dir"].mkdir(parents=True, exist_ok=True)
        vpaths["dataset_dir"].mkdir(parents=True, exist_ok=True)
        _write_jsonl(paths["records"], record_rows)
        _write_jsonl(paths["training_examples"], example_rows)
        _write_json(paths["source_lineage"], source_lineage)
        _write_json(paths["field_eligibility_summary"], field_elig_summary)
        _write_json(paths["loss_mask_summary"], loss_mask_summary)
        _write_json(paths["leakage_report"], leakage_report)
        _write_jsonl(vpaths["records"], val_rows)
        hashes = {
            "records_sha256": sha256_hex(paths["records"].read_bytes()),
            "training_examples_sha256": sha256_hex(paths["training_examples"].read_bytes()),
            "source_lineage_sha256": sha256_hex(paths["source_lineage"].read_bytes()),
            "field_eligibility_summary_sha256": sha256_hex(paths["field_eligibility_summary"].read_bytes()),
            "loss_mask_summary_sha256": sha256_hex(paths["loss_mask_summary"].read_bytes()),
            "leakage_report_sha256": sha256_hex(paths["leakage_report"].read_bytes()),
            "validation_records_sha256": sha256_hex(vpaths["records"].read_bytes()),
        }
        manifest["hashes"] = hashes
        manifest["manifest_hash"] = sha256_hex(canonical_json_bytes(manifest))
        _write_json(paths["manifest"], manifest)
        _write_json(paths["hashes"], {**hashes, "manifest_sha256": sha256_hex(paths["manifest"].read_bytes())})
        val_manifest = {
            "programme_id": PROGRAMME_ID,
            "role": "held_out_structured_smoke_validation",
            "split": REQUIRED_VAL_SPLIT,
            "record_count": len(val_rows),
            "record_ids": [row["id"] for row in val_rows],
            "development_only": True,
            "valid_for_official_use": False,
            "frozen_before_live_run": True,
            "hashes": {"records_sha256": hashes["validation_records_sha256"]},
        }
        val_manifest["manifest_hash"] = sha256_hex(canonical_json_bytes(val_manifest))
        _write_json(vpaths["manifest"], val_manifest)
        _write_json(
            vpaths["hashes"],
            {
                "records_sha256": hashes["validation_records_sha256"],
                "manifest_sha256": sha256_hex(vpaths["manifest"].read_bytes()),
            },
        )

    return {
        "manifest": manifest,
        "coverage": coverage,
        "record_rows": record_rows,
        "example_rows": example_rows,
        "val_rows": val_rows,
        "paths": paths,
        "validation_paths": vpaths,
        "leakage_report": leakage_report,
    }
