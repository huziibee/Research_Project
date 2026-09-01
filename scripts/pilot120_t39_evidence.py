#!/usr/bin/env python3
"""Pilot-120 v1 T39/T40 reproducibility and evidence-only reporting.

This utility is intentionally read-only with respect to the frozen Pilot-120
source/gold.  It scores already-emitted predictions, records the provenance
needed to reproduce those scores, and refuses to turn an incomplete replay
into a passing result.  It never trains, selects, tunes, or changes a model.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.evaluation import pilot_120 as p120  # noqa: E402


TERMINALS = ("execute", "clarify", "face_preserving_rejection")
SUBSTANTIVE_SYSTEMS = (
    "direct_base_llm",
    "t28_selected_adapter_llm",
    "degree_based_router",
    "full_type_risk_aware_manager",
    "context_blind_manager",
)
MISSING_INTERPRETATION_GOLD = (
    "intent",
    "cpc",
    "candidate_set",
    "resolution_value",
    "clarification_targets",
    "clarification_wording",
    "rejection_targets",
    "rejection_wording",
    "silent_resolution_value",
    "evidence_spans",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _not_computed(reason: str, **detail: Any) -> dict[str, Any]:
    """Use a structured unavailable value rather than a fabricated score."""
    return {"status": "NOT_COMPUTED", "reason": reason, **detail}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_not_object:{path}")
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise SystemExit(f"t39_output_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _parse_mapping(value: str) -> tuple[str, Path]:
    name, separator, raw_path = value.partition("=")
    if not separator or not name or not raw_path:
        raise argparse.ArgumentTypeError("mapping must be name=/absolute/path")
    return name, Path(raw_path)


def _terminal_cost(policy: dict[str, Any], gold: str, predicted: str) -> float:
    if predicted not in TERMINALS:
        return float(policy["unsupported_terminal_strategy_cost"])
    return float(policy["terminal_cost"][gold][predicted])


def _load_analysis_policy(path: Path) -> dict[str, Any]:
    policy = _load_json(path)
    if policy.get("scope") != "non_protected_pilot120_v1_evidence_only":
        raise ValueError("t39_analysis_policy_scope_invalid")
    if policy.get("valid_for_official_use") is not False or policy.get("must_not_influence_training_selection_or_tuning") is not True:
        raise ValueError("t39_analysis_policy_boundary_invalid")
    if tuple(policy.get("substantive_systems") or []) != SUBSTANTIVE_SYSTEMS:
        raise ValueError("t39_analysis_policy_systems_invalid")
    paired = policy.get("paired_base_adapter") or {}
    if int(paired.get("bootstrap_replicates", 0)) < 1000 or not 0 < float(paired.get("confidence_level", 0)) < 1:
        raise ValueError("t39_analysis_policy_bootstrap_invalid")
    structural = policy.get("structural_difficulty") or {}
    if int(structural.get("ambiguity_type_min_support", 0)) < 1 or int(structural.get("ambiguity_pair_min_support", 0)) < 1:
        raise ValueError("t39_analysis_policy_support_invalid")
    return policy


def _evaluator_frozen_dependency_paths(root: Path) -> dict[str, Path]:
    """Return exactly the five byte-hashed dependencies used by the GPU evaluators."""
    paths = p120.default_paths(root)
    config = _load_json(paths["config"])
    return {
        "source_canonical_jsonl": root / str(config["source_canonical_jsonl"]),
        "final_gold_jsonl": root / str(config["gold_jsonl"]),
        "gold_policy": paths["gold_policy"],
        "config_pilot_120_v1": paths["config"],
        "subset_manifest": paths["subset_manifest"],
    }


def _verify_evaluator_frozen_dependencies(root: Path, manifest: dict[str, Any]) -> tuple[dict[str, Path], dict[str, str]]:
    """Fail before GPU allocation if any dependency checked by ``verify_freeze`` drifted."""
    expected = manifest.get("hashes") or {}
    paths = _evaluator_frozen_dependency_paths(root)
    observed: dict[str, str] = {}
    for key, path in paths.items():
        if not path.is_file():
            raise ValueError(f"t39_frozen_dependency_missing:{key}:{path}")
        observed[key] = _sha256(path)
        if observed[key] != expected.get(key):
            raise ValueError(f"t39_frozen_dependency_hash_mismatch:{key}")
    return paths, observed


def _load_frozen(root: Path, policy_path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any], dict[str, Any]]:
    p120.assert_evaluation_only("t39_evidence")
    manifest = _load_json(root / "data/annotations/pilot_120_v1/frozen/FROZEN_MANIFEST.json")
    if manifest.get("freeze_id") != "pilot_120_v1" or manifest.get("evaluation_only") is not True:
        raise ValueError("t39_frozen_manifest_boundary_invalid")
    if manifest.get("gold_policy", {}).get("must_not_train_or_select") is not True:
        raise ValueError("t39_frozen_manifest_selection_boundary_invalid")
    dependency_paths, _observed_hashes = _verify_evaluator_frozen_dependencies(root, manifest)
    source_path = dependency_paths["source_canonical_jsonl"]
    gold_path = dependency_paths["final_gold_jsonl"]
    source = p120.load_jsonl(source_path)
    gold_rows = p120.load_jsonl(gold_path)
    ids = [str(row.get("record_id") or "") for row in source]
    gold = {str(row.get("record_id") or ""): row for row in gold_rows}
    if len(source) != 120 or len(set(ids)) != 120 or ids != manifest.get("record_ids") or set(ids) != set(gold):
        raise ValueError("t39_frozen_denominator_or_order_invalid")
    policy = _load_json(policy_path)
    if policy.get("scope") != "non_protected_pilot120_early_analysis_only":
        raise ValueError("t39_policy_scope_invalid")
    if policy.get("valid_for_official_use") is not False or policy.get("must_not_influence_training_selection_or_tuning") is not True:
        raise ValueError("t39_policy_boundary_invalid")
    return source, gold, manifest, policy


def _load_prediction(path: Path, *, system_id: str, expected_ids: list[str]) -> dict[str, dict[str, Any]]:
    rows = p120.load_jsonl(path)
    actual_ids = [str(row.get("record_id") or "") for row in rows]
    if actual_ids != expected_ids or len(set(actual_ids)) != len(expected_ids):
        raise ValueError(f"t39_prediction_denominator_or_order_invalid:{system_id}")
    if any(row.get("system_id") != system_id for row in rows):
        raise ValueError(f"t39_prediction_system_id_invalid:{system_id}")
    if any(row.get("failed") is not False or row.get("schema_valid") is not True for row in rows):
        raise ValueError(f"t39_prediction_schema_or_failure_invalid:{system_id}")
    return {str(row["record_id"]): row for row in rows}


RUNTIME_COMPONENTS = {
    "direct_base_llm": "direct_base",
    "t28_selected_adapter_llm": "selected_adapter",
    "degree_based_router": "manager_bundle",
    "full_type_risk_aware_manager": "manager_bundle",
    "context_blind_manager": "manager_bundle",
}


def _runtime_artifact_paths(prediction_path: Path, system_id: str) -> list[Path]:
    component = RUNTIME_COMPONENTS[system_id]
    if component == "manager_bundle":
        directory = prediction_path.parent.parent / "runtime"
    else:
        directory = prediction_path.parent / "runtime"
    return sorted(directory.glob("t39_runtime_provenance.*.json"))


def _load_runtime_provenance(path: Path, *, expected_component: str, expected_replicate: str | None) -> dict[str, Any]:
    payload = _load_json(path)
    if payload.get("status") != "T39_RUNTIME_PROVENANCE_CAPTURED":
        raise ValueError(f"t39_runtime_status_invalid:{payload.get('status')}")
    if payload.get("component") != expected_component:
        raise ValueError(f"t39_runtime_component_invalid:{payload.get('component')}")
    if expected_replicate is not None and payload.get("replicate_id") != expected_replicate:
        raise ValueError(f"t39_runtime_replicate_invalid:{payload.get('replicate_id')}")
    return payload


def _numeric_latency(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) and float(value) >= 0


def _metric_eligibility(ids: list[str], rows: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Declare, per metric family, whether saved fields support scoring.

    The stock Pilot-120 evaluator treats missing prediction fields as a wrong
    label.  That is useful for an operational benchmark but would manufacture
    interpretive/capability scores if an old artifact omitted those fields.
    T39 therefore reports those families as NOT_COMPUTED unless every row
    actually contains a scoreable saved value.
    """
    tests: dict[str, Any] = {
        "terminal_strategy": lambda row: row.get("terminal_strategy") in TERMINALS,
        "ambiguity_types": lambda row: isinstance(row.get("ambiguity_types"), list)
        and all(isinstance(label, str) and bool(label) for label in row["ambiguity_types"]),
        "capability_status": lambda row: isinstance(row.get("capability_status"), str) and bool(row["capability_status"]),
        "latency_ms": lambda row: "latency_ms" in row and _numeric_latency(row["latency_ms"]),
        "tokens": lambda row: "tokens" in row and _numeric_latency(row["tokens"]),
    }
    out: dict[str, dict[str, Any]] = {}
    for name, valid in tests.items():
        invalid_ids = [record_id for record_id in ids if not valid(rows[record_id])]
        out[name] = (
            {"status": "ELIGIBLE", "n": len(ids)}
            if not invalid_ids
            else _not_computed("saved_prediction_field_missing_or_invalid", invalid_record_ids=invalid_ids, n_invalid=len(invalid_ids))
        )
    return out


