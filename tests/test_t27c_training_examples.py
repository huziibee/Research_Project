"""T27C training-example contract tests (CPU-only)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.model.full_schema_token_masking import DeterministicCharTokenizer  # noqa: E402
from ambiguity_manager.model.task_conditioned_training import (  # noqa: E402
    TRAINING_EXAMPLE_SCHEMA,
    build_task_conditioned_training_example,
)
from ambiguity_manager.model.task_prediction_contract import (  # noqa: E402
    load_task_registry,
    validate_task_schema,
)
from ambiguity_manager.model.token_loss_masking import IGNORE_INDEX  # noqa: E402


class T27CTrainingExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_task_registry(ROOT)
        cls.examples_path = (
            ROOT / "data/development/qlora_task_conditioned_smoke_v1/task_examples.jsonl"
        )
        cls.rows = [
            json.loads(line)
            for line in cls.examples_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_prompt_contains_task_id_and_target_is_task_schema(self) -> None:
        self.assertGreaterEqual(len(self.rows), 256)
        for row in self.rows[:20]:
            tid = row["task_id"]
            self.assertIn(f"TASK_ID={tid}", row["task_instruction_prompt"])
            target = row["canonical_task_target"]
            self.assertIsInstance(target, dict)
            task = next(t for t in self.registry["tasks"] if t["task_id"] == tid)
            props = set((task["json_schema"].get("properties") or {}))
            self.assertTrue(set(target).issubset(props))
            self.assertEqual(validate_task_schema(task, target), [])
            for forbidden in (
                "recommended_strategy",
                "compound_ambiguity",
                "analysis_provenance",
            ):
                self.assertNotIn(forbidden, target)

    def test_masks_prompt_supervise_target_pad(self) -> None:
        for row in self.rows[:10]:
            labels = row["labels"]
            input_ids = row["input_ids"]
            attention = row["attention_mask"]
            self.assertEqual(len(labels), len(input_ids))
            supervised = sum(1 for x in labels if x != IGNORE_INDEX)
            self.assertGreater(supervised, 0)
            # Padding positions (attention 0) must be masked.
            for i, flag in enumerate(attention):
                if flag == 0:
                    self.assertEqual(labels[i], IGNORE_INDEX)
            self.assertEqual(row["schema"], TRAINING_EXAMPLE_SCHEMA)
            self.assertTrue(row.get("canonical_example_hash"))

    def test_zero_supervision_rejected_and_hashes_deterministic(self) -> None:
        intent = next(t for t in self.registry["tasks"] if t["task_id"] == "predict_intent_v1")
        record = {
            "id": "unit:1",
            "source_dataset": "ambik",
            "command": "bring the cup",
            "speech_act": "directive_command",
            "intent_summary": "bring cup",
            "label_eligibility": {"intent_slots": True},
        }
        eligibility = {"speech_act_intent": "eligible"}
        tok = DeterministicCharTokenizer()
        a = build_task_conditioned_training_example(
            record=record,
            eligibility=eligibility,
            task_spec=intent,
            source_dataset="ambik",
            tokenizer=tok,
            max_seq_len=2048,
            pad_token_id=int(tok.pad_token_id),
        )
        b = build_task_conditioned_training_example(
            record=record,
            eligibility=eligibility,
            task_spec=intent,
            source_dataset="ambik",
            tokenizer=tok,
            max_seq_len=2048,
            pad_token_id=int(tok.pad_token_id),
        )
        self.assertIsNotNone(a)
        assert a is not None and b is not None
        self.assertEqual(a.payload["canonical_example_hash"], b.payload["canonical_example_hash"])
        # Empty command without speech/intent signal is rejected.
        bad = build_task_conditioned_training_example(
            record={"id": "unit:2", "source_dataset": "ambik", "command": "x"},
            eligibility={"speech_act_intent": "ineligible"},
            task_spec=intent,
            source_dataset="ambik",
        )
        self.assertIsNone(bad)

    def test_speech_act_never_fabricated_from_dataset_defaults(self) -> None:
        intent = next(t for t in self.registry["tasks"] if t["task_id"] == "predict_intent_v1")
        tok = DeterministicCharTokenizer()
        # Intent text present, speech_act absent → example allowed, speech_act null.
        row = build_task_conditioned_training_example(
            record={
                "id": "unit:no-speech",
                "source_dataset": "ambik",
                "command": "bring the cup",
                "intent_summary": "bring cup",
                "label_eligibility": {"intent_slots": True},
            },
            eligibility={"speech_act_intent": "eligible"},
            task_spec=intent,
            source_dataset="ambik",
            tokenizer=tok,
            max_seq_len=2048,
            pad_token_id=int(tok.pad_token_id),
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertIsNone(row.payload["canonical_task_target"].get("speech_act"))
        self.assertEqual(row.payload["field_supervision_status"]["speech_act"], "missing")
        # No intent text → rejected even if dataset could imply a speech_act.
        missing = build_task_conditioned_training_example(
            record={
                "id": "unit:no-intent",
                "source_dataset": "ambik",
                "command": "bring the cup",
            },
            eligibility={"speech_act_intent": "eligible"},
            task_spec=intent,
            source_dataset="ambik",
            tokenizer=tok,
            max_seq_len=2048,
            pad_token_id=int(tok.pad_token_id),
        )
        self.assertIsNone(missing)


if __name__ == "__main__":
    unittest.main()
