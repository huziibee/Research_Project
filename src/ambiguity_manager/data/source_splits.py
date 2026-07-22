"""Source-dataset development split programme (T15, source-development phase).

Builds group-aware, leakage-checked ``source_train`` / ``source_dev`` /
``source_holdout`` splits (plus ``auxiliary_train`` / ``auxiliary_dev`` for
ClariQ) from the schema-v2 weak-labelled pools produced by T09/T10.

This programme is deliberately independent of manual adjudication (T14B/T14C):
it operates entirely on weak/derived labels and never invents gold. The
resulting ``source_holdout`` split is a development-era holdout only. It is
**not** the future protected ``manual_protected_challenge_set`` benchmark,
which remains gated on T14C adjudication (see
``cursor_plan/tickets/T15_gold_splits_leakage_and_eligibility.md``).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from ambiguity_manager.annotation.calibration_data import calibration_candidates
from ambiguity_manager.annotation.duplicates import normalise_text
from ambiguity_manager.data.model_selection_set import (
    CALIBRATION_ID_RE,
    FUTURE_MANUAL_ID_RES,
)
from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.io_guard import resolve_writable_path
from ambiguity_manager.paths import ProjectPaths

PROGRAMME_ID = "source_data_split_programme_v1"
PROGRAMME_VERSION = "1.0.0"

POLICY_PATH = "configs/data/source_split_policy_v1.json"
TRAINING_TARGET_POLICY_PATH = "configs/data/training_target_policy_v1.json"

PRIMARY_POOL_PATH = "data/processed/schema_v2/weak_pool/weak_pool_canonical.jsonl"
AUXILIARY_POOL_PATH = "data/processed/schema_v2/weak_pool/weak_pool_auxiliary.jsonl"

OUTPUT_DIR = "data/development/source_splits_v1"

MODEL_SELECTION_MANIFEST_PATH = "data/development/model_selection_v1/manifest.json"
MODEL_SELECTION_INPUTS_PATH = "data/development/model_selection_v1/inputs.jsonl"

SYNTHETIC_FIXTURE_RELATIVE_PATHS: tuple[str, ...] = (
    "tests/fixtures/t16_t24_synthetic/inputs.jsonl",
    "tests/fixtures/schema_v2/t12_synthetic_inputs.jsonl",
    "tests/fixtures/schema_v2/t12_d_final_smoke_inputs.jsonl",
)

PRIMARY_ALLOWED_DATASETS: frozenset[str] = frozenset(
    {"ambik", "indirect_requests", "codraw_icr_v2", "vague", "clara"}
)
AUXILIARY_ALLOWED_DATASETS: frozenset[str] = frozenset({"clariq"})
FORBIDDEN_DATASETS: frozenset[str] = frozenset({"teach", "teach_tatc", "TEACh"})

TASK_NAMES: tuple[str, ...] = (
    "structured_training_target",
    "speech_act_intent",
    "cpc",
    "candidate_interpretations",
    "ambiguity_presence_types",
    "compound_ambiguity",
    "risk",
    "capability",
    "route",
    "clarification_target",
    "rejection",
    "context_blind_pairing",
    "uncertainty_sampling",
    "adapter_training",
    "source_development_evaluation",
    "source_holdout_evaluation",
)

ELIGIBILITY_VALUES: tuple[str, ...] = ("eligible", "weakly_eligible", "ineligible", "unavailable")

_AT_SUFFIX_RE = re.compile(r"^(?P<base>.+)@\d+$")
_FRAME_SUFFIX_RE = re.compile(r"^(?P<base>.+)__frame_\d+$")


class SourceSplitError(RuntimeError):
    """Raised when source-split construction or validation invariants fail."""


# --------------------------------------------------------------------------
# Path / IO helpers
# --------------------------------------------------------------------------


def _effective_root(root: Path | None) -> Path:
    return root if root is not None else ProjectPaths.from_repo_root().root


def dataset_paths(root: Path | None = None) -> dict[str, Path]:
    base = _effective_root(root) / OUTPUT_DIR
    return {
        "dataset_dir": base,
        "record_manifest": base / "record_manifest.jsonl",
        "group_manifest": base / "group_manifest.jsonl",
        "leakage_report": base / "leakage_report.json",
        "coverage_report": base / "coverage_report.json",
        "eligibility_summary": base / "eligibility_summary.json",
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
                raise SourceSplitError(f"{path}:{line_number}: invalid JSON") from exc
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


def _relative_path(path: Path, root: Path | None) -> str:
    effective_root = _effective_root(root)
    try:
        return path.resolve().relative_to(effective_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def load_policy(root: Path | None = None) -> dict[str, Any]:
    path = _effective_root(root) / POLICY_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def load_training_target_policy(root: Path | None = None) -> dict[str, Any]:
    path = _effective_root(root) / TRAINING_TARGET_POLICY_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def load_primary_records(root: Path | None = None) -> list[dict[str, Any]]:
    return _read_jsonl(_effective_root(root) / PRIMARY_POOL_PATH)


def load_auxiliary_records(root: Path | None = None) -> list[dict[str, Any]]:
    return _read_jsonl(_effective_root(root) / AUXILIARY_POOL_PATH)


def _assert_allowed_datasets(records: list[dict[str, Any]], allowed: frozenset[str]) -> None:
    for record in records:
        dataset = record.get("source_dataset")
        if dataset in FORBIDDEN_DATASETS:
            raise SourceSplitError(f"forbidden source dataset present: {dataset!r} (record {record.get('id')!r})")
        if dataset not in allowed:
            raise SourceSplitError(f"unexpected source dataset {dataset!r} (record {record.get('id')!r})")


# --------------------------------------------------------------------------
# Deterministic grouping
# --------------------------------------------------------------------------


def compute_group_key(record: dict[str, Any]) -> str:
    group_id = record.get("group_id")
    if group_id:
        return f"group:{group_id}"
    record_id = str(record["id"])
    match = _AT_SUFFIX_RE.match(record_id) or _FRAME_SUFFIX_RE.match(record_id)
    if match:
        return f"lineage:{record['source_dataset']}:{match.group('base')}"
    normalized = normalise_text(str(record.get("command", "")))
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"cmd:{record['source_dataset']}:{digest}"


def compute_stratum_key(record: dict[str, Any]) -> str:
    ambiguity_present = record.get("ambiguity_present")
    if ambiguity_present is True:
        bucket = "amb_true"
    elif ambiguity_present is False:
        bucket = "amb_false"
    else:
        bucket = "amb_unknown"
    return f"{record['source_dataset']}|{bucket}"


def build_groups(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        key = compute_group_key(record)
        groups.setdefault(key, []).append(record)
    return groups


def _representative(members: list[dict[str, Any]]) -> dict[str, Any]:
    return min(members, key=lambda record: str(record["id"]))


def _digest_sort_value(seed: int, group_key: str) -> str:
    return hashlib.sha256(f"{seed}:{group_key}".encode("utf-8")).hexdigest()


def assign_pool_splits(
    records: list[dict[str, Any]],
    *,
    ratios: dict[str, float],
    seed: int,
) -> dict[str, str]:
    """Group-aware, stratified, deterministic split assignment.

    Returns a mapping from record ``id`` to split name. Every member of a
    group is always assigned to the same split.
    """
    groups = build_groups(records)
    split_names = list(ratios.keys())

    strata: dict[str, list[str]] = {}
    for group_key, members in groups.items():
        stratum = compute_stratum_key(_representative(members))
        strata.setdefault(stratum, []).append(group_key)

    group_split: dict[str, str] = {}
    for _stratum, group_keys in strata.items():
        ordered = sorted(group_keys, key=lambda gk: _digest_sort_value(seed, gk))
        stratum_total = sum(len(groups[gk]) for gk in ordered)
        assigned_counts = {name: 0 for name in split_names}
        for group_key in ordered:
            size = len(groups[group_key])

            def _deficit(name: str) -> float:
                target = ratios[name] * stratum_total
                return target - assigned_counts[name]

            chosen = max(split_names, key=_deficit)
            group_split[group_key] = chosen
            assigned_counts[chosen] += size

    record_split: dict[str, str] = {}
    for group_key, members in groups.items():
        split_name = group_split[group_key]
        for record in members:
            record_split[str(record["id"])] = split_name
    return record_split


# --------------------------------------------------------------------------
# Eligibility manifest
# --------------------------------------------------------------------------


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_items(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _eligibility_speech_act_intent(record: dict[str, Any]) -> str:
    label_eligibility = record["label_eligibility"]
    if not label_eligibility.get("intent_slots"):
        return "ineligible"
    if _has_text(record.get("speech_act")) or _has_text(record.get("intent_summary")):
        return "eligible"
    return "weakly_eligible"


def _eligibility_cpc(record: dict[str, Any]) -> str:
    label_eligibility = record["label_eligibility"]
    if not label_eligibility.get("intent_slots"):
        return "ineligible"
    cpc = record.get("cpc") or {}
    filled = sum(1 for slot in cpc.values() if isinstance(slot, dict) and slot.get("status") == "filled")
    if filled == 0:
        return "unavailable"
    if filled >= 2:
        return "eligible"
    return "weakly_eligible"


def _eligibility_candidate_interpretations(record: dict[str, Any]) -> str:
    if _has_items(record.get("candidate_interpretations")):
        return "eligible"
    if record["source_dataset"] == "clariq":
        return "ineligible"
    return "unavailable"


def _eligibility_ambiguity_presence_types(record: dict[str, Any]) -> str:
    label_eligibility = record["label_eligibility"]
    if not label_eligibility.get("ambiguity"):
        return "ineligible"
    if record.get("ambiguity_present") is None:
        return "unavailable"
    if record.get("ambiguity_present") and not _has_items(record.get("ambiguity_types")):
        return "weakly_eligible"
    return "eligible"


def _eligibility_compound_ambiguity(record: dict[str, Any]) -> str:
    label_eligibility = record["label_eligibility"]
    if not (label_eligibility.get("compound_sequence") or label_eligibility.get("ambiguity")):
        return "ineligible"
    if record.get("ambiguity_present") is None:
        return "unavailable"
    if record.get("compound_ambiguity"):
        return "eligible"
    if label_eligibility.get("ambiguity"):
        return "weakly_eligible"
    return "unavailable"


def _eligibility_risk(record: dict[str, Any]) -> str:
    label_eligibility = record["label_eligibility"]
    if not label_eligibility.get("risk"):
        return "ineligible"
    if record.get("risk_level"):
        return "eligible"
    return "unavailable"


def _eligibility_capability(record: dict[str, Any]) -> str:
    label_eligibility = record["label_eligibility"]
    if not label_eligibility.get("capability"):
        return "ineligible"
    if record.get("capability_status"):
        return "eligible"
    return "unavailable"


def _eligibility_route(record: dict[str, Any]) -> str:
    label_eligibility = record["label_eligibility"]
    if not label_eligibility.get("routing"):
        return "ineligible"
    if record.get("recommended_strategy"):
        return "eligible"
    return "unavailable"


def _eligibility_clarification_target(record: dict[str, Any]) -> str:
    label_eligibility = record["label_eligibility"]
    if not (label_eligibility.get("clarification_target") or label_eligibility.get("clarification_decision")):
        return "ineligible"
    if _has_items(record.get("clarification_targets")):
        return "eligible"
    if _has_text(record.get("clarification_question")):
        return "weakly_eligible"
    return "unavailable"


def _eligibility_rejection(record: dict[str, Any]) -> str:
    label_eligibility = record["label_eligibility"]
    if not label_eligibility.get("rejection"):
        return "ineligible"
    if _has_text(record.get("rejection_reason")):
        return "eligible"
    if record.get("recommended_strategy") == "face_preserving_rejection":
        return "weakly_eligible"
    return "unavailable"


def _eligibility_context_blind_pairing(record: dict[str, Any], *, group_size: int) -> str:
    label_eligibility = record["label_eligibility"]
    if not label_eligibility.get("context_benefit"):
        return "ineligible"
    return "eligible" if group_size > 1 else "weakly_eligible"


def _eligibility_uncertainty_sampling(record: dict[str, Any]) -> str:
    context_sampling_uncertainty = record.get("context_sampling_uncertainty") or {}
    if context_sampling_uncertainty.get("score") is not None or context_sampling_uncertainty.get("variant_count") is not None:
        return "eligible"
    if record["source_dataset"] == "vague":
        return "weakly_eligible"
    return "unavailable"


def _eligibility_structured_training_target(record: dict[str, Any]) -> str:
    label_eligibility = record["label_eligibility"]
    signal_count = sum(1 for value in label_eligibility.values() if value)
    if signal_count == 0:
        return "unavailable"
    if signal_count >= 3:
        return "eligible"
    return "weakly_eligible"


def _eligibility_adapter_training(record: dict[str, Any], structured_status: str) -> str:
    if record["source_dataset"] == "clariq":
        return "ineligible"
    if structured_status in ("eligible", "weakly_eligible"):
        return structured_status
    return "unavailable"


def _eligibility_source_development_evaluation(record: dict[str, Any], split_name: str) -> str:
    if record["source_dataset"] == "clariq":
        return "ineligible"
    return "eligible" if split_name == "source_dev" else "ineligible"


def _eligibility_source_holdout_evaluation(record: dict[str, Any], split_name: str) -> str:
    if record["source_dataset"] == "clariq":
        return "ineligible"
    return "eligible" if split_name == "source_holdout" else "ineligible"


def compute_record_eligibility(record: dict[str, Any], *, group_size: int, split_name: str) -> dict[str, str]:
    structured = _eligibility_structured_training_target(record)
    result = {
        "structured_training_target": structured,
        "speech_act_intent": _eligibility_speech_act_intent(record),
        "cpc": _eligibility_cpc(record),
        "candidate_interpretations": _eligibility_candidate_interpretations(record),
        "ambiguity_presence_types": _eligibility_ambiguity_presence_types(record),
        "compound_ambiguity": _eligibility_compound_ambiguity(record),
        "risk": _eligibility_risk(record),
        "capability": _eligibility_capability(record),
        "route": _eligibility_route(record),
        "clarification_target": _eligibility_clarification_target(record),
        "rejection": _eligibility_rejection(record),
        "context_blind_pairing": _eligibility_context_blind_pairing(record, group_size=group_size),
        "uncertainty_sampling": _eligibility_uncertainty_sampling(record),
        "adapter_training": _eligibility_adapter_training(record, structured),
        "source_development_evaluation": _eligibility_source_development_evaluation(record, split_name),
        "source_holdout_evaluation": _eligibility_source_holdout_evaluation(record, split_name),
    }
    if set(result) != set(TASK_NAMES):
        raise SourceSplitError("eligibility result task set mismatch")
    for value in result.values():
        if value not in ELIGIBILITY_VALUES:
            raise SourceSplitError(f"invalid eligibility value {value!r}")
    return result


# --------------------------------------------------------------------------
# Leakage checks
# --------------------------------------------------------------------------


def _read_jsonl_commands(path: Path) -> set[str]:
    commands: set[str] = set()
    if not path.is_file():
        return commands
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            command = payload.get("command")
            if isinstance(command, str) and command.strip():
                commands.add(normalise_text(command))
    return commands


def _load_model_selection_ids_and_commands(root: Path | None) -> tuple[set[str], set[str]]:
    effective_root = _effective_root(root)
    manifest_path = effective_root / MODEL_SELECTION_MANIFEST_PATH
    ids: set[str] = set()
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        ids = {str(rid) for rid in manifest.get("record_ids", [])}
    commands = _read_jsonl_commands(effective_root / MODEL_SELECTION_INPUTS_PATH)
    return ids, commands


def _load_calibration_ids_and_commands() -> tuple[set[str], set[str]]:
    candidates = calibration_candidates()
    ids = {str(row["record_id"]) for row in candidates}
    commands = {normalise_text(str(row["command"])) for row in candidates}
    return ids, commands


def _load_synthetic_fixture_commands(root: Path | None) -> set[str]:
    effective_root = _effective_root(root)
    commands: set[str] = set()
    for relative in SYNTHETIC_FIXTURE_RELATIVE_PATHS:
        commands |= _read_jsonl_commands(effective_root / relative)
    return commands


def build_leakage_report(
    primary_records: list[dict[str, Any]],
    auxiliary_records: list[dict[str, Any]],
    root: Path | None = None,
) -> dict[str, Any]:
    all_records = primary_records + auxiliary_records
    record_ids = {str(record["id"]) for record in all_records}
    normalised_commands = {normalise_text(str(record.get("command", ""))) for record in all_records}

    calibration_ids, calibration_commands = _load_calibration_ids_and_commands()
    model_selection_ids, model_selection_commands = _load_model_selection_ids_and_commands(root)
    synthetic_fixture_commands = _load_synthetic_fixture_commands(root)

    calibration_id_overlap = sorted(rid for rid in record_ids if CALIBRATION_ID_RE.match(rid))
    future_manual_id_overlap = sorted(
        rid for rid in record_ids if any(pattern.match(rid) for pattern in FUTURE_MANUAL_ID_RES)
    )
    calibration_command_overlap = sorted(normalised_commands & calibration_commands)
    model_selection_id_overlap = sorted(record_ids & model_selection_ids)
    model_selection_command_overlap = sorted(normalised_commands & model_selection_commands)
    synthetic_fixture_command_overlap = sorted(normalised_commands & synthetic_fixture_commands)
    teach_records = sorted(
        str(record["id"]) for record in all_records if record.get("source_dataset") in FORBIDDEN_DATASETS
    )

    checks = {
        "t13_calibration_id_overlap": calibration_id_overlap,
        "t13_calibration_command_overlap": calibration_command_overlap,
        "future_manual_namespace_id_overlap": future_manual_id_overlap,
        "model_selection_id_overlap": model_selection_id_overlap,
        "model_selection_command_overlap": model_selection_command_overlap,
        "synthetic_evaluator_fixture_command_overlap": synthetic_fixture_command_overlap,
        "teach_source_dataset_records": teach_records,
    }
    passed = {name: len(value) == 0 for name, value in checks.items()}
    return {
        "checks": checks,
        "passed": passed,
        "all_checks_passed": all(passed.values()),
        "reference_counts": {
            "calibration_ids": len(calibration_ids),
            "calibration_commands": len(calibration_commands),
            "model_selection_ids": len(model_selection_ids),
            "model_selection_commands": len(model_selection_commands),
            "synthetic_fixture_commands": len(synthetic_fixture_commands),
        },
    }


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def _pool_coverage(
    records: list[dict[str, Any]],
    split_map: dict[str, str],
    ratios: dict[str, float],
) -> dict[str, Any]:
    counts = Counter(split_map[str(record["id"])] for record in records)
    total = len(records)
    percentages = {name: (counts.get(name, 0) / total * 100.0 if total else 0.0) for name in ratios}
    target_percentages = {name: ratio * 100.0 for name, ratio in ratios.items()}
    deviations = {name: percentages[name] - target_percentages[name] for name in ratios}
    return {
        "input_record_count": total,
        "output_record_count": sum(counts.get(name, 0) for name in ratios),
        "counts": {name: counts.get(name, 0) for name in ratios},
        "percentages": percentages,
        "target_percentages": target_percentages,
        "deviation_percentage_points": deviations,
    }


def build_source_splits(root: Path | None = None, *, publish: bool = True) -> dict[str, Any]:
    """Build the full source-development split programme deterministically."""
    policy = load_policy(root)
    training_policy = load_training_target_policy(root)
    seed = int(policy["seed"])

    primary_records = load_primary_records(root)
    auxiliary_records = load_auxiliary_records(root)
    if not primary_records:
        raise SourceSplitError("primary weak pool is empty or missing")
    if not auxiliary_records:
        raise SourceSplitError("auxiliary weak pool is empty or missing")
    _assert_allowed_datasets(primary_records, PRIMARY_ALLOWED_DATASETS)
    _assert_allowed_datasets(auxiliary_records, AUXILIARY_ALLOWED_DATASETS)

    primary_ratios = policy["target_ratios"]["primary"]
    auxiliary_ratios = policy["target_ratios"]["auxiliary"]

    primary_split = assign_pool_splits(primary_records, ratios=primary_ratios, seed=seed)
    auxiliary_split = assign_pool_splits(auxiliary_records, ratios=auxiliary_ratios, seed=seed)

    primary_groups = build_groups(primary_records)
    auxiliary_groups = build_groups(auxiliary_records)

    group_size_by_record_id: dict[str, int] = {}
    group_key_by_record_id: dict[str, str] = {}
    for groups in (primary_groups, auxiliary_groups):
        for group_key, members in groups.items():
            for member in members:
                rid = str(member["id"])
                group_size_by_record_id[rid] = len(members)
                group_key_by_record_id[rid] = group_key

    pools = (
        ("primary", primary_records, primary_split),
        ("auxiliary", auxiliary_records, auxiliary_split),
    )

    record_rows: list[dict[str, Any]] = []
    for pool_name, records, split_map in pools:
        for record in records:
            rid = str(record["id"])
            split_name = split_map[rid]
            eligibility = compute_record_eligibility(
                record,
                group_size=group_size_by_record_id[rid],
                split_name=split_name,
            )
            record_rows.append(
                {
                    "id": rid,
                    "source_dataset": record["source_dataset"],
                    "source_id": record.get("source_id"),
                    "pool": pool_name,
                    "group_key": group_key_by_record_id[rid],
                    "split": split_name,
                    "eligibility": eligibility,
                }
            )
    record_rows.sort(key=lambda row: row["id"])

    group_rows: list[dict[str, Any]] = []
    for pool_name, groups, split_map in (
        ("primary", primary_groups, primary_split),
        ("auxiliary", auxiliary_groups, auxiliary_split),
    ):
        for group_key, members in groups.items():
            member_ids = sorted(str(member["id"]) for member in members)
            splits_in_group = sorted({split_map[mid] for mid in member_ids})
            group_rows.append(
                {
                    "group_key": group_key,
                    "pool": pool_name,
                    "source_dataset": members[0]["source_dataset"],
                    "member_count": len(member_ids),
                    "member_ids": member_ids,
                    "split": splits_in_group[0] if len(splits_in_group) == 1 else None,
                    "split_count": len(splits_in_group),
                }
            )
    group_rows.sort(key=lambda row: row["group_key"])

    if any(row["split_count"] != 1 for row in group_rows):
        raise SourceSplitError("a group was split across more than one output split")

    coverage_report = {
        "primary": _pool_coverage(primary_records, primary_split, primary_ratios),
        "auxiliary": _pool_coverage(auxiliary_records, auxiliary_split, auxiliary_ratios),
        "tolerance_max_absolute_percentage_point_deviation": policy["tolerance"][
            "max_absolute_percentage_point_deviation"
        ],
    }
    tolerance = policy["tolerance"]["max_absolute_percentage_point_deviation"]
    coverage_report["primary"]["within_tolerance"] = all(
        abs(value) <= tolerance for value in coverage_report["primary"]["deviation_percentage_points"].values()
    )
    coverage_report["auxiliary"]["within_tolerance"] = all(
        abs(value) <= tolerance for value in coverage_report["auxiliary"]["deviation_percentage_points"].values()
    )
    coverage_report["reconciliation"] = {
        "total_input_records": len(primary_records) + len(auxiliary_records),
        "total_output_records": len(record_rows),
        "reconciled": (len(primary_records) + len(auxiliary_records)) == len(record_rows),
    }

    eligibility_summary: dict[str, Any] = {"total_records": len(record_rows), "by_task": {}}
    for task in TASK_NAMES:
        counter = Counter(row["eligibility"][task] for row in record_rows)
        eligibility_summary["by_task"][task] = {status: counter.get(status, 0) for status in ELIGIBILITY_VALUES}

    leakage_report = build_leakage_report(primary_records, auxiliary_records, root)
    if not leakage_report["all_checks_passed"]:
        raise SourceSplitError(f"leakage checks failed: {leakage_report['checks']}")

    paths = dataset_paths(root)
    if publish:
        paths["dataset_dir"].mkdir(parents=True, exist_ok=True)
        _write_jsonl(paths["record_manifest"], record_rows)
        _write_jsonl(paths["group_manifest"], group_rows)
        _write_json(paths["leakage_report"], leakage_report)
        _write_json(paths["coverage_report"], coverage_report)
        _write_json(paths["eligibility_summary"], eligibility_summary)

    manifest_without_hashes: dict[str, Any] = {
        "programme_id": PROGRAMME_ID,
        "programme_version": PROGRAMME_VERSION,
        "policy_path": POLICY_PATH,
        "training_target_policy_path": TRAINING_TARGET_POLICY_PATH,
        "policy_seed": seed,
        "development_only": True,
        "protected": False,
        "valid_for_official_final_claims": False,
        "source_holdout_is_not_manual_protected_challenge_set": True,
        "notes": [
            "source_holdout is a development-era holdout, not the final protected manual benchmark.",
            "manual_protected_challenge_set remains gated on T14C adjudication and is out of scope here.",
            "TEACh is excluded; T13 calibration is excluded; the future manual namespace is excluded.",
            "ClariQ is auxiliary only and is split separately into auxiliary_train / auxiliary_dev.",
            "Missing or unknown labels are recorded as 'unavailable' or 'ineligible'; never as a negative label.",
        ],
        "record_counts": {
            "primary_input": len(primary_records),
            "auxiliary_input": len(auxiliary_records),
            "total_output": len(record_rows),
            "groups_primary": len(primary_groups),
            "groups_auxiliary": len(auxiliary_groups),
        },
        "paths": {
            "record_manifest": _relative_path(paths["record_manifest"], root),
            "group_manifest": _relative_path(paths["group_manifest"], root),
            "leakage_report": _relative_path(paths["leakage_report"], root),
            "coverage_report": _relative_path(paths["coverage_report"], root),
            "eligibility_summary": _relative_path(paths["eligibility_summary"], root),
        },
    }

    if publish:
        manifest_without_hashes["hashes"] = {
            "record_manifest_sha256": sha256_file(paths["record_manifest"]),
            "group_manifest_sha256": sha256_file(paths["group_manifest"]),
            "leakage_report_sha256": sha256_file(paths["leakage_report"]),
            "coverage_report_sha256": sha256_file(paths["coverage_report"]),
            "eligibility_summary_sha256": sha256_file(paths["eligibility_summary"]),
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
        "eligibility_summary": eligibility_summary,
        "leakage_report": leakage_report,
        "record_rows": record_rows,
        "group_rows": group_rows,
        "paths": paths,
        "training_target_policy": training_policy,
    }
