#!/usr/bin/env python3
"""Generate and score Pilot-120 predictions for locally runnable systems.

Evaluation-only. Does not modify the frozen benchmark, gold, prompts, or
thresholds. Constant policy baselines emit terminal strategy only; ambiguity
and capability fields are explicitly unsupported (null), never gold-leaked.

Systems that require a StructuredAnalysis provider/cache or cluster GPU are
documented under outputs/pilot_120/cluster_systems_pending.json and are not
fabricated here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.evaluation import pilot_120 as p120
from ambiguity_manager.io_guard import resolve_writable_path
from ambiguity_manager.systems.hashing import sha256_json
from ambiguity_manager.systems.variants import SYSTEM_IDS, load_system_variants

PILOT_CONFIG = Path("configs/evaluation/pilot_120_v1.json")
DEFAULT_OUT = Path("outputs/pilot_120/local_systems")
BOOTSTRAP_SEED = 20260807
BOOTSTRAP_B = 2000

# Constant policy routes already implemented in system_variants_v1 / variants.py.
# Emit Pilot-120 rows without inventing StructuredAnalysis.
CONSTANT_TERMINAL_SYSTEMS: dict[str, str] = {
    "always_execute": "execute",
    "always_clarify": "clarify",
    "always_silently_resolve": "silently_resolve",
}

TERMINALS_FOR_CI = ("execute", "clarify", "face_preserving_rejection")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_frozen_integrity(root: Path) -> dict[str, Any]:
    """Hard-stop if frozen Pilot-120 hashes are wrong."""
    paths = p120.default_paths()
    manifest_path = paths["freeze_dir"] / "FROZEN_MANIFEST.json"
    if not manifest_path.exists():
        raise p120.Pilot120Error(f"missing frozen manifest: {manifest_path}")

    manifest = p120.load_json(manifest_path)
    config = p120.load_json(root / PILOT_CONFIG)
    gold_path = root / config["gold_jsonl"]
    source_path = root / config["source_canonical_jsonl"]

    if not manifest.get("evaluation_only", False):
        raise p120.Pilot120Error("manifest evaluation_only is not true")
    if config.get("role") != "evaluation_only":
        raise p120.Pilot120Error("evaluation config role is not evaluation_only")
    if config.get("must_not_use_for_training_or_model_selection") is not True:
        raise p120.Pilot120Error("config missing training-forbidden flag")

    gold_rows = p120.load_jsonl(gold_path)
    source_rows = p120.load_jsonl(source_path)
    if len(gold_rows) != p120.EXPECTED_N or len(source_rows) != p120.EXPECTED_N:
        raise p120.Pilot120Error(
            f"expected {p120.EXPECTED_N} gold/source rows; "
            f"got gold={len(gold_rows)} source={len(source_rows)}"
        )

    hashes = manifest.get("hashes") or {}
    checks = {
        "source_canonical_jsonl": source_path,
        "final_gold_jsonl": gold_path,
        "gold_policy": paths["gold_policy"],
        "config_pilot_120_v1": root / PILOT_CONFIG,
    }
    mismatches = []
    observed: dict[str, str] = {}
    for key, path in checks.items():
        got = _sha256_file(path)
        observed[key] = got
        expected = hashes.get(key)
        if expected is None or got != expected:
            mismatches.append({"key": key, "expected": expected, "observed": got})

    if mismatches:
        raise p120.Pilot120Error(
            "frozen benchmark hash mismatch — refusing evaluation: "
            + json.dumps(mismatches)
        )

    p120.assert_evaluation_only("evaluate")
    try:
        p120.assert_evaluation_only("train")
        train_blocked = False
    except p120.Pilot120Error:
        train_blocked = True
    if not train_blocked:
        raise p120.Pilot120Error("training loader guard failed to block train purpose")

    return {
        "ok": True,
        "n_gold": len(gold_rows),
        "n_source": len(source_rows),
        "claim": manifest.get("claim"),
        "hashes_verified": observed,
        "config_id": config.get("config_id"),
        "gold_policy_decision": config.get("gold_policy_decision"),
    }


def _prediction_row(
    *,
    record_id: str,
    system_id: str,
    system_version: str,
    terminal_strategy: str | None,
    config_hash: str,
    latency_ms: float | None = None,
    error: str | None = None,
    failed: bool = False,
    raw_output: Any = None,
    parsed: dict[str, Any] | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    schema_valid = (not failed) and (error is None) and bool(terminal_strategy)
    row: dict[str, Any] = {
        "record_id": record_id,
        "system_id": system_id,
        "system_version": system_version,
        "model_id": model_id,
        "prompt_config_hash": config_hash,
        "terminal_strategy": terminal_strategy,
        "ambiguity_types": None,
        "capability_status": None,
        "supports_ambiguity_prediction": False,
        "supports_capability_prediction": False,
        "fields_unsupported": ["ambiguity_types", "capability_status"],
        "raw_output": raw_output,
        "parsed": parsed
        or {
            "terminal_strategy": terminal_strategy,
            "forced_route": terminal_strategy,
        },
        "schema_valid": schema_valid,
        "failed": failed,
        "error": error,
        "execution_mode": "deterministic-local",
    }
    # Evaluator only appends when the key is present; omit nulls.
    if latency_ms is not None:
        row["latency_ms"] = latency_ms
    return row


def generate_constant_predictions(
    *,
    system_id: str,
    record_ids: list[str],
    config_hash: str,
    system_version: str = "1.0.0",
) -> list[dict[str, Any]]:
    if system_id not in CONSTANT_TERMINAL_SYSTEMS:
        raise KeyError(system_id)
    terminal = CONSTANT_TERMINAL_SYSTEMS[system_id]
    rows: list[dict[str, Any]] = []
    for rid in record_ids:
        t0 = time.perf_counter()
        row = _prediction_row(
            record_id=rid,
            system_id=system_id,
            system_version=system_version,
            terminal_strategy=terminal,
            config_hash=config_hash,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            raw_output={"forced_route": terminal, "analysis": None},
        )
        rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path = resolve_writable_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def dump_json(path: Path, obj: Any) -> None:
    path = resolve_writable_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def validate_prediction_file(path: Path, expected_ids: list[str]) -> dict[str, Any]:
    rows = p120.load_jsonl(path)
    ids = [str(r.get("record_id") or "") for r in rows]
    missing = [i for i in expected_ids if i not in set(ids)]
    extras = [i for i in ids if i not in set(expected_ids)]
    dupes = [rid for rid, c in Counter(ids).items() if c > 1]
    return {
        "path": str(path.as_posix()),
        "n_rows": len(rows),
        "n_expected": len(expected_ids),
        "unique_ids": len(set(ids)),
        "missing_ids": missing,
        "extra_ids": extras,
        "duplicate_ids": dupes,
        "ok": (
            len(rows) == len(expected_ids)
            and not missing
            and not extras
            and not dupes
            and ids == expected_ids
        ),
    }


def _terminal_metrics(y_true: list[str], y_pred: list[str]) -> dict[str, Any]:
    """Match frozen evaluator class set + _prf macro-F1 definition."""
    n = len(y_true)
    acc = sum(t == p for t, p in zip(y_true, y_pred)) / n if n else 0.0
    labels = sorted(set(y_true) | set(y_pred))
    prf = p120._prf(y_true, y_pred, labels)
    per = prf["per_class"]

    def _f1(label: str) -> float | None:
        cell = per.get(label) or {}
        return cell.get("f1")

    return {
        "accuracy": acc,
        "macro_f1": prf["macro_f1"],
        "execute_f1": _f1("execute"),
        "clarify_f1": _f1("clarify"),
        "rejection_f1": _f1("face_preserving_rejection"),
        "per_class": per,
    }


def bootstrap_terminal_ci(
    y_true: list[str],
    y_pred: list[str],
    *,
    n_boot: int = BOOTSTRAP_B,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Percentile bootstrap 95% CIs for primary terminal metrics."""
    import random

    rng = random.Random(seed)
    n = len(y_true)
    keys = ("accuracy", "macro_f1", "execute_f1", "clarify_f1", "rejection_f1")
    samples: dict[str, list[float]] = {k: [] for k in keys}
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        yt = [y_true[i] for i in idx]
        yp = [y_pred[i] for i in idx]
        m = _terminal_metrics(yt, yp)
        for k in keys:
            v = m[k]
            if v is not None:
                samples[k].append(float(v))

    out: dict[str, Any] = {"n_boot": n_boot, "seed": seed, "metrics": {}}
    point = _terminal_metrics(y_true, y_pred)
    for k in keys:
        vals = sorted(samples[k])
        if not vals:
            out["metrics"][k] = {"point": point[k], "ci95": None}
            continue
        lo = vals[int(0.025 * (len(vals) - 1))]
        hi = vals[int(0.975 * (len(vals) - 1))]
        out["metrics"][k] = {"point": point[k], "ci95": [lo, hi], "n_samples": len(vals)}
    out["support"] = {lab: sum(t == lab for t in y_true) for lab in TERMINALS_FOR_CI}
    return out


