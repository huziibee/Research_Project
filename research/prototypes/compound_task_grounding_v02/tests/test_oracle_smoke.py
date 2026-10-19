import unittest
from compound_manager.engine import resolve
from run_oracle_candidate_smoke import construct_oracle_spec

class OracleCandidateSmokeTests(unittest.TestCase):
    def test_one_supplied_oracle_candidate(self):
        row={'record_id':'TEST-ONE','gold':{'candidate_set':[{'candidate_id':'T1','canonical_interpretation':'move the red cart','cpc_slots':{'object':'red cart'}}]}}
        d=resolve(construct_oracle_spec(row))
        self.assertEqual(d['status'],'action_ready')
    def test_two_supplied_oracle_candidates(self):
        row={'record_id':'TEST-TWO','gold':{'candidate_set':[
            {'candidate_id':'T1','canonical_interpretation':'file physically','cpc_slots':{}},
            {'candidate_id':'T2','canonical_interpretation':'file digitally','cpc_slots':{}}]}}
        d=resolve(construct_oracle_spec(row))
        self.assertEqual(d['status'],'needs_clarification')
        self.assertEqual(d['distinct_tasks'],2)
if __name__=='__main__':unittest.main()
