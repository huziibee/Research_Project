#!/usr/bin/env python3
"""New v0.3 source-only Qwen3-8B batch: contextual candidate preflight.

The historical experiment is immutable. v0.3 writes to a new output directory,
uses no Pilot-120 labels, preserves every failure and does not claim executed
robot tasks. Run --preflight first; GPU inference is opt-in without that flag.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from compound_manager.contextual_v03 import (
    contextual_prompt, contextual_alerts, CONTEXTUAL_PROMPT_VERSION,
    run_contextual_first_turn,
)
from compound_manager.qwen_adapter import QwenTaskSpecModel, QWEN_NAME, QWEN_REVISION
from run_qwen120 import load_rows

RUN_ID = 'compound_task_qwen3_8b_v03_contextual_source_only'


def run(args):
    rows = load_rows(args.source)  # checks exact frozen source SHA256 / 120 IDs
    selected = set(args.ids or [])
    if selected and not selected <= {r['record_id'] for r in rows}:
        raise ValueError('unknown_case_id')
    if selected:
        rows = [r for r in rows if r['record_id'] in selected]
    args.output.mkdir(parents=True, exist_ok=True)
    prediction_path = args.output / 'predictions.jsonl'
    old = {}
    if prediction_path.exists():
        for line in prediction_path.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            rid = row['record_id']
            if rid in old or rid not in {s['record_id'] for s in rows} or row.get('run_id') != RUN_ID:
                raise ValueError('invalid_existing_run_or_duplicate_id')
            old[rid] = row
    if args.preflight:
        prompts = [{
            'record_id': row['record_id'],
            'prompt_sha256': hashlib.sha256(contextual_prompt(row).encode()).hexdigest(),
            'contextual_targets': [h['target'] for h in contextual_alerts(row)],
        } for row in rows]
        (args.output/'prompt_manifest_v03.json').write_text(json.dumps({
            'run_id': RUN_ID, 'prompt_version': CONTEXTUAL_PROMPT_VERSION,
            'model': QWEN_NAME, 'revision': QWEN_REVISION,
            'rows': prompts,
        }, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps({'preflight':True,'n':len(rows),
            'alerted_cases':sum(bool(x['contextual_targets']) for x in prompts),
            'inference_performed':False,'model':QWEN_NAME,'revision':QWEN_REVISION}))
        return
    model = QwenTaskSpecModel.load(four_bit=not args.no_quant,
                                  local_files_only=not args.allow_download,
                                  max_new_tokens=args.max_new_tokens)
    for index, row in enumerate(rows, 1):
        rid = row['record_id']
        if rid in old:
            continue
        try:
            state = run_contextual_first_turn(row, model, strict_evidence=True)
            outcome = {'run_id':RUN_ID,'record_id':rid,'model':QWEN_NAME,
                'revision':QWEN_REVISION,'prompt_version':CONTEXTUAL_PROMPT_VERSION,
                'failed':state['status']=='parse_failed',
                'status':state['status'], 'result':state}
        except Exception as e:
            outcome = {'run_id':RUN_ID,'record_id':rid,'model':QWEN_NAME,
                'revision':QWEN_REVISION,'prompt_version':CONTEXTUAL_PROMPT_VERSION,
                'failed':True,'status':'inference_failed',
                'error':f'{type(e).__name__}:{e}'}
        with prediction_path.open('a', encoding='utf-8', newline='\n') as fh:
            fh.write(json.dumps(outcome, ensure_ascii=False, sort_keys=True) + '\n')
            fh.flush()
            os.fsync(fh.fileno())
        print(f'{index}/{len(rows)} {rid} {outcome["status"]}', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--ids', action='append', default=[])
    p.add_argument('--max-new-tokens', type=int, default=3072)
    p.add_argument('--no-quant', action='store_true')
    p.add_argument('--allow-download', action='store_true')
    p.add_argument('--preflight', action='store_true')
    run(p.parse_args())