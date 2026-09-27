#!/usr/bin/env bash
set -euo pipefail
python3 <<'PY'
import json
from pathlib import Path
from collections import Counter
out = Path('/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b/R2/manager')
print('manifest', (out/'run_manifest.json').read_text()[:400] if (out/'run_manifest.json').exists() else 'missing')
print('progress', (out/'progress.json').read_text() if (out/'progress.json').exists() else 'missing')
print('cpu_salvage_summary', (out/'cpu_salvage_summary.json').exists())
for p in sorted((out/'predictions').glob('*.jsonl')):
    rows=[json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    ids=[r.get('record_id') for r in rows]
    failed=sum(1 for r in rows if r.get('failed') is True)
    salvage_notes=0
    for r in rows:
        att=r.get('analysis_attempts') or []
        if any((isinstance(a, dict) and 'cpu_salvage' in str(a)) for a in att):
            salvage_notes += 1
    print(p.name, 'n', len(rows), 'unique', len(set(ids)), 'failed', failed, 'salvage_tagged', salvage_notes, 'last', ids[-3:] if ids else None)
print('evaluations_dir', (out/'evaluations').exists())
# job still writing?
import subprocess
print(subprocess.check_output(['squeue','-j','53188','-o','%T %M'], text=True))
PY
