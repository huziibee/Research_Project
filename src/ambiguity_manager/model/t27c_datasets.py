"""T27C task-conditioned datasets (CPU-only).

Builds:
- qlora_task_conditioned_smoke_v1 (~192 source_train → 256–512 task examples)
- t27c_diagnostic_dev_v1 (16 source_dev)
- t27c_final_smoke_v1 (12 sealed source_dev)

Does not import torch/transformers/peft/bitsandbytes/accelerate/vllm/requests/
lm_format_enforcer at module import time.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from ambiguity_manager.data.model_selection_set import CALIBRATION_ID_RE, FUTURE_MANUAL_ID_RES
from ambiguity_manager.data.source_splits import (
    FORBIDDEN_DATASETS,
    PRIMARY_ALLOWED_DATASETS,
)
from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.io_guard import resolve_writable_path
from ambiguity_manager.model.qlora_smoke_data import categorize_entry
from ambiguity_manager.model.qlora_task_aligned_smoke_data import build_split_pool
from ambiguity_manager.model.task_conditioned_training import (
    build_examples_for_record,
    build_task_conditioned_training_example,
)
from ambiguity_manager.model.task_prediction_contract import (
    load_field_responsibility_registry,
    load_task_registry,
    registry_hash,
)
from ambiguity_manager.paths import ProjectPaths

PROGRAMME_ID = "t27c_task_conditioned_v1"
PROGRAMME_VERSION = "1.0.0"
SEED = 20260723

TRAIN_DIR_REL = "data/development/qlora_task_conditioned_smoke_v1"
DIAGNOSTIC_DIR_REL = "data/development/t27c_diagnostic_dev_v1"
FINAL_SMOKE_DIR_REL = "data/development/t27c_final_smoke_v1"

TARGET_TRAIN_SOURCE_RECORDS = 192
TARGET_TRAIN_TASK_EXAMPLES_MIN = 256
TARGET_TRAIN_TASK_EXAMPLES_MAX = 512
TARGET_DIAGNOSTIC_COUNT = 16
TARGET_FINAL_COUNT = 12

JOB6059_VAL_IDS: frozenset[str] = frozenset(
    {"clara:1003", "clara:1180", "clara:1349", "codraw_icr_v2:4784"}
)
T27B_DIAGNOSTIC_IDS: frozenset[str] = frozenset(
    {
        "ambik:100",
        "ambik:1000",
        "ambik:120",
        "ambik:125",
        "ambik:126",
        "ambik:64",
        "clara:193",
        "codraw_icr_v2:11410",
        "codraw_icr_v2:12416",
        "codraw_icr_v2:1400",
        "codraw_icr_v2:14616",
        "codraw_icr_v2:4208",
    }
)
T27B_SEALED_IDS: frozenset[str] = frozenset(
    {
        "ambik:622",
        "ambik:653",
        "ambik:947",
        "clara:1148",
        "clara:5166",
        "clara:882",
        "codraw_icr_v2:12153",
        "codraw_icr_v2:8190",
    }
)
HISTORICAL_FORBIDDEN_IDS = JOB6059_VAL_IDS | T27B_DIAGNOSTIC_IDS | T27B_SEALED_IDS

MODEL_SELECTION_SET_REL = "data/development/model_selection_v1/record_ids.json"

REQUIRED_TASKS_DEFAULT = (
    "predict_intent_v1",
    "predict_cpc_v1",
    "predict_ambiguity_v1",
)


class T27CDatasetError(RuntimeError):
    """Raised when T27C datasets cannot be built safely."""


def _root(root: Path | None) -> Path:
    return root if root is not None else ProjectPaths.from_repo_root().root


def _digest(seed: int, key: str) -> str:
    return hashlib.sha256(f"{seed}:{key}".encode("utf-8")).hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    target = resolve_writable_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [canonical_json_bytes(row).decode("utf-8") for row in rows]
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    target = resolve_writable_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json_bytes(payload).decode("utf-8") + "\n", encoding="utf-8")


def _assert_no_leakage_id(record_id: str) -> None:
    if record_id in HISTORICAL_FORBIDDEN_IDS:
        raise T27CDatasetError(f"historical_forbidden_id:{record_id}")
    if CALIBRATION_ID_RE.match(record_id):
        raise T27CDatasetError(f"calibration_id_forbidden:{record_id}")
    if any(pattern.match(record_id) for pattern in FUTURE_MANUAL_ID_RES):
        raise T27CDatasetError(f"future_manual_id_forbidden:{record_id}")


def _load_model_selection_ids(root: Path) -> set[str]:
    path = root / MODEL_SELECTION_SET_REL
    if not path.is_file():
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


def _filter_pool(
    pool: list[dict[str, Any]],
    *,
    forbidden_ids: set[str],
    forbidden_groups: set[str],
    model_selection_ids: set[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in pool:
        rid = str(entry["id"])
        if rid in forbidden_ids or rid in model_selection_ids or rid in HISTORICAL_FORBIDDEN_IDS:
            continue
        if entry["group_key"] in forbidden_groups:
            continue
        _assert_no_leakage_id(rid)
        if entry["source_dataset"] in FORBIDDEN_DATASETS:
            continue
        if entry["source_dataset"] not in PRIMARY_ALLOWED_DATASETS:
            continue
        annotated = dict(entry)
        annotated["_categories"] = categorize_entry(entry)
        annotated["_digest"] = _digest(SEED, rid)
        out.append(annotated)
    return out


def _task_examples_for_entry(
    entry: dict[str, Any],
    task_registry: dict[str, Any],
) -> list[dict[str, Any]]:
    examples = build_examples_for_record(
        record=entry["record"],
        eligibility=entry["eligibility"],
        task_registry=task_registry,
        source_dataset=str(entry["source_dataset"]),
        split="source_train",
    )
    return [ex.to_dict() for ex in examples]


def _select_train(
    candidates: list[dict[str, Any]],
    task_registry: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Select ~192 source records yielding 256–512 task examples."""
    ordered = sorted(candidates, key=lambda e: (e["_digest"], e["id"]))
    # Prefer records that yield more tasks and cover datasets.
    scored: list[tuple[int, str, dict[str, Any], list[dict[str, Any]]]] = []
    for entry in ordered:
        examples = _task_examples_for_entry(entry, task_registry)
        if not examples:
            continue
        scored.append((len(examples), entry["_digest"], entry, examples))
    scored.sort(key=lambda x: (-x[0], x[1], x[2]["id"]))

    selected_entries: list[dict[str, Any]] = []
    selected_examples: list[dict[str, Any]] = []
    per_dataset: Counter[str] = Counter()
    per_task: Counter[str] = Counter()

    # Dataset floors
    floors = {"ambik": 30, "clara": 30, "codraw_icr_v2": 30, "indirect_requests": 8, "vague": 8}

    def _already_selected(entry: dict[str, Any]) -> bool:
        return any(str(e["id"]) == entry["id"] for e in selected_entries)

    # First pass: satisfy floors (IDs unique; groups may repeat within train)
    for ds, floor in floors.items():
        for _n, _d, entry, examples in scored:
            if len([e for e in selected_entries if e["source_dataset"] == ds]) >= floor:
                break
            if entry["source_dataset"] != ds or _already_selected(entry):
                continue
            selected_entries.append(entry)
            selected_examples.extend(examples)
            per_dataset[ds] += 1
            for ex in examples:
                per_task[ex["task_id"]] += 1

    # Second pass: fill toward ~192 source records while staying under example max.
    for _n, _d, entry, examples in scored:
        if len(selected_entries) >= TARGET_TRAIN_SOURCE_RECORDS:
            break
        if len(selected_examples) + len(examples) > TARGET_TRAIN_TASK_EXAMPLES_MAX:
            continue
        if _already_selected(entry):
            continue
        selected_entries.append(entry)
        selected_examples.extend(examples)
        per_dataset[entry["source_dataset"]] += 1
        for ex in examples:
            per_task[ex["task_id"]] += 1

    # Third pass: if still below the task-example floor, add more source records
    # (may exceed 192) until we reach MIN examples or exhaust the pool.
    if len(selected_examples) < TARGET_TRAIN_TASK_EXAMPLES_MIN:
        for _n, _d, entry, examples in scored:
            if len(selected_examples) >= TARGET_TRAIN_TASK_EXAMPLES_MIN:
                break
            if len(selected_examples) + len(examples) > TARGET_TRAIN_TASK_EXAMPLES_MAX:
                continue
            if _already_selected(entry):
                continue
            selected_entries.append(entry)
            selected_examples.extend(examples)
            per_dataset[entry["source_dataset"]] += 1
            for ex in examples:
                per_task[ex["task_id"]] += 1

    if len(selected_entries) < min(120, TARGET_TRAIN_SOURCE_RECORDS):
        raise T27CDatasetError(
            f"insufficient_train_source_records:{len(selected_entries)}"
        )
    if len(selected_examples) < TARGET_TRAIN_TASK_EXAMPLES_MIN:
        raise T27CDatasetError(
            f"insufficient_task_examples:{len(selected_examples)}"
        )
    if len(per_dataset) < 2:
        raise T27CDatasetError("train_requires_at_least_two_datasets")
    for task in task_registry["tasks"]:
        tid = task["task_id"]
        if per_task.get(tid, 0) <= 0:
            raise T27CDatasetError(f"no_training_examples_for_task:{tid}")

    selected_entries = sorted(selected_entries, key=lambda e: (e["_digest"], e["id"]))
    selected_examples = sorted(
        selected_examples,
        key=lambda e: (e["source_record_id"], e["task_id"]),
    )
    return selected_entries, selected_examples


