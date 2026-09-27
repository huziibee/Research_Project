#!/usr/bin/env bash
set -euo pipefail
python3 <<'PY'
import json
from pathlib import Path
root = Path('/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911/manager')
ids_full = ['CA-0105','CA-0332','CA-0360','CA-0382','CA-0648','CA-0714','CA-0762','CA-0866']
ids_blind = ['CA-0805']
pred = root/'predictions'/'goal_first_manager_v2.predictions.jsonl'
blind = root/'predictions'/'goal_first_context_blind_v2.predictions.jsonl'
rows = {json.loads(l)['record_id']: json.loads(l) for l in pred.read_text().splitlines() if l.strip()}
brows = {json.loads(l)['record_id']: json.loads(l) for l in blind.read_text().splitlines() if l.strip()}
out = []
for rid in ids_full:
    r = rows[rid]
    raw = r.get('raw_output') or ''
    out.append({
        'id': rid,
        'scope': 'full',
        'error': r.get('error'),
        'raw_len': len(raw),
        'raw_tail': raw[-400:],
        'raw_head': raw[:400],
        'brace_balance': raw.count('{')-raw.count('}'),
        'attempts': r.get('analysis_attempts'),
    })
    print('====', rid, r.get('error'), 'len', len(raw), 'bal', raw.count('{')-raw.count('}'))
    print('HEAD', raw[:300].replace('\n',' | '))
    print('TAIL', raw[-300:].replace('\n',' | '))
for rid in ids_blind:
    r = brows[rid]
    raw = r.get('raw_output') or ''
    print('==== BLIND', rid, r.get('error'), 'len', len(raw))
    print('HEAD', raw[:500].replace('\n',' | '))
    print('TAIL', raw[-300:].replace('\n',' | '))
    out.append({'id': rid, 'scope': 'blind', 'error': r.get('error'), 'raw_len': len(raw), 'raw_head': raw[:500], 'raw_tail': raw[-400:]})
(root/'remaining_failed_raw_diag_20260912.json').write_text(json.dumps(out, indent=2)+'\n')
print('wrote diag')
PY
