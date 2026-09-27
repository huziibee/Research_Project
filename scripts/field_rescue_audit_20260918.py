#!/usr/bin/env python3
"""Field-rescue audit on frozen Pilot-120 emits (CPU only).

Covers wording harvest, ambiguity pragmatic coerce, risk/CPC/safety
tables, and temperature routing from available local pulls.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ambiguity_manager.evaluation import pilot_120 as p120  # noqa: E402
from ambiguity_manager.systems.contracts import StructuredAnalysis  # noqa: E402
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
    OFFICIAL_RISK,
    OFFICIAL_WORDING,
    _first,
    _item_covered,
    _tokens,
    ask_label_prf,
    official_wording_score,
    overlay_official,
)
from score_pilot120_cpc_and_risk import (  # noqa: E402
    load_jsonl,
    metric_to_dict,
    normalize_prediction,
)
from ambiguity_manager.evaluation.evaluator import (  # noqa: E402
    DeterministicEvaluator,
    PredictionRecord,
)
from sprint_capability_ambiguity_rescue_20260918 import (  # noqa: E402
    gold_ambiguity_set,
    pred_ambiguity_set,
    soft_f1,
)

OUT = ROOT / "outputs" / "field_rescue_audit_20260918"
REPAIRED_T07 = (
    ROOT
    / "outputs/cluster_pulls/unified_55670_repaired_20260918/T0.7/predictions"
    / "goal_first_manager_v2.predictions.jsonl"
)
JUDGMENTS = (
    ROOT
    / "outputs/capability_debate_local_oracle_20260918"
    / "capability_judgments_cluster.jsonl"
)
LIVE = ROOT / "outputs/cluster_pulls/unified_55670_live_20260918"
FROZEN = ROOT / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl"


def refuse_like(route: str | None) -> bool:
    return norm_route(route) == "refuse"


def cover(items: list[str], blob: str) -> bool:
    token_sets = [_tokens(x) for x in items]
    shared = set.intersection(*token_sets) if token_sets else set()
    bt = _tokens(blob)
    return all(_item_covered(item, bt, shared) for item in items) and bool(blob.strip())


def speech_act_from_pred(pred: dict[str, Any]) -> str | None:
    analysis = analysis_dict_from_pred(pred) or {}
    sa = analysis.get("speech_act")
    return str(sa) if sa else None


def coerce_pragmatic(pred_types: set[str], speech_act: str | None) -> set[str]:
    out = set(pred_types)
    if speech_act == "directive_command" and "pragmatic" in out:
        out.discard("pragmatic")
    return out


def ambiguity_block(preds: dict[str, dict], gold: dict[str, dict]) -> dict[str, Any]:
    exact = soft = exact_c = soft_c = 0
    tag_pred = Counter()
    tag_gold = Counter()
    for rid, g in gold.items():
        pred = preds.get(rid) or {}
        gset = gold_ambiguity_set(g)
        pset = pred_ambiguity_set(pred)
        cset = coerce_pragmatic(pset, speech_act_from_pred(pred))
        for t in pset:
            tag_pred[t] += 1
        for t in gset:
            tag_gold[t] += 1
        if pset == gset:
            exact += 1
        if cset == gset:
            exact_c += 1
        soft += soft_f1(pset, gset)
        soft_c += soft_f1(cset, gset)
    n = len(gold)
    return {
        "n": n,
        "exact_set": exact,
        "soft_f1_mean": soft / n if n else None,
        "exact_set_after_pragmatic_coerce": exact_c,
        "soft_f1_mean_after_pragmatic_coerce": soft_c / n if n else None,
        "top_predicted": tag_pred.most_common(8),
        "pragmatic_pred_vs_gold": {"pred": tag_pred.get("pragmatic", 0), "gold": tag_gold.get("pragmatic", 0)},
        "action_order_pred": tag_pred.get("action_order", 0),
    }


def wording_harvest(preds: dict[str, dict], route_override: dict[str, str] | None = None) -> dict[str, Any]:
    gold_w = load_jsonl(OFFICIAL_WORDING)
    official = official_wording_score(preds)
    old_ok = harvest_ok = asked_old = asked_new = 0
    rows = []
    for rid, grow in sorted(gold_w.items()):
        items = grow["gold_clarification"]["wording_criteria"]["must_convey"]
        pred = preds.get(rid) or {}
        parsed = pred.get("parsed") if isinstance(pred.get("parsed"), dict) else {}
        analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
        emit_route = norm_route(
            _first(
                pred.get("terminal_strategy"),
                parsed.get("terminal_strategy"),
                analysis.get("recommended_strategy"),
            )
        )
        route = norm_route((route_override or {}).get(rid) or emit_route)
        old_q = _first(
            pred.get("clarification_question"),
            parsed.get("clarification_question"),
            analysis.get("clarification_question"),
        )
        summary = str(_first(pred.get("intent_summary"), analysis.get("intent_summary")) or "")
        targets = list(
            _first(parsed.get("clarification_targets"), analysis.get("clarification_targets"), []) or []
        )
        new_q = None
        if route == "clarify":
            asked_new += 1
            # Prefer live analysis object so candidate slots still apply when present.
            try:
                sa = analysis_from_dict(analysis_dict_from_pred(pred) or {})
            except Exception:
                sa = StructuredAnalysis(intent_summary=summary)
            if not getattr(sa, "intent_summary", None):
                sa.intent_summary = summary
            new_q = generate_clarification(sa, targets or ["intent"])
        if emit_route == "clarify":
            asked_old += 1
        old_pass = bool(old_q) and cover(items, str(old_q))
        new_pass = bool(new_q) and cover(items, str(new_q))
        if old_pass:
            old_ok += 1
        if new_pass:
            harvest_ok += 1
        rows.append(
            {
                "record_id": rid,
                "emit_route": emit_route,
                "scored_route": route,
                "old_q": old_q,
                "new_q": new_q,
                "old_pass": old_pass,
                "new_pass": new_pass,
                "summary_covers_all": cover(items, summary),
            }
        )
    return {
        "denominator": 23,
        "official_emit_wording_correct": official["wording_correct"],
        "official_emit_asked_on_gold_ask": official["predicted_ask_on_gold_ask"],
        "harvest_replay_wording_correct": harvest_ok,
        "harvest_asked_on_gold_ask": asked_new,
        "emit_asked_on_gold_ask_recount": asked_old,
        "emit_wording_recount": old_ok,
        "rows_improved": [r["record_id"] for r in rows if r["new_pass"] and not r["old_pass"]],
        "rows_still_fail": [r["record_id"] for r in rows if not r["new_pass"]],
        "summary_covers_all_count": sum(1 for r in rows if r["summary_covers_all"]),
        "rows": rows,
    }


def safety_table(preds: dict[str, Any], gold: dict[str, dict], label: str) -> dict[str, Any]:
    """False refuse / false execute / confusion on Pilot-120."""
    conf = Counter()
    false_refuse = false_execute = 0
    n_gold_exec = n_gold_refuse = correct = 0
    route_map_mode = label.startswith("reroute:")
    for rid, g in gold.items():
        gr = norm_route(g.get("terminal_strategy"))
        if route_map_mode:
            pr = norm_route(preds.get(rid) if isinstance(preds.get(rid), str) else None)
        else:
            pr = norm_route((preds.get(rid) or {}).get("terminal_strategy"))
        conf[(gr, pr)] += 1
        if gr == "execute":
            n_gold_exec += 1
            if pr == "refuse":
                false_refuse += 1
        if gr == "refuse":
            n_gold_refuse += 1
            if pr == "execute":
                false_execute += 1
        if gr == pr and gr is not None:
            correct += 1
    return {
        "label": label,
        "n_correct": correct,
        "accuracy": correct / 120,
        "false_refuse_on_gold_execute": false_refuse,
        "false_execute_on_gold_refuse": false_execute,
        "n_gold_execute": n_gold_exec,
        "n_gold_refuse": n_gold_refuse,
        "confusion_gold_to_pred": {
            g: {p: c for (gg, p), c in conf.items() if gg == g}
            for g in ("execute", "clarify", "refuse")
        },
    }


def risk_audit(preds: dict[str, dict], gold: dict[str, dict], judgments: dict[str, dict] | None) -> dict[str, Any]:
    risk_gold = load_jsonl(OFFICIAL_RISK)
    risk_ok = 0
    by_level = Counter()
    risk_wrong_when_route_wrong = 0
    cap_wrong_when_route_wrong = 0
    both_wrong = 0
    route_wrong = 0
    for rid, g in gold.items():
        pred = preds.get(rid) or {}
        analysis = analysis_dict_from_pred(pred) or {}
        pred_risk = str(analysis.get("risk_level") or "").lower()
        gold_risk = str(risk_gold[rid]["gold_risk_level"]).lower()
        by_level[gold_risk] += 1
        if pred_risk == gold_risk:
            risk_ok += 1
        gr = norm_route(g.get("terminal_strategy"))
        pr = norm_route(pred.get("terminal_strategy"))
        if gr != pr:
            route_wrong += 1
            risk_bad = pred_risk != gold_risk
            cap_pred = str(prior_capability_from_pred(pred) or "").lower()
            gold_cap = str(g.get("capability_status") or "").lower()
            cap_bad = bool(gold_cap) and cap_pred != gold_cap
            if risk_bad:
                risk_wrong_when_route_wrong += 1
            if cap_bad:
                cap_wrong_when_route_wrong += 1
            if risk_bad and cap_bad:
                both_wrong += 1

    # Oracle risk + frozen capability vs LLM-cap + frozen risk ceilings
    oracle_risk_routes: dict[str, str] = {}
    for rid, pred in preds.items():
        analysis = analysis_dict_from_pred(pred) or {}
        patched = dict(analysis)
        patched["risk_level"] = risk_gold[rid]["gold_risk_level"]
        try:
            oracle_risk_routes[rid] = route_from_analysis(analysis_from_dict(patched))[
                "goal_first_manager_v2"
            ]
        except Exception:
            oracle_risk_routes[rid] = norm_route(pred.get("terminal_strategy")) or "missing"

    llm_routes: dict[str, str] = {}
    if judgments:
        for rid, pred in preds.items():
            j = judgments.get(rid) or {}
            cap = j.get("capability_status") or j.get("final_capability")
            analysis = analysis_dict_from_pred(pred) or {}
            try:
                if not cap:
                    raise ValueError("no capability judgment")
                patched = patch_capability_in_analysis(analysis, str(cap))
                llm_routes[rid] = route_from_analysis(analysis_from_dict(patched))[
                    "goal_first_manager_v2"
                ]
            except Exception:
                llm_routes[rid] = norm_route(pred.get("terminal_strategy")) or "missing"

    sensitive_ids = [
        rid
        for rid, row in risk_gold.items()
        if str(row["gold_risk_level"]).lower() in {"medium", "high"}
    ]
    emit_sens = sum(
        1
        for rid in sensitive_ids
        if norm_route((preds.get(rid) or {}).get("terminal_strategy"))
        == norm_route(gold[rid].get("terminal_strategy"))
    )
    return {
        "risk_accuracy": risk_ok / 120,
        "risk_ok": risk_ok,
        "gold_risk_counts": dict(by_level),
        "route_wrong_n": route_wrong,
        "among_route_wrong": {
            "risk_also_wrong": risk_wrong_when_route_wrong,
            "capability_also_wrong": cap_wrong_when_route_wrong,
            "both_wrong": both_wrong,
        },
        "risk_sensitive_emit": {"correct": emit_sens, "denom": len(sensitive_ids)},
        "oracle_risk_only_routing": safety_table(oracle_risk_routes, gold, "reroute:oracle_risk"),
        "llm_cap_routing": safety_table(llm_routes, gold, "reroute:llm_cap") if llm_routes else None,
    }


def cpc_block(preds: dict[str, dict], gold_rows: dict[str, Any]) -> dict[str, Any]:
    cpc_rows = load_jsonl(OFFICIAL_CPC)
    risk_rows = load_jsonl(OFFICIAL_RISK)
    frozen = load_jsonl(FROZEN)
    gold_by_id = overlay_official(frozen, cpc_rows, risk_rows)
    pred_rows = {rid: normalize_prediction(row) for rid, row in preds.items()}
    pred_by_id = {
        rid: PredictionRecord(record_id=rid, payload=pred_rows[rid], system_id="gf")
        for rid in gold_by_id
        if rid in pred_rows
    }
    harness = DeterministicEvaluator()
    cpc = harness._cpc_metrics(gold_by_id, pred_by_id)
    fill = Counter()
    for rid, row in pred_rows.items():
        analysis = row.get("analysis") if isinstance(row.get("analysis"), dict) else {}
        cpc_obj = analysis.get("cpc") or {}
        filled = 0
        if isinstance(cpc_obj, dict):
            for slot, val in cpc_obj.items():
                if isinstance(val, dict) and val.get("status") == "filled" and val.get("value"):
                    filled += 1
        fill[filled] += 1
    return {
        "cpc_slot_f1": metric_to_dict(cpc["cpc_slot_f1"]),
        "cpc_slot_precision": metric_to_dict(cpc["cpc_slot_precision"]),
        "cpc_slot_recall": metric_to_dict(cpc["cpc_slot_recall"]),
        "rows_by_n_filled_slots": dict(sorted(fill.items())),
        "ask_label": ask_label_prf(frozen, pred_rows),
    }


def temp_routing(path: Path, gold: dict[str, dict]) -> dict[str, Any] | None:
    if not path.exists():
        return None
    preds = load_jsonl_by_id(path)
    systems = {}
    parent = path.parent
    for p in sorted(parent.glob("*.predictions.jsonl")):
        rows = load_jsonl_by_id(p)
        correct = sum(
            1
            for rid, g in gold.items()
            if norm_route((rows.get(rid) or {}).get("terminal_strategy"))
            == norm_route(g.get("terminal_strategy"))
        )
        failed = sum(1 for rid, row in rows.items() if row.get("failed"))
        systems[p.name.replace(".predictions.jsonl", "")] = {
            "routing_correct": correct,
            "n": len(gold),
            "failed_rows": failed,
        }
    # Merge official intent references for automatic-overlap screen.
    intent_refs_path = (
        ROOT
        / "pilot120_intent_evaluation_20260902"
        / "pilot120_intent_evaluation_20260902"
        / "validation"
        / "self_contained_rebuild"
        / "data"
        / "intent_gold_references_120.jsonl"
    )
    if not intent_refs_path.exists():
        intent_refs_path = ROOT / "data/annotations/pilot_120_v1/intent_gold_references_120.jsonl"
    refs = load_jsonl(intent_refs_path) if intent_refs_path.exists() else {}
    gf = load_jsonl_by_id(path)
    intent_ok = 0
    from sprint_capability_ambiguity_rescue_20260918 import intent_pass

    for rid, g in gold.items():
        pred = gf.get(rid) or {}
        summary = str(
            _first(
                pred.get("intent_summary"),
                (analysis_dict_from_pred(pred) or {}).get("intent_summary"),
            )
            or ""
        )
        g2 = dict(g)
        if rid in refs:
            g2["reference_A_intent_text"] = refs[rid].get("reference_A_intent_text")
            g2["reference_B_intent_text"] = refs[rid].get("reference_B_intent_text")
        if intent_pass(summary, g2):
            intent_ok += 1
    return {"systems": systems, "intent_auto_gf": intent_ok, "progress_note": str(path)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    gold = load_jsonl(FROZEN)
    preds = load_jsonl_by_id(REPAIRED_T07)
    judgments = load_jsonl_by_id(JUDGMENTS) if JUDGMENTS.exists() else {}

    # Build LLM-cap route map for wording under rescued asks
    llm_route_map: dict[str, str] = {}
    for rid, pred in preds.items():
        j = judgments.get(rid) or {}
        cap = j.get("capability_status") or j.get("final_capability")
        analysis = analysis_dict_from_pred(pred) or {}
        try:
            if not cap:
                raise ValueError("no capability judgment")
            patched = patch_capability_in_analysis(analysis, str(cap))
            routes = route_from_analysis(analysis_from_dict(patched))
            llm_route_map[rid] = routes["goal_first_manager_v2"]
        except Exception:
            llm_route_map[rid] = norm_route(pred.get("terminal_strategy")) or "missing"

    wording_emit = wording_harvest(preds)
    wording_llm = wording_harvest(preds, route_override=llm_route_map)
    amb = ambiguity_block(preds, gold)
    risk = risk_audit(preds, gold, judgments)
    cpc = cpc_block(preds, gold)
    safety_emit = safety_table(preds, gold, "emit_repaired_T0.7")
    safety_llm = safety_table(llm_route_map, gold, "reroute:llm_cap")

    temps = {}
    for T in ("T0.3", "T1.0"):
        p = LIVE / T / "predictions" / "goal_first_manager_v2.predictions.jsonl"
        temps[T] = temp_routing(p, gold)

    # Latency from repaired/original progress if present
    latency = {}
    for label, p in [
        ("T0.7_unified_pre_repair", ROOT / "outputs/cluster_pulls/unified_55670/T0.7/progress.json"),
        ("T1.0_live", LIVE / "T1.0" / "progress.json"),
        ("T0.3_fix_reemit", LIVE / "T0.3" / "progress.json"),
    ]:
        if p.exists():
            latency[label] = json.loads(p.read_text(encoding="utf-8"))

    report = {
        "predictions": str(REPAIRED_T07).replace("\\", "/"),
        "wording": {
            "emit_route": {k: v for k, v in wording_emit.items() if k != "rows"},
            "llm_cap_route_plus_harvest": {k: v for k, v in wording_llm.items() if k != "rows"},
        },
        "ambiguity": amb,
        "risk": risk,
        "cpc": cpc,
        "safety": {"emit": safety_emit, "llm_cap": safety_llm},
        "temperature_local_pulls": temps,
        "latency": latency,
        "job_56379": "PENDING — ambiguity debate repair; do not duplicate",
    }
    out_json = OUT / "field_rescue_summary.json"
    out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (OUT / "wording_harvest_rows_emit.json").write_text(
        json.dumps(wording_emit, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "wording_harvest_rows_llm_route.json").write_text(
        json.dumps(wording_llm, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: report[k] for k in report if k != "wording"}, indent=2))
    print("---WORDING---")
    print(json.dumps(report["wording"], indent=2))
    print("wrote", out_json)


if __name__ == "__main__":
    main()