def _pick_eval(
    candidates: list[dict[str, Any]],
    *,
    target_count: int,
    forbidden_ids: set[str],
    forbidden_groups: set[str],
    needs: list[tuple[str, Callable[[dict[str, Any]], bool]]],
) -> list[dict[str, Any]]:
    ordered = sorted(candidates, key=lambda e: (e["_digest"], e["id"]))
    picks: list[dict[str, Any]] = []
    used: set[str] = set()
    used_groups: set[str] = set(forbidden_groups)

    def _try(entry: dict[str, Any]) -> bool:
        rid = str(entry["id"])
        gk = str(entry["group_key"])
        if rid in used or rid in forbidden_ids or gk in used_groups:
            return False
        picks.append(entry)
        used.add(rid)
        used_groups.add(gk)
        return True

    for _label, pred in needs:
        for entry in ordered:
            if pred(entry) and _try(entry):
                break
    for entry in ordered:
        if len(picks) >= target_count:
            break
        _try(entry)
    if len(picks) < target_count:
        raise T27CDatasetError(f"insufficient_eval_picks:{len(picks)}<{target_count}")
    return picks[:target_count]


def _record_row(entry: dict[str, Any]) -> dict[str, Any]:
    rec = dict(entry["record"])
    return {
        "id": entry["id"],
        "group_key": entry["group_key"],
        "source_dataset": entry["source_dataset"],
        "split": entry["split"],
        "eligibility": entry["eligibility"],
        "categories": entry.get("_categories"),
        "command": rec.get("command"),
        "scene_context": rec.get("scene_context"),
        "dialogue_history": rec.get("dialogue_history") or [],
        "capability_context": rec.get("capability_context"),
        "speech_act": rec.get("speech_act"),
        "intent_summary": rec.get("intent_summary") or rec.get("intent"),
        "cpc": rec.get("cpc") or rec.get("slots"),
        "ambiguity_present": rec.get("ambiguity_present"),
        "ambiguity_types": rec.get("ambiguity_types"),
        "primary_ambiguity_type": rec.get("primary_ambiguity_type"),
        "unresolved_slots": rec.get("unresolved_slots"),
        "candidate_interpretations": rec.get("candidate_interpretations"),
        "selected_interpretation": rec.get("selected_interpretation"),
        "risk_relevant": rec.get("risk_relevant"),
        "risk_level": rec.get("risk_level"),
        "capability_status": rec.get("capability_status"),
        "group_id": rec.get("group_id"),
        "record": rec,
    }


