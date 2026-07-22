"""Deterministic QLoRA technical-smoke data subset builder (T27 Phase E).

Builds a small (32-64 record) deterministic subset of ``source_train`` only
(see ``data/development/source_splits_v1/``) for a QLoRA technical smoke on
the frozen adaptation base once Phase D selects it. This module never reads
``source_dev``, ``source_holdout``, the model-selection bake-off set, T13
calibration, the future manual namespace, or protected data; it only
consumes ``source_train`` rows already produced by
``src/ambiguity_manager/data/source_splits.py``.

This programme does not decide, select, or validate ``selected_base_model``;
that guard lives in ``src/ambiguity_manager/model/qlora_smoke.py``. It is
purely a deterministic data-subsetting step so a QLoRA smoke can exercise
shape/mask handling before any full training run.

CPU-only. Does not import torch, transformers, peft, bitsandbytes, or
accelerate.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, NamedTuple

from ambiguity_manager.data.model_selection_set import CALIBRATION_ID_RE, FUTURE_MANUAL_ID_RES
from ambiguity_manager.data.source_splits import (
    FORBIDDEN_DATASETS,
    PRIMARY_ALLOWED_DATASETS,
    load_training_target_policy,
)
from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.io_guard import resolve_writable_path
from ambiguity_manager.paths import ProjectPaths

PROGRAMME_ID = "qlora_smoke_data_v1"
PROGRAMME_VERSION = "1.0.0"

SOURCE_SPLITS_DIR_REL = "data/development/source_splits_v1"
RECORD_MANIFEST_REL = f"{SOURCE_SPLITS_DIR_REL}/record_manifest.jsonl"
PRIMARY_POOL_REL = "data/processed/weak_pool/weak_pool_canonical.jsonl"

OUTPUT_DIR_REL = "data/development/qlora_smoke_v1"

MIN_RECORD_COUNT = 32
MAX_RECORD_COUNT = 64
TARGET_RECORD_COUNT = 64

REQUIRED_SPLIT = "source_train"
FORBIDDEN_SPLITS: frozenset[str] = frozenset(
    {"source_dev", "source_holdout", "auxiliary_train", "auxiliary_dev"}
)

STRUCTURED_TARGET_TASK = "structured_training_target"
STRUCTURED_TARGET_STRONG: tuple[str, ...] = ("eligible", "weakly_eligible")


class SmokeDataError(RuntimeError):
    """Raised when the QLoRA smoke data subset cannot be built deterministically."""


class CategorySpec(NamedTuple):
    category_id: str
    description: str
    predicate: Callable[[dict[str, Any], dict[str, str]], bool]


def _has_ambiguity_type(record: dict[str, Any], type_name: str) -> bool:
    primary = record.get("primary_ambiguity_type")
    if primary == type_name:
        return True
    types = record.get("ambiguity_types") or []
    return isinstance(types, list) and type_name in types


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_items(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _is_direct_command(record: dict[str, Any], eligibility: dict[str, str]) -> bool:
    del eligibility
    return record.get("ambiguity_present") is False


def _is_indirect_request(record: dict[str, Any], eligibility: dict[str, str]) -> bool:
    del eligibility
    return record.get("source_dataset") == "indirect_requests"


def _is_referential_ambiguity(record: dict[str, Any], eligibility: dict[str, str]) -> bool:
    del eligibility
    return _has_ambiguity_type(record, "referential")


def _is_spatial_context_ambiguity(record: dict[str, Any], eligibility: dict[str, str]) -> bool:
    del eligibility
    return _has_ambiguity_type(record, "spatial") or _has_ambiguity_type(record, "contextual")


def _is_compound_ambiguity(record: dict[str, Any], eligibility: dict[str, str]) -> bool:
    del eligibility
    return bool(record.get("compound_ambiguity"))


def _is_clarification_route(record: dict[str, Any], eligibility: dict[str, str]) -> bool:
    if eligibility.get("clarification_target") not in ("eligible", "weakly_eligible"):
        return False
    if _has_items(record.get("clarification_targets")):
        return True
    question = record.get("clarification_question") or record.get("gold_clarification_question")
    return _has_text(question)


def _is_rejection_or_capability(record: dict[str, Any], eligibility: dict[str, str]) -> bool:
    if eligibility.get("rejection") in ("eligible", "weakly_eligible") and _has_text(
        record.get("rejection_reason")
    ):
        return True
    return eligibility.get("capability") == "eligible" and _has_text(record.get("capability_status"))


# Fixed, deterministic category order. Names mirror the QLoRA smoke deliverable
# list. "rejection_or_capability" is retained even though, at the time this
# module was written, `rejection` is structurally unsupported (0
# eligible/weakly_eligible records) across the entire source pool per
# data/development/source_splits_v1/eligibility_summary.json; the capability
# half of the predicate can still be satisfied and is recorded honestly via
# `legitimately_supported` in the coverage report rather than being faked.
CATEGORY_SPECS: tuple[CategorySpec, ...] = (
    CategorySpec("direct_command", "Unambiguous command with no clarification need.", _is_direct_command),
    CategorySpec(
        "indirect_request", "Non-imperative utterance implying a robot action.", _is_indirect_request
    ),
    CategorySpec(
        "referential_ambiguity", "Referential ambiguity (which object/entity).", _is_referential_ambiguity
    ),
    CategorySpec(
        "spatial_context_ambiguity",
        "Spatial or contextual ambiguity requiring scene grounding.",
        _is_spatial_context_ambiguity,
    ),
    CategorySpec("compound_ambiguity", "Multiple co-occurring ambiguities in one record.", _is_compound_ambiguity),
    CategorySpec(
        "clarification_route",
        "Record legitimately supports a clarification target/question.",
        _is_clarification_route,
    ),
    CategorySpec(
        "rejection_or_capability",
        "Rejection or capability signal (rejection is currently structurally "
        "unsupported in the source pool; capability is used where present).",
        _is_rejection_or_capability,
    ),
)

COVERAGE_PER_CATEGORY_PER_DATASET = 1


def _effective_root(root: Path | None) -> Path:
    return root if root is not None else ProjectPaths.from_repo_root().root


def dataset_paths(root: Path | None = None) -> dict[str, Path]:
    base = _effective_root(root) / OUTPUT_DIR_REL
    return {
        "dataset_dir": base,
        "smoke_records": base / "smoke_records.jsonl",
        "category_coverage": base / "category_coverage.json",
        "manifest": base / "manifest.json",
        "hashes": base / "hashes.json",
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise SmokeDataError(f"{path}:{line_number}: invalid JSON") from exc
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    target = resolve_writable_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [canonical_json_bytes(row).decode("utf-8") for row in rows]
    text = "\n".join(lines) + ("\n" if lines else "")
    target.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    target = resolve_writable_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json_bytes(payload).decode("utf-8") + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _digest_sort_value(seed: int, key: str) -> str:
    return hashlib.sha256(f"{seed}:{key}".encode("utf-8")).hexdigest()


def load_record_manifest_rows(root: Path | None = None) -> list[dict[str, Any]]:
    path = _effective_root(root) / RECORD_MANIFEST_REL
    if not path.is_file():
        raise SmokeDataError(
            f"missing {path}; run 'python scripts/build_source_data_splits.py' first"
        )
    return _read_jsonl(path)


def load_primary_pool_by_id(root: Path | None = None) -> dict[str, dict[str, Any]]:
    path = _effective_root(root) / PRIMARY_POOL_REL
    if not path.is_file():
        raise SmokeDataError(f"missing primary weak pool: {path}")
    rows = _read_jsonl(path)
    if not rows:
        raise SmokeDataError(f"primary weak pool is empty: {path}")
    return {str(row["id"]): row for row in rows}


def _assert_no_leakage(record_id: str) -> None:
    if CALIBRATION_ID_RE.match(record_id):
        raise SmokeDataError(f"t13_calibration_id_leaked_into_source_train:{record_id}")
    if any(pattern.match(record_id) for pattern in FUTURE_MANUAL_ID_RES):
        raise SmokeDataError(f"future_manual_namespace_id_leaked_into_source_train:{record_id}")


def build_eligible_source_train_pool(root: Path | None = None) -> list[dict[str, Any]]:
    """Return joined (full record + eligibility + split) rows for source_train only."""
    manifest_rows = load_record_manifest_rows(root)
    pool_by_id = load_primary_pool_by_id(root)

    joined: list[dict[str, Any]] = []
    for row in manifest_rows:
        record_id = str(row["id"])
        split = row["split"]
        if split in FORBIDDEN_SPLITS:
            continue
        if split != REQUIRED_SPLIT:
            continue
        _assert_no_leakage(record_id)
        dataset = row["source_dataset"]
        if dataset in FORBIDDEN_DATASETS:
            raise SmokeDataError(f"forbidden_source_dataset_in_source_train:{dataset}:{record_id}")
        if dataset not in PRIMARY_ALLOWED_DATASETS:
            raise SmokeDataError(f"unexpected_source_dataset_in_source_train:{dataset}:{record_id}")
        eligibility = row["eligibility"]
        if eligibility.get(STRUCTURED_TARGET_TASK) not in STRUCTURED_TARGET_STRONG:
            continue
        full_record = pool_by_id.get(record_id)
        if full_record is None:
            raise SmokeDataError(f"source_train_record_missing_from_primary_pool:{record_id}")
        joined.append(
            {
                "id": record_id,
                "group_key": row["group_key"],
                "source_dataset": dataset,
                "eligibility": eligibility,
                "record": full_record,
            }
        )
    if not joined:
        raise SmokeDataError("no eligible source_train records found for the QLoRA smoke subset")
    return joined


def categorize_entry(entry: dict[str, Any]) -> list[str]:
    record = entry["record"]
    eligibility = entry["eligibility"]
    return [spec.category_id for spec in CATEGORY_SPECS if spec.predicate(record, eligibility)]


def _tier(entry: dict[str, Any]) -> int:
    return 0 if entry["eligibility"][STRUCTURED_TARGET_TASK] == "eligible" else 1


def select_smoke_entries(
    pool: list[dict[str, Any]],
    *,
    seed: int,
    target_count: int = TARGET_RECORD_COUNT,
    min_count: int = MIN_RECORD_COUNT,
    max_count: int = MAX_RECORD_COUNT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Deterministically select a bounded, category- and source-diverse subset.

    Ordering is fully determined by ``seed`` and each entry's ``id``; no
    runtime randomness is used. Structurally eligible records are preferred
    over weakly-eligible ones ("strongest structured targets"); coverage of
    `CATEGORY_SPECS` x source dataset is attempted first, then the remainder
    is filled by descending structured-target strength.
    """
    if target_count > max_count or target_count < min_count:
        raise SmokeDataError("target_count must be within [min_count, max_count]")

    for entry in pool:
        entry["_digest"] = _digest_sort_value(seed, str(entry["id"]))
        entry["_tier"] = _tier(entry)
        entry["_categories"] = categorize_entry(entry)

    ordered = sorted(pool, key=lambda e: (e["_tier"], e["_digest"], e["id"]))
    by_id = {str(e["id"]): e for e in ordered}

    datasets_present = sorted({e["source_dataset"] for e in ordered})

    global_category_support: dict[str, bool] = {
        spec.category_id: any(spec.category_id in e["_categories"] for e in ordered)
        for spec in CATEGORY_SPECS
    }

    selected_ids: list[str] = []
    selected_set: set[str] = set()
    coverage_selections: dict[str, dict[str, str | None]] = {
        spec.category_id: {dataset: None for dataset in datasets_present} for spec in CATEGORY_SPECS
    }

    for spec in CATEGORY_SPECS:
        if not global_category_support[spec.category_id]:
            continue
        for dataset in datasets_present:
            if len(selected_ids) >= target_count:
                break
            picked = None
            for entry in ordered:
                if entry["id"] in selected_set:
                    continue
                if entry["source_dataset"] != dataset:
                    continue
                if spec.category_id not in entry["_categories"]:
                    continue
                picked = entry
                break
            if picked is not None:
                selected_ids.append(str(picked["id"]))
                selected_set.add(str(picked["id"]))
                coverage_selections[spec.category_id][dataset] = str(picked["id"])

    for entry in ordered:
        if len(selected_ids) >= target_count:
            break
        rid = str(entry["id"])
        if rid in selected_set:
            continue
        selected_ids.append(rid)
        selected_set.add(rid)

    if len(selected_ids) < min_count:
        raise SmokeDataError(
            f"insufficient eligible source_train records for smoke subset: "
            f"selected={len(selected_ids)} min_required={min_count}"
        )

    selected_entries = [by_id[rid] for rid in selected_ids]

    per_category_report: dict[str, Any] = {}
    for spec in CATEGORY_SPECS:
        selected_matches = [
            str(e["id"]) for e in selected_entries if spec.category_id in e["_categories"]
        ]
        per_category_report[spec.category_id] = {
            "description": spec.description,
            "legitimately_supported": global_category_support[spec.category_id],
            "selected_record_count": len(selected_matches),
            "selected_record_ids": sorted(selected_matches),
            "dataset_coverage": {
                dataset: coverage_selections[spec.category_id][dataset] is not None
                for dataset in datasets_present
            },
        }

    dataset_counts: dict[str, int] = {}
    for entry in selected_entries:
        dataset_counts[entry["source_dataset"]] = dataset_counts.get(entry["source_dataset"], 0) + 1

    coverage_report = {
        "seed": seed,
        "target_count": target_count,
        "min_count": min_count,
        "max_count": max_count,
        "selected_count": len(selected_entries),
        "pool_size": len(pool),
        "datasets_present_in_pool": datasets_present,
        "dataset_counts_in_selection": dataset_counts,
        "tier_counts_in_selection": {
            "eligible": sum(1 for e in selected_entries if e["_tier"] == 0),
            "weakly_eligible": sum(1 for e in selected_entries if e["_tier"] == 1),
        },
        "categories": per_category_report,
    }
    return selected_entries, coverage_report


