#!/usr/bin/env python3
"""Compute non-mutating T28-R2 source-exclusion scenarios."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.model.structured_target import StructuredTargetError, build_structured_target
from ambiguity_manager.model.training_target_packaging import load_training_target_policy_strict


VIEW = ROOT / "data/processed/weak_pool/t28_permitted_train_dev.jsonl"
OUT_JSON = ROOT / "docs/licences/T28_licence_impact_analysis.json"
OUT_MD = ROOT / "docs/licences/T28_licence_impact_analysis.md"
PRIMARY = ["ambik", "indirect_requests", "codraw_icr_v2", "vague", "clara"]
TASKS = ["speech_act_intent", "cpc", "candidate_interpretations", "ambiguity_presence_types", "compound_ambiguity", "risk", "capability", "route", "clarification_target", "rejection", "context_blind_pairing", "uncertainty_sampling", "adapter_training", "source_development_evaluation"]


def read_rows() -> list[dict]:
    return [json.loads(line) for line in VIEW.read_text(encoding="utf-8").splitlines() if line.strip()]


def scenario(rows: list[dict], policy: dict) -> dict:
    train = [r for r in rows if r["split"] == "source_train"]
    dev = [r for r in rows if r["split"] == "source_dev"]
    targets = Counter()
    valid_targets = 0
    for row in rows:
        try:
            target = build_structured_target(row["record"], row["eligibility"], policy=policy)
        except StructuredTargetError:
            continue
        valid_targets += 1
        targets.update(target.supervised_fields)
    groups = Counter(r["group_key"] for r in rows)
    train_groups = {r["group_key"] for r in train}
    dev_groups = {r["group_key"] for r in dev}
    def balance(field: str) -> dict:
        return dict(sorted(Counter(str(r["record"].get(field)) for r in rows).items()))
    return {
        "train_records": len(train),
        "dev_records": len(dev),
        "task_target_count": valid_targets,
        "per_task_counts": {task: targets.get(task, 0) for task in TASKS},
        "source_balance": dict(sorted(Counter(r["record"]["source_dataset"] for r in rows).items())),
        "ambiguity_label_balance": balance("ambiguity_present"),
        "route_balance": balance("recommended_strategy"),
        "risk_balance": balance("risk_level"),
        "capability_balance": balance("capability_status"),
        "group_count": len(groups),
        "train_dev_group_disjoint": not bool(train_groups & dev_groups),
        "minimum_coverage_satisfiable": bool(train and dev and valid_targets and all(targets.get(task, 0) > 0 for task in ("cpc", "route", "risk", "capability"))),
    }


def main() -> int:
    rows = read_rows()
    policy = load_training_target_policy_strict(ROOT / "configs/data/training_target_policy_v1.json")
    scenarios = {}
    scenarios["all_current_primary_sources"] = scenario(rows, policy)
    scenarios["only_explicitly_licensed_sources"] = scenario([], policy)
    scenarios["only_sources_verified_for_noncommercial_academic_training"] = scenario([], policy)
    for source in PRIMARY:
        scenarios[f"remove_{source}"] = scenario([r for r in rows if r["record"]["source_dataset"] != source], policy)
    scenarios["remove_all_unresolved_sources"] = scenario([], policy)
    payload = {
        "ticket": "T28-R2",
        "non_mutating": True,
        "view": "data/processed/weak_pool/t28_permitted_train_dev.jsonl",
        "view_sha256": "34b551c37c8f97c24c1263a2cc12a9497e65f754924f1404c47055999f04ea22",
        "scenarios": scenarios,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# T28-R2 licence impact analysis", "", "These are non-mutating decision-support scenarios. No reduced corpus was created and the frozen T15 manifests were not changed.", ""]
    for name, result in scenarios.items():
        lines += [f"## {name}", "", f"- train: {result['train_records']}; dev: {result['dev_records']}; task targets: {result['task_target_count']}", f"- source balance: `{json.dumps(result['source_balance'], sort_keys=True)}`", f"- per-task counts: `{json.dumps(result['per_task_counts'], sort_keys=True)}`", f"- ambiguity: `{json.dumps(result['ambiguity_label_balance'], sort_keys=True)}`", f"- route: `{json.dumps(result['route_balance'], sort_keys=True)}`", f"- risk: `{json.dumps(result['risk_balance'], sort_keys=True)}`", f"- capability: `{json.dumps(result['capability_balance'], sort_keys=True)}`", f"- groups: {result['group_count']}; train/dev group-disjoint: {result['train_dev_group_disjoint']}; minimum coverage satisfiable: {result['minimum_coverage_satisfiable']}", ""]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({name: {"train": value["train_records"], "dev": value["dev_records"], "targets": value["task_target_count"]} for name, value in scenarios.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
