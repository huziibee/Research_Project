from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_isolated_runner_continues_after_failure(tmp_path: Path):
    tasks = [
        {"id": "ok", "required": True, "argv": [sys.executable, "-c", "print('ok')"]},
        {"id": "boom", "required": True, "argv": [sys.executable, "-c", "raise SystemExit(7)"]},
        {"id": "after", "required": False, "argv": [sys.executable, "-c", "print('after')"]},
    ]
    task_path = tmp_path / "tasks.json"
    task_path.write_text(json.dumps(tasks), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "cluster_isolated_task_runner.py"),
            "--tasks",
            str(task_path),
            "--output-dir",
            str(tmp_path / "out"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2, completed.stdout + completed.stderr
    ledger = (tmp_path / "out" / "task_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(ledger) == 3
    statuses = [json.loads(line)["status"] for line in ledger]
    assert statuses == ["ok", "failed", "ok"]
    summary = json.loads((tmp_path / "out" / "task_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "REQUIRED_FAILED"
