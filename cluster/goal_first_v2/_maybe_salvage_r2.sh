#!/usr/bin/env bash
# If R2 just finished with failed rows AND R3 has not started writing yet, salvage R2 now.
# Never rewrite a replica that is still RUNNING.
set -euo pipefail
export GFV2_CODE_ROOT=/home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911
export FOLLOWON_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b
python3 <<'PY'
import json, os, subprocess
from pathlib import Path
out = Path(os.environ["FOLLOWON_OUTPUT"])
r2m = out / "R2" / "manager" / "run_manifest.json"
r3pred = out / "R3" / "manager" / "predictions"
if not r2m.exists():
    print("r2_manifest_missing")
    raise SystemExit(0)
m = json.loads(r2m.read_text())
status = str(m.get("status") or "")
print("r2_status", status)
if status == "RUNNING":
    print("skip_salvage_r2_still_running")
    raise SystemExit(0)
if r3pred.exists() and any(r3pred.glob("*.jsonl")):
    # R3 already writing — still safe to salvage R2 (separate dir) if verify finished.
    print("r3_started_but_r2_dir_independent")
systems = [
    "goal_first_manager_v2",
    "rich_conservative_manager_v2",
    "degree_based_router_v2",
    "goal_first_context_blind_v2",
]
failed = 0
for sid in systems:
    p = out / "R2" / "manager" / "predictions" / f"{sid}.predictions.jsonl"
    if not p.exists():
        continue
    failed += sum(1 for line in p.open() if line.strip() and json.loads(line).get("failed") is True)
print("r2_failed_rows", failed)
if failed == 0:
    print("no_salvage_needed")
    raise SystemExit(0)
print("running_salvage_r2")
raise SystemExit(11)
PY
rc=$?
if [[ "${rc}" -eq 11 ]]; then
  bash "${GFV2_CODE_ROOT}/cluster/goal_first_v2/_salvage_followon_replica.sh" R2
  echo "=== R2 AFTER SALVAGE ==="
  python3 -c "import json; from pathlib import Path; m=json.loads(Path('/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b/R2/manager/run_manifest.json').read_text()); print(m.get('status'), m.get('row_failure_total'), m.get('still_failed'))"
else
  echo "no_salvage_this_pass rc=${rc}"
fi
