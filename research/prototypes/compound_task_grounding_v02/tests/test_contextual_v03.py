"""v0.3 prompt and runtime integration tests; no GPU or gold labels."""
import json
import unittest
from pathlib import Path

from compound_manager.contextual_v03 import (
    CONTEXTUAL_PROMPT_VERSION, ContextualizedModel, add_alerts_to_prompt,
    contextual_alerts, contextual_prompt, run_contextual_first_turn,
)
from compound_manager.pipeline import FixtureModel

ROOT = Path(__file__).resolve().parents[1]


def fixture_source(case):
    spec = json.loads((ROOT/'examples'/f'{case}.json').read_text(encoding='utf-8'))
    scene = '\n'.join(spec.get('context_evidence', [])) + '\n' + '\n'.join(
        option['evidence'] for var in spec['variables'].values() for option in var['options'])
    source = {'record_id': case, 'command': spec['utterance'],
              'scene_context':scene, 'dialogue_history':[]}
    return source, spec


class SourceHintIntegrationTests(unittest.TestCase):
    def test_alerts_have_exact_provenance_and_no_gold(self):
        source = {
            'record_id':'TEST-ID-LEAK',
            'command':'Deliver the selected guest parcel.',
            'scene_context':'Two guest parcels are selected and both remain pending. '
                            'The command provides no item code, color, or recipient name.',
            'dialogue_history':[],
            'gold_route':'DONT_LEAK_THIS_LABEL',
            'capability_context':'DONT_LEAK_CAPABILITY',
        }
        hints = contextual_alerts(source)
        self.assertTrue(hints)
        self.assertEqual(hints[0]['target'], 'selected_item')
        self.assertFalse(hints[0]['verified_as_complete'])
        prompt = contextual_prompt(source)
        self.assertIn('SOURCE_ONLY_ALERTS_JSON', prompt)
        self.assertIn(CONTEXTUAL_PROMPT_VERSION, prompt)
        for secret in ('TEST-ID-LEAK','DONT_LEAK_THIS_LABEL','DONT_LEAK_CAPABILITY'):
            self.assertNotIn(secret,prompt)
        for hint in hints:
            self.assertIn(hint['verbatim_source_evidence'],source['scene_context'])

    def test_missed_model_choice_abstains_rather_than_claims_ready(self):
        source = {
            'record_id':'SYNTHETIC-TWO-ITEMS',
            'command':'Deliver the selected serving tray.',
            'scene_context':'Two serving trays are selected and both remain pending. '
                            'The command provides no item code, color, or recipient name.',
            'dialogue_history':[],
        }
        # The fake language model omits both item alternatives, which previously
        # caused a false-ready verdict for a fully specified but wrong graph.
        bad_spec = {
            'schema_version':'0.1','record_id':'model_authored',
            'variables':{},'templates':[{'actions':[{'id':'A1','op':'DELIVER',
                'args':{'object':'selected_tray'},'after':[]}]}],
            'context_evidence':[],'lookups':{},
        }
        state=run_contextual_first_turn(source,FixtureModel({source['record_id']:bad_spec}))
        self.assertEqual(state['status'],'needs_context_repair')
        self.assertEqual(state['verdict']['reason'],'source_candidate_multiplicity_not_represented_in_ready_task')
        self.assertTrue(state['readiness_blocked_by_context_audit'])
        self.assertFalse(state['ready_with_full_coverage_verified'])

    def test_correct_two_bay_fixture_retains_clarification(self):
        source,spec=fixture_source('CA-0070')
        state=run_contextual_first_turn(source,FixtureModel({'CA-0070':spec}))
        self.assertEqual(state['status'],'needs_clarification')
        self.assertEqual(state['verdict']['distinct_tasks'],2)
        self.assertEqual(state['verdict']['question_target'],'bay_unit')
        self.assertFalse(state['readiness_blocked_by_context_audit'])
        self.assertTrue(state['audit']['quotes_verified'])

    def test_ready_compound_task_not_blocked_without_an_alert(self):
        source,spec=fixture_source('CA-0226')
        state=run_contextual_first_turn(source,FixtureModel({'CA-0226':spec}))
        self.assertEqual(state['status'],'action_ready')
        self.assertFalse(state['source_only_context_alerts'])
        self.assertEqual(len(state['verdict']['complete_task']['actions']),2)

    def test_decorated_model_receives_the_updated_prompt(self):
        class Capture:
            def __init__(self): self.text=''
            def generate(self, prompt, source):
                self.text=prompt
                return '{}'
        capture=Capture()
        source={'command':'Move the marked cart','scene_context':'One marked cart is present','dialogue_history':[]}
        output=ContextualizedModel(capture).generate('RAW_MODEL_PROMPT',source)
        self.assertEqual(output,'{}')
        self.assertIn('RAW_MODEL_PROMPT',capture.text)
        self.assertIn('SOURCE_ONLY_ALERTS_JSON',capture.text)

if __name__=='__main__': unittest.main()