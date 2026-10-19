import json
import unittest
from pathlib import Path
from compound_manager.engine import apply_answer, resolve

ROOT=Path(__file__).resolve().parents[1]/'examples'
def load(id): return json.loads((ROOT/(id+'.json')).read_text(encoding='utf-8'))

class CompoundFailureTests(unittest.TestCase):
    def test_two_carts_shared_return_referent_and_two_bays(self):
        spec=load('CA-0070')
        result=resolve(spec)
        self.assertEqual(result['status'],'needs_clarification')
        self.assertEqual(len(result['candidate_tasks'][0]['actions']),3)
        selected=resolve(apply_answer(spec,'bay_unit','equipment_bay_B'))
        self.assertEqual(selected['status'],'action_ready')
        self.assertEqual(selected['complete_task']['actions'][2]['args']['destination'],'equipment_bay_B')
        self.assertEqual(selected['complete_task']['actions'][2]['args']['object'],'linen_cart')
    def test_instrument_range_changes_gauge(self):
        spec=load('CA-0671')
        self.assertEqual(resolve(spec)['status'],'needs_clarification')
        lo=resolve(apply_answer(spec,'expected_range','low'))
        hi=resolve(apply_answer(spec,'expected_range','high'))
        self.assertEqual(lo['complete_task']['actions'][0]['args']['instrument'],'handheld_pressure_gauge')
        self.assertEqual(hi['complete_task']['actions'][0]['args']['instrument'],'cart_mounted_pressure_gauge')
    def test_do_same_inherits_relevant_action_then_choice(self):
        spec=load('CA-0714')
        initial=resolve(spec)
        self.assertEqual(initial['status'],'needs_clarification')
        ready=resolve(apply_answer(spec,'secure_cage','cage_inspection'))
        self.assertEqual([a['op'] for a in ready['complete_task']['actions']],['INSPECT','PLACE'])
        self.assertEqual(ready['complete_task']['actions'][1]['args']['destination'],'cage_inspection')
if __name__=='__main__':unittest.main()
