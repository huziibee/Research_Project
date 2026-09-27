#!/usr/bin/env bash
set -euo pipefail
export GFV2_CODE_ROOT=/home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911
export GFV2_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911
cd "${GFV2_CODE_ROOT}"
export PYTHONPATH="${GFV2_CODE_ROOT}/src:${GFV2_CODE_ROOT}/scripts:${PYTHONPATH:-}"
# Confirm uploads present
test -f scripts/cpu_salvage_goal_first_v2_failed_20260912.py
test -f src/ambiguity_manager/systems/goal_first_analysis_v2.py
python3 scripts/cpu_salvage_goal_first_v2_failed_20260912.py \
  --root "${GFV2_CODE_ROOT}" \
  --manager-dir "${GFV2_OUTPUT}/manager"
echo "=== AFTER SALVAGE COUNTS ==="
python3 - <<'PY'
import json
from pathlib import Path
root=Path('/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911/manager')
m=json.loads((root/'run_manifest.json').read_text())
print('status', m.get('status'), 'row_failure_total', m.get('row_failure_total'))
print('still_failed', m.get('still_failed'))
print('repaired', m.get('repaired'))
s=json.loads((root/'cpu_salvage_summary.json').read_text())
print(json.dumps(s, indent=2))
PY
echo "=== FOLLOWON GLANCE ==="
squeue -u mbangie || true
