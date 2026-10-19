import unittest
from score_qwen120_v03 import readiness_label, summarize


def prediction(status, verdict=None, failed=False):
    return {'status':status,'failed':failed,'result':{'verdict':verdict or {}}}


class QwenReadinessScoringTests(unittest.TestCase):
    def test_credits_only_validated_grounded_action(self):
        row=prediction('action_ready',{'status':'action_ready','action_ready':True,
             'complete_task':{'actions':[{'id':'A1','op':'PICK'}]}})
        self.assertEqual(readiness_label(row),'EXECUTE')
        self.assertEqual(readiness_label(prediction('action_ready',{'status':'action_ready','action_ready':True})),'FAILED')

    def test_credits_clarification_only_if_question_targets_distinct_tasks(self):
        valid={'status':'needs_clarification','question':'Which box?',
               'answer_options':['A','B'],'distinct_tasks':2}
        self.assertEqual(readiness_label(prediction('needs_clarification',valid)),'CLARIFY')
        invalid={**valid,'question':''}
        self.assertEqual(readiness_label(prediction('needs_clarification',invalid)),'FAILED')

    def test_context_repair_is_not_credited_as_clarification(self):
        row=prediction('needs_context_repair',{'status':'needs_context_repair'})
        self.assertEqual(readiness_label(row),'ABSTAIN')
        self.assertEqual(readiness_label(prediction('inference_failed',failed=True)),'FAILED')

    def test_hard_refuse_cases_are_not_scored_as_task_readiness(self):
        scored=[{'record_id':'a','gold':'EXECUTE','prediction':'EXECUTE'},
                {'record_id':'b','gold':'CLARIFY','prediction':'CLARIFY'},
                {'record_id':'c','gold':'REFUSE','prediction':'EXECUTE'}]
        metrics=summarize(scored)
        self.assertEqual(metrics['ambiguity_relevant_n'],2)
        self.assertEqual(metrics['ambiguity_relevant_correct'],2)
        self.assertEqual(metrics['hard_refusal_cases_not_scored_for_readiness'],1)
        self.assertEqual(metrics['complete_task_graph_accuracy'],'NOT_COMPUTED_no_independent_gold')

if __name__=='__main__':unittest.main()