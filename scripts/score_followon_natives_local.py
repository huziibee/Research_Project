#!/usr/bin/env python3
"""Score pulled follow-on natives locally. Majority + unique-input; no Pilot-120 pooling."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)


def summarize(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    keep = {
        k: data[k]
        for k in (
            "status",
            "task",
            "n",
            "correct",
            "accuracy",
            "accuracy_interval",
            "macro_exact_set_recall",
            "modal_joint_baseline",
            "unique_input_sensitivity",
            "field_scores",
            "conditions",
            "paired_caption_benefit",
            "ambiguity_present_confusion",
            "claim_boundary",
        )
        if k in data
    }
    if "modal_joint_baseline" in keep:
        keep["majority_baseline"] = keep["modal_joint_baseline"]
    return keep


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-root", type=Path, required=True, help="Local pulled native/ directory")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    summary: dict = {
        "claim_boundary": (
            "Exploratory source-native scores only. Majority/modal and unique-input "
            "sensitivity are reported separately. Do not pool with Pilot-120 route accuracy. "
            "T39/T41 frozen. Adapter unofficial."
        ),
        "native_scores": {},
        "errors": [],
        "missing": [],
    }
    jobs = [
        {
            "system": "gemma4",
            "task": "vague",
            "script": ROOT / "scripts" / "score_vague_goal_intent.py",
            "extra": [
                "--gold",
                str(ROOT / "outputs" / "vague_goal_intent_context_ablation_inputs_20260902.jsonl"),
            ],
        },
        {
            "system": "glm47",
            "task": "vague",
            "script": ROOT / "scripts" / "score_vague_goal_intent.py",
            "extra": [
                "--gold",
                str(ROOT / "outputs" / "vague_goal_intent_context_ablation_inputs_20260902.jsonl"),
            ],
        },
        {
            "system": "gemma4",
            "task": "ambik",
            "script": ROOT / "scripts" / "score_ambik_ambiguity_type.py",
            "extra": ["--key", str(ROOT / "outputs" / "ambik_ambiguity_type_source_key_20260908.jsonl")],
        },
        {
            "system": "glm47",
            "task": "ambik",
            "script": ROOT / "scripts" / "score_ambik_ambiguity_type.py",
            "extra": ["--key", str(ROOT / "outputs" / "ambik_ambiguity_type_source_key_20260908.jsonl")],
        },
        {
            "system": "gemma4",
            "task": "indirect",
            "script": ROOT / "scripts" / "score_native_context.py",
            "extra": [
                "--task",
                "indirect",
                "--key",
                str(ROOT / "outputs" / "indirect_pragmatic_key_20260908.jsonl"),
                "--unique-input-ledger",
                str(ROOT / "outputs" / "indirect_effective_input_ledger_20260911.jsonl"),
            ],
        },
        {
            "system": "glm47",
            "task": "indirect",
            "script": ROOT / "scripts" / "score_native_context.py",
            "extra": [
                "--task",
                "indirect",
                "--key",
                str(ROOT / "outputs" / "indirect_pragmatic_key_20260908.jsonl"),
                "--unique-input-ledger",
                str(ROOT / "outputs" / "indirect_effective_input_ledger_20260911.jsonl"),
            ],
        },
        {
            "system": "gemma4",
            "task": "clara",
            "script": ROOT / "scripts" / "score_native_context.py",
            "extra": [
                "--task",
                "clara",
                "--key",
                str(ROOT / "outputs" / "clara_context_routing_key_20260908.jsonl"),
                "--unique-input-ledger",
                str(ROOT / "outputs" / "clara_effective_input_ledger_20260911.jsonl"),
            ],
        },
        {
            "system": "glm47",
            "task": "clara",
            "script": ROOT / "scripts" / "score_native_context.py",
            "extra": [
                "--task",
                "clara",
                "--key",
                str(ROOT / "outputs" / "clara_context_routing_key_20260908.jsonl"),
                "--unique-input-ledger",
                str(ROOT / "outputs" / "clara_effective_input_ledger_20260911.jsonl"),
            ],
        },
    ]
    for job in jobs:
        pred = args.native_root / job["system"] / job["task"] / "predictions.jsonl"
        key = f"{job['system']}/{job['task']}"
        if not pred.is_file():
            summary["missing"].append(key)
            continue
        dest = out / job["system"] / f"{job['task']}_score.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.unlink()
        cmd = [sys.executable, str(job["script"]), "--predictions", str(pred), "--out", str(dest), *job["extra"]]
        try:
            run(cmd)
            summary["native_scores"][key] = {"path": str(dest), **summarize(dest)}
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(f"{key}:{exc!r}")
    (out / "followon_native_score_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: summary[k] for k in ("missing", "errors", "native_scores")}, indent=2, sort_keys=True)[:4000])
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