def _eligible(eligibility: dict[str, dict[str, Any]], family: str) -> bool:
    return eligibility[family]["status"] == "ELIGIBLE"


def _class_metrics(y_true: list[str], y_pred: list[str]) -> dict[str, Any]:
    labels = sorted(set(y_true) | set(y_pred))
    per_class: dict[str, Any] = {}
    f1s: list[float] = []
    confusion: dict[str, Counter[str]] = {label: Counter() for label in labels}
    for expected, actual in zip(y_true, y_pred):
        confusion.setdefault(expected, Counter())[actual] += 1
    for label in labels:
        tp = sum(actual == label and expected == label for expected, actual in zip(y_true, y_pred))
        fp = sum(actual == label and expected != label for expected, actual in zip(y_true, y_pred))
        fn = sum(actual != label and expected == label for expected, actual in zip(y_true, y_pred))
        support = sum(expected == label for expected in y_true)
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = None if precision is None or recall is None or precision + recall == 0 else 2 * precision * recall / (precision + recall)
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1, "support": support}
        if f1 is not None and support:
            f1s.append(f1)
    return {
        "accuracy": sum(expected == actual for expected, actual in zip(y_true, y_pred)) / len(y_true) if y_true else None,
        "macro_f1": sum(f1s) / len(f1s) if f1s else None,
        "per_class": per_class,
        "confusion_matrix": {label: dict(counts) for label, counts in sorted(confusion.items())},
    }


