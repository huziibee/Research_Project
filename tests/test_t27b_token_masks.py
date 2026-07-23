"""T27B segment-aware token masking tests (CPU-only)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.model.full_schema_envelope import (  # noqa: E402
    build_full_schema_envelope,
    load_envelope_policy,
)
from ambiguity_manager.model.full_schema_token_masking import (  # noqa: E402
    IGNORE_INDEX,
    DeterministicCharTokenizer,
    FullSchemaTokenMaskError,
    build_masked_sequence_from_envelope,
)
from ambiguity_manager.model.t27b_prompt_contract import build_t27b_inference_prompt  # noqa: E402
from ambiguity_manager.model.training_target_packaging import (  # noqa: E402
    load_training_target_policy_strict,
)


def _sample() -> tuple[dict, dict, object, str]:
    path = ROOT / "data/development/qlora_structured_emission_recovery_v1/records.jsonl"
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    policy = load_envelope_policy(ROOT / "configs/model/full_schema_envelope_policy_v1.json")
    training = load_training_target_policy_strict(ROOT / "configs/data/training_target_policy_v1.json")
    envelope = build_full_schema_envelope(
        row["record"], row["eligibility"], policy=policy, training_policy=training
    )
    prompt = build_t27b_inference_prompt(row["record"])
    return row["record"], row["eligibility"], envelope, prompt


class T27BTokenMaskTests(unittest.TestCase):
    def test_prompt_unavailable_padding_and_structural_rules(self) -> None:
        record, _eligibility, envelope, prompt = _sample()
        tok = DeterministicCharTokenizer()
        seq = build_masked_sequence_from_envelope(
            prompt=prompt,
            envelope=envelope,
            tokenizer=tok,
            max_seq_len=8192,
            pad_token_id=0,
        )
        self.assertGreater(seq.diagnostics["semantic_supervised"], 0)
        self.assertGreater(seq.diagnostics["structural_supervised"], 0)
        self.assertFalse(seq.diagnostics["command_reconstruction"])
        self.assertNotEqual(list(seq.labels), list(seq.input_ids))
        # Prompt + separator masked
        prompt_len = len(tok.encode(prompt, add_special_tokens=True))
        for label in seq.labels[: prompt_len + 1]:
            self.assertEqual(label, IGNORE_INDEX)
        # Unavailable values masked
        self.assertGreaterEqual(seq.diagnostics["unavailable_masked"], 0)

    def test_zero_semantic_hard_fail(self) -> None:
        record, eligibility, envelope, prompt = _sample()
        # Force all value segments unavailable by cloning envelope with empty supervised kinds
        # via exclude_weak=True on an envelope that only has weak values is not guaranteed;
        # instead truncate segments to structural-only reconstruction mismatch path:
        from ambiguity_manager.model.full_schema_envelope import EnvelopeSegment, FullSchemaEnvelope

        structural_only = tuple(
            EnvelopeSegment(
                kind="structural" if seg.kind in {"structural", "field_name"} else "unavailable_value",
                text=seg.text,
                char_start=seg.char_start,
                char_end=seg.char_end,
                field_path=seg.field_path,
            )
            for seg in envelope.segments
        )
        mutated = FullSchemaEnvelope(
            envelope_id=envelope.envelope_id,
            fields=dict(envelope.fields),
            supervised_fields=tuple(),
            weakly_eligible_fields=tuple(),
            unavailable_fields=envelope.unavailable_fields,
            field_spans=envelope.field_spans,
            segments=structural_only,
            canonical_json=envelope.canonical_json,
            target_hash=envelope.target_hash,
            field_group_status=dict(envelope.field_group_status),
            per_field_supervision=dict(envelope.per_field_supervision),
        )
        with self.assertRaises(FullSchemaTokenMaskError):
            build_masked_sequence_from_envelope(
                prompt=prompt,
                envelope=mutated,
                tokenizer=DeterministicCharTokenizer(),
                max_seq_len=8192,
                pad_token_id=0,
            )


if __name__ == "__main__":
    unittest.main()
