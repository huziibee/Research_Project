#!/usr/bin/env python3
"""Replay Qwen-generated TaskSpecs for up to five genuine question/answer steps.

Requires independently supplied, question-specific answer bindings; never reads
legacy gold, and never constructs an oracle full-intent restatement. Passing a
valid option only establishes state-machine completeness, NOT final task accuracy.

The initial TaskSpec must come from a separately recorded first-turn model run.
This replay does not re-run Qwen and cannot repair a model's missing candidate.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from compound_manager.pipeline import answer_turn
from run_qwen120_v03 import RUN_ID

MAX_QUESTIONS = 5


def replay(state: dict[str, Any], answer: Callable[[str, list[Any], int], str | None],
           *, max_questions: int = MAX_QUESTIONS) -> dict[str, Any]:
    if not 0 <= max_questions <= MAX_QUESTIONS:
        raise ValueError('max_questions_out_of_range')
    record_id = state.get('record_id')
    transcript: list[dict[str, Any]] = []
    turns_used = 0
    initial_status = state.get('status')
    termination = initial_status
    readiness_depth = 0 if initial_status == 'action_ready' else None
    while state.get('status') == 'needs_clarification' and turns_used < max_questions:
        verdict = state.get('verdict') or {}
        target = verdict.get('question_target')
        options = verdict.get('answer_options')
        question = verdict.get('question')
        if not target or not isinstance(options, list) or not question:
            termination = 'invalid_question_state'
            break
        reply = answer(target, options, turns_used + 1)
        entry = {
            'turn': turns_used + 1,
            'target': target,
            'question': question,
            'answer_options': options,
            'answer': reply,
        }
        if reply is None:
            entry['outcome'] = 'no_answer_available'
            transcript.append(entry)
            termination = 'no_answer_available'
            break
        try:
            state = answer_turn(state, reply)
        except (ValueError, KeyError, TypeError) as exc:
            entry['outcome'] = 'invalid_answer'
            entry['error'] = f'{type(exc).__name__}:{exc}'
            transcript.append(entry)
            termination = 'invalid_answer'
            break
        turns_used += 1
        entry['outcome'] = state.get('status')
        transcript.append(entry)
        termination = state.get('status')
        if state.get('status') == 'action_ready':
            readiness_depth = turns_used
            break
        if state.get('status') == 'needs_context_repair':
            termination = 'needs_context_repair'
            break
    else:
        if state.get('status') == 'needs_clarification' and turns_used == max_questions:
            termination = 'depth_cap'

    verdict = state.get('verdict') or {}
    return {
        'record_id': record_id,
        'initial_status': initial_status,
        'final_status': state.get('status'),
        'termination': termination,
        'turns_used': turns_used,
        'readiness_depth': readiness_depth,
        'transcript': transcript,
        'final_complete_task': verdict.get('complete_task') if state.get('status') == 'action_ready' else None,
        'gold_task_correct': 'NOT_COMPUTED_NO_INDEPENDENT_TASK_GOLD',
        'answer_source': 'external_question_specific_values_not_gold_route',
    }


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def load_answer_map(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    records = read_jsonl(path)
    answer_map: dict[str, dict[str, str]] = {}
    for row in records:
        rid = row.get('record_id')
        bindings = row.get('answers')
        if not isinstance(rid, str) or rid in answer_map or not isinstance(bindings, dict):
            raise ValueError('invalid_answer_source_record')
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in bindings.items()):
            raise ValueError('answer_values_must_be_strings')
        answer_map[rid] = bindings
    return answer_map


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predictions', type=Path, required=True,
                        help='First-turn Qwen v0.3 predictions.jsonl')
    parser.add_argument('--answers', type=Path, default=None,
                        help='Independent answer JSONL: {record_id,answers:{variable:"option"}}')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-questions', type=int, default=MAX_QUESTIONS)
    parser.add_argument('--interactive', action='store_true',
                        help='Ask a human in the terminal when a variable has no supplied answer')
    args = parser.parse_args()
    if not 0 <= args.max_questions <= MAX_QUESTIONS:
        parser.error('max questions must be in [0,5]')
    rows = read_jsonl(args.predictions)
    ids = [row.get('record_id') for row in rows]
    if not ids or len(set(ids)) != len(ids) or any(row.get('run_id') != RUN_ID for row in rows):
        raise ValueError('wrong_run_or_duplicate_prediction_rows')
    answers = load_answer_map(args.answers)
    unknown = set(answers) - set(ids)
    if unknown:
        raise ValueError('answer_ids_missing_from_predictions')
    results = []
    for row in rows:
        rid = row['record_id']
        state = row.get('result')
        if not isinstance(state, dict):
            results.append({'record_id':rid, 'termination':'missing_model_state',
                            'final_status':'inference_failed', 'turns_used':0,
                            'gold_task_correct':'NOT_COMPUTED_NO_INDEPENDENT_TASK_GOLD'})
            continue

        def respond(target: str, options: list[Any], depth: int) -> str | None:
            supplied = answers.get(rid, {}).get(target)
            if supplied is not None:
                return supplied
            if not args.interactive:
                return None
            print(f'[{rid}][{depth}/5] {state.get("verdict",{}).get("question",target)}')
            print('Options:', options)
            reply = input('Answer (empty to stop): ').strip()
            return reply if reply else None

        results.append(replay(state, respond, max_questions=args.max_questions))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'five_turn_replay.jsonl').write_text(
        ''.join(json.dumps(x, ensure_ascii=False, sort_keys=True)+'\n' for x in results),
        encoding='utf-8')
    summary = {
        'run_id':'compound_task_five_turn_replay_v01',
        'source_run_id':RUN_ID,
        'prediction_records':len(results),
        'max_questions':args.max_questions,
        'termination_counts':dict(Counter(r['termination'] for r in results)),
        'ready_by_depth':{str(d):sum(r.get('readiness_depth') is not None and r['readiness_depth'] <= d for r in results) for d in range(args.max_questions+1)},
        'correct_task_success_by_depth':'NOT_COMPUTED_NO_INDEPENDENT_GOLD',
        'note':'Ready-by-depth is a proxy, not correct complete task success. Missing answers are not fabricated.',
    }
    (args.output/'five_turn_summary.json').write_text(json.dumps(summary, indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()