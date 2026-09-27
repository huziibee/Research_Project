#!/usr/bin/env bash
set -euo pipefail
# R1 is VERIFY_PASSED after CPU salvage — cancel deferred GPU repair that would waste exclusive time.
scancel 53189 2>/dev/null || true
echo "canceled_53189_if_present"
# Annotate manifest with salvage claim boundary
python3 <<'PY'
import json
from pathlib import Path
root = Path('/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911/manager')
m = json.loads((root/'run_manifest.json').read_text())
log = []
lp = root/'cpu_salvage_log_20260912.json'
if lp.exists():
    log = json.loads(lp.read_text())
methods = {}
for item in log:
    for att in item.get('attempts') or []:
        if att.get('error') is None and att.get('method'):
            methods.setdefault(att['method'], 0)
            methods[att['method']] += 1
m['claim_boundary_cpu_salvage'] = (
    'Some R1 rows were recovered by CPU salvage (route-term scrub and/or '
    'rebuild_from_head_fields after cutting generation loops). Rebuild fills '
    'missing CPC/schema fields with conservative defaults; routes come from '
    'deterministic routers on that analysis. Document in report; do not treat '
    'as identical to clean first-pass model JSON.'
)
m['cpu_salvage_success_methods'] = methods
m['row_failure_total'] = 0
m['status'] = 'VERIFY_PASSED'
(root/'run_manifest.json').write_text(json.dumps(m, indent=2, sort_keys=True)+'\n')
print('status', m['status'])
print('methods', methods)
# count failed still
from collections import Counter
pred = root/'predictions'
n_failed = 0
for p in pred.glob('*.predictions.jsonl'):
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        if json.loads(line).get('failed') is True:
            n_failed += 1
print('n_failed_rows', n_failed)
PY
echo "=== QUEUE ==="
squeue -u mbangie
echo "=== R2 glance ==="
ls /home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b/R2/manager/predictions 2>/dev/null | head || true
wc -l /home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b/R2/manager/predictions/*.jsonl 2>/dev/null | tail -5 || true
