#!/usr/bin/env bash
# Salvage R3 only after it is no longer RUNNING.
set -euo pipefail
export GFV2_CODE_ROOT=/home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911
export FOLLOWON_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b
python3 <<'PY'
import json, os, sys
from pathlib import Path
out = Path(os.environ["FOLLOWON_OUTPUT"])
man = out / "R3" / "manager" / "run_manifest.json"
if not man.exists():
    print("r3_manifest_missing")
    sys.exit(0)
m = json.loads(man.read_text())
status = str(m.get("status") or "")
print("r3_status", status)
if status == "RUNNING":
    print("skip_salvage_r3_still_running")
    sys.exit(0)
systems = [
    "goal_first_manager_v2",
    "rich_conservative_manager_v2",
    "degree_based_router_v2",
    "goal_first_context_blind_v2",
]
failed = 0
for sid in systems:
    p = out / "R3" / "manager" / "predictions" / f"{sid}.predictions.jsonl"
    if not p.exists():
        continue
    failed += sum(1 for line in p.open() if line.strip() and json.loads(line).get("failed") is True)
print("r3_failed_rows", failed)
if failed == 0:
    print("no_salvage_needed")
    sys.exit(0)
print("running_salvage_r3")
sys.exit(11)
PY
rc=$?
if [[ "${rc}" -eq 11 ]]; then
  bash "${GFV2_CODE_ROOT}/cluster/goal_first_v2/_salvage_followon_replica.sh" R3
  python3 -c "import json; from pathlib import Path; m=json.loads(Path('/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b/R3/manager/run_manifest.json').read_text()); print('AFTER', m.get('status'), m.get('row_failure_total'), m.get('still_failed'))"
else
  echo "no_salvage_this_pass rc=${rc}"
fi