def build_qlora_smoke_dataset(root: Path | None = None, *, publish: bool = True) -> dict[str, Any]:
    """Build the deterministic QLoRA smoke data subset and (optionally) persist it."""
    effective_root = _effective_root(root)
    training_target_policy = load_training_target_policy(effective_root)
    smoke_policy = training_target_policy.get("qlora_smoke_subset") or {}
    seed = int(smoke_policy.get("seed", 20260722))

    pool = build_eligible_source_train_pool(effective_root)
    selected_entries, coverage_report = select_smoke_entries(pool, seed=seed)

    smoke_rows: list[dict[str, Any]] = []
    for entry in sorted(selected_entries, key=lambda e: str(e["id"])):
        smoke_rows.append(
            {
                "id": entry["id"],
                "group_key": entry["group_key"],
                "source_dataset": entry["source_dataset"],
                "eligibility": entry["eligibility"],
                "category_tags": sorted(entry["_categories"]),
                "structured_training_target_status": entry["eligibility"][STRUCTURED_TARGET_TASK],
                "record": entry["record"],
            }
        )

    paths = dataset_paths(effective_root)
    if publish:
        paths["dataset_dir"].mkdir(parents=True, exist_ok=True)
        _write_jsonl(paths["smoke_records"], smoke_rows)
        _write_json(paths["category_coverage"], coverage_report)

    manifest_without_hashes: dict[str, Any] = {
        "programme_id": PROGRAMME_ID,
        "programme_version": PROGRAMME_VERSION,
        "ticket": "T27",
        "source_split_used": REQUIRED_SPLIT,
        "forbidden_splits": sorted(FORBIDDEN_SPLITS),
        "excluded_sources": [
            "source_dev",
            "source_holdout",
            "model_selection_development_set_v1",
            "t13_calibration",
            "future_manual_namespace",
            "protected_data",
        ],
        "seed": seed,
        "development_only": True,
        "protected": False,
        "valid_for_official_use": False,
        "record_count": len(smoke_rows),
        "min_record_count": MIN_RECORD_COUNT,
        "max_record_count": MAX_RECORD_COUNT,
        "record_ids": [row["id"] for row in smoke_rows],
        "notes": [
            "This subset never selects, sets, or implies selected_base_model/selected_adapter.",
            "structured_training_target eligibility is restricted to eligible/weakly_eligible; "
            "ineligible/unavailable records are never included.",
            "rejection is currently structurally unsupported (0 eligible/weakly_eligible) across "
            "the whole source pool; see category_coverage.json 'rejection_or_capability'.",
        ],
        "paths": {
            "smoke_records": "data/development/qlora_smoke_v1/smoke_records.jsonl",
            "category_coverage": "data/development/qlora_smoke_v1/category_coverage.json",
        },
    }

    if publish:
        manifest_without_hashes["hashes"] = {
            "smoke_records_sha256": sha256_file(paths["smoke_records"]),
            "category_coverage_sha256": sha256_file(paths["category_coverage"]),
        }
        manifest_hash = sha256_hex(canonical_json_bytes(manifest_without_hashes))
        manifest_without_hashes["manifest_hash"] = manifest_hash
        _write_json(paths["manifest"], manifest_without_hashes)
        hashes_payload = {
            **manifest_without_hashes["hashes"],
            "manifest_sha256": sha256_file(paths["manifest"]),
        }
        _write_json(paths["hashes"], hashes_payload)

    return {
        "manifest": manifest_without_hashes,
        "coverage_report": coverage_report,
        "smoke_rows": smoke_rows,
        "paths": paths,
    }