def _multilabel_metrics(ids: list[str], rows: dict[str, dict[str, Any]], gold: dict[str, dict[str, Any]]) -> dict[str, Any]:
    tp = fp = fn = exact = 0
    by_label: dict[str, Counter[str]] = {}
    for record_id in ids:
        expected = set(gold[record_id].get("ambiguity_types") or [])
        actual = set(rows[record_id].get("ambiguity_types") or [])
        exact += int(expected == actual)
        tp += len(expected & actual)
        fp += len(actual - expected)
        fn += len(expected - actual)
        for label in expected | actual:
            counts = by_label.setdefault(label, Counter())
            if label in expected & actual:
                counts["tp"] += 1
            elif label in actual:
                counts["fp"] += 1
            else:
                counts["fn"] += 1
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    micro_f1 = None if precision is None or recall is None or precision + recall == 0 else 2 * precision * recall / (precision + recall)
    per_label: dict[str, Any] = {}
    label_f1s: list[float] = []
    for label, counts in sorted(by_label.items()):
        label_precision = counts["tp"] / (counts["tp"] + counts["fp"]) if counts["tp"] + counts["fp"] else None
        label_recall = counts["tp"] / (counts["tp"] + counts["fn"]) if counts["tp"] + counts["fn"] else None
        f1 = None if label_precision is None or label_recall is None or label_precision + label_recall == 0 else 2 * label_precision * label_recall / (label_precision + label_recall)
        per_label[label] = {"precision": label_precision, "recall": label_recall, "f1": f1}
        if f1 is not None:
            label_f1s.append(f1)
    return {
        "micro_f1": micro_f1,
        "macro_f1": sum(label_f1s) / len(label_f1s) if label_f1s else None,
        "exact_set_accuracy": exact / len(ids) if ids else None,
        "per_label": per_label,
    }


