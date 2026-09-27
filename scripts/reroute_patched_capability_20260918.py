#!/usr/bin/env python3
"""CPU re-route after capability patch (reuse frozen intent/analysis).

Patches only pilot_capability_status + canonical capability_status, then runs
goal-first / timid / degree routers. Supports:
  --judgments PATH   LLM capability judgments JSONL
  --oracle-gold      Use gold capability_status (upper-bound sanity check)
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

from ambiguity_manager.evaluation import pilot_120 as p120  # noqa: E402
from lib_capability_debate_20260918 import (  # noqa: E402
    CAPABILITY_SET,
    analysis_dict_from_pred,
    analysis_from_dict,
    load_jsonl_by_id,
    norm_route,
    patch_capability_in_analysis,
    prior_capability_from_pred,
    route_from_analysis,
    slice_stats,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--judgments", type=Path, default=None)
    parser.add_argument("--oracle-gold", action="store_true")
    parser.add_argument("--tag", type=str, default="capability_patch")
    args = parser.parse_args()
    if not args.oracle_gold and args.judgments is None:
        raise SystemExit("need --judgments or --oracle-gold")

    root = args.root.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    gold = load_jsonl_by_id(root / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl")
    preds = load_jsonl_by_id(args.predictions.resolve())
    judgments = load_jsonl_by_id(args.judgments.resolve()) if args.judgments else {}

    if set(preds) != set(gold) or len(preds) != 120:
        raise SystemExit(f"pred_gold_id_mismatch n_pred={len(preds)} n_gold={len(gold)}")

    baseline_rows: list[dict[str, Any]] = []
    patched_rows: list[dict[str, Any]] = []
    detail_path = out / f"{args.tag}_per_record.jsonl"
    if detail_path.exists():
        detail_path.unlink()

    n_cap_changed = 0
    n_judge_failed = 0
    n_skipped_no_analysis = 0
    n_false_refuse_baseline = 0
    n_false_refuse_patched = 0

    for rid in sorted(preds):
        pred = preds[rid]
        g = gold[rid]
        gold_route = norm_route(str(g.get("terminal_strategy")))
        gold_cap = str(g.get("capability_status"))
        prior_cap = prior_capability_from_pred(pred)

        analysis0 = analysis_dict_from_pred(pred)
        if analysis0 is None:
            n_skipped_no_analysis += 1
            live = norm_route(str(pred.get("terminal_strategy") or "")) or "missing"
            baseline_rows.append(
                {
                    "record_id": rid,
                    "gold_route": gold_route,
                    "goal_first_manager_v2": live,
                    "rich_conservative_manager_v2": "missing",
                    "degree_based_router_v2": "missing",
                }
            )
            patched_rows.append(
                {
                    "record_id": rid,
                    "gold_route": gold_route,
                    "goal_first_manager_v2": live,
                    "rich_conservative_manager_v2": "missing",
                    "degree_based_router_v2": "missing",
                }
            )
            with detail_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "record_id": rid,
                            "gold_route": gold_route,
                            "skipped": True,
                            "reason": "missing_parsed_analysis",
                            "pred_failed": bool(pred.get("failed")),
                            "pred_error": pred.get("error"),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )
            continue

        base_routes = route_from_analysis(analysis_from_dict(analysis0))
        baseline_row = {
            "record_id": rid,
            "gold_route": gold_route,
            "gold_capability_status": gold_cap,
            "prior_capability": prior_cap,
            **{f"baseline_{k}": v for k, v in base_routes.items()},
        }
        baseline_rows.append(
            {
                "record_id": rid,
                "gold_route": gold_route,
                "goal_first_manager_v2": base_routes["goal_first_manager_v2"],
                "rich_conservative_manager_v2": base_routes["rich_conservative_manager_v2"],
                "degree_based_router_v2": base_routes["degree_based_router_v2"],
            }
        )

        if args.oracle_gold:
            new_cap = gold_cap
            judge_meta: dict[str, Any] = {"source": "oracle_gold"}
            if new_cap not in CAPABILITY_SET:
                raise SystemExit(f"gold_cap_not_in_enum:{rid}:{new_cap}")
        else:
            j = judgments.get(rid)
            if j is None or j.get("failed") or not j.get("capability_status"):
                n_judge_failed += 1
                new_cap = prior_cap if prior_cap in CAPABILITY_SET else "capable"
                judge_meta = {
                    "source": "fallback_prior_or_capable",
                    "failed": True,
                    "judgment": j,
                }
            else:
                new_cap = str(j["capability_status"])
                judge_meta = {
                    "source": "llm_judgment",
                    "confidence": j.get("confidence"),
                    "reason": j.get("reason"),
                    "match_gold": j.get("capability_match_gold"),
                }

        if new_cap != prior_cap:
            n_cap_changed += 1

        patched = patch_capability_in_analysis(analysis0, new_cap)
        new_routes = route_from_analysis(analysis_from_dict(patched))
        patched_rows.append(
            {
                "record_id": rid,
                "gold_route": gold_route,
                "goal_first_manager_v2": new_routes["goal_first_manager_v2"],
                "rich_conservative_manager_v2": new_routes["rich_conservative_manager_v2"],
                "degree_based_router_v2": new_routes["degree_based_router_v2"],
            }
        )

        if gold_route == "execute" and base_routes["goal_first_manager_v2"] == "refuse":
            n_false_refuse_baseline += 1
        if gold_route == "execute" and new_routes["goal_first_manager_v2"] == "refuse":
            n_false_refuse_patched += 1

        detail = {
            **baseline_row,
            "patched_capability": new_cap,
            "capability_changed": new_cap != prior_cap,
            "judge": judge_meta,
            **{f"patched_{k}": v for k, v in new_routes.items()},
            "gf_fixed_false_refuse": (
                gold_route == "execute"
                and base_routes["goal_first_manager_v2"] == "refuse"
                and new_routes["goal_first_manager_v2"] != "refuse"
            ),
            "gf_became_correct": (
                base_routes["goal_first_manager_v2"] != gold_route
                and new_routes["goal_first_manager_v2"] == gold_route
            ),
            "gf_became_wrong": (
                base_routes["goal_first_manager_v2"] == gold_route
                and new_routes["goal_first_manager_v2"] != gold_route
            ),
        }
        with detail_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(detail, ensure_ascii=False, sort_keys=True) + "\n")

    systems = [
        "goal_first_manager_v2",
        "rich_conservative_manager_v2",
        "degree_based_router_v2",
    ]
    summary = {
        "tag": args.tag,
        "mode": "oracle_gold" if args.oracle_gold else "llm_judgments",
        "predictions": str(args.predictions).replace("\\", "/"),
        "judgments": None if args.judgments is None else str(args.judgments).replace("\\", "/"),
        "n": 120,
        "n_skipped_no_analysis": n_skipped_no_analysis,
        "n_capability_changed": n_cap_changed,
        "n_judge_failed_fallback": n_judge_failed,
        "false_refuse_on_gold_execute": {
            "baseline_gf": n_false_refuse_baseline,
            "patched_gf": n_false_refuse_patched,
            "rescued": n_false_refuse_baseline - n_false_refuse_patched,
        },
        "baseline": {sid: slice_stats(baseline_rows, sid) for sid in systems},
        "patched": {sid: slice_stats(patched_rows, sid) for sid in systems},
        "delta_accuracy": {
            sid: slice_stats(patched_rows, sid)["accuracy"]
            - slice_stats(baseline_rows, sid)["accuracy"]
            for sid in systems
        },
        "reused_intent": True,
        "note": (
            "Only capability findings/status patched; intent_summary and other "
            "analysis fields reused from frozen predictions. Rows without "
            "parsed.analysis are left unchanged."
        ),
    }
    write_json(out / f"{args.tag}_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
