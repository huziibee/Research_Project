#!/usr/bin/env python3
"""CPU reparse of ambiguity debate raws with hardened JSON normaliser.

Recovers typo keys (pilot_ambiguuity_types / pilot_ambiguities) and coerces routes
without re-running the GPU. Rows whose adjudicator still lacks a valid route are
listed for optional GPU repair.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ambiguity_manager.systems.goal_first_analysis_v2 import CANONICAL_AMBIGUITY  # noqa: E402
from lib_capability_debate_20260918 import (  # noqa: E402
    CAPABILITY_SET,
    analysis_dict_from_pred,
    analysis_from_dict,
    extract_json_object,
    load_jsonl,
    load_jsonl_by_id,
    norm_route,
    normalise_debate_obj,
    patch_capability_in_analysis,
    prior_capability_from_pred,
    route_from_analysis,
    slice_stats,
    write_json,
)


def _reparse_role(part: dict[str, Any] | None) -> dict[str, Any]:
    part = dict(part or {})
    raw = part.get("raw_output") or ""
    obj = extract_json_object(raw)
    parsed, meta = normalise_debate_obj(obj)
    # Accept type-only partials for debaters; adjudicator needs a route.
    ok = parsed is not None and not (parsed.get("route_missing") and part.get("role") == "adjudicator")
    # Role may not be inside part; caller sets expectation.
    part["parsed"] = parsed
    part["reparse_meta"] = meta
    part["failed"] = parsed is None or bool(parsed.get("route_missing"))
    part["error"] = None if not part["failed"] else meta.get("error", "reparse_failed")
    return part


def _patch_ambiguity(analysis: dict[str, Any], pilot_types: list[str]) -> dict[str, Any]:
    findings = [
        f
        for f in list(analysis.get("findings") or [])
        if not str(f).startswith("pilot_ambiguity_types:")
    ]
    findings.append("pilot_ambiguity_types:" + json.dumps(pilot_types, separators=(",", ":")))
    canonical = sorted({CANONICAL_AMBIGUITY[t] for t in pilot_types if t in CANONICAL_AMBIGUITY})
    out = dict(analysis)
    out["findings"] = findings
    out["ambiguity_types"] = canonical
    out["ambiguity_present"] = bool(pilot_types) or bool(out.get("ambiguity_present"))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--debate-jsonl", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--capability-judgments", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    gold = load_jsonl_by_id(root / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl")
    preds = load_jsonl_by_id(args.predictions.resolve())
    caps = load_jsonl_by_id(args.capability_judgments.resolve())
    rows_in = load_jsonl(args.debate_jsonl.resolve())

    out_path = out / "ambiguity_debate_adjudication.jsonl"
    if out_path.exists():
        out_path.unlink()

    watch_rows: list[dict[str, Any]] = []
    suggested_rows: list[dict[str, Any]] = []
    need_gpu: list[str] = []
    n_adj_ok = 0

    for row in rows_in:
        rid = str(row["record_id"])
        a = _reparse_role({**(row.get("debater_a") or {}), "role": "debater_a"})
        # Debaters: types-only is enough
        if a.get("parsed") is not None:
            a["failed"] = False
            a["error"] = None
        b = _reparse_role({**(row.get("debater_b") or {}), "role": "debater_b"})
        if b.get("parsed") is not None:
            b["failed"] = False
            b["error"] = None
        adj = _reparse_role({**(row.get("adjudicator") or {}), "role": "adjudicator"})
        # Adjudicator must have a real route
        if adj.get("parsed") is not None and not adj["parsed"].get("route_missing"):
            adj["failed"] = False
            adj["error"] = None
            n_adj_ok += 1
        else:
            adj["failed"] = True
            need_gpu.append(rid)

        final = adj.get("parsed") or {}
        final_types = list(final.get("pilot_ambiguity_types") or [])
        suggested = final.get("suggested_route")
        gold_route = norm_route(str((gold.get(rid) or {}).get("terminal_strategy")))

        analysis = analysis_dict_from_pred(preds[rid]) if rid in preds else None
        routes = {
            "goal_first_manager_v2": "missing",
            "rich_conservative_manager_v2": "missing",
            "degree_based_router_v2": "missing",
        }
        if analysis is not None:
            cap_j = caps.get(rid)
            if cap_j and not cap_j.get("failed") and cap_j.get("capability_status") in CAPABILITY_SET:
                analysis = patch_capability_in_analysis(analysis, str(cap_j["capability_status"]))
            elif prior_capability_from_pred(preds[rid]) in CAPABILITY_SET:
                analysis = patch_capability_in_analysis(
                    analysis, str(prior_capability_from_pred(preds[rid]))
                )
            if final_types or (adj.get("parsed") and not adj.get("failed")):
                analysis = _patch_ambiguity(analysis, final_types)
            routes = route_from_analysis(analysis_from_dict(analysis))

        new_row = {
            **row,
            "debater_a": a,
            "debater_b": b,
            "adjudicator": adj,
            "final_pilot_ambiguity_types": final_types,
            "final_suggested_route": suggested,
            "final_reason": final.get("reason"),
            "accept_debater": final.get("accept_debater"),
            "dissent_notes": final.get("dissent_notes"),
            "gold_route": gold_route,
            "suggested_match_gold": suggested == gold_route if suggested else False,
            "manager_watch_routes": routes,
            "manager_gf_match_gold": routes["goal_first_manager_v2"] == gold_route,
            "failed": bool(adj.get("failed")),
            "reparsed_cpu": True,
            "reused_intent": True,
        }
        with out_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(new_row, ensure_ascii=False, sort_keys=True) + "\n")

        watch_rows.append(
            {
                "record_id": rid,
                "gold_route": gold_route,
                "goal_first_manager_v2": routes["goal_first_manager_v2"],
                "rich_conservative_manager_v2": routes["rich_conservative_manager_v2"],
                "degree_based_router_v2": routes["degree_based_router_v2"],
            }
        )
        suggested_rows.append(
            {
                "record_id": rid,
                "gold_route": gold_route,
                "adjudicator_suggested": suggested or "missing",
            }
        )

    systems = [
        "goal_first_manager_v2",
        "rich_conservative_manager_v2",
        "degree_based_router_v2",
    ]
    summary = {
        "status": "COMPLETE_REPARSE",
        "n": len(rows_in),
        "n_ok": n_adj_ok,
        "n_failed": len(rows_in) - n_adj_ok,
        "need_gpu_repair_ids": need_gpu,
        "suggested_route_accuracy": slice_stats(suggested_rows, "adjudicator_suggested"),
        "manager_watch_after_patch": {sid: slice_stats(watch_rows, sid) for sid in systems},
        "reused_intent": True,
        "capability_judgments_applied": True,
        "reparsed_from": str(args.debate_jsonl).replace("\\", "/"),
        "debate_path": str(out_path).replace("\\", "/"),
    }
    write_json(out / "ambiguity_debate_summary.json", summary)
    write_json(out / "debate_progress.json", {"status": "COMPLETE_REPARSE", **summary})
    write_json(out / "need_gpu_repair.json", {"n": len(need_gpu), "record_ids": need_gpu})
    print(json.dumps(summary, indent=2))
    return 0 if n_adj_ok == len(rows_in) else 2


if __name__ == "__main__":
    raise SystemExit(main())
