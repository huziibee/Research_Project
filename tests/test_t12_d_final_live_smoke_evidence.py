"""CPU-only validation tests for T12 Stage D-Final live smoke evidence."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

from ambiguity_manager.model.cluster.path_policy import scan_forbidden_paths
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root
EVIDENCE_REL = "configs/model/evidence/t12_d_final_live_smoke.json"
REPORT_REL = "docs/reports/ticket_T12_D_final_live_smoke.md"
ETHICS_REL = "configs/governance/human_annotation_governance.json"
EXPECTED_SHA = "02f43622b2db90a7e5ed2662a48a0752a9a0e8cc"
CONTAINER_SHA = "d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1"
MODEL_REPO = "Qwen/Qwen3-8B"
MODEL_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
SEMANTIC_SCHEMA_HASH = "232235fec53ee38eafcd714fd53664b250e848a6b0f75fca1ff7ec903b08cfb4"
STRUCTURED_DECODE_HASH = "0c0aae4cff8e80c87a57833d476d7b41310a49c3256cf48b71593aca544bc5b9"
PIPELINE_HASH_CANONICAL = "786cf6e7213fa3519ba7797464c25495f790cdf4ebc0c139c433168bd703b758"
INPUT_HASH = "c20b0659793e4b1c6bf9fb7ce44a5ddd8b9e5c6214a36de1e7b5d589997102af"
ARCHIVE_SHA = "ecedefa30a1e358f9fea55da8105543e1445e1794f4617ec3a94327e5292fe6f"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")


def _load(relpath: str) -> dict:
    return json.loads((ROOT / relpath).read_text(encoding="utf-8"))


class T12DFinalLiveSmokeEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = _load(EVIDENCE_REL)
        cls.report = (ROOT / REPORT_REL).read_text(encoding="utf-8")
        cls.ethics = _load(ETHICS_REL)
        cls.evidence_text = (ROOT / EVIDENCE_REL).read_text(encoding="utf-8")

    def test_evidence_and_report_exist(self) -> None:
        self.assertTrue((ROOT / EVIDENCE_REL).is_file())
        self.assertTrue((ROOT / REPORT_REL).is_file())

    def test_source_commit_sha(self) -> None:
        self.assertEqual(self.evidence["source_transfer"]["local_commit_sha"], EXPECTED_SHA)
        self.assertEqual(self.evidence["source_identity_manifest"]["source_commit_sha"], EXPECTED_SHA)
        self.assertRegex(EXPECTED_SHA, SHA40_RE)

    def test_transfer_method_is_git_archive(self) -> None:
        self.assertEqual(self.evidence["source_transfer"]["method"], "git_archive")
        self.assertEqual(self.evidence["source_identity_manifest"]["transfer_method"], "git_archive")

    def test_source_archive_hash_format_and_manifest_match(self) -> None:
        archive_sha = self.evidence["source_transfer"]["archive_sha256"]
        self.assertEqual(archive_sha, ARCHIVE_SHA)
        self.assertRegex(archive_sha, SHA256_RE)
        self.assertEqual(
            self.evidence["source_identity_manifest"]["source_archive_sha256"],
            archive_sha,
        )
        self.assertTrue(self.evidence["source_identity_manifest"]["local_validation_passed"])
        self.assertTrue(
            self.evidence["source_identity_manifest"]["cluster_recomputed_archive_sha256_match"]
        )

    def test_container_hash_matches(self) -> None:
        integrity = self.evidence["container_integrity"]
        self.assertEqual(integrity["expected_sha256"], CONTAINER_SHA)
        self.assertEqual(integrity["observed_sha256"], CONTAINER_SHA)
        self.assertTrue(integrity["match"])
        self.assertEqual(integrity["method"], "full_sha256")

    def test_model_and_revision_match(self) -> None:
        model = self.evidence["model_identity"]
        self.assertEqual(model["model_repository"], MODEL_REPO)
        self.assertEqual(model["model_revision"], MODEL_REVISION)

    def test_t11_gate_is_pass(self) -> None:
        self.assertEqual(self.evidence["governance_state"]["t11_status"], "PASS")

    def test_ethics_determination_not_required(self) -> None:
        gov = self.evidence["governance_state"]
        self.assertEqual(gov["ethics_determination_status"], "not_required")
        self.assertEqual(gov["ethics_determination_basis"], "supervisor_only_annotation")
        self.assertFalse(gov["external_annotators_permitted"])
        self.assertEqual(self.ethics["determination_status"], "not_required")
        self.assertFalse(self.ethics["external_annotators_permitted"])

    def test_selected_model_remains_null(self) -> None:
        self.assertIsNone(self.evidence["governance_state"]["selected_model"])

    def test_response_mode_scope_is_transport_only(self) -> None:
        probe = self.evidence["response_mode_probe"]
        self.assertFalse(probe["semantic_schema_required_for_mode_selection"])
        self.assertEqual(
            probe["semantic_schema_validation_role"],
            "diagnostic_only_for_response_mode_selection",
        )
        self.assertEqual(
            probe["verification_scope"],
            "clean_single_json_object_with_verified_structured_decode",
        )

    def test_selected_mode_passes_transport_gates(self) -> None:
        probe = self.evidence["response_mode_probe"]
        selected = probe["selected_response_mode"]
        self.assertEqual(selected, "enable_thinking_false")
        mode = probe[selected]
        self.assertTrue(mode["passed"])
        self.assertEqual(mode["finish_reason"], "stop")
        self.assertEqual(mode["direct_json_parse_status"], "success")
        self.assertEqual(mode["raw_object_status"], "single_object")
        self.assertEqual(mode["local_repair_attempts"], 0)
        self.assertFalse(mode["prose_before_json"])
        self.assertFalse(mode["prose_after_json"])
        self.assertFalse(mode["thinking_markers_present"])
        self.assertEqual(probe["response_mode_verification_status"], "verified_for_run")

    def test_probe_semantic_status_retained_diagnostically(self) -> None:
        probe = self.evidence["response_mode_probe"]
        self.assertEqual(probe["probe_semantic_schema_status_selected"], "invalid")
        self.assertEqual(probe["enable_thinking_false"]["semantic_schema_status"], "invalid")
        self.assertIn("supporting_evidence", probe["enable_thinking_false"]["semantic_schema_error"])

    def test_engine_starts_exactly_once(self) -> None:
        self.assertEqual(self.evidence["generation_execution"]["engine_start_count"], 1)

    def test_generation_call_accounting_distinguishes_probe_and_record(self) -> None:
        gen = self.evidence["generation_execution"]
        self.assertEqual(gen["probe_generation_call_count"], 2)
        self.assertEqual(gen["record_generation_call_count"], 12)
        self.assertEqual(gen["total_generation_call_count"], 14)
        self.assertEqual(
            gen["total_generation_call_count"],
            gen["probe_generation_call_count"] + gen["record_generation_call_count"],
        )
        self.assertEqual(gen["runner_reported_generation_call_count"], 2)
        self.assertEqual(gen["runner_generation_count_semantics"], "probe_calls_only")
        self.assertEqual(gen["record_raw_attempt_count"], 12)
        self.assertNotIn("generation_call_count", gen)
        self.assertIn("probe calls only", self.report.lower())
        self.assertIn("total_generation_call_count", self.report)
        self.assertRegex(self.report, r"total_generation_call_count[`\s|]*\|?\s*14")
        self.assertIn("must not be read as the total model-generation count", self.report)

    def test_four_records_attempted_none_accepted_for_blocked(self) -> None:
        records = self.evidence["record_results"]
        self.assertEqual(records["records_attempted"], 4)
        self.assertEqual(records["records_accepted"], 0)
        self.assertEqual(records["records_rejected_after_attempts"], 4)
        self.assertEqual(self.evidence["run_status"]["status"], "BLOCKED")
        self.assertEqual(
            self.evidence["synthetic_input"]["record_ids"],
            ["dfinal-001", "dfinal-002", "dfinal-003", "dfinal-004"],
        )

    def test_accepted_prediction_validity_totals_are_zero(self) -> None:
        records = self.evidence["record_results"]
        self.assertEqual(records["schema_valid_accepted_count"], 0)
        self.assertEqual(records["canonical_schema_v2_valid_accepted_count"], 0)
        self.assertEqual(records["unsupported_commitment_count"], 0)

    def test_all_raw_attempts_retained(self) -> None:
        self.assertEqual(self.evidence["record_results"]["raw_attempt_retention_count"], 12)
        self.assertEqual(self.evidence["output_file_hashes"]["raw_attempts.jsonl"]["row_count"], 12)
        self.assertEqual(self.evidence["output_file_hashes"]["attempt_ledgers.jsonl"]["row_count"], 12)

    def test_no_fallback_or_lossy_adaptation(self) -> None:
        sd = self.evidence["structured_decode"]
        self.assertEqual(sd["construction_status"], "constructed")
        self.assertFalse(sd["guided_decoding_used"])
        self.assertFalse(sd["unconstrained_fallback"])
        self.assertFalse(sd["lossy_adaptation"])
        self.assertFalse(self.evidence["execution_method"]["unconstrained_generation"])
        self.assertFalse(self.evidence["execution_method"]["remote_source_modified"])

    def test_semantic_correctness_not_evaluated(self) -> None:
        self.assertEqual(self.evidence["semantic_correctness_status"], "not_evaluated")

    def test_manifest_verification_passed(self) -> None:
        mv = self.evidence["manifest_verification"]
        self.assertTrue(mv["performed"])
        self.assertTrue(mv["passed"])
        self.assertTrue(mv["independent_recompute"])
        self.assertTrue(mv["all_listed_hashes_matched"])
        self.assertTrue(mv["all_required_evidence_files_present"])

    def test_contract_and_input_hashes(self) -> None:
        contracts = self.evidence["contract_hashes"]
        self.assertEqual(contracts["semantic_schema_hash"], SEMANTIC_SCHEMA_HASH)
        self.assertEqual(contracts["structured_decode_contract_hash"], STRUCTURED_DECODE_HASH)
        self.assertEqual(contracts["pipeline_contract_hash_canonical"], PIPELINE_HASH_CANONICAL)
        self.assertEqual(contracts["pipeline_contract_hash_method"], "canonical_json_sha256_v1")
        self.assertEqual(self.evidence["synthetic_input"]["input_sha256"], INPUT_HASH)

    def test_no_protected_or_research_data(self) -> None:
        gov = self.evidence["governance_state"]
        self.assertFalse(gov["protected_data_used"])
        self.assertFalse(gov["research_pool_used"])
        self.assertFalse(self.evidence["synthetic_input"]["protected_or_research_pool_data_used"])
        self.assertTrue(self.evidence["synthetic_input"]["synthetic"])

    def test_nested_preflight_passed(self) -> None:
        preflight = self.evidence["preflight"]
        self.assertEqual(preflight["status"], "pass")
        self.assertTrue(preflight["nested_runner_acceptance"])
        self.assertTrue(preflight["offline_resolution_passed"])
        self.assertFalse(preflight["network_fallback"])
        self.assertEqual(preflight["snapshot_inventory_status"], "pass")

    def test_report_records_blocked_not_pass(self) -> None:
        self.assertIn("BLOCKED", self.report)
        self.assertIn(EXPECTED_SHA, self.report)
        self.assertIn("3974", self.report)
        self.assertIn("enable_thinking_false", self.report)
        self.assertNotIn("D-FINAL LIVE SMOKE PASS", self.report)

    def test_no_forbidden_personal_paths_or_credentials(self) -> None:
        errors = scan_forbidden_paths(self.evidence)
        self.assertEqual(errors, [])
        for pattern in (
            r"\bmbangie\b",
            r"\bhuzii\b",
            r"C:\\Users\\",
            r"/home-mscluster/",
            r"password\s*=",
            r"api[_-]?key\s*=",
            r"BEGIN (RSA|OPENSSH) PRIVATE KEY",
        ):
            self.assertIsNone(re.search(pattern, self.evidence_text))
            self.assertIsNone(re.search(pattern, self.report))

    def test_sanitised_path_templates_used(self) -> None:
        self.assertIn("${T12_CLUSTER_ROOT}", self.evidence["run_identity"]["remote_run_path_template"])
        self.assertIn("${T12_CONTAINER_SIF}", self.evidence["container_integrity"]["container_path_template"])
        self.assertIn("${T12_CLUSTER_ROOT}", self.report)

    def test_importing_evidence_module_does_not_load_torch_or_vllm(self) -> None:
        for module_name in (
            "ambiguity_manager.model.cluster.identities",
            "ambiguity_manager.model.cluster.path_policy",
        ):
            spec = importlib.util.find_spec(module_name)
            self.assertIsNotNone(spec)
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("vllm", sys.modules)
        self.assertNotIn("transformers", sys.modules)


if __name__ == "__main__":
    unittest.main()
