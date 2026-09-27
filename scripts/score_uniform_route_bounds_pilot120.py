"""Uniform-policy routing bounds on frozen Pilot-120 gold.

Does not rerun T39. Always-* policies need no model: they emit one route for all
120 records. This closes the proposal baseline table that T39 did not execute
as GPU systems (always-clarify / always-silent-resolve / always-execute).
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl"
EVALS = {
    "direct_base_llm": ROOT
    / "review_bundles/pilot120_t39_20260902/cluster_outputs/R1/direct_base/direct_base_llm.eval.json",
    "t28_selected_adapter_llm": ROOT
    / "review_bundles/pilot120_t39_20260902/cluster_outputs/R1/selected_adapter/t28_selected_adapter_llm.eval.json",
    "degree_based_router": ROOT
    / "review_bundles/pilot120_t39_20260902/cluster_outputs/R1/manager/evaluations/degree_based_router.eval.json",
    "full_type_risk_aware_manager": ROOT
    / "review_bundles/pilot120_t39_20260902/cluster_outputs/R1/manager/evaluations/full_type_risk_aware_manager.eval.json",
    "context_blind_manager": ROOT
    / "review_bundles/pilot120_t39_20260902/cluster_outputs/R1/manager/evaluations/context_blind_manager.eval.json",
}
OUT = ROOT / "outputs/uniform_route_bounds_pilot120_20260911.json"


def main() -> None:
    golds = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    gold_routes = [row["terminal_strategy"] for row in golds]
    n = len(gold_routes)
    counts = Counter(gold_routes)
    uniforms = {
        "always_clarify": "clarify",
        "always_execute": "execute",
        "always_face_preserving_rejection": "face_preserving_rejection",
        "always_silently_resolve": "silently_resolve",
    }
    uniform_scores = {}
    for name, route in uniforms.items():
        correct = sum(1 for gold in gold_routes if gold == route)
        uniform_scores[name] = {
            "predicted_route": route,
            "n_correct": correct,
            "n": n,
            "accuracy": correct / n,
            "note": "constant policy; no model",
        }
    frozen = {}
    for name, path in EVALS.items():
        obj = json.loads(path.read_text(encoding="utf-8"))
        frozen[name] = {
            "accuracy": obj["terminal_strategy"]["accuracy"],
            "n_correct": round(obj["terminal_strategy"]["accuracy"] * n),
            "n": n,
            "macro_f1": obj["terminal_strategy"].get("macro_f1"),
            "source": str(path.relative_to(ROOT)).replace("\\", "/"),
        }
    payload = {
        "dataset": "pilot_120_v1",
        "n": n,
        "gold_terminal_strategy_counts": dict(counts),
        "claim_boundary": (
            "Uniform bounds are arithmetic on frozen gold, not GPU systems. "
            "Frozen T39 ran five systems only. silently_resolve has gold support 0, "
            "so always_silently_resolve cannot score above 0 on this set."
        ),
        "uniform_bounds": uniform_scores,
        "frozen_t39_r1_route_accuracy": frozen,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "gold": dict(counts), "always_clarify": uniform_scores["always_clarify"]}, indent=2))


if __name__ == "__main__":
    main()