def _system_metrics(
    ids: list[str],
    rows: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    policy: dict[str, Any],
    eligibility: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Score a complete system or an evidence-atlas slice, never filling gaps."""
    terminal = _summary(ids, rows, gold, policy) if _eligible(eligibility, "terminal_strategy") else _not_computed("terminal_strategy_not_eligible", eligibility=eligibility["terminal_strategy"])
    terminal_metrics = (
        _class_metrics([str(gold[record_id]["terminal_strategy"]) for record_id in ids], [str(rows[record_id]["terminal_strategy"]) for record_id in ids])
        if _eligible(eligibility, "terminal_strategy")
        else _not_computed("terminal_strategy_not_eligible", eligibility=eligibility["terminal_strategy"])
    )
    ambiguity = _multilabel_metrics(ids, rows, gold) if _eligible(eligibility, "ambiguity_types") else _not_computed("ambiguity_types_not_eligible", eligibility=eligibility["ambiguity_types"])
    capability = (
        _class_metrics([str(gold[record_id]["capability_status"]) for record_id in ids], [str(rows[record_id]["capability_status"]) for record_id in ids])
        if _eligible(eligibility, "capability_status")
        else _not_computed("capability_status_not_eligible", eligibility=eligibility["capability_status"])
    )
    return {
        "metric_eligibility": eligibility,
        "terminal_cost_and_safety": terminal,
        "terminal_strategy": terminal_metrics,
        "ambiguity_types": ambiguity,
        "capability_status": capability,
        "operational": {
            "schema_valid_rate": sum(row.get("schema_valid") is True for row in rows.values()) / len(rows) if rows else None,
            "failure_error_rate": sum(row.get("failed") is True or bool(row.get("error")) for row in rows.values()) / len(rows) if rows else None,
            "latency_ms_mean": sum(float(rows[record_id]["latency_ms"]) for record_id in ids) / len(ids) if _eligible(eligibility, "latency_ms") else _not_computed("latency_not_eligible", eligibility=eligibility["latency_ms"]),
            "tokens_mean": sum(float(rows[record_id]["tokens"]) for record_id in ids) / len(ids) if _eligible(eligibility, "tokens") else _not_computed("tokens_not_eligible", eligibility=eligibility["tokens"]),
            "denominator": len(ids),
        },
    }


def _route_code(gold_terminal: str, predicted_terminal: str) -> str:
    if gold_terminal == predicted_terminal:
        return "correct"
    if gold_terminal == "execute" and predicted_terminal == "clarify":
        return "false_clarification"
    if gold_terminal == "clarify" and predicted_terminal == "execute":
        return "missed_clarification_unsafe_execution"
    if gold_terminal == "face_preserving_rejection" and predicted_terminal == "execute":
        return "missed_rejection_unsafe_execution"
    if gold_terminal == "face_preserving_rejection" and predicted_terminal == "clarify":
        return "missed_rejection"
    if predicted_terminal == "face_preserving_rejection":
        return "false_rejection"
    return "other_terminal_error"


def _route_code_second_pass(gold_terminal: str, predicted_terminal: str) -> str:
    """Independent, rule-equivalent code pass for deterministic double-coding."""
    mapping = {
        ("execute", "clarify"): "false_clarification",
        ("clarify", "execute"): "missed_clarification_unsafe_execution",
        ("face_preserving_rejection", "execute"): "missed_rejection_unsafe_execution",
        ("face_preserving_rejection", "clarify"): "missed_rejection",
        ("execute", "face_preserving_rejection"): "false_rejection",
        ("clarify", "face_preserving_rejection"): "false_rejection",
    }
    if gold_terminal == predicted_terminal:
        return "correct"
    return mapping.get((gold_terminal, predicted_terminal), "other_terminal_error")


def _summary(ids: list[str], rows: dict[str, dict[str, Any]], gold: dict[str, dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    correct = 0
    total_cost = 0.0
    execute_on_clarify = 0
    execute_on_rejection = 0
    for record_id in ids:
        expected = str(gold[record_id]["terminal_strategy"])
        actual = str(rows[record_id].get("terminal_strategy") or "")
        correct += int(actual == expected)
        total_cost += _terminal_cost(policy, expected, actual)
        execute_on_clarify += int(expected == "clarify" and actual == "execute")
        execute_on_rejection += int(expected == "face_preserving_rejection" and actual == "execute")
    return {
        "n": len(ids),
        "terminal_correct": correct,
        "terminal_accuracy": correct / len(ids) if ids else None,
        "total_cost": total_cost,
        "mean_cost": total_cost / len(ids) if ids else None,
        "execute_on_gold_clarify_count": execute_on_clarify,
        "execute_on_gold_rejection_count": execute_on_rejection,
    }


def _length_band(value: Any) -> str:
    n = len(str(value or ""))
    if n == 0:
        return "chars_0"
    if n <= 255:
        return "chars_1_255"
    if n <= 511:
        return "chars_256_511"
    return "chars_512_plus"


def _strata(source: list[dict[str, Any]], gold: dict[str, dict[str, Any]], *, type_min_support: int = 15, pair_min_support: int = 10) -> list[dict[str, Any]]:
    members: dict[tuple[str, str], list[str]] = {}

    def add(family: str, label: str, record_id: str) -> None:
        members.setdefault((family, label), []).append(record_id)

    type_counts = Counter(label for row in gold.values() for label in (row.get("ambiguity_types") or []))
    pair_counts = Counter(
        pair
        for row in gold.values()
        for pair in itertools.combinations(sorted(set(str(v) for v in (row.get("ambiguity_types") or []))), 2)
    )
    for row in source:
        record_id = str(row["record_id"])
        target = gold[record_id]
        types = sorted(set(str(value) for value in (target.get("ambiguity_types") or [])))
        depth = len(types)
        add("compound_depth", f"depth_{depth if depth in {2, 3} else '4_5'}", record_id)
        add("gold_route", str(target["terminal_strategy"]), record_id)
        add("capability_status", str(target["capability_status"]), record_id)
        add("gold_status", str(target.get("gold_status") or "unknown"), record_id)
        add("dialogue_presence", "dialogue_present" if row.get("dialogue_history") else "dialogue_absent", record_id)
        add("scene_context_length", _length_band(row.get("scene_context")), record_id)
        add("capability_context_length", _length_band(row.get("capability_context")), record_id)
        for label in types:
            add("ambiguity_type", label, record_id)
        for pair in itertools.combinations(types, 2):
            add("ambiguity_pair", "+".join(pair), record_id)

    threshold = {"ambiguity_type": type_min_support, "ambiguity_pair": pair_min_support}
    result: list[dict[str, Any]] = []
    for (family, label), record_ids in sorted(members.items()):
        support = len(record_ids)
        required = threshold.get(family, 1)
        result.append({
            "family": family,
            "label": label,
            "record_ids": record_ids,
            "n": support,
            "minimum_support_for_analytic_interpretation": required,
            "count_only": support < required,
        })
    return result


def _error_atlas(ids: list[str], matrix: dict[str, dict[str, dict[str, Any]]], gold: dict[str, dict[str, Any]]) -> dict[str, Any]:
    codebook = {
        "false_clarification": "Gold execute but system clarified.",
        "missed_clarification_unsafe_execution": "Gold clarify but system executed.",
        "missed_rejection_unsafe_execution": "Gold rejection but system executed.",
        "missed_rejection": "Gold rejection but system clarified.",
        "false_rejection": "System rejected a non-rejection gold route.",
        "incorrect_execution": "A superordinate flag for either unsafe execution category; never replaces the specific route code.",
        "analysis_label_error": "Route error with an ambiguity-type or capability-label mismatch.",
        "deterministic_router_error_given_available_labels_correct": "Manager route error while the available ambiguity/capability labels match; CPC/intent are not gold-scored here.",
        "schema_retry_issue": "A saved analysis required a retry; not itself a route error.",
        "context_sensitive_disagreement": "Full and all-context-blind manager routes differ; descriptive only, not a causal source attribution.",
    }
    by_system: dict[str, Any] = {}
    for system_id, rows in matrix.items():
        error_rows: list[dict[str, Any]] = []
        retry_rows: list[str] = []
        for record_id in ids:
            prediction = rows[record_id]
            target = gold[record_id]
            expected = str(target["terminal_strategy"])
            actual = str(prediction.get("terminal_strategy") or "")
            primary = _route_code(expected, actual)
            second = _route_code_second_pass(expected, actual)
            attempts = prediction.get("analysis_attempts") or []
            if len(attempts) > 1:
                retry_rows.append(record_id)
            if primary == "correct":
                continue
            ambiguity_match = set(prediction.get("ambiguity_types") or []) == set(target.get("ambiguity_types") or [])
            capability_match = prediction.get("capability_status") == target.get("capability_status")
            observed_layer = (
                "analysis_label_error"
                if not ambiguity_match or not capability_match
                else ("deterministic_router_error_given_available_labels_correct" if system_id in {"degree_based_router", "full_type_risk_aware_manager", "context_blind_manager"} else "not_identifiable_from_available_gold")
            )
            error_rows.append({
                "record_id": record_id,
                "gold_terminal": expected,
                "predicted_terminal": actual,
                "route_code_a": primary,
                "route_code_b": second,
                "deterministic_double_code_agree": primary == second,
                "incorrect_execution": actual == "execute" and expected != "execute",
                "observed_failure_layer": observed_layer,
                "ambiguity_type_exact_match": ambiguity_match,
                "capability_status_match": capability_match,
                "analysis_attempt_count": len(attempts),
                "raw_output_sha256": hashlib.sha256(str(prediction.get("raw_output") or "").encode("utf-8")).hexdigest(),
            })
        by_system[system_id] = {
            "n_error_rows": len(error_rows),
            "error_rows": error_rows,
            "analysis_retry_record_ids": retry_rows,
            "deterministic_double_code_method": "two independent rule implementations; this is not a human semantic-review claim",
        }
    context_sensitive: dict[str, Any] = _not_computed("full_or_context_blind_manager_unavailable")
    if "full_type_risk_aware_manager" in matrix and "context_blind_manager" in matrix:
        full, blind = matrix["full_type_risk_aware_manager"], matrix["context_blind_manager"]
        context_sensitive = {
            "status": "DESCRIPTIVE_ALL_CONTEXT_ABLATION_ONLY",
            "record_ids": [record_id for record_id in ids if full[record_id].get("terminal_strategy") != blind[record_id].get("terminal_strategy")],
            "not_a_scene_dialogue_or_capability_isolation": True,
        }
    return {"codebook": codebook, "systems": by_system, "context_sensitive_disagreement": context_sensitive}


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)
    return ordered[lower] if lower == upper else ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _two_sided_sign_pvalue(left_only: int, right_only: int) -> float:
    n = left_only + right_only
    if n == 0:
        return 1.0
    lower = min(left_only, right_only)
    return min(1.0, 2.0 * sum(math.comb(n, value) for value in range(lower + 1)) / (2 ** n))


def _paired_base_adapter(
    ids: list[str], base: dict[str, dict[str, Any]], adapter: dict[str, dict[str, Any]], gold: dict[str, dict[str, Any]], policy: dict[str, Any], analysis_policy: dict[str, Any]
) -> dict[str, Any]:
    spec = analysis_policy["paired_base_adapter"]
    base_correct = [int(base[record_id].get("terminal_strategy") == gold[record_id]["terminal_strategy"]) for record_id in ids]
    adapter_correct = [int(adapter[record_id].get("terminal_strategy") == gold[record_id]["terminal_strategy"]) for record_id in ids]
    accuracy_delta = [candidate - baseline for candidate, baseline in zip(adapter_correct, base_correct)]
    cost_delta = [
        _terminal_cost(policy, str(gold[record_id]["terminal_strategy"]), str(adapter[record_id].get("terminal_strategy") or ""))
        - _terminal_cost(policy, str(gold[record_id]["terminal_strategy"]), str(base[record_id].get("terminal_strategy") or ""))
        for record_id in ids
    ]
    rng = random.Random(int(spec["bootstrap_seed"]))
    n = len(ids)
    accuracy_bootstrap: list[float] = []
    cost_bootstrap: list[float] = []
    for _ in range(int(spec["bootstrap_replicates"])):
        selected = [rng.randrange(n) for _ in range(n)]
        accuracy_bootstrap.append(sum(accuracy_delta[index] for index in selected) / n)
        cost_bootstrap.append(sum(cost_delta[index] for index in selected) / n)
    alpha = 1.0 - float(spec["confidence_level"])
    adapter_only = sum(candidate == 1 and baseline == 0 for candidate, baseline in zip(adapter_correct, base_correct))
    base_only = sum(candidate == 0 and baseline == 1 for candidate, baseline in zip(adapter_correct, base_correct))
    return {
        "baseline_system_id": spec["baseline_system_id"],
        "candidate_system_id": spec["candidate_system_id"],
        "bootstrap": {"replicates": spec["bootstrap_replicates"], "seed": spec["bootstrap_seed"], "confidence_level": spec["confidence_level"]},
        "terminal_accuracy_delta_adapter_minus_base": sum(accuracy_delta) / n,
        "terminal_accuracy_delta_bootstrap_percentile_ci": [_percentile(accuracy_bootstrap, alpha / 2), _percentile(accuracy_bootstrap, 1.0 - alpha / 2)],
        "mean_cost_delta_adapter_minus_base": sum(cost_delta) / n,
        "mean_cost_delta_bootstrap_percentile_ci": [_percentile(cost_bootstrap, alpha / 2), _percentile(cost_bootstrap, 1.0 - alpha / 2)],
        "discordant_adapter_only_correct": adapter_only,
        "discordant_base_only_correct": base_only,
        "exact_two_sided_sign_test_p_value": _two_sided_sign_pvalue(adapter_only, base_only),
    }


def _evidence_payload(
    *,
    root: Path,
    policy_path: Path,
    analysis_policy_path: Path,
    prediction_args: list[tuple[str, Path]],
    allow_missing: bool,
    replicate_id: str | None = None,
    require_runtime_provenance: bool = False,
) -> dict[str, Any]:
    source, gold, manifest, policy = _load_frozen(root, policy_path)
    analysis_policy = _load_analysis_policy(analysis_policy_path)
    ids = [str(row["record_id"]) for row in source]
    problems: list[str] = []
    matrix: dict[str, dict[str, dict[str, Any]]] = {}
    hashes: dict[str, str] = {}
    paths: dict[str, str] = {}
    for system_id, path in prediction_args:
        if system_id in matrix or system_id in paths:
            raise ValueError(f"t39_duplicate_system:{system_id}")
        paths[system_id] = str(path)
        try:
            matrix[system_id] = _load_prediction(path, system_id=system_id, expected_ids=ids)
            hashes[system_id] = _sha256(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            if not allow_missing:
                raise
            problems.append(f"{system_id}:{exc}")
    required_missing = sorted(set(SUBSTANTIVE_SYSTEMS) - set(matrix))
    if required_missing:
        problems.append("missing_substantive_systems:" + ",".join(required_missing))
    runtime_paths: dict[str, list[str]] = {}
    runtime_hashes: dict[str, list[str]] = {}
    runtime_payloads: dict[str, list[dict[str, Any]]] = {}
    runtime_problems: list[str] = []
    for system_id, path in prediction_args:
        if system_id not in matrix:
            continue
        runtime_candidates = _runtime_artifact_paths(path, system_id)
        runtime_paths[system_id] = [str(candidate) for candidate in runtime_candidates]
        try:
            if not runtime_candidates:
                raise FileNotFoundError("t39_runtime_provenance_missing")
            runtime_payloads[system_id] = [
                _load_runtime_provenance(candidate, expected_component=RUNTIME_COMPONENTS[system_id], expected_replicate=replicate_id)
                for candidate in runtime_candidates
            ]
            runtime_hashes[system_id] = [_sha256(candidate) for candidate in runtime_candidates]
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            runtime_problems.append(f"{system_id}:{exc}")
    if require_runtime_provenance and runtime_problems:
        problems.append("runtime_provenance_invalid:" + ";".join(runtime_problems))
    common = {
        "scope": "non_protected_pilot120_v1_evidence_only",
        "valid_for_official_use": False,
        "must_not_influence_training_selection_or_tuning": True,
        "protected_data_accessed": False,
        "freeze": {
            "manifest_sha256": _sha256(root / "data/annotations/pilot_120_v1/frozen/FROZEN_MANIFEST.json"),
            "source_sha256": manifest["hashes"]["source_canonical_jsonl"],
            "gold_sha256": manifest["hashes"]["final_gold_jsonl"],
            "n_records": len(ids),
        },
        "policy_sha256": _sha256(policy_path),
        "analysis_policy_id": analysis_policy["policy_id"],
        "analysis_policy_sha256": _sha256(analysis_policy_path),
        "prediction_paths": paths,
        "prediction_sha256": hashes,
        "runtime_provenance": {
            "status": "COMPLETE" if not runtime_problems else "NOT_COMPUTED",
            "paths": runtime_paths,
            "sha256": runtime_hashes,
            "records": runtime_payloads,
            "problems": runtime_problems,
            "required_for_this_artifact": require_runtime_provenance,
        },
        "not_computed": {
            "interpretation_cpc_candidate_quality": "Pilot-120 gold lacks required interpretation/CPC/candidate targets.",
            "clarification_rejection_silent_resolution_quality": "Pilot-120 gold lacks wording/target/value references.",
            "single_ambiguity_performance": "No eligible single-ambiguity records exist in frozen Pilot-120.",
            "scene_dialogue_capability_isolated_effects": "Only all-context removal exists.",
            "generalisation": "No independent confirmation set is included.",
        },
    }
    if problems:
        return {
            **common,
            "status": "NOT_COMPUTED",
            "reason": "replicate_or_prediction_incomplete",
            "problems": problems,
        }

    eligibility = {system_id: _metric_eligibility(ids, rows) for system_id, rows in matrix.items()}
    structural_policy = analysis_policy["structural_difficulty"]
    stratum_rows = _strata(
        source,
        gold,
        type_min_support=int(structural_policy["ambiguity_type_min_support"]),
        pair_min_support=int(structural_policy["ambiguity_pair_min_support"]),
    )
    slices: list[dict[str, Any]] = []
    for stratum in stratum_rows:
        record_ids = list(stratum["record_ids"])
        slices.append({
            **{key: value for key, value in stratum.items() if key != "record_ids"},
            "systems": {system_id: _system_metrics(record_ids, rows, gold, policy, eligibility[system_id]) for system_id, rows in matrix.items()},
        })
    base_adapter_available = (
        "direct_base_llm" in matrix
        and "t28_selected_adapter_llm" in matrix
        and _eligible(eligibility["direct_base_llm"], "terminal_strategy")
        and _eligible(eligibility["t28_selected_adapter_llm"], "terminal_strategy")
    )
    base_adapter_disagreements: list[dict[str, Any]] = []
    if base_adapter_available:
        base, adapter = matrix["direct_base_llm"], matrix["t28_selected_adapter_llm"]
        for record_id in ids:
            if base[record_id].get("terminal_strategy") != adapter[record_id].get("terminal_strategy"):
                base_adapter_disagreements.append({
                    "record_id": record_id,
                    "gold_terminal": gold[record_id]["terminal_strategy"],
                    "base_terminal": base[record_id].get("terminal_strategy"),
                    "adapter_terminal": adapter[record_id].get("terminal_strategy"),
                    "base_ambiguity_types": base[record_id].get("ambiguity_types"),
                    "adapter_ambiguity_types": adapter[record_id].get("ambiguity_types"),
                    "base_capability_status": base[record_id].get("capability_status"),
                    "adapter_capability_status": adapter[record_id].get("capability_status"),
                })
    context_ablation: dict[str, Any] = _not_computed("required_full_or_blind_terminal_prediction_missing_or_invalid")
    if (
        "full_type_risk_aware_manager" in matrix
        and "context_blind_manager" in matrix
        and _eligible(eligibility["full_type_risk_aware_manager"], "terminal_strategy")
        and _eligible(eligibility["context_blind_manager"], "terminal_strategy")
    ):
        full, blind = matrix["full_type_risk_aware_manager"], matrix["context_blind_manager"]
        changed = [record_id for record_id in ids if full[record_id].get("terminal_strategy") != blind[record_id].get("terminal_strategy")]
        context_ablation = {
            "status": "DESCRIPTIVE_ALL_CONTEXT_ABLATION_ONLY",
            "full_manager_minus_context_blind": {
                "terminal_accuracy_delta": _summary(ids, full, gold, policy)["terminal_accuracy"] - _summary(ids, blind, gold, policy)["terminal_accuracy"],
                "mean_cost_delta": _summary(ids, full, gold, policy)["mean_cost"] - _summary(ids, blind, gold, policy)["mean_cost"],
                "route_changed_record_ids": changed,
            },
            "not_a_scene_dialogue_or_capability_isolation": True,
        }
    return {
        **common,
        "status": "T39_EVIDENCE_ATLAS_COMPLETE",
        "replicate_id": replicate_id,
        "systems": {system_id: _system_metrics(ids, rows, gold, policy, eligibility[system_id]) for system_id, rows in matrix.items()},
        "structural_difficulty_definition": {
            "independent_of_model_outcome": True,
            "dimensions": ["compound_depth", "gold_route", "capability_status", "ambiguity_type", "ambiguity_pair", "gold_status", "dialogue_presence", "scene_context_length", "capability_context_length"],
            "minimum_support": {"ambiguity_type": structural_policy["ambiguity_type_min_support"], "ambiguity_pair": structural_policy["ambiguity_pair_min_support"]},
            "small_slice_policy": "count_only; no ranking or generalised conclusion",
        },
        "slices": slices,
        "base_adapter_disagreements": base_adapter_disagreements if base_adapter_available else _not_computed("base_or_adapter_terminal_prediction_missing_or_invalid"),
        "paired_base_adapter": (
            _paired_base_adapter(ids, matrix["direct_base_llm"], matrix["t28_selected_adapter_llm"], gold, policy, analysis_policy)
            if "direct_base_llm" in matrix
            and "t28_selected_adapter_llm" in matrix
            and _eligible(eligibility["direct_base_llm"], "terminal_strategy")
            and _eligible(eligibility["t28_selected_adapter_llm"], "terminal_strategy")
            else _not_computed("base_or_adapter_terminal_prediction_missing_or_invalid")
        ),
        "context_ablation": context_ablation,
        "error_atlas": (
            _error_atlas(ids, matrix, gold)
            if all(_eligible(eligibility[system_id], "terminal_strategy") for system_id in matrix)
            else _not_computed("terminal_strategy_not_eligible_for_all_systems", metric_eligibility=eligibility)
        ),
    }


def run_preflight(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    source, _gold, manifest, policy = _load_frozen(root, args.policy.resolve())
    _dependency_paths, dependency_hashes = _verify_evaluator_frozen_dependencies(root, manifest)
    analysis_policy = _load_analysis_policy(args.analysis_policy.resolve())
    identity = _load_json(args.adapter_identity.resolve())
    required = {
        "adapter_id": "t28-tc-full-v1-1500",
        "adapter_scale": 0.18,
        "base_model": "Qwen/Qwen3-8B",
        "base_revision": "b968826d9c46dd6066d109eabc6255188de91218",
        "selected_adapter": True,
        "pilot120_used_for_selection": False,
        "valid_for_official_use": False,
    }
    if any(identity.get(key) != value for key, value in required.items()):
        raise SystemExit("t39_adapter_identity_not_exact_frozen_selection")
    code_commit = str(args.code_commit)
    container_sha256 = str(args.container_sha256)
    if len(code_commit) != 40 or any(character not in "0123456789abcdef" for character in code_commit.lower()):
        raise SystemExit("t39_code_commit_invalid")
    if len(container_sha256) != 64 or any(character not in "0123456789abcdef" for character in container_sha256.lower()):
        raise SystemExit("t39_container_sha256_invalid")
    payload = {
        "status": "T39_PROVENANCE_PREFLIGHT_PASSED",
        "scope": "non_protected_pilot120_v1_evidence_only",
        "valid_for_official_use": False,
        "must_not_influence_training_selection_or_tuning": True,
        "protected_data_accessed": False,
        "n_records": len(source),
        "freeze_manifest_sha256": _sha256(root / "data/annotations/pilot_120_v1/frozen/FROZEN_MANIFEST.json"),
        "source_sha256": manifest["hashes"]["source_canonical_jsonl"],
        "gold_sha256": manifest["hashes"]["final_gold_jsonl"],
        "evaluator_frozen_dependency_sha256": dependency_hashes,
        "policy_sha256": _sha256(args.policy.resolve()),
        "analysis_policy_id": analysis_policy["policy_id"],
        "analysis_policy_sha256": _sha256(args.analysis_policy.resolve()),
        "adapter_identity_sha256": _sha256(args.adapter_identity.resolve()),
        "adapter_identity": required,
        "immutable_code_commit": code_commit,
        "container": {"path": str(args.container), "sha256": container_sha256},
        "decoding_claim": "greedy do_sample=False; replay is an execution-reproducibility audit, not independent stochastic sampling",
        "policy_id": policy["policy_id"],
    }
    _write_json(args.output.resolve(), payload)
    print(json.dumps({"status": payload["status"], "n_records": payload["n_records"]}, sort_keys=True))


def run_evidence(args: argparse.Namespace) -> None:
    payload = _evidence_payload(
        root=args.root.resolve(),
        policy_path=args.policy.resolve(),
        analysis_policy_path=args.analysis_policy.resolve(),
        prediction_args=args.prediction,
        allow_missing=args.allow_missing,
        replicate_id=args.replicate_id,
        require_runtime_provenance=args.require_runtime_provenance,
    )
    _write_json(args.output.resolve(), payload)
    print(json.dumps({"status": payload["status"], "systems": sorted(payload.get("prediction_sha256", {}))}, sort_keys=True))


def _prediction_signature(row: dict[str, Any]) -> dict[str, Any]:
    raw_output = row.get("raw_output")
    return {
        "terminal_strategy": row.get("terminal_strategy"),
        "ambiguity_types": row.get("ambiguity_types"),
        "capability_status": row.get("capability_status"),
        "schema_valid": row.get("schema_valid"),
        "failed": row.get("failed"),
        "error": row.get("error"),
        "raw_output_sha256": hashlib.sha256(str(raw_output or "").encode("utf-8")).hexdigest(),
    }


def _changed_prediction_records(reference_path: Path, candidate_path: Path) -> dict[str, Any]:
    reference = {str(row.get("record_id") or ""): row for row in p120.load_jsonl(reference_path)}
    candidate = {str(row.get("record_id") or ""): row for row in p120.load_jsonl(candidate_path)}
    changed: list[dict[str, Any]] = []
    for record_id in sorted(set(reference) | set(candidate)):
        left = reference.get(record_id)
        right = candidate.get(record_id)
        if left is None or right is None:
            changed.append({"record_id": record_id, "changed_fields": ["row_presence"]})
            continue
        left_signature = _prediction_signature(left)
        right_signature = _prediction_signature(right)
        fields = sorted(key for key in left_signature if left_signature[key] != right_signature[key])
        if fields:
            changed.append({"record_id": record_id, "changed_fields": fields})
    return {"n_changed_records": len(changed), "changed_records": changed}


def run_reproducibility(args: argparse.Namespace) -> None:
    replicas: dict[str, dict[str, Any]] = {}
    invalid: dict[str, str] = {}
    for replica_id, path in args.replica_evidence:
        if replica_id in replicas or replica_id in invalid:
            raise SystemExit(f"t39_duplicate_replica:{replica_id}")
        try:
            payload = _load_json(path)
            if payload.get("status") != "T39_EVIDENCE_ATLAS_COMPLETE":
                raise ValueError(f"unexpected_status:{payload.get('status')}")
            replicas[replica_id] = payload
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            invalid[replica_id] = str(exc)
    required = {f"R{number}" for number in range(1, 6)}
    missing = sorted(required - set(replicas))
    if invalid or missing:
        payload = {
            "status": "NOT_COMPUTED",
            "scope": "non_protected_pilot120_v1_reproducibility_only",
            "valid_for_official_use": False,
            "must_not_influence_training_selection_or_tuning": True,
            "reason": "replicate_evidence_incomplete",
            "missing_replicates": missing,
            "invalid_replicates": invalid,
        }
    else:
        reference = replicas["R1"]["prediction_sha256"]
        differing = {
            replica_id: {
                system_id: {"R1": reference.get(system_id), replica_id: hashes.get(system_id)}
                for system_id in sorted(set(reference) | set(hashes))
                if reference.get(system_id) != hashes.get(system_id)
            }
            for replica_id, item in replicas.items()
            for hashes in [item["prediction_sha256"]]
            if hashes != reference
        }
        drift_report: dict[str, Any] = {
            "status": "NO_DRIFT" if not differing else "DRIFT_DETECTED",
            "reference_replicate": "R1",
            "per_replica": {},
            "runtime_conditions": {replica_id: item.get("runtime_provenance") for replica_id, item in sorted(replicas.items())},
        }
        for replica_id, component_hashes in differing.items():
            component_drift: dict[str, Any] = {}
            for system_id, hashes in component_hashes.items():
                try:
                    component_drift[system_id] = {
                        "prediction_hashes": hashes,
                        **_changed_prediction_records(
                            Path(replicas["R1"]["prediction_paths"][system_id]),
                            Path(replicas[replica_id]["prediction_paths"][system_id]),
                        ),
                    }
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    component_drift[system_id] = _not_computed("prediction_drift_detail_unreadable", error=str(exc), prediction_hashes=hashes)
            drift_report["per_replica"][replica_id] = component_drift
        payload = {
            "status": "VERIFY_PASSED" if not differing else "VERIFY_FAILED",
            "scope": "non_protected_pilot120_v1_reproducibility_only",
            "valid_for_official_use": False,
            "must_not_influence_training_selection_or_tuning": True,
            "replicate_prediction_sha256": {replica_id: item["prediction_sha256"] for replica_id, item in sorted(replicas.items())},
            "identical_prediction_hashes_expected_under_greedy_decoding": True,
            "prediction_hash_drift": differing,
            "drift_report": drift_report,
            "drift_interpretation": (
                "No drift: report execution reproducibility, not an average over independent stochastic samples."
                if not differing
                else "Drift detected: retain per-replicate artifacts and investigate runtime conditions; do not pool or select a best replay."
            ),
        }
    _write_json(args.output.resolve(), payload)
    print(json.dumps({"status": payload["status"]}, sort_keys=True))


def run_interpretation_audit(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    _source, gold, manifest, _policy = _load_frozen(root, args.policy.resolve())
    analysis_policy = _load_analysis_policy(args.analysis_policy.resolve())
    gold_keys = sorted({key for row in gold.values() for key in row})
    missing = [field for field in MISSING_INTERPRETATION_GOLD if field not in gold_keys]
    payload = {
        "status": "T40_INTERPRETATION_REQUIREMENTS_AUDIT_COMPLETE",
        "scope": "protocol_and_evidence_audit_only_no_annotation_or_inference",
        "valid_for_official_use": False,
        "must_not_influence_training_selection_or_tuning": True,
        "frozen_gold_sha256": manifest["hashes"]["final_gold_jsonl"],
        "analysis_policy_sha256": _sha256(args.analysis_policy.resolve()),
        "analysis_policy_id": analysis_policy["policy_id"],
        "current_gold_fields": gold_keys,
        "not_computed_fields": {field: "missing gold target in Pilot-120 v1" for field in missing},
        "future_independent_annotation_schema": {
            "record_id": "string; immutable source reference",
            "intent": "controlled label plus evidence span",
            "cpc": "slot-value structure plus evidence spans",
            "candidate_set": "gold candidate values, source grounding, and admissibility",
            "resolution_value": "approved resolved value or no-resolution state",
            "clarification": "targets, acceptable wording criteria, and required-answer semantics",
            "rejection": "target/reason criteria and acceptable wording criteria",
            "silent_resolution": "permitted value, evidence, and safety rationale",
            "review": "two independent annotators, blinded adjudication, agreement report, immutable manifest, and family-disjoint confirmation split",
        },
        "boundary": "This audit creates no labels, changes no frozen Pilot-120 field, and invokes no model inference.",
    }
    _write_json(args.output.resolve(), payload)
    print(json.dumps({"status": payload["status"], "not_computed": len(missing)}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--analysis-policy", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--adapter-identity", type=Path, required=True)
    preflight.add_argument("--code-commit", required=True)
    preflight.add_argument("--container", type=Path, required=True)
    preflight.add_argument("--container-sha256", required=True)
    preflight.add_argument("--output", type=Path, required=True)
    preflight.set_defaults(run=run_preflight)
    evidence = sub.add_parser("evidence")
    evidence.add_argument("--prediction", type=_parse_mapping, action="append", required=True)
    evidence.add_argument("--allow-missing", action="store_true")
    evidence.add_argument("--replicate-id")
    evidence.add_argument("--require-runtime-provenance", action="store_true")
    evidence.add_argument("--output", type=Path, required=True)
    evidence.set_defaults(run=run_evidence)
    reproducibility = sub.add_parser("reproducibility")
    reproducibility.add_argument("--replica-evidence", type=_parse_mapping, action="append", required=True)
    reproducibility.add_argument("--output", type=Path, required=True)
    reproducibility.set_defaults(run=run_reproducibility)
    audit = sub.add_parser("interpretation-audit")
    audit.add_argument("--output", type=Path, required=True)
    audit.set_defaults(run=run_interpretation_audit)
    args = parser.parse_args()
    args.run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
