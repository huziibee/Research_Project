#!/usr/bin/env python3
"""Gold-visible engineering consistency test, NOT an accuracy evaluation.

Consumes the archival interpretation key. This key embeds curated candidate
interpretations and therefore cannot be used as independent model input.
The exercise checks whether the deterministic equivalence/verifier runs on
all 120 records and tracks the original alternatives without dropping one.

These reference candidates are textual task descriptions, NOT parsed atomic
multi-action graphs; this smoke test cannot validate task compilation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from collections import Counter

from compound_manager.engine import resolve, apply_answer


def construct_oracle_spec(row: dict) -> dict:
    candidates = row['gold']['candidate_set']
    if not candidates:
        raise ValueError('empty_oracle_candidate_set')
    options = [
        {'value': c['candidate_id'], 'evidence': 'ARCHIVAL_GOLD_VISIBLE_REFERENCE'}
        for c in candidates
    ]
    lookup = {
        c['candidate_id']: {
            'canonical_interpretation': c['canonical_interpretation'],
            'cpc_slots': c.get('cpc_slots', {}),
        }
        for c in candidates
    }
    return {
        'schema_version':'0.1',
        'record_id':row['record_id'],
        'utterance':'ARCHIVAL_REFERENCE_INPUT_NOT_RAW_UTTERANCE',
        'context_evidence':[],
        'variables':{
            'oracle_interpretation':{
                'options':options,
                'grounded': options[0]['value'] if len(options)==1 else None,
                'question':'Which of the archived alternative interpretations applies?',
            }
        },
        'lookups':{'oracle_candidate':lookup},
        'templates':[{
            'actions':[{
                'id':'REFERENCE_1',
                'op':'DESCRIBED_TASK_NOT_ATOMIC_ACTION_GRAPH',
                'args':{'representation':{'$lookup':{'table':'oracle_candidate','key':{'$var':'oracle_interpretation'}}}},
                'after':[],
            }],
        }],
        'fixture_status':'GOLD_VISIBLE_ORACLE_ENGINE_SMOKE_NOT_MODEL_PREDICTION',
    }


def run(input_file:Path, output:Path) -> dict:
    data=input_file.read_bytes()
    rows=[json.loads(line) for line in data.splitlines() if line.strip()]
    if len(rows)!=120 or len({r['record_id'] for r in rows})!=120:
        raise ValueError('expected_120_unique_rows')
    results=[]
    for row in rows:
        spec=construct_oracle_spec(row)
        d=resolve(spec)
        candidate_count=len(row['gold']['candidate_set'])
        if candidate_count not in (1,2):
            raise ValueError('unexpected_candidate_count')
        # Deliberately audit against the original candidate count, not gold route.
        expected='action_ready' if candidate_count==1 else 'needs_clarification'
        if d['status']!=expected:
            raise AssertionError(f"engine_candidate_state_mismatch:{row['record_id']}:{d['status']}:{expected}")
        result={'record_id':row['record_id'],'oracle_candidates':candidate_count,'status':d['status'],
                'distinct_reference_tasks':d.get('distinct_tasks'), 'first_turn_match_to_supplied_count':True}
        if candidate_count==2:
            a=apply_answer(spec,'oracle_interpretation',spec['variables']['oracle_interpretation']['options'][0]['value'])
            b=apply_answer(spec,'oracle_interpretation',spec['variables']['oracle_interpretation']['options'][1]['value'])
            ra,rb=resolve(a),resolve(b)
            if ra['status']!='action_ready' or rb['status']!='action_ready' or ra['complete_task']==rb['complete_task']:
                raise AssertionError(f"oracle_answer_update_failure:{row['record_id']}")
            result['each_oracle_answer_resolves']=True
        results.append(result)
    counts=Counter(r['status'] for r in results)
    summary={'input_sha256':hashlib.sha256(data).hexdigest(),'n':len(results),
             'one_candidate_ready_consistency':counts['action_ready'],
             'two_candidates_clarify_consistency':counts['needs_clarification'],
             'two_candidate_answer_checks':sum(r.get('each_oracle_answer_resolves',False) for r in results),
             'validity':'GOLD_VISIBLE_TAUTOLOGICAL_ENGINE_SMOKE_NOT_BLIND_PERFORMANCE',
             'candidate_source':'historical interpretation-key candidate list (already annotated)',
             'complete_action_graph_correctness':'NOT_TESTED',
             'clarification_question_quality':'NOT_TESTED'}
    output.mkdir(parents=True,exist_ok=True)
    (output/'oracle_smoke_results.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in results),encoding='utf-8')
    (output/'oracle_smoke_summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    print(json.dumps(run(args.input,args.out),indent=2))