def _required_task_matrix(entries: list[dict[str, Any]], task_registry: dict[str, Any]) -> dict[str, Any]:
    matrix: dict[str, Any] = {}
    optional_ids = [
        t["task_id"]
        for t in task_registry["tasks"]
        if t["task_id"] not in REQUIRED_TASKS_DEFAULT
    ]
    for entry in entries:
        matrix[str(entry["id"])] = {
            "required": list(REQUIRED_TASKS_DEFAULT),
            "optional": list(optional_ids),
        }
    return {
        "matrix_version": "1.0.0",
        "records": matrix,
        "matrix_hash": sha256_hex(canonical_json_bytes(matrix)),
    }


def _supervision_report(examples: list[dict[str, Any]]) -> dict[str, Any]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ex in examples:
        by_task[ex["task_id"]].append(ex)
    per_task: dict[str, Any] = {}
    for tid, rows in by_task.items():
        densities = [
            float((r.get("mask_diagnostics") or {}).get("supervised_token_percentage") or 0.0)
            for r in rows
        ]
        target_tokens = [
            int((r.get("mask_diagnostics") or {}).get("target_supervised_tokens") or 0)
            for r in rows
        ]
        sources = Counter(r["source_dataset"] for r in rows)
        weak = sum(
            1
            for r in rows
            if any((r.get("weak_label_status") or {}).values())
        )
        per_task[tid] = {
            "example_count": len(rows),
            "mean_target_token_count": round(sum(target_tokens) / max(1, len(rows)), 4),
            "mean_supervised_percentage": round(sum(densities) / max(1, len(rows)), 4),
            "source_distribution": dict(sources),
            "weak_label_count": weak,
        }
    return {
        "total_task_examples": len(examples),
        "per_task": per_task,
        "prompt_masking": "all_prompt_tokens_-100",
        "command_reconstruction": False,
    }


