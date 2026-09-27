#!/usr/bin/env bash
set -euo pipefail
python3 <<'PY'
import json
from pathlib import Path
root = Path('/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b')
for rep in ('R2','R3'):
    man = root/rep/'manager'/'run_manifest.json'
    m = json.loads(man.read_text())
    print('====', rep, 'status', m.get('status'), 'row_fail', m.get('row_failure_total'), 'cpu_salvage', m.get('cpu_salvage'), 'repaired', m.get('repaired'))
    print('  salvage_summary', (root/rep/'manager'/'cpu_salvage_summary.json').exists())
    evals = root/rep/'manager'/'evaluations'
    if evals.exists():
        for p in sorted(evals.glob('*.eval.json')):
            e=json.loads(p.read_text())
            acc=(e.get('terminal_strategy') or {}).get('accuracy')
            print(' ', p.name, 'acc', acc)
    tagged=0
    failed=0
    for p in (root/rep/'manager'/'predictions').glob('*.jsonl'):
        for line in p.open():
            if not line.strip():
                continue
            r=json.loads(line)
            if r.get('failed'):
                failed += 1
            if any('cpu_salvage' in str(a) for a in (r.get('analysis_attempts') or [])):
                tagged += 1
    print('  failed_rows', failed, 'salvage_tagged', tagged)

# native start
native=root/'native'
if native.exists():
    for p in sorted(native.rglob('predictions.jsonl')):
        n=sum(1 for line in p.open() if line.strip())
        print('native', p.relative_to(root), n)
    for p in sorted(native.rglob('run_manifest.json')):
        print('native_man', p.relative_to(root), p.read_text()[:200].replace('\n',' '))
print('gemma_vague_stdout', (root/'task_logs'/'gemma4_vague.stdout.log').read_text()[:200] if (root/'task_logs'/'gemma4_vague.stdout.log').exists() else 'missing')
PY
squeue -u mbangie
