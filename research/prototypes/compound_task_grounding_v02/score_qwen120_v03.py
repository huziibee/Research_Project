#!/usr/bin/env python3
"""Score completed v0.3 Qwen task-readiness predictions (no inference).

Uses frozen Pilot-120 gold ONLY AFTER the source-only Qwen run has completed.
Scores the 99 historical EXECUTE/CLARIFY cases separately from the 21
historical hard-refusal cases, which are outside the ambiguity-only task.
The original v35 three-way route labels are a proxy for readiness, not
independent complete-task/action-graph annotations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from run_qwen120_v03 import RUN_ID
from run_qwen120 import SOURCE_SHA256
from run_pilot120_diagnostic_v03 import EXPECTED_GOLD_SHA
from compound_manager.qwen_adapter import QWEN_NAME, QWEN_REVISION

PREDICTION_LABELS = ('EXECUTE', 'CLARIFY', 'ABSTAIN', 'FAILED')


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def readiness_label(row: dict[str, Any]) -> str:
    """Do not credit an unsupported 'clarify' or context repair as success."""
    status = row.get('status')
    if row.get('failed') or status in ('parse_failed', 'inference_failed'):
        return 'FAILED'
    result = row.get('result')
    if not isinstance(result, dict):
        return 'FAILED'
    verdict = result.get('verdict')
    if not isinstance(verdict, dict):
        return 'FAILED'
    if status == 'action_ready':
        task = verdict.get('complete_task')
        if verdict.get('status') == 'action_ready' and verdict.get('action_ready') is True and isinstance(task, dict) and isinstance(task.get('actions'), list) and task['actions']:
            return 'EXECUTE'
        return 'FAILED'
    if status == 'needs_clarification':
        if (verdict.get('status') == 'needs_clarification'
            and isinstance(verdict.get('question'), str) and verdict['question'].strip()
            and isinstance(verdict.get('answer_options'), list) and len(verdict['answer_options']) >= 2
            and isinstance(verdict.get('distinct_tasks'), int) and verdict['distinct_tasks'] >= 2):
            return 'CLARIFY'
        return 'FAILED'
    if status == 'needs_context_repair':
        return 'ABSTAIN'
    return 'FAILED'


def summarize(scored: list[dict[str, Any]]) -> dict[str, Any]:
    applicable = [x for x in scored if x['gold'] in ('EXECUTE','CLARIFY')]
    correct = sum(x['prediction'] == x['gold'] for x in applicable)
    confusion = {actual: {p:sum(x['gold']==actual and x['prediction']==p for x in applicable)
                          for p in PREDICTION_LABELS}
                 for actual in ('EXECUTE','CLARIFY')}
    return {
        'ambiguity_relevant_n':len(applicable),
        'ambiguity_relevant_correct': correct,
        'readiness_accuracy': correct/len(applicable) if applicable else None,
        'full_120_coverage': len(scored),
        'hard_refusal_cases_not_scored_for_readiness': sum(x['gold']=='REFUSE' for x in scored),
        'false_ready_on_gold_clarify': confusion['CLARIFY']['EXECUTE'],
        'unnecessary_clarifications_on_gold_execute': confusion['EXECUTE']['CLARIFY'],
        'abstentions_on_99': sum(x['prediction']=='ABSTAIN' for x in applicable),
        'model_failures_on_99': sum(x['prediction']=='FAILED' for x in applicable),
        'confusion_e_c':confusion,
        'readiness_unscored_21_predictions': dict(Counter(x['prediction'] for x in scored if x['gold']=='REFUSE')),
        'complete_task_graph_accuracy':'NOT_COMPUTED_no_independent_gold',
        'evidence_and_candidate_completeness':'NOT_INDEPENDENTLY_VALIDATED',
        'model_inference_status':'RECORDED_IN_INPUT_STREAM_NOT_REPLAYED_BY_THIS_SCORER',
        'development_only':True,
    }


def evaluate(source: Path, gold: Path, predictions: Path, output: Path) -> dict[str, Any]:
    source_digest, gold_digest = sha256(source), sha256(gold)
    if source_digest != SOURCE_SHA256 or gold_digest != EXPECTED_GOLD_SHA:
        raise ValueError('frozen_file_checksum_mismatch')
    sources = read_jsonl(source)
    golds = read_jsonl(gold)
    predictions_rows = read_jsonl(predictions)
    ids = [r['record_id'] for r in sources]
    if len(ids) != 120 or len(set(ids)) != 120:
        raise ValueError('invalid_source_identity')
    gold_map = {r['record_id']: ('REFUSE' if r['terminal_strategy']=='face_preserving_rejection' else r['terminal_strategy'].upper()) for r in golds}
    if len(gold_map) != 120 or set(gold_map)!=set(ids):
        raise ValueError('invalid_gold_coverage')
    received_ids = [r['record_id'] for r in predictions_rows]
    if len(received_ids) != 120 or len(set(received_ids)) != 120 or set(received_ids) != set(ids):
        raise ValueError('model_prediction_coverage_not_120_unique')
    by_id = {r['record_id']:r for r in predictions_rows}
    for row in predictions_rows:
        if row.get('run_id') != RUN_ID or row.get('model')!=QWEN_NAME or row.get('revision')!=QWEN_REVISION:
            raise ValueError('unexpected_run_model_or_revision')
    scored=[]
    for rid in ids:
        row = by_id[rid]
        result = row.get('result') or {}
        verdict = result.get('verdict') or {}
        scored.append({
            'record_id':rid, 'gold':gold_map[rid],
            'prediction':readiness_label(row), 'model_status':row.get('status'),
            'distinct_tasks':verdict.get('distinct_tasks'),
            'question_target':verdict.get('question_target'),
            'alert_targets':[h.get('target') for h in (result.get('source_only_context_alerts') or [])],
            'readiness_blocked_by_context_audit':bool(result.get('readiness_blocked_by_context_audit')),
            'quotes_verified':(result.get('audit') or {}).get('quotes_verified'),
        })
    metrics=summarize(scored)
    metrics.update({'run_id':RUN_ID,'source_sha256':source_digest,
                    'gold_sha256':gold_digest,'prediction_file_sha256':sha256(predictions)})
    output.mkdir(parents=True,exist_ok=True)
    (output/'readiness_metrics_v03.json').write_text(json.dumps(metrics,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    (output/'readiness_case_ledger_v03.jsonl').write_text(''.join(json.dumps(row,sort_keys=True)+'\n' for row in scored),encoding='utf-8')
    return metrics


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source', type=Path,required=True)
    p.add_argument('--gold', type=Path,required=True)
    p.add_argument('--predictions',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    print(json.dumps(evaluate(args.source,args.gold,args.predictions,args.output),indent=2))