def paired_bootstrap_accuracy_delta(
    y_true: list[str],
    y_pred_a: list[str],
    y_pred_b: list[str],
    *,
    n_boot: int = BOOTSTRAP_B,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    import random

    rng = random.Random(seed + 17)
    n = len(y_true)
    deltas: list[float] = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        acc_a = sum(y_true[i] == y_pred_a[i] for i in idx) / n
        acc_b = sum(y_true[i] == y_pred_b[i] for i in idx) / n
        deltas.append(acc_a - acc_b)
    deltas.sort()
    point = (
        sum(t == p for t, p in zip(y_true, y_pred_a)) / n
        - sum(t == p for t, p in zip(y_true, y_pred_b)) / n
    )
    return {
        "metric": "terminal_accuracy_delta",
        "point": point,
        "ci95": [deltas[int(0.025 * (n_boot - 1))], deltas[int(0.975 * (n_boot - 1))]],
        "n_boot": n_boot,
        "seed": seed + 17,
    }


def extract_aligned_terminals(
    gold_by_id: dict[str, dict[str, Any]],
    pred_rows: list[dict[str, Any]],
    expected_ids: list[str],
) -> tuple[list[str], list[str]]:
    pred_by_id = {str(r["record_id"]): r for r in pred_rows}
    y_true: list[str] = []
    y_pred: list[str] = []
    for rid in expected_ids:
        y_true.append(str(gold_by_id[rid]["terminal_strategy"]))
        p = pred_by_id.get(rid) or {}
        y_pred.append(str(p.get("terminal_strategy") or "<missing>"))
    return y_true, y_pred


def failure_analysis(
    gold_by_id: dict[str, dict[str, Any]],
    system_preds: dict[str, list[dict[str, Any]]],
    expected_ids: list[str],
) -> dict[str, Any]:
    """Descriptive only — do not feed into tuning."""
    analyses: dict[str, Any] = {}
    for system_id, rows in system_preds.items():
        pred_by_id = {str(r["record_id"]): r for r in rows}
        confusion: Counter[tuple[str, str]] = Counter()
        examples: dict[str, list[str]] = {}
        for rid in expected_ids:
            g = gold_by_id[rid]
            p = pred_by_id[rid]
            gt = str(g["terminal_strategy"])
            pr = str(p.get("terminal_strategy") or "<missing>")
            confusion[(gt, pr)] += 1
            if gt != pr:
                key = f"{gt}->{pr}"
                examples.setdefault(key, []).append(rid)

        analyses[system_id] = {
            "note": (
                "Constant terminal policy only; ambiguity/capability intentionally "
                "unsupported (null). Do not tune prompts/thresholds from this analysis."
            ),
            "terminal_confusion_gold_to_pred": {
                f"{a}->{b}": c for (a, b), c in sorted(confusion.items())
            },
            "error_patterns": {
                "execute_to_clarify": confusion.get(("execute", "clarify"), 0),
                "clarify_to_execute": confusion.get(("clarify", "execute"), 0),
                "rejection_false_negatives": sum(
                    c
                    for (g, p), c in confusion.items()
                    if g == "face_preserving_rejection" and p != "face_preserving_rejection"
                ),
                "rejection_false_positives": sum(
                    c
                    for (g, p), c in confusion.items()
                    if g != "face_preserving_rejection" and p == "face_preserving_rejection"
                ),
                "non_pilot_terminal_emitted": sum(
                    c
                    for (g, p), c in confusion.items()
                    if p not in p120.TERMINALS and p != "<missing>"
                ),
            },
            "example_ids_by_pattern": {k: v[:8] for k, v in sorted(examples.items())},
            "unsupported_fields": ["ambiguity_types", "capability_status"],
            "schema_failures": sum(1 for r in rows if r.get("failed") or r.get("error")),
        }
    return {
        "descriptive_only": True,
        "must_not_tune_from_this": True,
        "systems": analyses,
        "cross_system_notes": [
            "always_execute captures the gold majority (execute) but cannot reject or clarify.",
            "always_clarify recovers all clarify gold at the cost of false clarifications on execute/reject.",
            "always_silently_resolve emits silently_resolve, which is not a Pilot-120 terminal label, so terminal match is structurally zero.",
            "No StructuredAnalysis cache exists for Pilot-120 outside synthetic fixtures; degree_based_router and managers remain blocked.",
        ],
    }


def build_system_inventory() -> dict[str, Any]:
    variants = load_system_variants()
    by_id = {s["system_id"]: s for s in variants["systems"]}
    inventory = []

    for sid in SYSTEM_IDS:
        meta = by_id[sid]
        if sid in CONSTANT_TERMINAL_SYSTEMS:
            inventory.append(
                {
                    "system_id": sid,
                    "description": f"Constant forced route → {CONSTANT_TERMINAL_SYSTEMS[sid]}",
                    "implementation": "src/ambiguity_manager/systems/variants.py",
                    "config": "configs/manager/system_variants_v1.json",
                    "execution_mode": "deterministic-local",
                    "runnable_now": True,
                    "credentials_required": False,
                    "model_provider": None,
                    "prompt_config_hash_source": "system_variants_v1.json",
                    "notes": (
                        "Run via scripts/evaluate_pilot_120_local_systems.py without "
                        "StructuredAnalysis; ambiguity/capability fields unsupported."
                    ),
                }
            )
        elif sid == "degree_based_router":
            inventory.append(
                {
                    "system_id": sid,
                    "description": "Scalar uncertainty thresholds on shared full_context analysis",
                    "implementation": "src/ambiguity_manager/systems/variants.py",
                    "config": "configs/manager/system_variants_v1.json",
                    "execution_mode": "cluster-required",
                    "runnable_now": False,
                    "reason": (
                        "Requires approved full_context StructuredAnalysis cache from a "
                        "live analysis provider (T27F/T28 stack); no Pilot-120 cache exists "
                        "locally and gold-leaked analysis is forbidden."
                    ),
                    "credentials_required": False,
                    "model_provider": "structured_analysis_provider (cluster)",
                    "thresholds": variants.get("degree_router_thresholds"),
                }
            )
        elif sid == "direct_base_llm":
            inventory.append(
                {
                    "system_id": sid,
                    "description": "Direct base LLM interpretation (no shared analysis cache)",
                    "implementation": "src/ambiguity_manager/systems/variants.py",
                    "config": "configs/model/selected_identities_v1.json",
                    "execution_mode": "cluster-required",
                    "runnable_now": False,
                    "reason": (
                        "Requires injected DirectLLMProvider loading selected base "
                        "Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218; no local "
                        "API-hosted or lightweight provider is configured. Zero-shot bakeoff rejected."
                    ),
                    "credentials_required": False,
                    "model_provider": "Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218",
                }
            )
        elif sid == "context_blind_manager":
            inventory.append(
                {
                    "system_id": sid,
                    "description": "Full manager on context-ablated input",
                    "implementation": "src/ambiguity_manager/systems/variants.py",
                    "config": "configs/manager/system_variants_v1.json",
                    "execution_mode": "cluster-required",
                    "runnable_now": False,
                    "reason": "Requires context_blind StructuredAnalysis cache or live provider; awaits selected model strategy / T28 adapter path.",
                    "credentials_required": False,
                    "model_provider": "structured_analysis_provider + DeterministicRouter",
                }
            )
        elif sid == "full_type_risk_aware_manager":
            inventory.append(
                {
                    "system_id": sid,
                    "description": "Full type/risk/capability manager with DeterministicRouter",
                    "implementation": "src/ambiguity_manager/systems/manager.py",
                    "config": "configs/manager/system_variants_v1.json",
                    "execution_mode": "cluster-required",
                    "runnable_now": False,
                    "reason": (
                        "Requires full_context analysis + T28 selected adapter "
                        "(selected_adapter=true). T28 packaging/selection incomplete."
                    ),
                    "credentials_required": False,
                    "model_provider": "T28 adapter on Qwen3-8B (not selected)",
                    "awaits_t28_adapter": meta.get("awaits_t28_adapter", True),
                }
            )
        else:
            inventory.append(
                {
                    "system_id": sid,
                    "description": "registered system",
                    "execution_mode": "unknown",
                    "runnable_now": False,
                    "reason": "unclassified",
                    "config_meta": meta,
                }
            )

    inventory.append(
        {
            "system_id": "t28_full_type_risk_aware_manager_qlora_r5_retry5",
            "description": "Proposed T28 QLoRA full manager (handoff artifact)",
            "implementation": "outputs/t28_r5/evidence/t28_pilot120_handoff.json",
            "execution_mode": "cluster-required",
            "runnable_now": False,
            "reason": (
                "T28 incomplete for Pilot-120: selected_adapter=false; source-dev eval / "
                "frozen checkpoint selection / packaging / clean-load still required. "
                "MUST NOT run on Pilot-120 until selected_adapter=true."
            ),
            "credentials_required": False,
            "model_provider": "Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 + LoRA r5-retry5",
        }
    )

    return {
        "registry": "SYSTEM_IDS + T28 handoff",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "systems": inventory,
        "not_implemented_as_registry_ids": [
            "majority_baseline",
            "rule_based_ambiguity_manager",
            "heuristic_router",
            "prompt_only_manager",
            "base_manager",
            "api_hosted_llm",
            "api_hosted_manager",
        ],
    }


def build_cluster_pending() -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prediction_schema": {
            "required_fields": [
                "record_id",
                "terminal_strategy",
                "ambiguity_types",
                "capability_status",
                "system_id",
                "schema_valid",
                "failed",
                "error",
            ],
            "optional_fields": [
                "latency_ms",
                "tokens",
                "raw_output",
                "parsed",
                "model_id",
                "prompt_config_hash",
                "system_version",
            ],
            "n_rows_required": 120,
            "unique_record_ids": True,
            "must_match_frozen_pilot_ids": True,
            "evaluate_command": (
                "python -m ambiguity_manager.evaluation.pilot_120_cli evaluate "
                "--config configs/evaluation/pilot_120_v1.json "
                "--predictions <PREDICTIONS.jsonl>"
            ),
        },
        "deferred_systems": [
            {
                "system_id": "degree_based_router",
                "reason_cluster_needed": (
                    "Needs full_context StructuredAnalysis for all 120 Pilot records from "
                    "cluster analysis provider; thresholds unfrozen for official use."
                ),
                "model_base_model_id": "analysis from selected base / future T28 analysis stack",
                "adapter_id_path": None,
                "inference_config": {
                    "config": "configs/manager/system_variants_v1.json",
                    "degree_router_thresholds": load_system_variants().get(
                        "degree_router_thresholds"
                    ),
                    "required_analysis_variant": "full_context",
                },
                "expected_output_filename": (
                    "outputs/pilot_120/cluster_systems/degree_based_router.predictions.jsonl"
                ),
            },
            {
                "system_id": "direct_base_llm",
                "reason_cluster_needed": (
                    "Requires HF local load of Qwen/Qwen3-8B selected base under "
                    "DirectLLMProvider; GPU memory not available for official local run."
                ),
                "model_base_model_id": "Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218",
                "adapter_id_path": None,
                "forbids_selected_adapter": True,
                "inference_config": {
                    "selected_identities": "configs/model/selected_identities_v1.json",
                    "do_sample": False,
                },
                "expected_output_filename": (
                    "outputs/pilot_120/cluster_systems/direct_base_llm.predictions.jsonl"
                ),
            },
            {
                "system_id": "context_blind_manager",
                "reason_cluster_needed": (
                    "Requires context_blind StructuredAnalysis (live provider or cache) "
                    "and selected model strategy; same adapter trajectory as full manager."
                ),
                "model_base_model_id": "Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218",
                "adapter_id_path": "pending T28 selected_adapter",
                "inference_config": {
                    "required_analysis_variant": "context_blind",
                    "config": "configs/manager/system_variants_v1.json",
                },
                "expected_output_filename": (
                    "outputs/pilot_120/cluster_systems/context_blind_manager.predictions.jsonl"
                ),
            },
            {
                "system_id": "full_type_risk_aware_manager",
                "reason_cluster_needed": (
                    "Requires full_context analysis + selected T28 adapter "
                    "(selected_adapter=true). Do not run before selection completes."
                ),
                "model_base_model_id": "Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218",
                "adapter_id_path": "pending; see T28 handoff when selected_adapter=true",
                "inference_config": {
                    "required_analysis_variant": "full_context",
                    "uses_deterministic_router": True,
                    "awaits_t28_adapter": True,
                },
                "expected_output_filename": (
                    "outputs/pilot_120/cluster_systems/full_type_risk_aware_manager.predictions.jsonl"
                ),
                "t28_gate": {
                    "required": [
                        "source-dev evaluation complete",
                        "frozen checkpoint selection",
                        "packaging",
                        "clean-load verify",
                        "selected_adapter=true",
                    ],
                    "include_before_gate": False,
                    "proposed_system_id_after_selection": (
                        "t28_full_type_risk_aware_manager_qlora_r5_retry5"
                    ),
                    "handoff_ref": "outputs/t28_r5/evidence/t28_pilot120_handoff.json",
                },
            },
        ],
        "explicitly_excluded_until_ready": [
            {
                "system_id": "t28_full_type_risk_aware_manager_qlora_r5_retry5",
                "reason": (
                    "T28 workstream incomplete: selected_adapter=false. Pilot-120 must not "
                    "be used for checkpoint selection."
                ),
            }
        ],
    }


