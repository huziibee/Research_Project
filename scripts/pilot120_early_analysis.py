#!/usr/bin/env python3
"""Hash-bound non-protected T31--T33 analysis over completed Pilot-120 outputs.

These results are descriptive, evaluation-only evidence. They must not tune,
select, train, or otherwise alter a model, adapter, prompt, or policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.evaluation import pilot_120 as p120  # noqa: E402


TERMINALS = ("execute", "clarify", "face_preserving_rejection")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_not_object:{path}")
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise SystemExit(f"early_analysis_output_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _parse_prediction_arg(value: str) -> tuple[str, Path]:
    system_id, separator, raw_path = value.partition("=")
    if not separator or not system_id or not raw_path:
        raise argparse.ArgumentTypeError("prediction must be system_id=/absolute/path.jsonl")
    return system_id, Path(raw_path)


def _load_policy(path: Path) -> dict[str, Any]:
    policy = _load_json(path)
    if policy.get("scope") != "non_protected_pilot120_early_analysis_only":
        raise ValueError("policy_scope_invalid")
    if policy.get("valid_for_official_use") is not False:
        raise ValueError("policy_official_boundary_invalid")
    if policy.get("must_not_influence_training_selection_or_tuning") is not True:
        raise ValueError("policy_tuning_boundary_invalid")
    if policy.get("terminal_labels") != list(TERMINALS):
        raise ValueError("policy_terminal_labels_invalid")
    costs = policy.get("terminal_cost")
    if not isinstance(costs, dict) or set(costs) != set(TERMINALS):
        raise ValueError("policy_terminal_cost_rows_invalid")
    for gold in TERMINALS:
        if set(costs[gold]) != set(TERMINALS):
            raise ValueError(f"policy_terminal_cost_columns_invalid:{gold}")
        for predicted in TERMINALS:
            if float(costs[gold][predicted]) < 0:
                raise ValueError("policy_negative_cost")
    bootstrap = policy.get("bootstrap") or {}
    if int(bootstrap.get("replicates", 0)) < 100 or not 0 < float(bootstrap.get("confidence_level", 0)) < 1:
        raise ValueError("policy_bootstrap_invalid")
    return policy


def _validated_matrix(
    *, root: Path, preflight_path: Path, early_gate_path: Path, paired_path: Path, predictions: list[tuple[str, Path]]
) -> tuple[list[str], dict[str, str], dict[str, dict[str, dict[str, Any]]], dict[str, Any]]:
    p120.assert_evaluation_only("early_analysis")
    preflight = _load_json(preflight_path)
    gate = _load_json(early_gate_path)
    if preflight.get("status") != "READY_FOR_T31PLUS_EARLY_ANALYSIS":
        raise ValueError("t31plus_not_ready")
    if gate.get("status") != "T29_T30_EARLY_COMPLETE_NON_PROTECTED":
        raise ValueError("t29_t30_early_matrix_not_complete")
    if preflight.get("protected_data_accessed") is not False or gate.get("protected_data_accessed") is not False:
        raise ValueError("non_protected_boundary_invalid")
    paired = _load_json(paired_path)
    if paired.get("status") != "VERIFY_PASSED" or paired.get("denominator") != p120.EXPECTED_N:
        raise ValueError("paired_comparison_not_verified")
    source = p120.load_jsonl(root / "data/annotations/pilot_120_v1/source_canonical.jsonl")
    gold = {str(row["record_id"]): row for row in p120.load_jsonl(root / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl")}
    ids = [str(row["record_id"]) for row in source]
    if len(ids) != p120.EXPECTED_N or set(ids) != set(gold):
        raise ValueError("frozen_pilot_denominator_invalid")
    matrix: dict[str, dict[str, dict[str, Any]]] = {}
    hashes: dict[str, str] = {}
    for system_id, path in predictions:
        if system_id in matrix:
            raise ValueError(f"duplicate_system_id:{system_id}")
        rows = p120.load_jsonl(path)
        by_id = {str(row.get("record_id") or ""): row for row in rows}
        if len(rows) != len(by_id) or list(by_id) != ids:
            raise ValueError(f"prediction_denominator_or_order_invalid:{system_id}")
        if any(row.get("system_id") != system_id for row in rows):
            raise ValueError(f"prediction_system_id_invalid:{system_id}")
        if any(row.get("failed") is not False or row.get("schema_valid") is not True for row in rows):
            raise ValueError(f"prediction_schema_or_failure_invalid:{system_id}")
        matrix[system_id] = by_id
        hashes[system_id] = _sha256(path)
    if paired.get("base", {}).get("predictions_sha256") != hashes.get("direct_base_llm"):
        raise ValueError("paired_direct_base_hash_mismatch")
    if paired.get("adapter", {}).get("predictions_sha256") != hashes.get("t28_selected_adapter_llm"):
        raise ValueError("paired_adapter_hash_mismatch")
    return ids, hashes, matrix, gold


def _cost(policy: dict[str, Any], gold_terminal: str, predicted_terminal: str) -> float:
    if predicted_terminal not in TERMINALS:
        return float(policy["unsupported_terminal_strategy_cost"])
    return float(policy["terminal_cost"][gold_terminal][predicted_terminal])


def _common_payload(*, policy_path: Path, policy: dict[str, Any], preflight_path: Path, early_gate_path: Path, paired_path: Path, hashes: dict[str, str]) -> dict[str, Any]:
    return {
        "scope": "non_protected_pilot120_early_analysis_only",
        "valid_for_official_use": False,
        "must_not_influence_training_selection_or_tuning": True,
        "protected_data_accessed": False,
        "policy_id": policy["policy_id"],
        "policy_sha256": _sha256(policy_path),
        "preflight_sha256": _sha256(preflight_path),
        "early_gate_sha256": _sha256(early_gate_path),
        "paired_comparison_sha256": _sha256(paired_path),
        "prediction_sha256": hashes,
    }


def run_cost(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    policy = _load_policy(args.policy)
    ids, hashes, matrix, gold = _validated_matrix(
        root=root, preflight_path=args.preflight, early_gate_path=args.early_gate, paired_path=args.paired_comparison, predictions=args.prediction
    )
    systems: dict[str, Any] = {}
    for system_id, rows in matrix.items():
        costs = [_cost(policy, str(gold[rid]["terminal_strategy"]), str(rows[rid].get("terminal_strategy") or "")) for rid in ids]
        by_gold = {
            terminal: [cost for rid, cost in zip(ids, costs) if gold[rid]["terminal_strategy"] == terminal]
            for terminal in TERMINALS
        }
        systems[system_id] = {
            "n": len(costs),
            "total_cost": sum(costs),
            "mean_cost": sum(costs) / len(costs),
            "mean_cost_by_gold_terminal": {terminal: sum(values) / len(values) for terminal, values in by_gold.items()},
        }
    payload = _common_payload(policy_path=args.policy, policy=policy, preflight_path=args.preflight, early_gate_path=args.early_gate, paired_path=args.paired_comparison, hashes=hashes)
    payload.update({"status": "T31_EARLY_COST_SENSITIVE_EVALUATION_COMPLETE", "denominator": len(ids), "systems": systems,
                    "prediction_paths": {sid: str(path.resolve()) for sid, path in args.prediction}})
    _write_json(args.output, payload)
    print(json.dumps({"status": payload["status"], "systems": sorted(systems)}, sort_keys=True))


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)
    return ordered[lower] if lower == upper else ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _two_sided_sign_pvalue(discordant_left_only: int, discordant_right_only: int) -> float:
    n = discordant_left_only + discordant_right_only
    if n == 0:
        return 1.0
    lower = min(discordant_left_only, discordant_right_only)
    probability = sum(math.comb(n, k) for k in range(lower + 1)) / (2 ** n)
    return min(1.0, 2.0 * probability)


def run_paired(args: argparse.Namespace) -> None:
    cost = _load_json(args.cost_input)
    if cost.get("status") != "T31_EARLY_COST_SENSITIVE_EVALUATION_COMPLETE":
        raise ValueError("t31_cost_artifact_not_complete")
    if cost.get("valid_for_official_use") is not False or cost.get("protected_data_accessed") is not False:
        raise ValueError("t31_cost_boundary_invalid")
    policy = _load_policy(args.policy)
    if cost.get("policy_sha256") != _sha256(args.policy):
        raise ValueError("t31_policy_hash_mismatch")
    predictions = [(str(system_id), Path(path)) for system_id, path in (cost.get("prediction_paths") or {}).items()]
    ids, hashes, matrix, gold = _validated_matrix(
        root=args.root.resolve(), preflight_path=args.preflight, early_gate_path=args.early_gate, paired_path=args.paired_comparison, predictions=predictions
    )
    if hashes != cost.get("prediction_sha256"):
        raise ValueError("t31_prediction_hash_mismatch")
    baseline = str(policy["paired_baseline_system_id"])
    if baseline not in matrix:
        raise ValueError("paired_baseline_missing")
    seed = int(policy["bootstrap"]["seed"])
    replicates = int(policy["bootstrap"]["replicates"])
    alpha = 1.0 - float(policy["bootstrap"]["confidence_level"])
    comparison: dict[str, Any] = {}
    base_correct = [matrix[baseline][rid].get("terminal_strategy") == gold[rid]["terminal_strategy"] for rid in ids]
    for system_id, rows in matrix.items():
        if system_id == baseline:
            continue
        candidate_correct = [rows[rid].get("terminal_strategy") == gold[rid]["terminal_strategy"] for rid in ids]
        deltas = [int(candidate) - int(base) for candidate, base in zip(candidate_correct, base_correct)]
        rng = random.Random(f"{seed}:{system_id}")
        bootstrap = [sum(deltas[rng.randrange(len(deltas))] for _ in deltas) / len(deltas) for _ in range(replicates)]
        candidate_only = sum(candidate and not base for candidate, base in zip(candidate_correct, base_correct))
        base_only = sum(base and not candidate for candidate, base in zip(candidate_correct, base_correct))
        comparison[system_id] = {
            "paired_terminal_accuracy_delta_vs_direct_base": sum(deltas) / len(deltas),
            "bootstrap_percentile_ci": [_percentile(bootstrap, alpha / 2), _percentile(bootstrap, 1 - alpha / 2)],
            "discordant_candidate_only_correct": candidate_only,
            "discordant_base_only_correct": base_only,
            "exact_two_sided_sign_test_p_value": _two_sided_sign_pvalue(candidate_only, base_only),
        }
    payload = _common_payload(policy_path=args.policy, policy=policy, preflight_path=args.preflight, early_gate_path=args.early_gate, paired_path=args.paired_comparison, hashes=hashes)
    payload.update({"status": "T32_EARLY_PAIRED_STATISTICS_COMPLETE", "denominator": len(ids), "baseline_system_id": baseline,
                    "bootstrap": policy["bootstrap"], "t31_cost_sha256": _sha256(args.cost_input), "comparisons": comparison})
    _write_json(args.output, payload)
    print(json.dumps({"status": payload["status"], "comparisons": len(comparison)}, sort_keys=True))


def run_ablations(args: argparse.Namespace) -> None:
    cost = _load_json(args.cost_input)
    paired = _load_json(args.paired_input)
    if cost.get("status") != "T31_EARLY_COST_SENSITIVE_EVALUATION_COMPLETE" or paired.get("status") != "T32_EARLY_PAIRED_STATISTICS_COMPLETE":
        raise ValueError("t31_or_t32_not_complete")
    if paired.get("t31_cost_sha256") != _sha256(args.cost_input):
        raise ValueError("t32_cost_input_hash_mismatch")
    policy = _load_policy(args.policy)
    if cost.get("policy_sha256") != _sha256(args.policy) or paired.get("policy_sha256") != _sha256(args.policy):
        raise ValueError("ablation_policy_hash_mismatch")
    systems = cost.get("systems") or {}
    output: list[dict[str, Any]] = []
    for spec in policy["predeclared_ablations"]:
        left, right = str(spec["left"]), str(spec["right"])
        if left not in systems or right not in systems:
            raise ValueError(f"ablation_system_missing:{spec['ablation_id']}")
        output.append({
            "ablation_id": spec["ablation_id"], "left_system_id": left, "right_system_id": right,
            "mean_cost_delta_left_minus_right": systems[left]["mean_cost"] - systems[right]["mean_cost"],
            "descriptive_only": True,
            "must_not_be_used_for_tuning_or_selection": True,
        })
    if cost.get("paired_comparison_sha256") != _sha256(args.paired_comparison):
        raise ValueError("t31_paired_comparison_hash_mismatch")
    payload = _common_payload(policy_path=args.policy, policy=policy, preflight_path=args.preflight, early_gate_path=args.early_gate, paired_path=args.paired_comparison, hashes=cost["prediction_sha256"])
    payload.update({"status": "T33_EARLY_PREDECLARED_ABLATIONS_COMPLETE", "denominator": cost["denominator"],
                    "t31_cost_sha256": _sha256(args.cost_input), "t32_paired_sha256": _sha256(args.paired_input), "ablations": output})
    _write_json(args.output, payload)
    print(json.dumps({"status": payload["status"], "ablations": len(output)}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--early-gate", type=Path, required=True)
    parser.add_argument("--paired-comparison", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    p_cost = sub.add_parser("cost")
    p_cost.add_argument("--prediction", type=_parse_prediction_arg, action="append", required=True)
    p_cost.add_argument("--output", type=Path, required=True)
    p_cost.set_defaults(run=run_cost)
    p_paired = sub.add_parser("paired")
    p_paired.add_argument("--cost-input", type=Path, required=True)
    p_paired.add_argument("--output", type=Path, required=True)
    p_paired.set_defaults(run=run_paired)
    p_ablation = sub.add_parser("ablations")
    p_ablation.add_argument("--cost-input", type=Path, required=True)
    p_ablation.add_argument("--paired-input", type=Path, required=True)
    p_ablation.add_argument("--output", type=Path, required=True)
    p_ablation.set_defaults(run=run_ablations)
    args = parser.parse_args()
    args.run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
