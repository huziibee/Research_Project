"""Unit tests against manually authored development fixtures, NOT benchmark claims."""
import json
import unittest
from pathlib import Path
from copy import deepcopy
from compound_manager import apply_answer, check_spec, resolve

ROOT=Path(__file__).resolve().parents[1]

def load(case):
    return json.loads((ROOT/'examples'/f'{case}.json').read_text(encoding='utf-8'))

class EngineTests(unittest.TestCase):
    def test_all_fixtures_schema_valid(self):
        for p in (ROOT/'examples').glob('*.json'):
            with self.subTest(p=p.name):check_spec(json.loads(p.read_text(encoding='utf-8')))

    def test_context_disambiguates_cart_and_time(self):
        result=resolve(load('CA-0012'))
        self.assertTrue(result['action_ready'])
        action=result['complete_task']['actions'][0]
        self.assertEqual(action['args']['object'],'red_pending')
        self.assertIn('08:00',action['args']['scheduled_slot'])

    def test_filing_medium_unresolved_then_grounded(self):
        state=load('CA-0215')
        result=resolve(state)
        self.assertEqual(result['question_target'],'medium')
        self.assertEqual(result['distinct_tasks'],2)
        ready=resolve(apply_answer(state,'medium','digital'))
        self.assertTrue(ready['action_ready'])
        self.assertEqual(ready['complete_task']['actions'][0]['args']['destination'],'records_system')

    def test_compound_refill_and_return(self):
        result=resolve(load('CA-0226'))
        self.assertTrue(result['action_ready'])
        first,second=result['complete_task']['actions']
        self.assertEqual(first['args']['quantity_ml'],800)
        self.assertEqual(first['args']['tool'],'handheld_dosing_bottle')
        self.assertEqual(second['args']['object'],'disinfectant_bottle')
        self.assertEqual(second['after'],['A1'])

    def test_small_quantity_requires_question(self):
        result=resolve(load('CA-0608'))
        self.assertFalse(result['action_ready'])
        self.assertEqual(result['answer_options'],[20,60])
        ready=resolve(apply_answer(load('CA-0608'),'quantity_ml',20))
        self.assertEqual(ready['complete_task']['actions'][0]['args']['quantity_ml'],20)

    def test_pronoun_and_computed_reserve(self):
        result=resolve(load('CA-0702'))
        self.assertTrue(result['action_ready'])
        first,second=result['complete_task']['actions']
        self.assertEqual(first['args']['quantity_ml'],550)
        self.assertEqual(second['args']['object'],'cleaner_bottle')

    def test_negation_alternative_action_graphs(self):
        spec=load('CA-0878')
        result=resolve(spec)
        self.assertFalse(result['action_ready'])
        self.assertEqual(result['question_target'],'negation_scope')
        a=resolve(apply_answer(spec,'negation_scope','inspect_without_moving'))
        b=resolve(apply_answer(spec,'negation_scope','cancel_both'))
        self.assertEqual(a['complete_task']['actions'][0]['op'],'INSPECT')
        self.assertEqual(b['complete_task']['actions'][0]['op'],'CANCEL')

    def test_multiple_linked_choices(self):
        spec=load('SYN-DEPENDENT-001')
        first=resolve(spec)
        self.assertEqual(first['candidate_assignments'],2)
        self.assertEqual(first['question_target'],'container')
        self.assertTrue(resolve(apply_answer(spec,'container','B1'))['action_ready'])
        ready=resolve(apply_answer(spec,'container','B2'))
        actions=ready['complete_task']['actions']
        self.assertEqual(actions[0]['args']['object'],'B2')
        self.assertEqual(actions[1]['args']['using'],'B2')
        self.assertEqual(actions[2]['args']['object'],'B2')
        self.assertEqual(actions[2]['args']['destination'],'Shelf_B')

    def test_selected_medicine_tray_needs_choice(self):
        spec=load('CA-0007')
        self.assertEqual(resolve(spec)['question_target'],'tray')
        ready=resolve(apply_answer(spec,'tray','tray_for_nurse'))
        self.assertEqual(ready['complete_task']['actions'][0]['args']['recipient'],'nurse')
        self.assertEqual(ready['complete_task']['actions'][0]['args']['after_event'],'11:00_meal_service')

    def test_answer_does_not_modify_original(self):
        spec=load('CA-0608')
        newer=apply_answer(spec,'quantity_ml',20)
        self.assertIsNone(spec['variables']['quantity_ml']['grounded'])
        self.assertEqual(newer['answer_history'][0]['source'],'user_answer')

    def test_rejects_unsupported_answer(self):
        with self.assertRaisesRegex(ValueError,'invalid_answer'):
            apply_answer(load('CA-0608'),'quantity_ml',40)

    def test_rejects_change_to_grounded_context(self):
        with self.assertRaisesRegex(ValueError,'contradicts_grounded_context'):
            apply_answer(load('CA-0012'),'cart','black_complete')

    def test_equivalent_bindings_do_not_force_question(self):
        spec=load('CA-0608')
        spec['templates'][0]['actions'][0]['args']['quantity_ml']=20
        self.assertTrue(resolve(spec)['action_ready'])
        self.assertEqual(resolve(spec)['candidate_assignments'],2)

    def test_cap_excessive_combinatorics_and_abstain(self):
        spec=load('SYN-DEPENDENT-001')
        for i in range(13):
            spec['variables'][f'unused{i}']={'options':[{'value':'a','evidence':'test'},{'value':'b','evidence':'test'}], 'question':f'value of unused{i}?', 'grounded':None}
        result=resolve(spec)
        self.assertEqual(result['status'],'needs_context_repair')
        self.assertIn('candidate_limit_exceeded',result['reason'])

    def test_incorrect_return_dependency_is_not_equivalent(self):
        spec=load('SYN-DEPENDENT-001')
        result=resolve(spec)
        self.assertEqual(result['distinct_tasks'],2)
        self.assertIn('usual_storage',str(spec['templates']))

    def test_absent_lookup_never_declares_ready(self):
        spec=load('SYN-DEPENDENT-001')
        del spec['lookups']['usual_storage']['B2']
        result=resolve(spec)
        self.assertFalse(result['action_ready'])
        self.assertEqual(result['status'],'needs_context_repair')

    def test_no_atomic_action_restriction(self):
        ready=resolve(load('CA-0226'))
        self.assertTrue(ready['action_ready'])
        self.assertEqual(len(ready['complete_task']['actions']),2)

if __name__=='__main__':unittest.main()