def comparison_row(
    system_id: str,
    execution_mode: str,
    report: dict[str, Any],
    ci: dict[str, Any],
    notes: str,
) -> dict[str, Any]:
    term = report["terminal_strategy"]
    per = term.get("per_class") or {}
    amb = report["ambiguity_types"]
    cap = report["capability_status"]
    ops = report["operational"]

    def _f1(label: str) -> Any:
        cell = per.get(label) or {}
        return cell.get("f1")

    return {
        "system_id": system_id,
        "execution_mode": execution_mode,
        "terminal_accuracy": term.get("accuracy"),
        "terminal_accuracy_ci95": (ci.get("metrics") or {}).get("accuracy", {}).get("ci95"),
        "terminal_macro_f1": term.get("macro_f1"),
        "terminal_macro_f1_ci95": (ci.get("metrics") or {}).get("macro_f1", {}).get("ci95"),
        "execute_f1": _f1("execute"),
        "clarify_f1": _f1("clarify"),
        "rejection_f1": _f1("face_preserving_rejection"),
        "ambiguity_micro_f1": amb.get("micro_f1"),
        "ambiguity_macro_f1": amb.get("macro_f1"),
        "ambiguity_exact_set": amb.get("exact_set_accuracy"),
        "capability_accuracy": cap.get("accuracy"),
        "schema_valid_pct": 100.0 * float(ops.get("schema_valid_rate") or 0.0),
        "error_pct": 100.0 * float(ops.get("failure_error_rate") or 0.0),
        "mean_latency_ms": ops.get("latency_ms_mean"),
        "mean_tokens": ops.get("tokens_mean"),
        "notes": notes,
    }


