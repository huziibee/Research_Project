#!/usr/bin/env python3
"""CPU clarify + CPC rescue on frozen repaired T0.7 preds (2026-09-18).

Does not rewrite gold. Does not call an LLM.
- Clarification: scene-grounded generator v1.2.0 on ask routes
  (emit routes and/or LLM-capability patched routes).
- CPC: coerce not_applicable+value -> filled; demote placeholder filled.
Writes repaired prediction jsonl + summary JSON under outputs/.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ambiguity_manager.evaluation.evaluator import (  # noqa: E402
    DeterministicEvaluator,
    PredictionRecord,
)
from ambiguity_manager.systems.response_generation import generate_clarification  # noqa: E402
from lib_capability_debate_20260918 import (  # noqa: E402
    analysis_dict_from_pred,
    analysis_from_dict,
    load_jsonl_by_id,
    norm_route,
    patch_capability_in_analysis,
    prior_capability_from_pred,
    route_from_analysis,
)
from score_official_sidecar_followon import (  # noqa: E402
    OFFICIAL_CPC,
    OFFICIAL_WORDING,
    ask_label_prf,
    official_wording_score,
)
from score_pilot120_cpc_and_risk import (  # noqa: E402
    load_jsonl,
    metric_to_dict,
    normalize_prediction,
)

OUT = ROOT / "outputs" / "clarify_cpc_rescue_20260918"
REPAIRED = (
    ROOT
    / "outputs/cluster_pulls/unified_55670_repaired_20260918/T0.7/predictions"
    / "goal_first_manager_v2.predictions.jsonl"
)
JUDGMENTS = (
    ROOT
    / "outputs/capability_debate_local_oracle_20260918"
    / "capability_judgments_cluster.jsonl"
)
SOURCE = ROOT / "data/annotations/pilot_120_v1/source_canonical.jsonl"
FROZEN = ROOT / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl"

PLACEHOLDERS = {
    "",
    "none",
    "null",
    "unknown",
    "unassigned",
    "n/a",
    "na",
    "not specified",
    "not applicable",
    "not_applicable",
}


def load_source() -> dict[str, dict]:
    return load_jsonl(SOURCE)


def coerce_cpc(cpc: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(cpc, dict):
        return {}
    out: dict[str, Any] = {}
    for name, slot in cpc.items():
        if not isinstance(slot, dict):
            out[name] = slot
            continue
        status = slot.get("status")
        value = slot.get("value")
        if isinstance(value, str) and value.strip():
            cleaned = value.strip()
            if cleaned.casefold() in PLACEHOLDERS:
                value = None
                status = "not_applicable" if status == "filled" else status
            elif status in (None, "unknown", "not_applicable"):
                status = "filled"
        elif status == "filled":
            status = "missing"
            value = None
        out[name] = {"status": status, "value": value}
    return out


def score_cpc(preds: dict[str, dict]) -> dict[str, Any]:
    gold = load_jsonl(OFFICIAL_CPC)
    ev = DeterministicEvaluator()
    rules = ev.norm.get("rules", {})
    tp = fp = fn = 0
    for rid, grow in gold.items():
        pred = preds.get(rid) or {}
        nrow = normalize_prediction(pred)
        gcpc = grow.get("gold_cpc") or {}
        pcpc = nrow.get("cpc") or {}
        gfill, pfill = ev._extract_filled_cpc(gcpc, pcpc, rules)
        for slot in set(gfill) | set(pfill):
            gv, pv = gfill.get(slot), pfill.get(slot)
            if gv is not None and pv == gv:
                tp += 1
            elif gv is not None and pv is None:
                fn += 1
            elif gv is not None:
                fn += 1
                fp += 1
            elif pv is not None:
                fp += 1
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "n_rows": len(gold),
    }


def apply_clarify(
    pred: dict[str, Any],
    *,
    route: str,
    scene: str,
    targets: list[str] | None = None,
) -> dict[str, Any]:
    out = copy.deepcopy(pred)
    parsed = out.setdefault("parsed", {}) if isinstance(out.get("parsed"), dict) else {}
    if not isinstance(out.get("parsed"), dict):
        out["parsed"] = {}
        parsed = out["parsed"]
    analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
    if route != "clarify":
        return out
    try:
        sa = analysis_from_dict(analysis_dict_from_pred(out) or {})
    except Exception:
        from ambiguity_manager.systems.contracts import StructuredAnalysis

        sa = StructuredAnalysis(
            intent_summary=str(analysis.get("intent_summary") or out.get("intent_summary") or "")
        )
    tgt = targets
    if not tgt:
        tgt = list(
            analysis.get("clarification_targets")
            or parsed.get("clarification_targets")
            or ["intent"]
        )
    # Ensure targets non-empty so scene harvest can fire
    if not tgt:
        tgt = ["intent"]
    q = generate_clarification(sa, tgt, scene_context=scene)
    out["clarification_question"] = q
    out["terminal_strategy"] = "clarify"
    parsed["clarification_question"] = q
    parsed["terminal_strategy"] = "clarify"
    parsed["recommended_strategy"] = "clarify"
    if isinstance(analysis, dict):
        analysis = dict(analysis)
        analysis["clarification_question"] = q
        analysis["recommended_strategy"] = "clarify"
        analysis["clarification_targets"] = tgt
        # keep coerced cpc if already present
        parsed["analysis"] = analysis
    return out


def apply_cpc_coerce(pred: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(pred)
    parsed = out.get("parsed") if isinstance(out.get("parsed"), dict) else {}
    analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
    if not analysis:
        return out
    analysis = dict(analysis)
    analysis["cpc"] = coerce_cpc(analysis.get("cpc"))
    parsed = dict(parsed)
    parsed["analysis"] = analysis
    out["parsed"] = parsed
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    preds = load_jsonl_by_id(REPAIRED)
    source = load_source()
    judgments = {}
    if JUDGMENTS.exists():
        judgments = load_jsonl_by_id(JUDGMENTS)

    # Baseline scores
    baseline_wording = official_wording_score(preds)
    baseline_cpc = score_cpc(preds)

    # Build LLM-cap route map (patch capability on analysis dict, then re-route)
    llm_routes: dict[str, str] = {}
    for rid, pred in preds.items():
        if rid not in judgments:
            continue
        j = judgments[rid]
        cap = j.get("capability_status") or j.get("predicted_capability") or j.get("label")
        if not cap:
            cap = (j.get("judgment") or {}).get("capability_status")
        if not cap:
            continue
        try:
            adict = analysis_dict_from_pred(pred) or {}
            patched = patch_capability_in_analysis(adict, str(cap))
            analysis = analysis_from_dict(patched)
            llm_routes[rid] = route_from_analysis(analysis)["goal_first_manager_v2"]
        except Exception as exc:  # noqa: BLE001
            llm_routes[rid] = f"error:{exc}"

    # Emit-route clarify + scene harvest
    emit_rescued: dict[str, dict] = {}
    for rid, pred in preds.items():
        route = norm_route(pred.get("terminal_strategy"))
        scene = str((source.get(rid) or {}).get("scene_context") or "")
        row = apply_cpc_coerce(pred)
        row = apply_clarify(row, route=route or "", scene=scene)
        emit_rescued[rid] = row

    # LLM-cap route clarify + scene harvest + CPC coerce
    llm_rescued: dict[str, dict] = {}
    for rid, pred in preds.items():
        route = norm_route(llm_routes.get(rid) or pred.get("terminal_strategy"))
        scene = str((source.get(rid) or {}).get("scene_context") or "")
        row = apply_cpc_coerce(pred)
        # When LLM route says clarify, force ask targets if empty
        targets = None
        if route == "clarify":
            analysis = (pred.get("parsed") or {}).get("analysis") or {}
            targets = list(analysis.get("clarification_targets") or []) or ["intent"]
        row = apply_clarify(row, route=route or "", scene=scene, targets=targets)
        if route:
            row["terminal_strategy"] = route
            if isinstance(row.get("parsed"), dict):
                row["parsed"]["terminal_strategy"] = route
                row["parsed"]["recommended_strategy"] = route
        llm_rescued[rid] = row

    emit_wording = official_wording_score(emit_rescued)
    llm_wording = official_wording_score(llm_rescued)
    emit_cpc = score_cpc(emit_rescued)
    llm_cpc = score_cpc(llm_rescued)  # same coerce

    # Write artifacts
    def write_jsonl(path: Path, rows: dict[str, dict]) -> None:
        with path.open("w", encoding="utf-8") as fh:
            for rid in sorted(rows):
                fh.write(json.dumps(rows[rid], ensure_ascii=False) + "\n")

    write_jsonl(OUT / "goal_first_v2.emit_route_scene_clarify.predictions.jsonl", emit_rescued)
    write_jsonl(OUT / "goal_first_v2.llmcap_route_scene_clarify.predictions.jsonl", llm_rescued)

    # Row-level wording detail for paper
    gold_w = load_jsonl(OFFICIAL_WORDING)
    detail = []
    for rid in sorted(gold_w):
        detail.append(
            {
                "record_id": rid,
                "emit_route": norm_route(preds[rid].get("terminal_strategy")),
                "llm_route": llm_routes.get(rid),
                "emit_q": emit_rescued[rid].get("clarification_question"),
                "llm_q": llm_rescued[rid].get("clarification_question"),
            }
        )
    (OUT / "wording_row_detail.json").write_text(
        json.dumps(detail, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    summary = {
        "predictions_source": str(REPAIRED),
        "clarification_generator": "deterministic_clarification@1.2.0",
        "scene_source": str(SOURCE),
        "baseline": {
            "wording": baseline_wording,
            "cpc": baseline_cpc,
        },
        "after_emit_route_scene_clarify": {
            "wording": emit_wording,
            "cpc": emit_cpc,
        },
        "after_llmcap_route_scene_clarify": {
            "wording": llm_wording,
            "cpc": llm_cpc,
            "n_llm_routes": len(llm_routes),
            "ask_on_gold_ask_llm": llm_wording.get("predicted_ask_on_gold_ask"),
        },
        "cpc_note": (
            "CPC coerce is route-independent; emit and llmcap CPC scores should match."
        ),
        "artifacts": {
            "emit_preds": str(OUT / "goal_first_v2.emit_route_scene_clarify.predictions.jsonl"),
            "llmcap_preds": str(OUT / "goal_first_v2.llmcap_route_scene_clarify.predictions.jsonl"),
            "wording_rows": str(OUT / "wording_row_detail.json"),
        },
    }
    (OUT / "clarify_cpc_rescue_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
