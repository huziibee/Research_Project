"""Five-turn replay must never silently substitute a reference intent."""
import unittest
from compound_manager.pipeline import FixtureModel, run_first_turn
from replay_five_turn_v01 import replay, load_answer_map
from test_depth5_contract_v01 import synthetic_spec, synthetic_source


class ReplayFiveTurnTests(unittest.TestCase):
    def state(self, n):
        s = synthetic_spec(n)
        return run_first_turn(synthetic_source(s), FixtureModel({s['record_id']:s}))

    def test_five_independent_variables_complete_at_depth_five(self):
        state = self.state(5)
        result = replay(state, lambda target, options, depth: 'B')
        self.assertEqual(result['termination'],'action_ready')
        self.assertEqual(result['readiness_depth'],5)
        self.assertEqual(len(result['transcript']),5)
        self.assertTrue(all(t['outcome'] in ('needs_clarification','action_ready') for t in result['transcript']))
        self.assertEqual(result['final_complete_task']['actions'][0]['args'],{f'v{i}':'B' for i in range(1,6)})
        self.assertEqual(result['gold_task_correct'],'NOT_COMPUTED_NO_INDEPENDENT_TASK_GOLD')

    def test_six_needed_questions_caps_after_five(self):
        result = replay(self.state(6),lambda target, options,depth:'A')
        self.assertEqual(result['termination'],'depth_cap')
        self.assertEqual(result['turns_used'],5)
        self.assertIsNone(result['final_complete_task'])

    def test_no_answer_cannot_fabricate_success(self):
        result = replay(self.state(2),lambda *args:None)
        self.assertEqual(result['termination'],'no_answer_available')
        self.assertEqual(result['turns_used'],0)
        self.assertIsNone(result['readiness_depth'])

    def test_bad_answer_cannot_fabricate_success(self):
        result = replay(self.state(2),lambda *args:'not-an-option')
        self.assertEqual(result['termination'],'invalid_answer')
        self.assertEqual(result['turns_used'],0)

    def test_direct_ready_depth_zero(self):
        spec=synthetic_spec(1)
        spec['variables']['v1']['grounded']='A'
        state=run_first_turn(synthetic_source(spec), FixtureModel({spec['record_id']:spec}))
        result=replay(state,lambda *args: self.fail('No question expected'))
        self.assertEqual(result['readiness_depth'],0)
        self.assertEqual(result['turns_used'],0)


if __name__ == '__main__':unittest.main()