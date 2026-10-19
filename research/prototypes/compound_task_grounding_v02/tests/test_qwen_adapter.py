import unittest
from compound_manager.qwen_adapter import QWEN_NAME, QWEN_REVISION, QwenTaskSpecModel

class QwenAdapterContractTests(unittest.TestCase):
    def test_pinned_identity(self):
        self.assertEqual(QWEN_NAME,'Qwen/Qwen3-8B')
        self.assertEqual(len(QWEN_REVISION),40)
    def test_injected_callable_matches_pipeline_contract(self):
        self.assertTrue(callable(QwenTaskSpecModel.generate))
        self.assertTrue(callable(QwenTaskSpecModel.load))
if __name__=='__main__':unittest.main()
