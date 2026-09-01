#!/usr/bin/env python3
"""Reconcile immutable Pilot-120 T31 bytes and rescore saved early outputs.

T45 is deliberately CPU-only and read-only.  It does not call a model, alter a
prediction, or replace a historical result.  Its purpose is much narrower:
prove whether the bytes cited by the early T31 cost report still reproduce the
reported direct-base cost, then create a clearly bounded evidence-only slice
report from those already saved outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.evaluation import pilot_120 as p120  # noqa: E402
from scripts import pilot120_t39_evidence as t39  # noqa: E402


REQUIRED_SYSTEMS = (
    "always_clarify",
    "always_execute",
    "always_silently_resolve",
    "context_blind_manager",
    "degree_based_router",
    "direct_base_llm",
    "full_type_risk_aware_manager",
    "t28_selected_adapter_llm",
)
SLICE_FAMILIES = {"compound_depth", "ambiguity_type", "capability_status", "dialogue_presence"}


def _sha256(path: Path) -> str:
    """Hash streams so this CPU-only check is safe for large provenance files."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_not_object:{path}")
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise SystemExit(f"t45_output_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _parse_mapping(value: str) -> tuple[str, Path]:
    system_id, separator, raw_path = value.partition("=")
    if not separator or not system_id or not raw_path:
        raise argparse.ArgumentTypeError("mapping must be system_id=/path/to/predictions.jsonl")
    return system_id, Path(raw_path)


def _not_computed(reason: str, **detail: Any) -> dict[str, Any]:
    return {"status": "NOT_COMPUTED", "reason": reason, **detail}


def _frozen_inputs(root: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any], dict[str, Path]]:
    p120.assert_evaluation_only("t45_historical_reconciliation")
    config_path = root / "configs/evaluation/pilot_120_v1.json"
    config = _load_json(config_path)
    paths = {
        "source_canonical_jsonl": root / str(config["source_canonical_jsonl"]),
        "final_gold_jsonl": root / str(config["gold_jsonl"]),
        "gold_policy": root / str(config["gold_policy"]),
        "config_pilot_120_v1": config_path,
        "frozen_manifest": root / str(config["frozen_manifest"]),
    }
    manifest = _load_json(paths["frozen_manifest"])
    if manifest.get("freeze_id") != "pilot_120_v1" or manifest.get("evaluation_only") is not True:
        raise ValueError("t45_frozen_manifest_boundary_invalid")
    expected_hashes = manifest.get("hashes") or {}
    for key in ("source_canonical_jsonl", "final_gold_jsonl", "gold_policy", "config_pilot_120_v1"):
        if not paths[key].is_file() or _sha256(paths[key]) != expected_hashes.get(key):
            raise ValueError(f"t45_current_frozen_input_hash_mismatch:{key}")
    source = p120.load_jsonl(paths["source_canonical_jsonl"])
    gold_rows = p120.load_jsonl(paths["final_gold_jsonl"])
    ids = [str(row.get("record_id") or "") for row in source]
    gold = {str(row.get("record_id") or ""): row for row in gold_rows}
    if len(ids) != 120 or len(set(ids)) != 120 or ids != manifest.get("record_ids") or set(ids) != set(gold):
        raise ValueError("t45_frozen_denominator_or_order_invalid")
    return source, gold, manifest, paths


def _load_prediction(path: Path, system_id: str, expected_ids: list[str]) -> dict[str, dict[str, Any]]:
    rows = p120.load_jsonl(path)
    actual_ids = [str(row.get("record_id") or "") for row in rows]
    if actual_ids != expected_ids or len(set(actual_ids)) != len(expected_ids):
        raise ValueError(f"t45_prediction_denominator_or_order_invalid:{system_id}")
    if any(row.get("system_id") != system_id for row in rows):
        raise ValueError(f"t45_prediction_system_id_invalid:{system_id}")
    return {str(row["record_id"]): row for row in rows}


