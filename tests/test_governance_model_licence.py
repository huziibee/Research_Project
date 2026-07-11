"""Tests for model licence register T12 transition validation."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.governance.model_licence import (
    REGISTER_SCHEMA_VERSION,
    validate_model_licence_register,
)
from ambiguity_manager.paths import ProjectPaths

REGISTER_PATH = (
    ProjectPaths.from_repo_root().root / "configs" / "licences" / "model_licence_register.json"
)


def _checkpoint_ref(model_id: str = "org/model", sha: str = "a" * 40) -> dict:
    return {
        "model_id": model_id,
        "immutable_revision_sha": sha,
        "tokenizer_revision_sha": sha,
    }


def _candidate_entry(
    entry_id: str = "candidate-001",
    status: str = "candidate_evaluated",
) -> dict:
    return {
        "entry_id": entry_id,
        "model_id": "org/model",
        "immutable_revision_sha": "a" * 40,
        "revision_alias": None,
        "tokenizer_revision_sha": "a" * 40,
        "verification_status": status,
        "licence_identifier": "apache-2.0",
        "licence_evidence_url": "https://example.org/licence",
        "licence_file_relpath": None,
        "local_inference_permitted": True,
        "academic_research_permitted": True,
        "adapter_training_permitted": True,
        "redistribution_restrictions": "none documented",
        "adapter_release_restrictions": "none documented",
        "gated_access": False,
        "gated_access_evidence": None,
        "inference_checkpoint_ref": _checkpoint_ref(),
        "training_checkpoint_ref": _checkpoint_ref(),
        "estimated_download_bytes": 1000000,
        "parameter_count": 1000000000,
        "architecture": "LlamaForCausalLM",
        "context_limit": 4096,
        "redistribution_restrictions": "none documented",
        "adapter_release_restrictions": "none documented",
        "acceptable_use_restrictions": "none documented",
        "rejection_reason": None,
        "verification_date": "2026-07-11",
        "verifier": "AUTHOR-01",
    }


class ModelLicenceRegisterTests(unittest.TestCase):
    def test_slice1_register_selected_model_null(self) -> None:
        data = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
        self.assertIsNone(data["selected_model"])
        errors = validate_model_licence_register(data)
        self.assertEqual(errors, [])

    def test_schema_version_110(self) -> None:
        data = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
        self.assertEqual(data["register_schema_version"], REGISTER_SCHEMA_VERSION)

    def test_null_permissions_deny_selection(self) -> None:
        entry = _candidate_entry(status="selected")
        entry["adapter_training_permitted"] = None
        data = {
            "register_schema_version": REGISTER_SCHEMA_VERSION,
            "selected_model": entry["entry_id"],
            "entries": [entry],
        }
        errors = validate_model_licence_register(data)
        self.assertTrue(any("adapter_training_permitted" in e for e in errors))

    def test_selected_must_reference_existing_entry(self) -> None:
        data = {
            "register_schema_version": REGISTER_SCHEMA_VERSION,
            "selected_model": "missing",
            "entries": [_candidate_entry()],
        }
        errors = validate_model_licence_register(data)
        self.assertTrue(any("selected_model" in e for e in errors))

    def test_inference_training_checkpoint_must_match(self) -> None:
        entry = _candidate_entry(status="selected")
        entry["training_checkpoint_ref"] = _checkpoint_ref(sha="b" * 40)
        data = {
            "register_schema_version": REGISTER_SCHEMA_VERSION,
            "selected_model": entry["entry_id"],
            "entries": [entry],
        }
        errors = validate_model_licence_register(data)
        self.assertTrue(any("checkpoint" in e for e in errors))

    def test_pending_candidate_not_treated_as_approved(self) -> None:
        entry = _candidate_entry(status="candidate_evaluated")
        data = {
            "register_schema_version": REGISTER_SCHEMA_VERSION,
            "selected_model": entry["entry_id"],
            "entries": [entry],
        }
        errors = validate_model_licence_register(data)
        self.assertTrue(any("verification_status" in e for e in errors))

    def test_rejected_candidate_retains_reason(self) -> None:
        entry = _candidate_entry(status="rejected")
        entry["rejection_reason"] = "licence incompatible"
        entry["local_inference_permitted"] = False
        data = {
            "register_schema_version": REGISTER_SCHEMA_VERSION,
            "selected_model": None,
            "entries": [entry],
        }
        errors = validate_model_licence_register(data)
        self.assertEqual(errors, [])

    def test_fairness_invariant_same_revision_tokenizer(self) -> None:
        entry = _candidate_entry(status="selected")
        entry["tokenizer_revision_sha"] = "b" * 40
        data = {
            "register_schema_version": REGISTER_SCHEMA_VERSION,
            "selected_model": entry["entry_id"],
            "entries": [entry],
        }
        errors = validate_model_licence_register(data)
        self.assertTrue(any("tokenizer" in e or "revision" in e for e in errors))

    def test_qwen3_candidate_preserved_distinct_from_qwen25(self) -> None:
        data = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
        entry_ids = [entry["entry_id"] for entry in data["entries"]]
        self.assertIn("t12-cand-001", entry_ids)
        self.assertIn("t12-cand-qwen3-8b", entry_ids)
        qwen3 = next(entry for entry in data["entries"] if entry["entry_id"] == "t12-cand-qwen3-8b")
        qwen25 = next(entry for entry in data["entries"] if entry["entry_id"] == "t12-cand-001")
        self.assertNotEqual(qwen3["model_id"], qwen25["model_id"])
        self.assertEqual(
            qwen3["candidate_status"],
            "provisionally_selected_for_cluster_validation",
        )

    def test_register_still_has_null_selected_model(self) -> None:
        data = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
        self.assertIsNone(data["selected_model"])


if __name__ == "__main__":
    unittest.main()
