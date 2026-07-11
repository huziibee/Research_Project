"""Tests for T12 Slice 3A model candidate and licence verification."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.governance.ethics import derive_ticket_verdict, validate_ethics_determination
from ambiguity_manager.governance.model_licence import (
    CUMULATIVE_DOWNLOAD_CAP_BYTES,
    MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES,
    MANDATORY_CONTEXT_LIMIT,
    REGISTER_SCHEMA_VERSION,
    validate_model_licence_register,
)
from ambiguity_manager.model.candidate_evidence import (
    CUMULATIVE_DOWNLOAD_CAP_BYTES as EVIDENCE_CAP_BYTES,
    DECIMAL_30_GB_BYTES,
    EVIDENCE_REL,
    MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES as EVIDENCE_MAX_BYTES,
    REGISTER_REL,
    _FORBIDDEN_ALLOWLIST_PATTERNS,
    _REQUIRED_ALLOWLIST_PATTERNS,
    validate_candidate_evidence,
)
from ambiguity_manager.model.environment import INFERENCE_ENV_REL, TRAINING_ENV_REL
from ambiguity_manager.model.environment_evidence import EVIDENCE_REL as ENV_EVIDENCE_REL
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root
REGISTER_PATH = ROOT / REGISTER_REL
EVIDENCE_PATH = ROOT / EVIDENCE_REL
ETHICS_PATH = ROOT / "configs" / "governance" / "human_annotation_governance.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _minimal_candidate(**overrides: object) -> dict:
    base = {
        "register_entry_id": "t12-cand-001",
        "provider": "Qwen",
        "model_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "immutable_revision_sha": "a" * 40,
        "revision_alias": "main",
        "tokenizer_repository": "Qwen/Qwen2.5-1.5B-Instruct",
        "tokenizer_revision_sha": "a" * 40,
        "architecture": "Qwen2ForCausalLM",
        "parameter_count": 1543714304,
        "context_limit": 32768,
        "licence_identifier": "apache-2.0",
        "official_evidence_references": ["https://example.org/evidence"],
        "local_inference_permitted": True,
        "academic_research_permitted": True,
        "adapter_training_permitted": True,
        "gated_access": False,
        "authoritative_checkpoint_ref": {
            "model_id": "Qwen/Qwen2.5-1.5B-Instruct",
            "immutable_revision_sha": "a" * 40,
            "tokenizer_revision_sha": "a" * 40,
        },
        "estimated_checkpoint_download_bytes": 1000000,
        "expected_quantisation_approach": "bitsandbytes 4-bit NF4",
        "transformers_compatibility_evidence": "AutoModelForCausalLM",
        "peft_compatibility_evidence": "Qwen2 LoRA target modules",
        "verification_status": "candidate_evaluated",
        "eligibility_gates": {
            "public_ungated": True,
            "text_only_causal": True,
            "official_provider": True,
            "immutable_revision_sha": True,
            "official_licence": True,
            "local_inference_permitted": True,
            "academic_research_permitted": True,
            "adapter_training_permitted": True,
            "transformers_supported": True,
            "peft_compatible": True,
            "tokenizer_available": True,
            "no_lvlm_dependency": True,
            "download_under_cap": True,
            "quantised_inference_plausible": True,
            "authoritative_checkpoint": True,
        },
    }
    base.update(overrides)
    return base


def _minimal_evidence(**overrides: object) -> dict:
    base = {
        "manifest_schema_version": "1.0.0",
        "ticket": "T12",
        "slice": "3A",
        "verification_date": "2026-07-11",
        "verifier": "AUTHOR-01",
        "no_model_download": True,
        "no_model_execution": True,
        "no_absolute_paths": True,
        "cumulative_download_cap_bytes": EVIDENCE_MAX_BYTES,
        "maximum_cumulative_download_bytes": EVIDENCE_MAX_BYTES,
        "cumulative_download_cap_display": "30 GiB",
        "recommended_first_probe_download_bytes": 3098955668,
        "remaining_headroom_bytes": 29113299052,
        "max_single_candidate_download_bytes": 1000000,
        "recommended_first_probe_candidate": "t12-cand-001",
        "recommended_fallback_candidate": "t12-cand-002",
        "candidates": [_minimal_candidate(), _minimal_candidate(register_entry_id="t12-cand-002", model_id="HuggingFaceTB/SmolLM2-1.7B-Instruct")],
        "download_plan": {
            "execute_in_slice": "3B",
            "stop_before_checkpoint_load": True,
            "maximum_cumulative_download_bytes": EVIDENCE_MAX_BYTES,
            "cumulative_download_cap_display": "30 GiB",
            "size_tolerance_bytes": 104857600,
            "allowlist": {
                "include_patterns": list(_REQUIRED_ALLOWLIST_PATTERNS),
                "exclude_patterns": list(_FORBIDDEN_ALLOWLIST_PATTERNS),
            },
        },
    }
    base.update(overrides)
    return base


class T12ModelCandidateVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.register = _load_json(REGISTER_PATH)
        cls.evidence = _load_json(EVIDENCE_PATH)

    def test_register_selected_model_remains_null(self) -> None:
        self.assertIsNone(self.register["selected_model"])

    def test_no_selected_entries_in_slice_3a(self) -> None:
        statuses = [entry["verification_status"] for entry in self.register["entries"]]
        self.assertNotIn("selected", statuses)

    def test_register_validation_passes(self) -> None:
        errors = validate_model_licence_register(self.register)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_evidence_validation_passes(self) -> None:
        errors = validate_candidate_evidence(self.evidence, register=self.register)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_candidate_evaluated_requires_exact_model_commit_sha(self) -> None:
        for entry in self.register["entries"]:
            if entry["verification_status"] == "candidate_evaluated":
                self.assertRegex(entry["immutable_revision_sha"], r"^[0-9a-f]{40}$")

    def test_tokenizer_revision_sha_required(self) -> None:
        for entry in self.register["entries"]:
            if entry.get("tokenizer_revision_sha") is not None:
                self.assertRegex(entry["tokenizer_revision_sha"], r"^[0-9a-f]{40}$")

    def test_branch_tag_alone_rejected_by_validator(self) -> None:
        data = _minimal_evidence()
        data["candidates"][0]["immutable_revision_sha"] = "main"
        errors = validate_candidate_evidence(data)
        self.assertTrue(any("SHA" in e or "branch" in e for e in errors))

    def test_gated_candidates_rejected(self) -> None:
        gated = [e for e in self.register["entries"] if e.get("gated_access") is True]
        for entry in gated:
            self.assertEqual(entry["verification_status"], "rejected")

    def test_null_licence_permissions_reject_eligibility(self) -> None:
        candidate = _minimal_candidate(local_inference_permitted=None)
        data = _minimal_evidence(candidates=[candidate])
        errors = validate_candidate_evidence(data)
        self.assertTrue(any("local_inference_permitted" in e for e in errors))

    def test_local_inference_permission_required(self) -> None:
        candidate = _minimal_candidate(local_inference_permitted=False)
        data = _minimal_evidence(candidates=[candidate])
        errors = validate_candidate_evidence(data)
        self.assertTrue(any("local_inference_permitted" in e for e in errors))

    def test_academic_research_permission_required(self) -> None:
        candidate = _minimal_candidate(academic_research_permitted=False)
        data = _minimal_evidence(candidates=[candidate])
        errors = validate_candidate_evidence(data)
        self.assertTrue(any("academic_research_permitted" in e for e in errors))

    def test_adapter_training_permission_required(self) -> None:
        candidate = _minimal_candidate(adapter_training_permitted=False)
        data = _minimal_evidence(candidates=[candidate])
        errors = validate_candidate_evidence(data)
        self.assertTrue(any("adapter_training_permitted" in e for e in errors))

    def test_inference_training_checkpoint_parity(self) -> None:
        for entry in self.register["entries"]:
            self.assertEqual(entry["inference_checkpoint_ref"], entry["training_checkpoint_ref"])

    def test_official_evidence_references_required(self) -> None:
        for candidate in self.evidence["candidates"]:
            self.assertIsInstance(candidate["official_evidence_references"], list)
            self.assertTrue(candidate["official_evidence_references"])

    def test_estimated_download_size_required(self) -> None:
        for entry in self.register["entries"]:
            if entry["verification_status"] == "candidate_evaluated":
                self.assertIsInstance(entry["estimated_download_bytes"], int)
                self.assertGreater(entry["estimated_download_bytes"], 0)

    def test_30gb_cumulative_cap_enforced(self) -> None:
        for entry in self.register["entries"]:
            if entry["verification_status"] == "candidate_evaluated":
                self.assertLessEqual(entry["estimated_download_bytes"], CUMULATIVE_DOWNLOAD_CAP_BYTES)
        self.assertEqual(self.evidence["maximum_cumulative_download_bytes"], MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES)
        self.assertEqual(self.evidence["cumulative_download_cap_bytes"], MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES)
        self.assertEqual(self.evidence["cumulative_download_cap_display"], "30 GiB")
        self.assertNotEqual(self.evidence["cumulative_download_cap_bytes"], DECIMAL_30_GB_BYTES)

    def test_headroom_arithmetic_is_correct(self) -> None:
        self.assertEqual(self.evidence["recommended_first_probe_download_bytes"], 3098955668)
        self.assertEqual(self.evidence["remaining_headroom_bytes"], 29113299052)
        self.assertEqual(
            self.evidence["recommended_first_probe_download_bytes"] + self.evidence["remaining_headroom_bytes"],
            MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES,
        )

    def test_every_evaluated_candidate_has_register_entry(self) -> None:
        register_ids = {entry["entry_id"] for entry in self.register["entries"]}
        evidence_ids = {candidate["register_entry_id"] for candidate in self.evidence["candidates"]}
        self.assertEqual(len(self.evidence["candidates"]), 9)
        self.assertGreaterEqual(len(self.register["entries"]), 9)
        self.assertTrue(evidence_ids.issubset(register_ids))

    def test_final_candidate_counts(self) -> None:
        evaluated = len(self.evidence["candidates"])
        eligible = sum(
            1 for entry in self.register["entries"] if entry["verification_status"] == "candidate_evaluated"
        )
        rejected = sum(1 for entry in self.register["entries"] if entry["verification_status"] == "rejected")
        self.assertEqual(evaluated, 9)
        self.assertEqual(eligible, 6)
        self.assertEqual(rejected, 4)

    def test_third_party_quant_rejected_in_register(self) -> None:
        entry = next(e for e in self.register["entries"] if e["entry_id"] == "t12-rej-003")
        self.assertEqual(entry["model_id"], "TheBloke/Qwen2.5-1.5B-Instruct-GPTQ")
        self.assertEqual(entry["verification_status"], "rejected")
        self.assertFalse(entry["authoritative_checkpoint"])
        self.assertTrue(entry["third_party_quantised_repository"])

    def test_context_limit_below_4096_cannot_be_eligible(self) -> None:
        tiny = next(e for e in self.register["entries"] if e["entry_id"] == "t12-cand-003")
        self.assertEqual(tiny["verification_status"], "rejected")
        self.assertEqual(tiny["context_limit"], 2048)
        self.assertEqual(tiny["failed_gate"], "context_limit")
        self.assertNotIn(
            tiny["entry_id"],
            {
                e["entry_id"]
                for e in self.register["entries"]
                if e["verification_status"] == "candidate_evaluated"
            },
        )

    def test_no_smaller_fallback_recommendation(self) -> None:
        self.assertNotIn("recommended_smaller_fallback_candidate", self.evidence)

    def test_download_allowlist_excludes_redundant_formats(self) -> None:
        allowlist = self.evidence["download_plan"]["allowlist"]
        self.assertIn("*.safetensors", allowlist["include_patterns"])
        self.assertIn("pytorch_model*.bin", allowlist["exclude_patterns"])
        self.assertIn("*-gptq*", allowlist["exclude_patterns"])
        self.assertIn("*.gguf", allowlist["exclude_patterns"])
        self.assertIn("onnx/**", allowlist["exclude_patterns"])

    def test_first_probe_candidate_references_eligible_register_entry(self) -> None:
        primary = self.evidence["recommended_first_probe_candidate"]
        eligible = {
            e["entry_id"]
            for e in self.register["entries"]
            if e["verification_status"] == "candidate_evaluated"
        }
        self.assertIn(primary, eligible)

    def test_fallback_candidate_differs_from_primary(self) -> None:
        self.assertNotEqual(
            self.evidence["recommended_first_probe_candidate"],
            self.evidence["recommended_fallback_candidate"],
        )

    def test_rejected_candidates_retain_reasons(self) -> None:
        for entry in self.register["entries"]:
            if entry["verification_status"] == "rejected":
                self.assertTrue(entry.get("rejection_reason"))

    def test_third_party_quantised_repos_cannot_be_authoritative(self) -> None:
        entry = next(e for e in self.register["entries"] if e["entry_id"] == "t12-rej-003")
        self.assertIn("third-party", entry["rejection_reason"].lower())
        self.assertIn("GPTQ", entry["model_id"])

    def test_candidate_evidence_rejects_absolute_paths_and_usernames(self) -> None:
        text = EVIDENCE_PATH.read_text(encoding="utf-8").lower()
        self.assertNotIn("huzii", text)
        self.assertNotIn("c:\\users\\", text)
        self.assertNotIn("/home/", text)

    def test_no_model_weight_extensions_in_tracked_evidence(self) -> None:
        excluded_prefixes = (
            "tests/",
            "external/",
            "outputs/",
            ".venv",
            ".git/",
        )
        weight_suffixes = {".safetensors", ".gguf", ".pt", ".pth", ".onnx", ".ckpt"}
        for path in (ROOT / "configs" / "model").rglob("*"):
            if path.is_file() and path.suffix.lower() in weight_suffixes:
                self.fail(f"unexpected model weight file: {path.relative_to(ROOT).as_posix()}")
        for path in ROOT.rglob("*.bin"):
            rel = path.relative_to(ROOT).as_posix()
            if any(rel.startswith(prefix) for prefix in excluded_prefixes):
                continue
            if rel.startswith("configs/model/"):
                self.fail(f"unexpected model weight file: {rel}")

    def test_normal_package_import_remains_ml_free(self) -> None:
        import importlib.util

        import ambiguity_manager  # noqa: F401

        self.assertIsNone(importlib.util.find_spec("torch"))

    def test_t11_remains_blocked(self) -> None:
        ethics = _load_json(ETHICS_PATH)
        errors = validate_ethics_determination(ethics)
        self.assertEqual(errors, [])
        self.assertEqual(derive_ticket_verdict(ethics), "BLOCKED")

    def test_checkpoint_load_verified_remains_false(self) -> None:
        for rel in (INFERENCE_ENV_REL, TRAINING_ENV_REL):
            manifest = _load_json(ROOT / rel)
            self.assertFalse(manifest["checkpoint_load_verified"])
        env_evidence = _load_json(ROOT / ENV_EVIDENCE_REL)
        self.assertFalse(env_evidence["checkpoint_load_verified"])

    def test_t13_t14_artefacts_do_not_exist(self) -> None:
        for rel in (
            "docs/reports/ticket_T13_completion_report.md",
            "docs/reports/ticket_T14_completion_report.md",
            "configs/model/evidence/t13_annotation_evidence.json",
            "configs/model/evidence/t14_annotation_evidence.json",
        ):
            self.assertFalse((ROOT / rel).exists(), msg=f"unexpected artefact: {rel}")

    def test_no_model_download_or_execution_flags(self) -> None:
        self.assertTrue(self.evidence["no_model_download"])
        self.assertTrue(self.evidence["no_model_execution"])

    def test_download_plan_defers_to_slice_3b(self) -> None:
        plan = self.evidence["download_plan"]
        self.assertEqual(plan["execute_in_slice"], "3B")
        self.assertTrue(plan["stop_before_checkpoint_load"])


if __name__ == "__main__":
    unittest.main()