def build_t27c_datasets(root: Path | None = None) -> dict[str, Any]:
    base = _root(root)
    task_registry = load_task_registry(base)
    field_registry = load_field_responsibility_registry(base)
    model_selection_ids = _load_model_selection_ids(base)

    train_pool = _filter_pool(
        build_split_pool(base, split="source_train"),
        forbidden_ids=set(HISTORICAL_FORBIDDEN_IDS),
        forbidden_groups=set(),
        model_selection_ids=model_selection_ids,
    )
    train_entries, train_examples = _select_train(train_pool, task_registry)
    train_ids = {str(e["id"]) for e in train_entries}
    train_groups = {str(e["group_key"]) for e in train_entries}

    dev_pool = _filter_pool(
        build_split_pool(base, split="source_dev"),
        forbidden_ids=set(HISTORICAL_FORBIDDEN_IDS) | train_ids,
        forbidden_groups=set(train_groups),
        model_selection_ids=model_selection_ids,
    )

    def _has_ambiguity(e: dict[str, Any]) -> bool:
        return bool((e["record"] or {}).get("ambiguity_present"))

    def _clear(e: dict[str, Any]) -> bool:
        return (e["record"] or {}).get("ambiguity_present") is False

    def _indirect(e: dict[str, Any]) -> bool:
        return (e["record"] or {}).get("speech_act") == "indirect_request" or e[
            "source_dataset"
        ] == "indirect_requests"

    def _risk(e: dict[str, Any]) -> bool:
        return e["eligibility"].get("risk") in {"eligible", "weakly_eligible"}

    def _compound(e: dict[str, Any]) -> bool:
        types = (e["record"] or {}).get("ambiguity_types") or []
        return isinstance(types, list) and len(set(types)) >= 2

    diagnostic = _pick_eval(
        dev_pool,
        target_count=TARGET_DIAGNOSTIC_COUNT,
        forbidden_ids=set(HISTORICAL_FORBIDDEN_IDS) | train_ids,
        forbidden_groups=set(train_groups),
        needs=[
            ("clear", _clear),
            ("ambiguous", _has_ambiguity),
            ("indirect", _indirect),
            ("risk", _risk),
            ("compound", _compound),
            ("ambik", lambda e: e["source_dataset"] == "ambik"),
            ("clara", lambda e: e["source_dataset"] == "clara"),
            ("codraw", lambda e: e["source_dataset"] == "codraw_icr_v2"),
        ],
    )
    diagnostic_ids = {str(e["id"]) for e in diagnostic}
    diagnostic_groups = {str(e["group_key"]) for e in diagnostic}

    sealed = _pick_eval(
        [e for e in dev_pool if e["id"] not in diagnostic_ids],
        target_count=TARGET_FINAL_COUNT,
        forbidden_ids=set(HISTORICAL_FORBIDDEN_IDS) | train_ids | diagnostic_ids,
        forbidden_groups=set(train_groups) | diagnostic_groups,
        needs=[
            ("clear", _clear),
            ("ambiguous", _has_ambiguity),
            ("indirect", _indirect),
            ("risk", _risk),
            ("compound", _compound),
            ("ambik", lambda e: e["source_dataset"] == "ambik"),
            ("clara", lambda e: e["source_dataset"] == "clara"),
            ("codraw", lambda e: e["source_dataset"] == "codraw_icr_v2"),
        ],
    )

    # Write train
    train_dir = base / TRAIN_DIR_REL
    train_records = [_record_row(e) for e in train_entries]
    _write_jsonl(train_dir / "source_records.jsonl", train_records)
    _write_jsonl(train_dir / "task_examples.jsonl", train_examples)
    supervision = _supervision_report(train_examples)
    train_manifest = {
        "dataset_id": "qlora_task_conditioned_smoke_v1",
        "programme_id": PROGRAMME_ID,
        "programme_version": PROGRAMME_VERSION,
        "split": "source_train",
        "record_count": len(train_entries),
        "task_example_count": len(train_examples),
        "record_ids": [e["id"] for e in train_entries],
        "datasets": sorted({e["source_dataset"] for e in train_entries}),
        "per_task_example_counts": {
            tid: info["example_count"] for tid, info in supervision["per_task"].items()
        },
        "task_registry_hash": registry_hash(task_registry),
        "field_responsibility_registry_hash": registry_hash(field_registry),
        "seed": SEED,
    }
    train_manifest["manifest_hash"] = sha256_hex(canonical_json_bytes(train_manifest))
    _write_json(train_dir / "manifest.json", train_manifest)
    _write_json(train_dir / "supervision_report.json", supervision)
    _write_json(
        train_dir / "leakage_report.json",
        {
            "historical_forbidden_overlap": sorted(
                train_ids & set(HISTORICAL_FORBIDDEN_IDS)
            ),
            "model_selection_overlap": sorted(train_ids & model_selection_ids),
            "source_holdout_used": False,
            "passed": not (train_ids & set(HISTORICAL_FORBIDDEN_IDS | model_selection_ids)),
        },
    )
    _write_json(
        train_dir / "hashes.json",
        {
            "manifest_hash": train_manifest["manifest_hash"],
            "task_registry_hash": registry_hash(task_registry),
            "field_responsibility_registry_hash": registry_hash(field_registry),
            "source_records_sha256": sha256_hex(
                (train_dir / "source_records.jsonl").read_bytes()
            ),
            "task_examples_sha256": sha256_hex(
                (train_dir / "task_examples.jsonl").read_bytes()
            ),
        },
    )

    # Diagnostic
    diag_dir = base / DIAGNOSTIC_DIR_REL
    diag_records = [_record_row(e) for e in diagnostic]
    _write_jsonl(diag_dir / "records.jsonl", diag_records)
    diag_manifest = {
        "dataset_id": "t27c_diagnostic_dev_v1",
        "split": "source_dev",
        "record_count": len(diagnostic),
        "record_ids": [e["id"] for e in diagnostic],
        "diagnostic_only": True,
        "valid_for_final_t27c_gate": False,
        "datasets": sorted({e["source_dataset"] for e in diagnostic}),
        "seed": SEED,
    }
    diag_manifest["manifest_hash"] = sha256_hex(canonical_json_bytes(diag_manifest))
    _write_json(diag_dir / "manifest.json", diag_manifest)
    _write_json(
        diag_dir / "hashes.json",
        {
            "manifest_hash": diag_manifest["manifest_hash"],
            "records_sha256": sha256_hex((diag_dir / "records.jsonl").read_bytes()),
        },
    )

    # Sealed
    sealed_dir = base / FINAL_SMOKE_DIR_REL
    sealed_records = [_record_row(e) for e in sealed]
    _write_jsonl(sealed_dir / "records.jsonl", sealed_records)
    matrix = _required_task_matrix(sealed, task_registry)
    sealed_manifest = {
        "dataset_id": "t27c_final_smoke_v1",
        "split": "source_dev",
        "record_count": len(sealed),
        "record_ids": [e["id"] for e in sealed],
        "seal_status": "sealed",
        "datasets": sorted({e["source_dataset"] for e in sealed}),
        "required_task_matrix_hash": matrix["matrix_hash"],
        "seed": SEED,
    }
    sealed_manifest["manifest_hash"] = sha256_hex(canonical_json_bytes(sealed_manifest))
    _write_json(sealed_dir / "manifest.json", sealed_manifest)
    _write_json(sealed_dir / "required_task_matrix.json", matrix)
    _write_json(
        sealed_dir / "coverage_report.json",
        {
            "datasets": sealed_manifest["datasets"],
            "ambiguity_present_true": sum(
                1 for e in sealed if (e["record"] or {}).get("ambiguity_present")
            ),
            "ambiguity_present_false": sum(
                1 for e in sealed if (e["record"] or {}).get("ambiguity_present") is False
            ),
            "source_count": len(sealed_manifest["datasets"]),
        },
    )
    _write_json(
        sealed_dir / "leakage_report.json",
        {
            "overlap_train": sorted({e["id"] for e in sealed} & train_ids),
            "overlap_diagnostic": sorted({e["id"] for e in sealed} & diagnostic_ids),
            "group_overlap_train": sorted(
                {e["group_key"] for e in sealed} & train_groups
            ),
            "group_overlap_diagnostic": sorted(
                {e["group_key"] for e in sealed} & diagnostic_groups
            ),
            "historical_forbidden_overlap": sorted(
                {e["id"] for e in sealed} & set(HISTORICAL_FORBIDDEN_IDS)
            ),
            "passed": True,
        },
    )
    _write_json(
        sealed_dir / "hashes.json",
        {
            "manifest_hash": sealed_manifest["manifest_hash"],
            "records_sha256": sha256_hex((sealed_dir / "records.jsonl").read_bytes()),
            "required_task_matrix_hash": matrix["matrix_hash"],
        },
    )

    summary = {
        "train_record_count": len(train_entries),
        "train_task_example_count": len(train_examples),
        "diagnostic_count": len(diagnostic),
        "sealed_count": len(sealed),
        "train_manifest_hash": train_manifest["manifest_hash"],
        "diagnostic_manifest_hash": diag_manifest["manifest_hash"],
        "sealed_manifest_hash": sealed_manifest["manifest_hash"],
        "task_registry_hash": registry_hash(task_registry),
        "field_responsibility_registry_hash": registry_hash(field_registry),
        "per_task_example_counts": train_manifest["per_task_example_counts"],
        "diagnostic_ids": diag_manifest["record_ids"],
        "sealed_ids": sealed_manifest["record_ids"],
    }
    _write_json(base / TRAIN_DIR_REL / "build_summary.json", summary)
    return summary


if __name__ == "__main__":
    result = build_t27c_datasets()
    print(json.dumps(result, indent=2, sort_keys=True))
