"""Tests of the injected-model full pipeline, never blind accuracy claims."""
from __future__ import annotations
import json
import unittest
from pathlib import Path
from copy import deepcopy

from compound_manager.pipeline import (FixtureModel, answer_turn, dependency_analysis, parse_task_spec,
    run_dialogue, run_first_turn, TaskParseError)
ROOT = Path(__file__).resolve().parents[1]

def fixture(id):
    return json.loads((ROOT / 'examples' / (id + '.json')).read_text(encoding='utf-8'))

def source(id):
    spec = fixture(id)
    return {'record_id':id,'command':spec['utterance'],'scene_context':'\n'.join(spec.get('context_evidence',[])) + '\n' + '\n'.join(
        str(option['evidence']) for v in spec['variables'].values() for option in v['options']), 'dialogue_history':[]}

class PipelineTests(unittest.TestCase):
    def test_all_example_graphs_are_processed(self):
        ids=[p.stem for p in (ROOT/'examples').glob('CA-*.json')]
        m=FixtureModel({i:fixture(i) for i in ids})
        for i in ids:
            with self.subTest(id=i):
                x=run_first_turn(source(i),m)
                self.assertIn(x['status'], ('action_ready','needs_clarification','needs_context_repair'))
                self.assertTrue(x['audit']['quotes_verified'])
                self.assertFalse(x['ready_with_full_coverage_verified'])

    def test_multi_action_can_be_ready(self):
        m=FixtureModel({'CA-0226': fixture('CA-0226')})
        x=run_first_turn(source('CA-0226'),m)
        self.assertEqual(x['status'],'action_ready')
        self.assertEqual(len(x['verdict']['complete_task']['actions']),2)

    def test_five_turn_dialogue_and_targeted_answer(self):
        m=FixtureModel({'CA-0608':fixture('CA-0608')})
        x=run_dialogue(source('CA-0608'),m,['quantity_ml=20'])
        self.assertEqual(x['status'],'action_ready')
        self.assertEqual(x['turns_used'],1)
        self.assertEqual(x['verdict']['complete_task']['actions'][0]['args']['quantity_ml'],20)

    def test_compound_dependency(self):
        d=dependency_analysis(fixture('SYN-DEPENDENT-001'))
        self.assertEqual(d['classification'],'dependent_compound')
        self.assertIn('container', d['shared_across_actions'])
        self.assertEqual(d['dependent_lookups'][0]['depends_on'],'container')

    def test_scope_ambiguity_and_two_outcomes(self):
        x=run_first_turn(source('CA-0878'),FixtureModel({'CA-0878':fixture('CA-0878')}))
        self.assertEqual(x['status'],'needs_clarification')
        self.assertEqual(x['dependencies']['alternative_action_graphs'],2)
        a=answer_turn(x,'inspect_without_moving')
        b=answer_turn(x,'cancel_both')
        self.assertNotEqual(a['verdict']['complete_task'], b['verdict']['complete_task'])

    def test_unsupported_quote_abstains(self):
        s=source('CA-0608')
        s['scene_context']='irrelevant unrelated context'
        x=run_first_turn(s,FixtureModel({'CA-0608':fixture('CA-0608')}))
        self.assertEqual(x['status'],'needs_context_repair')
        self.assertEqual(x['verdict']['reason'],'unsupported_source_evidence')

    def test_unrecognized_answer_does_not_guess(self):
        m=FixtureModel({'CA-0608':fixture('CA-0608')})
        x=run_dialogue(source('CA-0608'),m,['a small amount'])
        self.assertEqual(x['status'],'needs_clarification')
        self.assertEqual(x['turns_used'],0)
        self.assertIn('ambiguous_or_unrecognized_answer',x['answer_error'])

    def test_bad_json_abstains(self):
        class Bad:
            def generate(self,*args):return '{not valid'
        x=run_first_turn(source('CA-0608'),Bad())
        self.assertEqual(x['status'],'parse_failed')

    def test_gold_or_route_in_semantics_rejected(self):
        obj=fixture('CA-0608')
        obj['gold_route']='clarify'
        with self.assertRaisesRegex(TaskParseError,'route_or_policy_field'):
            parse_task_spec(source('CA-0608'),json.dumps(obj))

    def test_unknown_lookup_abstains(self):
        obj=fixture('SYN-DEPENDENT-001')
        obj['lookups'].clear()
        with self.assertRaisesRegex(TaskParseError,'unknown_lookup'):
            parse_task_spec(source('SYN-DEPENDENT-001'),json.dumps(obj))

    def test_command_mismatch_rejected(self):
        obj=fixture('CA-0608')
        obj['utterance']='please perform unrelated action'
        with self.assertRaisesRegex(TaskParseError,'utterance_mismatch'):
            parse_task_spec(source('CA-0608'),json.dumps(obj))

if __name__ == '__main__': unittest.main()