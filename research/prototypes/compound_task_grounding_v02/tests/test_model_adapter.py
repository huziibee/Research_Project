import unittest
import json
from compound_manager.model_adapter import build_model_prompt, process_model_output
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class AdapterTests(unittest.TestCase):
    def test_only_source_allowed_into_prompt(self):
        source={'record_id':'ID-123', 'command':'Move the blue cup', 'scene_context':'A blue cup on table',
                'dialogue_history':[], 'gold_route':'execute', 'correct_answer':'blue_cup', 'capability_context':'secret capability'}
        prompt=build_model_prompt(source)
        self.assertIn('blue cup',prompt)
        self.assertNotIn('ID-123',prompt)
        self.assertNotIn('secret capability',prompt)
        self.assertNotIn('correct_answer',prompt)
        self.assertNotIn('gold_route',prompt)

    def test_model_output_exact_quote_supported(self):
        source={'record_id':'demo','command':'Refill a bottle', 'scene_context':'Two bottles exist'}
        spec=json.loads((ROOT/'examples'/'CA-0608.json').read_text(encoding='utf-8'))
        spec['context_evidence']=['Two bottles exist']
        result=process_model_output(source,json.dumps(spec))
        self.assertEqual(result['status'],'needs_clarification')

    def test_model_output_quote_rejects_unsupported(self):
        source={'record_id':'demo','command':'Refill a bottle', 'scene_context':'Two bottles exist'}
        spec=json.loads((ROOT/'examples'/'CA-0608.json').read_text(encoding='utf-8'))
        spec['context_evidence']=['A made-up fact']
        with self.assertRaisesRegex(ValueError,'unsupported_context_evidence'):
            process_model_output(source,json.dumps(spec))

if __name__=='__main__':unittest.main()