def write_comparison_table(path: Path, rows: list[dict[str, Any]]) -> None:
    path = resolve_writable_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            for k, v in list(flat.items()):
                if isinstance(v, (list, dict)):
                    flat[k] = json.dumps(v)
            writer.writerow(flat)


def write_markdown_table(path: Path, rows: list[dict[str, Any]]) -> None:
    path = resolve_writable_path(path)
    cols = [
        "system_id",
        "execution_mode",
        "terminal_accuracy",
        "terminal_macro_f1",
        "execute_f1",
        "clarify_f1",
        "rejection_f1",
        "schema_valid_pct",
        "error_pct",
        "notes",
    ]
    lines = [
        "# Pilot-120 local systems comparison",
        "",
        "Ambiguity/capability metrics for constant baselines are **not meaningful** "
        "(fields unsupported / null). See notes.",
        "",
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for row in rows:
        cells = []
        for c in cols:
            v = row.get(c)
            if isinstance(v, float):
                cells.append(f"{v:.4f}" if c.endswith("f1") or c.endswith("accuracy") else f"{v:.2f}")
            else:
                cells.append(str(v if v is not None else ""))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run(out_dir: Path, systems: list[str] | None = None) -> dict[str, Any]:
    root = Path.cwd()
    out_dir = resolve_writable_path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    selected = list(CONSTANT_TERMINAL_SYSTEMS if systems is None else systems)
    unknown = [s for s in selected if s not in CONSTANT_TERMINAL_SYSTEMS]
    if unknown:
        raise p120.Pilot120Error(f"not locally-runnable constant systems: {unknown}")

    integrity = verify_frozen_integrity(root)
    dump_json(out_dir / "integrity_check.json", integrity)

    inventory = build_system_inventory()
    dump_json(out_dir / "system_inventory.json", inventory)

    cluster_pending = build_cluster_pending()
    cluster_path = resolve_writable_path(root / "outputs/pilot_120/cluster_systems_pending.json")
    dump_json(cluster_path, cluster_pending)

    expected_ids = p120.expected_record_ids()
    gold_rows = p120.load_jsonl(root / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl")
    gold_by_id = {str(r["record_id"]): r for r in gold_rows}
    variants = load_system_variants()
    config_hash = sha256_json(variants)

    pred_paths: dict[str, Path] = {}
    system_preds: dict[str, list[dict[str, Any]]] = {}
    validations: dict[str, Any] = {}
    eval_reports: dict[str, Any] = {}
    cis: dict[str, Any] = {}
    comparison_rows: list[dict[str, Any]] = []
    rerun_commands: dict[str, str] = {}

    for system_id in selected:
        rows = generate_constant_predictions(
            system_id=system_id,
            record_ids=expected_ids,
            config_hash=config_hash,
        )
        pred_path = out_dir / "predictions" / f"{system_id}.predictions.jsonl"
        write_jsonl(pred_path, rows)
        pred_paths[system_id] = pred_path
        system_preds[system_id] = rows
        validations[system_id] = validate_prediction_file(pred_path, expected_ids)
        if not validations[system_id]["ok"]:
            raise p120.Pilot120Error(f"prediction validation failed for {system_id}: {validations[system_id]}")

        report = p120.evaluate_predictions(pred_path, config_path=root / PILOT_CONFIG)
        eval_path = out_dir / "evaluations" / f"{system_id}.eval.json"
        dump_json(eval_path, report)
        eval_reports[system_id] = report

        y_true, y_pred = extract_aligned_terminals(gold_by_id, rows, expected_ids)
        ci = bootstrap_terminal_ci(y_true, y_pred)
        cis[system_id] = ci
        dump_json(out_dir / "uncertainty" / f"{system_id}.bootstrap.json", ci)

        note = (
            "Terminal-only constant policy; ambiguity/capability unsupported (null). "
            "Ambiguity/capability scores in raw eval are not interpretable for this system."
        )
        comparison_rows.append(
            comparison_row(system_id, "deterministic-local", report, ci, note)
        )
        rerun_commands[system_id] = (
            f"python scripts/evaluate_pilot_120_local_systems.py --systems {system_id} "
            f"--output {out_dir.as_posix()}"
        )

    # Paired bootstrap among constant systems
    paired = {}
    for i, a in enumerate(selected):
        for b in selected[i + 1 :]:
            yt, ya = extract_aligned_terminals(gold_by_id, system_preds[a], expected_ids)
            _, yb = extract_aligned_terminals(gold_by_id, system_preds[b], expected_ids)
            paired[f"{a}__minus__{b}"] = paired_bootstrap_accuracy_delta(yt, ya, yb)
    dump_json(out_dir / "uncertainty" / "paired_bootstrap_terminal_accuracy.json", paired)

    failures = failure_analysis(gold_by_id, system_preds, expected_ids)
    dump_json(out_dir / "failure_analysis.json", failures)

    write_comparison_table(out_dir / "comparison_table.csv", comparison_rows)
    write_markdown_table(out_dir / "comparison_table.md", comparison_rows)
    dump_json(out_dir / "comparison_table.json", comparison_rows)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "integrity": integrity,
        "systems_run": selected,
        "systems_deferred_cluster": [s["system_id"] for s in cluster_pending["deferred_systems"]],
        "systems_excluded_t28": [
            s["system_id"] for s in cluster_pending["explicitly_excluded_until_ready"]
        ],
        "systems_unavailable_other": inventory["not_implemented_as_registry_ids"],
        "prediction_files": {k: str(v.as_posix()) for k, v in pred_paths.items()},
        "validations": validations,
        "config_hash_system_variants_v1": config_hash,
        "rerun_commands": rerun_commands,
        "evaluate_command_template": (
            "python -m ambiguity_manager.evaluation.pilot_120_cli evaluate "
            "--config configs/evaluation/pilot_120_v1.json "
            "--predictions <PREDICTIONS.jsonl>"
        ),
        "cluster_systems_pending": str(cluster_path.as_posix()),
        "comparison_table": str((out_dir / "comparison_table.csv").as_posix()),
        "notes": [
            "No independent Pilot-120 StructuredAnalysis cache found.",
            "No API-hosted comparison systems are wired in the registry.",
            "Pilot-120 gold/source unmodified.",
        ],
    }
    dump_json(out_dir / "run_summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUT,
        help="Output directory under outputs/pilot_120/local_systems",
    )
    parser.add_argument(
        "--systems",
        nargs="*",
        default=None,
        help="Optional subset of constant systems (default: all constant baselines)",
    )
    parser.add_argument(
        "--integrity-only",
        action="store_true",
        help="Only verify frozen hashes then exit",
    )
    args = parser.parse_args(argv)

    try:
        if args.integrity_only:
            report = verify_frozen_integrity(Path.cwd())
            print(json.dumps(report, indent=2))
            return 0
        summary = run(args.output, systems=args.systems)
        print(json.dumps(summary, indent=2, default=str))
        return 0
    except p120.Pilot120Error as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
