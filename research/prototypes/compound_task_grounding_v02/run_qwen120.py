#!/usr/bin/env python3
"""Prospective source-only Qwen -> TaskSpec -> readiness experiment.

This does not use gold or old predictions. Failed cases remain rows.
This script was authored without executing Qwen in the current environment.
Model weights/environment must be supplied separately on a suitable GPU.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path

from compound_manager.pipeline import run_first_turn
from compound_manager.qwen_adapter import QwenTaskSpecModel, QWEN_NAME, QWEN_REVISION
from compound_manager.model_adapter import build_model_prompt

SOURCE_SHA256='f33b1e29f1e8aa256a475f07213aa07247def47d8e2148d54a472a40b71b05c9'
RUN_ID='compound_task_qwen3_8b_v02_source_only'


def load_rows(path:Path):
    blob=path.read_bytes()
    digest=hashlib.sha256(blob).hexdigest()
    if digest!=SOURCE_SHA256:
        raise ValueError(f'changed_frozen_source:{digest}')
    rows=[json.loads(line) for line in blob.splitlines() if line.strip()]
    ids=[r['record_id'] for r in rows]
    if len(rows)!=120 or len(set(ids))!=120:
        raise ValueError('source_coverage_not_120_unique')
    return rows


def run(args):
    rows=load_rows(args.source)
    ids=set(args.ids or [])
    if ids and not ids <= {r['record_id'] for r in rows}:
        raise ValueError('unknown_case_id')
    if ids:
        rows=[r for r in rows if r['record_id'] in ids]
    args.output.mkdir(parents=True,exist_ok=True)
    predpath=args.output/'predictions.jsonl'
    existing={}
    if predpath.exists():
        for line in predpath.read_text(encoding='utf-8').splitlines():
            row=json.loads(line)
            rid=row['record_id']
            if rid in existing or row.get('run_id')!=RUN_ID:
                raise ValueError('invalid_existing_run_or_duplicate_id')
            existing[rid]=row
    if args.preflight:
        prompts=[{'record_id':r['record_id'], 'prompt_sha256':hashlib.sha256(build_model_prompt(r).encode('utf-8')).hexdigest()} for r in rows]
        (args.output/'prompt_manifest.json').write_text(json.dumps(prompts,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'preflight':True,'n':len(rows),'model':QWEN_NAME,'revision':QWEN_REVISION,'inference_performed':False}))
        return
    model=QwenTaskSpecModel.load(four_bit=not args.no_quant,
        local_files_only=not args.allow_download, max_new_tokens=args.max_new_tokens)
    for index,row in enumerate(rows,1):
        rid=row['record_id']
        if rid in existing:continue
        try:
            result=run_first_turn(row,model,strict_evidence=True)
            outcome={'run_id':RUN_ID,'record_id':rid,'model':QWEN_NAME,'revision':QWEN_REVISION,
                'failed':result['status']=='parse_failed','status':result['status'],
                'result':result}
        except Exception as err:  # Preserve failure in denominator for audit.
            outcome={'run_id':RUN_ID,'record_id':rid,'model':QWEN_NAME,'revision':QWEN_REVISION,
                'failed':True,'status':'inference_failed','error':f'{type(err).__name__}:{err}'}
        with predpath.open('a',encoding='utf-8',newline='\n') as f:
            f.write(json.dumps(outcome,ensure_ascii=False,sort_keys=True)+'\n')
            f.flush();os.fsync(f.fileno())
        print(f'{index}/{len(rows)} {rid} {outcome["status"]}',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ids',action='append',default=[])
    p.add_argument('--max-new-tokens',type=int,default=3072)
    p.add_argument('--no-quant',action='store_true')
    p.add_argument('--allow-download',action='store_true')
    p.add_argument('--preflight',action='store_true')
    run(p.parse_args())
