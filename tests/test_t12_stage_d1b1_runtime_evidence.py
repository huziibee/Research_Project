"""CPU-only validation tests for T12 Stage D1B1 pinned runtime inspection evidence."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

from ambiguity_manager.model.cluster.identities import _EXPECTED
from ambiguity_manager.model.cluster.path_policy import scan_forbidden_paths
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root
EVIDENCE_REL = "configs/model/evidence/t12_stage_d1b1_pinned_runtime.json"
REPORT_REL = "docs/reports/ticket_T12_stage_D1B1_pinned_runtime_inspection.md"
LICENCE_REGISTER_REL = "configs/licences/model_licence_register.json"
EXPECTED_SHA = "885ae878120a2fd5db3950056ea39f4a4f847704"
CONTAINER_SHA = "d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1"
MODEL_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
SEMANTIC_SCHEMA_HASH = "232235fec53ee38eafcd714fd53664b250e848a6b0f75fca1ff7ec903b08cfb4"
DERIVATION_VERSION = "t12-d1a-1.1.0"
ALLOWED_CONSTRUCTION = frozenset(
    {
        "supported_as_is",
        "supported_with_documented_lossless_adapter",
        "unsupported_by_pinned_runtime",
        "inspection_inconclusive",
    }
)
ALLOWED_TEMPLATE_CONTROL = frozenset(
    {
        "template_non_thinking_control_verified",
        "template_control_unsupported",
        "template_control_incompatible_revision",
        "template_inspection_inconclusive",
    }
)
FORBIDDEN_PATTERNS = (
    r"\bmbangie\b",
    r"\bhuzii\b",
    r"\bhuziiee\b",
    r"C:\\Users\\",
    r"/mnt/c/Users/",
    r"/home-mscluster/mbangie/",
    r"password\s*=",
    r"api[_-]?key\s*=",
    r"BEGIN (RSA|OPENSSH) PRIVATE KEY",
)


def _load(relpath: str) -> dict:
    return json.loads((ROOT / relpath).read_text(encoding="utf-8"))


class T12StageD1B1RuntimeEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = _load(EVIDENCE_REL)
        cls.report = (ROOT / REPORT_REL).read_text(encoding="utf-8")
        cls.licence_register = _load(LICENCE_REGISTER_REL)
        cls.evidence_text = (ROOT / EVIDENCE_REL).read_text(encoding="utf-8")

    def test_evidence_and_report_exist(self) -> None:
        self.assertTrue((ROOT / EVIDENCE_REL).is_file())
        self.assertTrue((ROOT / REPORT_REL).is_file())

    def test_source_git_sha(self) -> None:
        self.assertEqual(self.evidence["source_transfer"]["local_commit_sha"], EXPECTED_SHA)

    def test_model_repository_and_revision(self) -> None:
        model = self.evidence["model_identity"]
        self.assertEqual(model["model_repository"], _EXPECTED["model_repository"])
        self.assertEqual(model["model_revision"], MODEL_REVISION)

    def test_container_full_sif_sha(self) -> None:
        integrity = self.evidence["container_integrity"]
        self.assertEqual(integrity["expected_sha256"], CONTAINER_SHA)
        self.assertEqual(integrity["observed_sha256"], CONTAINER_SHA)
        self.assertTrue(integrity["match"])
        self.assertEqual(integrity["hash_method"], "full_sha256")

    def test_vllm_version(self) -> None:
        self.assertEqual(self.evidence["runtime_versions"]["vllm_version"], "0.20.1")

    def test_semantic_schema_hash_and_derivation(self) -> None:
        schema = self.evidence["semantic_schema"]
        self.assertEqual(schema["derivation_version"], DERIVATION_VERSION)
        self.assertEqual(schema["canonical_export_sha256"], SEMANTIC_SCHEMA_HASH)
        self.assertEqual(schema["expected_canonical_sha256"], SEMANTIC_SCHEMA_HASH)
        self.assertTrue(schema["canonical_hash_match"])

    def test_structured_output_class_and_module_recorded(self) -> None:
        vllm_out = self.evidence["vllm_structured_output"]
        self.assertEqual(vllm_out["structured_output_class"], "StructuredOutputsParams")
        self.assertEqual(
            vllm_out["structured_output_module"],
            "vllm.sampling_params.StructuredOutputsParams",
        )
        self.assertEqual(vllm_out["structured_output_field_name"], "structured_outputs")

    def test_schema_parameter_recorded(self) -> None:
        vllm_out = self.evidence["vllm_structured_output"]
        self.assertEqual(vllm_out["schema_parameter_name"], "json")
        self.assertIn("dict", vllm_out["schema_parameter_accepted_types"])

    def test_construction_classification_allowed(self) -> None:
        classification = self.evidence["vllm_structured_output"]["construction_classification"]
        self.assertIn(classification, ALLOWED_CONSTRUCTION)

    def test_no_lossy_schema_adaptation_claimed(self) -> None:
        self.assertFalse(self.evidence["vllm_structured_output"]["lossy_schema_adaptation_required"])

    def test_tokenizer_artefact_hashes_recorded(self) -> None:
        hashes = self.evidence["tokenizer_inspection"]["artefact_hashes"]
        for key in ("tokenizer_config.json", "tokenizer.json", "vocab.json", "merges.txt"):
            with self.subTest(key=key):
                self.assertTrue(hashes[key])

    def test_template_control_classification_recorded(self) -> None:
        classification = self.evidence["tokenizer_inspection"]["template_control_classification"]
        self.assertIn(classification, ALLOWED_TEMPLATE_CONTROL)
        self.assertEqual(
            self.evidence["response_mode"]["template_control_status"],
            classification,
        )

    def test_non_thinking_control_tied_to_pinned_revision(self) -> None:
        tok = self.evidence["tokenizer_inspection"]
        self.assertEqual(tok["non_thinking_control_method"], "apply_chat_template(enable_thinking=False)")
        self.assertEqual(self.evidence["model_identity"]["model_revision"], MODEL_REVISION)

    def test_generation_output_verification_pending(self) -> None:
        self.assertEqual(
            self.evidence["response_mode"]["generation_output_verification_status"],
            "pending_stage_d2_live_schema_smoke",
        )

    def test_no_model_engine_or_generation(self) -> None:
        proof = self.evidence["no_model_load_proof"]
        self.assertFalse(proof["engine_instantiated"])
        self.assertFalse(proof["generation_called"])
        self.assertFalse(proof["model_weights_loaded"])

    def test_offline_and_no_network_fallback(self) -> None:
        self.assertTrue(self.evidence["governance_state"]["offline"])
        self.assertFalse(self.evidence["governance_state"]["network_fallback_used"])

    def test_no_protected_or_research_data(self) -> None:
        gov = self.evidence["governance_state"]
        self.assertFalse(gov["protected_data_used"])
        self.assertFalse(gov["research_pool_data_used"])

    def test_t11_blocked_and_selected_model_null(self) -> None:
        self.assertEqual(self.evidence["governance_state"]["t11_status"], "BLOCKED")
        self.assertIsNone(self.evidence["governance_state"]["selected_model"])
        self.assertIsNone(self.licence_register["selected_model"])

    def test_stage_d1b_adapter_not_implemented(self) -> None:
        self.assertFalse(self.evidence["governance_state"]["stage_d1b_adapter_implemented"])

    def test_rendered_prompt_hashes_recorded(self) -> None:
        tok = self.evidence["tokenizer_inspection"]
        self.assertTrue(tok["default_rendered_prompt_sha256"])
        self.assertTrue(tok["non_thinking_rendered_prompt_sha256"])
        self.assertNotEqual(
            tok["default_rendered_prompt_sha256"],
            tok["non_thinking_rendered_prompt_sha256"],
        )

    def test_no_forbidden_paths_or_credentials(self) -> None:
        errors = scan_forbidden_paths(self.evidence)
        self.assertEqual(errors, [], msg="\n".join(errors))
        for pattern in FORBIDDEN_PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertIsNone(
                    re.search(pattern, self.evidence_text, re.IGNORECASE),
                    msg=f"forbidden pattern matched in evidence: {pattern}",
                )
                self.assertIsNone(
                    re.search(pattern, self.report, re.IGNORECASE),
                    msg=f"forbidden pattern matched in report: {pattern}",
                )

    def test_importing_evidence_helpers_does_not_load_torch_or_vllm(self) -> None:
        for module_name in (
            "ambiguity_manager.model.cluster.identities",
            "ambiguity_manager.model.cluster.path_policy",
        ):
            spec = importlib.util.find_spec(module_name)
            self.assertIsNotNone(spec)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("vllm", sys.modules)
        self.assertNotIn("transformers", sys.modules)


if __name__ == "__main__":
    unittest.main()
