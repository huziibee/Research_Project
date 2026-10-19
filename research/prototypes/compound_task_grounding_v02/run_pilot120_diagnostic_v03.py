#!/usr/bin/env python3
"""Exploratory v0.3 contextual source-probe evaluation (not language-model inference).

Run inside the historical research repository, or pass --repo-root. Does not
modify frozen source, gold or historical result packages. Prediction generation
is a separate first pass that cannot access gold or baseline routing.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from collections import Counter

from compound_manager.source_probe_v03 import probe, action_scaffold, PROBE_VERSION

EXPECTED_SOURCE_SHA = 'f33b1e29f1e8aa256a475f07213aa07247def47d8e2148d54a472a40b71b05c9'
EXPECTED_GOLD_SHA = '5e23ad1a92ff1873c8f039a8ce560a111dd6fb6b8ae8c11d6cf34dbfa1c360db'


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def check_unique(rows, expected=120):
    ids=[r['record_id'] for r in rows]
    if len(ids)!=expected or len(set(ids))!=expected:
        raise ValueError('coverage_mismatch')
    return set(ids)


def matrix(rows):
    labels=['EXECUTE','CLARIFY','REFUSE']
    return {g:{p:sum(r['gold']==g and r['prediction']==p for r in rows) for p in labels} for g in labels}


def evaluate(repo: Path, out: Path) -> dict:
    src=repo/'data/annotations/pilot_120_v1/source_canonical.jsonl'
    golden=repo/'data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl'
    baseline=repo/'research/pilot120/gliner25_action_readiness_repair_v1/baseline83.predictions.jsonl'
    for path,sha in [(src,EXPECTED_SOURCE_SHA),(golden,EXPECTED_GOLD_SHA)]:
        observed=hashlib.sha256(path.read_bytes()).hexdigest()
        if observed!=sha: raise ValueError(f'source_hash_mismatch:{path.name}:{observed}')
    sources=read_jsonl(src)
    ids=check_unique(sources)
    # FIRST PASS: no gold, route or historical predictions are read here.
    predictions=[]
    for row in sources:
        p=probe(row)
        p['action_scaffold']=action_scaffold(row)
        predictions.append(p)
    assert check_unique(predictions)==ids
    # SECOND PASS: frozen gold and previous gate are opened for SCORING only.
    gold={r['record_id']:'REFUSE' if r['terminal_strategy']=='face_preserving_rejection' else r['terminal_strategy'].upper() for r in read_jsonl(golden)}
    gates={r['record_id']:r for r in read_jsonl(baseline)}
    if set(gold)!=ids or set(gates)!=ids: raise ValueError('reference_ids_mismatch')
    scored=[]
    for row in predictions:
        rid=row['record_id']
        raw='CLARIFY' if row['predicted_readiness']=='blocking_ambiguity' else 'EXECUTE'
        gate=gates[rid]
        hybrid='REFUSE' if gate['gate_refuse'] else raw
        scored.append({'record_id':rid,'gold':gold[rid],'prediction':hybrid,'raw_probe':raw,
                       'historical_83_prediction':gate['route'],'gate_refuse':gate['gate_refuse'],
                       'evidence_reasons':[q['reason'] for q in row['evidence']]})
    readiness=[{'record_id':r['record_id'],'gold':r['gold'],'prediction':r['raw_probe']} for r in scored if r['gold']!='REFUSE']
    metrics={
        'run_id':PROBE_VERSION, 'method':'evidence_linked_context_rules_not_llm',
        'design_status':'exploratory_pilot120_development_only',
        'source_sha256':EXPECTED_SOURCE_SHA, 'gold_sha256':EXPECTED_GOLD_SHA,
        'n':len(scored),
        'source_only_99_correct':sum(r['gold']==r['prediction'] for r in readiness),
        'source_only_99_total':len(readiness),
        'hybrid_correct':sum(r['gold']==r['prediction'] for r in scored),
        'hybrid_total':len(scored),
        'baseline_83_correct':sum(r['gold']==r['historical_83_prediction'] for r in scored),
        'all_ready_gated_reference_correct':sum(r['gold']==('REFUSE' if r['gate_refuse'] else 'EXECUTE') for r in scored),
        'confusion':matrix(scored),
        'source_only_confusion':matrix(readiness),
        'unresolved_n':sum(r['predicted_readiness']=='blocking_ambiguity' for r in predictions),
        'wrong_ids':[r['record_id'] for r in scored if r['gold']!=r['prediction']],
        'complete_task_correctness':'NOT_COMPUTED',
        'candidate_coverage_verified':False,
        'disclaimer':'Probe may exploit lexical regularities of this already-examined synthetic panel; do not interpret as task-grounding accuracy or held-out improvement.',
    }
    out.mkdir(parents=True,exist_ok=True)
    for filename,rows in [('predictions.jsonl',predictions),('score_rows.jsonl',scored)]:
        (out/filename).write_text(''.join(json.dumps(x,ensure_ascii=False,sort_keys=True)+'\n' for x in rows),encoding='utf-8')
    (out/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return metrics

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo-root',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ns=ap.parse_args()
    result=evaluate(ns.repo_root,ns.out)
    print(json.dumps(result,indent=2))