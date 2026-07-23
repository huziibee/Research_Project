"""T27B full-schema envelope builder tests (CPU-only)."""

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
    FULL_SCHEMA_ENVELOPE_ID,
    TRAINING_TO_PRODUCTION_MAPPING,
    FullSchemaEnvelopeError,
    build_full_schema_envelope,
    load_envelope_policy,
    validate_envelope_against_production_shape,
)
from ambiguity_manager.model.prediction_contract import MODEL_OUTPUT_REQUIRED_FIELDS  # noqa: E402
from ambiguity_manager.model.training_target_packaging import (  # noqa: E402
    load_training_target_policy_strict,
)
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES  # noqa: E402


def _sample_row() -> tuple[dict, dict]:
    path = ROOT / "data/development/qlora_structured_emission_recovery_v1/records.jsonl"
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    return row["record"], row["eligibility"]


class FullSchemaEnvelopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_envelope_policy(ROOT / "configs/model/full_schema_envelope_policy_v1.json")
        self.training_policy = load_training_target_policy_strict(
            ROOT / "configs/data/training_target_policy_v1.json"
        )

    def test_complete_25_field_envelope_and_stable_hash(self) -> None:
        record, eligibility = _sample_row()
        a = build_full_schema_envelope(
            record, eligibility, policy=self.policy, training_policy=self.training_policy
        )
        b = build_full_schema_envelope(
            record, eligibility, policy=self.policy, training_policy=self.training_policy
        )
        self.assertEqual(a.envelope_id, FULL_SCHEMA_ENVELOPE_ID)
        self.assertEqual(a.target_hash, b.target_hash)
        self.assertEqual(set(a.fields), set(MODEL_OUTPUT_REQUIRED_FIELDS))
        self.assertEqual(set(a.fields["cpc"]), set(CPC_SLOT_NAMES))
        self.assertTrue(a.supervised_fields)
        validate_envelope_against_production_shape(a.canonical_json)

    def test_segment_reconstruction_equals_canonical(self) -> None:
        record, eligibility = _sample_row()
        envelope = build_full_schema_envelope(
            record, eligibility, policy=self.policy, training_policy=self.training_policy
        )
        rebuilt = "".join(seg.text for seg in envelope.segments)
        self.assertEqual(rebuilt, envelope.canonical_json)
        reference = json.dumps(envelope.fields, ensure_ascii=False, sort_keys=True)
        self.assertEqual(envelope.canonical_json, reference)

    def test_no_admin_or_eligibility_in_target(self) -> None:
        record, eligibility = _sample_row()
        envelope = build_full_schema_envelope(
            record, eligibility, policy=self.policy, training_policy=self.training_policy
        )
        for forbidden in ("id", "command", "label_eligibility", "source_dataset", "eligibility"):
            self.assertNotIn(forbidden, envelope.fields)

    def test_always_masked_fields_unavailable(self) -> None:
        record, eligibility = _sample_row()
        envelope = build_full_schema_envelope(
            record, eligibility, policy=self.policy, training_policy=self.training_policy
        )
        for name in (
            "unresolved_slots",
            "supporting_evidence",
            "resolved_slots",
            "resolution_method",
            "resolution_evidence",
            "context_sampling_uncertainty",
        ):
            self.assertEqual(envelope.per_field_supervision[name], "unavailable_masked")

    def test_zero_semantic_rejected(self) -> None:
        with self.assertRaises(FullSchemaEnvelopeError):
            build_full_schema_envelope(
                {"id": "x", "command": "go"},
                {
                    "structured_training_target": "unavailable",
                    "speech_act_intent": "unavailable",
                    "cpc": "unavailable",
                    "candidate_interpretations": "unavailable",
                    "ambiguity_presence_types": "unavailable",
                    "compound_ambiguity": "unavailable",
                    "risk": "unavailable",
                    "capability": "unavailable",
                    "route": "unavailable",
                    "clarification_target": "unavailable",
                    "rejection": "unavailable",
                },
                policy=self.policy,
                training_policy=self.training_policy,
            )

    def test_mapping_docs_present(self) -> None:
        self.assertEqual(
            TRAINING_TO_PRODUCTION_MAPPING["omitted_field_policy"],
            "never_omit_keys_mask_unavailable_values",
        )
        self.assertTrue(
            TRAINING_TO_PRODUCTION_MAPPING["fabricated_nulls_forbidden_as_supervised_labels"]
        )


if __name__ == "__main__":
    unittest.main()
