#!/usr/bin/env python3
"""Aggregate ABLE IX five-run Goal-First scores. Report each seed and the mean.

Does not pool seeds as independent cases. Intent is the automatic screen.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


TEMPS = ("0.0", "0.3", "0.5", "0.7", "1.0")


def mean_sd(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"n": 0, "mean": None, "sd": None, "min": None, "max": None}
    if len(values) == 1:
        return {"n": 1, "mean": values[0], "sd": 0.0, "min": values[0], "max": values[0]}
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "sd": statistics.stdev(values),
        "min": min(values),
        "max": max(values),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    by_temp: dict[str, dict] = {}
    for temp in TEMPS:
        tdir = root / f"T{temp}"
        seeds = []
        for score_path in sorted(tdir.glob("seed_*/score.json")):
            row = json.loads(score_path.read_text(encoding="utf-8"))
            seeds.append(
                {
                    "seed": row.get("seed"),
                    "route": row.get("exact_route"),
                    "intent_screen": row.get("intent_screen"),
                    "failed": row.get("failed_in_denominator"),
                    "n": row.get("n"),
                    "path": str(score_path),
                }
            )
        routes = [s["route"] for s in seeds if s["route"] is not None]
        intents = [s["intent_screen"] for s in seeds if s["intent_screen"] is not None]
        by_temp[f"T{temp}"] = {
            "temperature": float(temp),
            "seeds_retained": seeds,
            "route_over_120": mean_sd([float(x) for x in routes]),
            "intent_screen_over_120": mean_sd([float(x) for x in intents]),
            "n_complete_seeds": len(seeds),
            "target_seeds": 5,
        }

    payload = {
        "experiment": "ABLE_IX_five_seed_goal_first_temperature_ablation",
        "intent_metric": "automatic_jaccard_0.18_polarity_skip_not_official_two_judge",
        "aggregation": "descriptive_mean_across_pre_specified_seeds_do_not_pool_as_independent_cases",
        "seed_policy": "seed 0 = existing unified fix-stack emit; seeds 1-4 = new matched emits; all retained",
        "by_temperature": by_temp,
        "paper_table": [
            {
                "T": temp,
                "route_mean": by_temp[f"T{temp}"]["route_over_120"]["mean"],
                "route_sd": by_temp[f"T{temp}"]["route_over_120"]["sd"],
                "intent_mean": by_temp[f"T{temp}"]["intent_screen_over_120"]["mean"],
                "intent_sd": by_temp[f"T{temp}"]["intent_screen_over_120"]["sd"],
                "n_seeds": by_temp[f"T{temp}"]["n_complete_seeds"],
                "per_seed_routes": [s["route"] for s in by_temp[f"T{temp}"]["seeds_retained"]],
            }
            for temp in TEMPS
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
