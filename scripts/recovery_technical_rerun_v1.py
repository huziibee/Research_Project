#!/usr/bin/env python3
"""Versioned technical sensitivity rerun of three failed seed-0 answered steps.

Never writes the original experiment. The original 26-row score remains primary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import one_turn_recovery_20260922 as original

RUN_ID = "one_turn_recovery_failed_analysis_rerun_v1_20260927"
IDS = ("CA-0702", "CA-0733", "CA-0778")
CAP = 4096  # Original constrained-final cap was 1024; all three hit it.
EXPECTED = {
    "01_frozen_manifest.json": "600ca7b241d556e52487f77dcf9ace12b850758888468e8f88eb3518013c68b3",
    "04_oracle_responses.jsonl": "4e72e07df1136c416f5b3063c14cfd48d03a085a4a4fd13790dcd18820edc0ff",
    "06_answered_predictions_seed0.jsonl": "ca1b80b46af38fc7faec8dc64fbfcde9904be35afde422169efebd971b260d23",
}
FAILED_DEPTH = {"CA-0702": 1, "CA-0733": 2, "CA-0778": 2}
ROW_SHA = {
    "CA-0702": "ddd50590e382271b544b216b6f269a914f19560e5c5036c5518c67862b810920",
    "CA-0733": "c50d096cda12db41b205a1498b7618809f47de81ae8158cc5d5182a86e75f08a",
    "CA-0778": "4cd1479aef289424e683413ff33538c0410e48a73faec9a657f1ae60a4a0d1f7",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def code_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    paths = (
        "scripts/recovery_technical_rerun_v1.py",
        "scripts/one_turn_recovery_20260922.py",
        "scripts/lib_capability_debate_20260918.py",
        "src/ambiguity_manager/systems/goal_first_analysis_v2.py",
        "src/ambiguity_manager/model/task_constrained_decoding.py",
        "src/ambiguity_manager/systems/routing.py",
    )
    return {path: digest((root / path).read_bytes()) for path in paths}


def load_checked(folder: Path) -> tuple[dict, dict[str, dict], list[bytes]]:
    for name, expected in EXPECTED.items():
        actual = digest((folder / name).read_bytes())
        if actual != expected:
            raise ValueError(f"original artifact SHA mismatch: {name}: {actual}")
    manifest = json.loads((folder / "01_frozen_manifest.json").read_text(encoding="utf-8"))
    if not set(IDS).issubset(set(manifest["secondary_ids"])):
        raise ValueError("affected IDs absent from frozen cohort")
    oracles = original.load_jsonl_by_id(folder / "04_oracle_responses.jsonl")
    lines = (folder / "06_answered_predictions_seed0.jsonl").read_bytes().splitlines()
    rows: dict[str, dict] = {}
    selected: list[bytes] = []
    for line in lines:
        row = json.loads(line)
        rid = row["record_id"]
        if rid not in IDS:
            continue
        if rid in rows or digest(line) != ROW_SHA[rid]:
            raise ValueError(f"original failed row identity mismatch: {rid}")
        if row.get("condition") != "answered" or row.get("seed") != 0:
            raise ValueError(f"wrong experimental condition: {rid}")
        if not row.get("failed") or row.get("clarify_depth") != FAILED_DEPTH[rid]:
            raise ValueError(f"not the recorded failure step: {rid}")
        if row.get("terminal_route") not in (None, ""):
            raise ValueError(f"original route unexpectedly present: {rid}")
        steps = row["depth_path"]
        if len(steps) != FAILED_DEPTH[rid] or not steps[-1]["failed"]:
            raise ValueError(f"original depth path mismatch: {rid}")
        if any(step["failed"] for step in steps[:-1]):
            raise ValueError(f"earlier path step failed: {rid}")
        rows[rid] = row
        selected.append(line)
    if len(lines) != 26 or set(rows) != set(IDS) or set(oracles) != set(manifest["secondary_ids"]):
        raise ValueError("original 26-case evidence coverage mismatch")
    return oracles, rows, selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-exp", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--run", action="store_true", help="load GPU and run three failed steps")
    args = parser.parse_args()
    source = args.original_exp.resolve()
    out = args.out.resolve()
    if out == source or source in out.parents:
        raise ValueError("versioned output must differ from original")
    oracles, rows, selected = load_checked(source)
    print(f"PREFLIGHT_OK original=26 affected={','.join(IDS)} answered_seed0_only cap={CAP}", flush=True)
    if not args.run:
        return 0
    if out.exists() and any(out.iterdir()):
        raise ValueError("versioned output is nonempty; refusing overwrite")
    out.mkdir(parents=True, exist_ok=True)
    (out / "original_failed_rows.jsonl").write_bytes(b"\n".join(selected) + b"\n")
    model, tokenizer = original._load_model()
    reruns = []
    for index, rid in enumerate(IDS):
        old = rows[rid]
        rerun_seed = 2026092700 + index
        original.set_run_seed(rerun_seed)
        row = original.process_case(
            model=model,
            tokenizer=tokenizer,
            oracle=oracles[rid],
            condition="answered",
            seed=rerun_seed,
            temperature=0.7,
            max_clarify_depth=5,
            constrained_final_max_new_tokens=CAP,
            resume_turn={
                "depth": FAILED_DEPTH[rid],
                "command": old["command"],
                "dialogue_history": old["dialogue_history"],
            },
            prior_depth_path=old["depth_path"][:-1],
        )
        row["provenance"].update({
            "experiment_id": RUN_ID,
            "original_experiment_id": "one_turn_recovery_20260922",
            "original_condition": "answered_seed0",
            "original_failed_row_sha256": ROW_SHA[rid],
            "resume_at_original_failed_depth": FAILED_DEPTH[rid],
            "constrained_final_max_new_tokens": CAP,
            "rerun_seed": rerun_seed,
            "classification": "technical_sensitivity_only_not_original_score",
        })
        reruns.append(row)
        print(f"RERUN {rid} depth={row['clarify_depth']} route={row['terminal_route']} failed={row['failed']}", flush=True)
    target = out / "answered_failed_step_reruns.jsonl"
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for row in reruns:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    report = {
        "run_id": RUN_ID,
        "code_sha256": code_hashes(),
        "model_id": f"{original.BASE_MODEL}@{original.BASE_REVISION}",
        "scientific_status": "technical_sensitivity_only; original 26-row scores unchanged",
        "original_artifact_sha256": EXPECTED,
        "original_failed_row_sha256": ROW_SHA,
        "affected_condition": "answered seed0 only",
        "constrained_final_max_new_tokens_original": 1024,
        "constrained_final_max_new_tokens_rerun": CAP,
        "rerun_prediction_sha256": digest(target.read_bytes()),
        "cases": [{"record_id": r["record_id"], "failed": r["failed"],
                   "route": r["terminal_route"], "depth": r["clarify_depth"]} for r in reruns],
    }
    (out / "technical_rerun_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"TECHNICAL_RERUN_DONE {target} sha256={report['rerun_prediction_sha256']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
