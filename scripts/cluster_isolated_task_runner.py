#!/usr/bin/env python3
"""Run a list of cluster tasks with isolation: one failure does not skip the rest.

Required tasks can fail without aborting later tasks. The process exits 2 if any
required task failed. Optional tasks are skipped when remaining wall time is low.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _remaining_seconds(budget: float | None, started: float) -> float | None:
    if budget is None:
        slurm_end = os.environ.get("SLURM_JOB_END_TIME")
        if slurm_end and slurm_end.isdigit():
            return max(0.0, float(slurm_end) - time.time())
        return None
    return max(0.0, budget - (time.time() - started))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--time-budget-seconds", type=float)
    args = parser.parse_args()
    tasks = json.loads(args.tasks.read_text(encoding="utf-8"))
    if not isinstance(tasks, list) or not tasks:
        raise SystemExit("tasks_must_be_a_nonempty_list")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    ledger_path = output / "task_ledger.jsonl"
    started = time.time()
    required_failed = False
    for index, task in enumerate(tasks):
        task_id = str(task["id"])
        argv = [str(part) for part in task["argv"]]
        required = bool(task.get("required", False))
        min_remaining = float(task.get("min_remaining_seconds", 0))
        remaining = _remaining_seconds(args.time_budget_seconds, started)
        record: dict[str, Any] = {
            "task_id": task_id,
            "index": index,
            "required": required,
            "argv": argv,
            "started_at_epoch": time.time(),
        }
        if remaining is not None and remaining < min_remaining:
            record.update({"status": "skipped_low_time", "remaining_seconds": remaining, "exit_code": None})
            ledger_path.open("a", encoding="utf-8").write(json.dumps(record) + "\n")
            print(json.dumps(record, sort_keys=True), flush=True)
            continue
        log_dir = output / "task_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = log_dir / f"{task_id}.stdout.log"
        stderr_path = log_dir / f"{task_id}.stderr.log"
        try:
            with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
                completed = subprocess.run(argv, stdout=stdout, stderr=stderr, check=False)
            record["exit_code"] = completed.returncode
            record["status"] = "ok" if completed.returncode == 0 else "failed"
        except Exception as exc:  # noqa: BLE001
            record["exit_code"] = None
            record["status"] = "failed"
            record["error"] = f"{type(exc).__name__}:{exc}"
        record["elapsed_seconds"] = round(time.time() - record["started_at_epoch"], 1)
        if record["status"] != "ok" and required:
            required_failed = True
        ledger_path.open("a", encoding="utf-8").write(json.dumps(record) + "\n")
        print(json.dumps({key: record[key] for key in record if key != "argv"}, sort_keys=True), flush=True)
    summary = {
        "status": "REQUIRED_FAILED" if required_failed else "ALL_REQUIRED_OK",
        "n_tasks": len(tasks),
        "elapsed_seconds": round(time.time() - started, 1),
    }
    (output / "task_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 2 if required_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
