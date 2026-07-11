"""Tests for T12 Stage D1C1 attempt evidence ledger."""

from __future__ import annotations

import json
import unittest

from ambiguity_manager.model.attempt_evidence import (
    AttemptDisposition,
    AttemptEvidenceEntry,
    AttemptEvidenceLedger,
    AttemptKind,
    attempt_evidence_json_bytes,
    defensive_copy_metadata,
)


def _sample_entry(**overrides: object) -> AttemptEvidenceEntry:
    defaults = {
        "caller_request_id": "pred:syn-test-001",
        "attempt_index": 0,
        "attempt_kind": AttemptKind.INITIAL.value,
        "prompt_message_hash": "a" * 64,
        "rendered_prompt_hash": "b" * 64,
        "repair_prompt_hash": None,
        "response_mode_identity": "test-renderer-v1",
        "response_mode_status": "verified",
        "structured_decode_contract_hash": "c" * 64,
        "semantic_schema_hash": "d" * 64,
        "backend_identifier": "fake-backend",
        "backend_configuration_hash": "e" * 64,
        "model_repository": "Qwen/Qwen3-8B",
        "model_revision": "b968826d9c46dd6066d109eabc6255188de91218",
        "container_sha": None,
        "raw_generated_text": '{"recommended_strategy":"execute"}',
        "generation_status": "success",
        "generation_error_type": None,
        "generation_error_message": None,
        "engine_request_id": "engine-req-abc",
        "finish_reason": "stop",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "json_extraction_status": "success",
        "local_repair_operations": ("remove_markdown_json_fence",),
        "extracted_json_text": '{"recommended_strategy":"execute"}',
        "json_parse_status": "success",
        "semantic_schema_validation_status": "valid",
        "canonical_assembly_status": "success",
        "unsupported_commitment_count": 0,
        "structural_validity_status": "valid",
        "semantic_correctness_status": "not_evaluated",
        "integrity_context_hash": "g" * 64,
        "final_attempt_disposition": AttemptDisposition.ACCEPTED.value,
    }
    defaults.update(overrides)
    return AttemptEvidenceEntry(**defaults)


class T12AttemptEvidenceTests(unittest.TestCase):
    def test_entry_retains_raw_and_extracted_separately(self) -> None:
        entry = _sample_entry(
            raw_generated_text="```json\n{\"x\":1}\n```",
            extracted_json_text='{"x":1}',
            local_repair_operations=("remove_markdown_json_fence",),
        )
        self.assertIn("```", entry.raw_generated_text)
        self.assertNotIn("```", entry.extracted_json_text or "")

    def test_engine_request_id_recorded_diagnostically(self) -> None:
        entry = _sample_entry(engine_request_id="engine-req-xyz")
        self.assertEqual(entry.engine_request_id, "engine-req-xyz")

    def test_ledger_append_only_ordering(self) -> None:
        ledger = AttemptEvidenceLedger()
        ledger.append(_sample_entry(attempt_index=0))
        ledger.append(_sample_entry(attempt_index=1, attempt_kind=AttemptKind.REGENERATION.value))
        self.assertEqual([e.attempt_index for e in ledger.entries], [0, 1])

    def test_ledger_serialization_deterministic(self) -> None:
        ledger = AttemptEvidenceLedger(entries=[_sample_entry(), _sample_entry(attempt_index=1)])
        first = attempt_evidence_json_bytes(ledger)
        second = attempt_evidence_json_bytes(ledger)
        self.assertEqual(first, second)
        parsed = json.loads(first.decode("utf-8"))
        self.assertEqual(len(parsed["entries"]), 2)

    def test_defensive_copy_metadata(self) -> None:
        original = {"nested": {"value": 1}}
        copied = defensive_copy_metadata(original)
        copied["nested"]["value"] = 99
        self.assertEqual(original["nested"]["value"], 1)

    def test_to_dict_includes_failure_fields(self) -> None:
        entry = _sample_entry(
            final_attempt_disposition=AttemptDisposition.REPAIRABLE_REJECTED.value,
            failure_categories=("json_parse_failure",),
            failure_reasons=("invalid JSON",),
        )
        payload = entry.to_dict()
        self.assertEqual(payload["failure_categories"], ["json_parse_failure"])
        self.assertEqual(payload["failure_reasons"], ["invalid JSON"])


if __name__ == "__main__":
    unittest.main()
