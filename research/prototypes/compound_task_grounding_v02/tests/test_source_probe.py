import unittest
from compound_manager.source_probe import probe, action_scaffold

class SourceProbeTests(unittest.TestCase):
    def test_explicit_no_default(self):
        s={'record_id':'x','command':'Add a small amount','scene_context':'The allowed quantities are 20 and 60 ml. Neither is the default.'}
        self.assertEqual(probe(s)['predicted_readiness'],'blocking_ambiguity')
    def test_no_unsupported_ready_task_claim(self):
        s={'record_id':'y','command':'Move the marked cart','scene_context':'Work order identifies the cart.'}
        r=probe(s)
        self.assertEqual(r['predicted_readiness'],'ready_candidate')
        self.assertFalse(r['complete_task_verified'])
    def test_multi_action_scaffold(self):
        s={'record_id':'z','command':'Use a dosing bottle to top up the cleaner then return it'}
        self.assertEqual(action_scaffold(s)['action_sequence'],['REFILL','RETURN'])
    def test_scope_preserved(self):
        s={'record_id':'w','command':'Do not move and inspect the box','scene_context':'transcribed without punctuation'}
        self.assertEqual(len(action_scaffold(s)['alternative_action_sequences']),2)
        self.assertEqual(probe(s)['predicted_readiness'],'blocking_ambiguity')

if __name__=='__main__':unittest.main()