def _input_provenance(paths: dict[str, Path]) -> dict[str, dict[str, str]]:
    return {
        name: {"path": str(path.resolve()), "sha256": _sha256(path)}
        for name, path in sorted(paths.items())
    }


def _reconciliation(
    *,
    source: list[dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
    frozen_paths: dict[str, Path],
    policy_path: Path,
    t31_path: Path,
    run_manifest_path: Path,
    predictions: dict[str, Path],
) -> dict[str, Any]:
    """Return a terminal PASS/NOT_COMPUTED reconciliation without replacing T31."""
    problems: list[str] = []
    t31 = _load_json(t31_path)
    historical_run = _load_json(run_manifest_path)
    policy = _load_json(policy_path)
    ids = [str(row["record_id"]) for row in source]
    expected_hashes = t31.get("prediction_sha256") or {}

    if t31.get("status") != "T31_EARLY_COST_SENSITIVE_EVALUATION_COMPLETE":
        problems.append("t31_status_not_complete")
    if t31.get("scope") != "non_protected_pilot120_early_analysis_only" or t31.get("valid_for_official_use") is not False:
        problems.append("t31_scope_or_boundary_invalid")
    if t31.get("policy_sha256") != _sha256(policy_path):
        problems.append("t31_policy_bytes_do_not_match_local_policy")
    if historical_run.get("freeze", {}).get("source_sha256") != manifest.get("hashes", {}).get("source_canonical_jsonl"):
        problems.append("historical_run_source_bytes_unresolved")
    if historical_run.get("freeze", {}).get("gold_sha256") != manifest.get("hashes", {}).get("final_gold_jsonl"):
        problems.append("historical_run_gold_bytes_unresolved")
    if historical_run.get("freeze", {}).get("n") != len(ids):
        problems.append("historical_run_denominator_unresolved")
    if tuple(sorted(predictions)) != tuple(sorted(REQUIRED_SYSTEMS)):
        problems.append("historical_system_inventory_incomplete_or_unexpected")

    direct_path = predictions.get("direct_base_llm")
    direct_rows: dict[str, dict[str, Any]] = {}
    actual_prediction_hashes: dict[str, str] = {}
    for system_id, path in sorted(predictions.items()):
        if not path.is_file():
            problems.append(f"prediction_file_missing:{system_id}")
            continue
        observed = _sha256(path)
        actual_prediction_hashes[system_id] = observed
        if observed != expected_hashes.get(system_id):
            problems.append(f"prediction_bytes_do_not_match_t31:{system_id}")
    if direct_path is not None and direct_path.is_file() and actual_prediction_hashes.get("direct_base_llm") == expected_hashes.get("direct_base_llm"):
        direct_rows = _load_prediction(direct_path, "direct_base_llm", ids)
        recomputed_total = sum(
            t39._terminal_cost(policy, str(gold[record_id]["terminal_strategy"]), str(direct_rows[record_id].get("terminal_strategy") or ""))
            for record_id in ids
        )
        reported = ((t31.get("systems") or {}).get("direct_base_llm") or {})
        reported_total = reported.get("total_cost")
        reported_mean = reported.get("mean_cost")
        if reported.get("n") != len(ids):
            problems.append("t31_direct_base_denominator_mismatch")
        if not isinstance(reported_total, (int, float)) or not math.isclose(recomputed_total, float(reported_total), rel_tol=0.0, abs_tol=1e-12):
            problems.append("t31_direct_base_total_cost_not_reproduced")
        if not isinstance(reported_mean, (int, float)) or not math.isclose(recomputed_total / len(ids), float(reported_mean), rel_tol=0.0, abs_tol=1e-12):
            problems.append("t31_direct_base_mean_cost_not_reproduced")
    else:
        recomputed_total = None
        problems.append("direct_base_prediction_bytes_unavailable")

    status = "VERIFY_PASSED" if not problems else "NOT_COMPUTED"
    return {
        "status": status,
        "scope": "non_protected_pilot120_early_analysis_only",
        "valid_for_official_use": False,
        "must_not_influence_training_selection_or_tuning": True,
        "no_new_inference": True,
        "historical_result_is_not_replaced": True,
        "reconciliation": {
            "historical_t31_report": {"path": str(t31_path.resolve()), "sha256": _sha256(t31_path)},
            "historical_run_manifest": {"path": str(run_manifest_path.resolve()), "sha256": _sha256(run_manifest_path)},
            "policy": {"path": str(policy_path.resolve()), "sha256": _sha256(policy_path), "policy_id": policy.get("policy_id")},
            "frozen_inputs": _input_provenance(frozen_paths),
            "historical_prediction_sha256": actual_prediction_hashes,
            "reported_direct_base_cost": ((t31.get("systems") or {}).get("direct_base_llm") or {}),
            "recomputed_direct_base_cost": (
                {"n": len(ids), "total_cost": recomputed_total, "mean_cost": recomputed_total / len(ids)}
                if recomputed_total is not None
                else _not_computed("direct_base_prediction_bytes_unavailable")
            ),
            "problems": problems,
        },
    }


def _base_adapter_disagreements(
    ids: list[str], matrix: dict[str, dict[str, dict[str, Any]]]
) -> dict[str, Any]:
    base = matrix["direct_base_llm"]
    adapter = matrix["t28_selected_adapter_llm"]
    rows: list[dict[str, Any]] = []
    raw_output_disagreement_ids: list[str] = []
    core_fields = ("terminal_strategy", "ambiguity_types", "capability_status", "schema_valid", "failed", "error")
    for record_id in ids:
        base_signature = t39._prediction_signature(base[record_id])
        adapter_signature = t39._prediction_signature(adapter[record_id])
        base_core = {field: base_signature[field] for field in core_fields}
        adapter_core = {field: adapter_signature[field] for field in core_fields}
        if base_signature["raw_output_sha256"] != adapter_signature["raw_output_sha256"]:
            raw_output_disagreement_ids.append(record_id)
        if base_core != adapter_core:
            rows.append(
                {
                    "record_id": record_id,
                    "terminal_strategy_disagrees": base_signature["terminal_strategy"] != adapter_signature["terminal_strategy"],
                    "ambiguity_types_disagree": base_signature["ambiguity_types"] != adapter_signature["ambiguity_types"],
                    "capability_status_disagrees": base_signature["capability_status"] != adapter_signature["capability_status"],
                    "base": base_core,
                    "adapter": adapter_core,
                    "base_raw_output_sha256": base_signature["raw_output_sha256"],
                    "adapter_raw_output_sha256": adapter_signature["raw_output_sha256"],
                }
            )
    return {
        "denominator": len(ids),
        "n_core_prediction_signature_disagreements": len(rows),
        "core_prediction_disagreement_rows": rows,
        "n_raw_output_hash_disagreements": len(raw_output_disagreement_ids),
        "raw_output_hash_disagreement_record_ids": raw_output_disagreement_ids,
        "raw_output_hash_is_not_an_interpretation_or_semantic_metric": True,
    }


def _slice_report(
    *,
    source: list[dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    policy: dict[str, Any],
    predictions: dict[str, Path],
    input_reports: dict[str, Path],
) -> dict[str, Any]:
    ids = [str(row["record_id"]) for row in source]
    matrix = {system_id: _load_prediction(path, system_id, ids) for system_id, path in sorted(predictions.items())}
    eligibility = {system_id: t39._metric_eligibility(ids, rows) for system_id, rows in matrix.items()}
    strata = [row for row in t39._strata(source, gold) if row["family"] in SLICE_FAMILIES]
    slices: list[dict[str, Any]] = []
    for stratum in strata:
        member_ids = list(stratum["record_ids"])
        if stratum["count_only"]:
            metrics: dict[str, Any] = _not_computed(
                "insufficient_support_count_only",
                n=len(member_ids),
                minimum_support_for_analytic_interpretation=stratum["minimum_support_for_analytic_interpretation"],
            )
        else:
            metrics = {
                system_id: t39._system_metrics(member_ids, rows, gold, policy, eligibility[system_id])
                for system_id, rows in matrix.items()
            }
        slices.append({
            **stratum,
            "metrics": metrics,
        })
    return {
        "status": "T45_SAVED_OUTPUT_SLICE_REPORT_COMPLETE",
        "scope": "non_protected_pilot120_early_analysis_only",
        "valid_for_official_use": False,
        "must_not_influence_training_selection_or_tuning": True,
        "no_new_inference": True,
        "not_interpretation_or_wording_evaluation": True,
        "not_single_ambiguity_evaluation": True,
        "not_isolated_scene_dialogue_or_capability_effect": True,
        "not_generalisation_evaluation": True,
        "denominator": len(ids),
        "systems": {
            system_id: {
                "prediction": {"path": str(path.resolve()), "sha256": _sha256(path)},
                "metric_eligibility": eligibility[system_id],
                "overall_metrics": t39._system_metrics(ids, matrix[system_id], gold, policy, eligibility[system_id]),
            }
            for system_id, path in sorted(predictions.items())
        },
        "slice_families": ["compound_depth", "ambiguity_type", "capability_status", "dialogue_presence"],
        "ambiguity_type_minimum_support_for_analytic_interpretation": 15,
        "slices": slices,
        "all_base_adapter_disagreements": _base_adapter_disagreements(ids, matrix),
        "unavailable_claims": {
            "interpretation_cpc_candidate_resolution_wording_and_silent_resolution": _not_computed("pilot120_gold_lacks_required_fields"),
            "single_ambiguity_performance": _not_computed("no_eligible_pilot120_records_and_no_separate_frozen_study"),
            "isolated_scene_dialogue_capability_effects": _not_computed("only_historical_all_context_removal_is_available"),
            "generalisation": _not_computed("no_independent_family_disjoint_confirmation_set"),
        },
        "saved_input_reports": {
            name: {"path": str(path.resolve()), "sha256": _sha256(path)}
            for name, path in sorted(input_reports.items())
            if path.is_file()
        },
    }


def run(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    source, gold, manifest, frozen_paths = _frozen_inputs(args.root.resolve())
    policy_path = args.policy.resolve()
    policy = _load_json(policy_path)
    if policy.get("scope") != "non_protected_pilot120_early_analysis_only" or policy.get("valid_for_official_use") is not False:
        raise ValueError("t45_policy_boundary_invalid")
    predictions = dict(args.prediction)
    input_reports = dict(args.input_report)
    reconciliation = _reconciliation(
        source=source,
        gold=gold,
        manifest=manifest,
        frozen_paths=frozen_paths,
        policy_path=policy_path,
        t31_path=args.t31_report.resolve(),
        run_manifest_path=args.run_manifest.resolve(),
        predictions=predictions,
    )
    slices = _slice_report(
        source=source,
        gold=gold,
        policy=policy,
        predictions=predictions,
        input_reports=input_reports,
    )
    _write_json(args.reconciliation_output.resolve(), reconciliation)
    _write_json(args.slice_output.resolve(), slices)
    return reconciliation, slices


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--t31-report", type=Path, required=True)
    parser.add_argument("--run-manifest", type=Path, required=True)
    parser.add_argument("--prediction", action="append", default=[], type=_parse_mapping, required=True)
    parser.add_argument("--input-report", action="append", default=[], type=_parse_mapping)
    parser.add_argument("--reconciliation-output", type=Path, required=True)
    parser.add_argument("--slice-output", type=Path, required=True)
    args = parser.parse_args()
    reconciliation, _slices = run(args)
    print(json.dumps({"status": reconciliation["status"], "reconciliation_output": str(args.reconciliation_output), "slice_output": str(args.slice_output)}, sort_keys=True))


if __name__ == "__main__":
    main()
