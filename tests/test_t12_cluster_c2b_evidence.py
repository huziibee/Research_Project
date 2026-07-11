"""CPU-only validation tests for T12 Stage C2B live backend smoke evidence."""

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
EVIDENCE_REL = "configs/model/evidence/t12_cluster_c2b_backend_smoke.json"
REPORT_REL = "docs/reports/ticket_T12_stage_C2B_live_backend_smoke.md"
LICENCE_REGISTER_REL = "configs/licences/model_licence_register.json"
EXPECTED_SHA = "b7dfba94ceae2f430e9eec7a64c4c6cd24b5a7a2"
CONTAINER_SHA = "d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1"
MODEL_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
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
PRELIM_HASHES = {
    "cd05e52f85609f5ebdde2404fc9380c2880334e11449fcdebd5be64c7e8fbb34",
    "b27e1ced350cbb6968e2af2cbe419a75007619d9c9ebc4a8b756f1b46c6a8e06",
}


def _load(relpath: str) -> dict:
    return json.loads((ROOT / relpath).read_text(encoding="utf-8"))


class T12ClusterC2BEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = _load(EVIDENCE_REL)
        cls.report = (ROOT / REPORT_REL).read_text(encoding="utf-8")
        cls.licence_register = _load(LICENCE_REGISTER_REL)
        cls.evidence_text = (ROOT / EVIDENCE_REL).read_text(encoding="utf-8")

    def test_evidence_file_exists(self) -> None:
        self.assertTrue((ROOT / EVIDENCE_REL).is_file())
        self.assertTrue((ROOT / REPORT_REL).is_file())

    def test_git_sha_matches_fix_commit(self) -> None:
        self.assertEqual(self.evidence["source_transfer"]["local_commit_sha"], EXPECTED_SHA)

    def test_source_archive_contains_fix_sha(self) -> None:
        self.assertEqual(self.evidence["source_transfer"]["local_commit_sha"], EXPECTED_SHA)
        self.assertTrue(self.evidence["source_transfer"]["archive_sha256"])
        self.assertIn(EXPECTED_SHA[:7], self.evidence["run_identity"]["run_id"])

    def test_execution_method_is_committed_backend_unchanged(self) -> None:
        method = self.evidence["execution_method"]
        self.assertEqual(method["method"], "committed_backend_unchanged")
        self.assertFalse(method["cluster_side_workaround"])
        self.assertFalse(method["instrumented_driver_used"])
        self.assertFalse(method["monkey_patch_used"])
        self.assertFalse(method["backend_source_modified_on_cluster"])

    def test_container_hash_method_is_full_sha256(self) -> None:
        self.assertEqual(self.evidence["container_integrity"]["method"], "full_sha256")

    def test_observed_sif_hash_matches_expected(self) -> None:
        integrity = self.evidence["container_integrity"]
        self.assertEqual(integrity["expected_sha256"], CONTAINER_SHA)
        self.assertEqual(integrity["observed_sha256"], CONTAINER_SHA)
        self.assertTrue(integrity["match"])

    def test_preflight_passed(self) -> None:
        self.assertEqual(self.evidence["preflight"]["status"], "pass")

    def test_model_repository_and_revision_match(self) -> None:
        model = self.evidence["model_identity"]
        self.assertEqual(model["model_repository"], _EXPECTED["model_repository"])
        self.assertEqual(model["model_revision"], MODEL_REVISION)

    def test_four_caller_ids_retained(self) -> None:
        correlation = self.evidence["request_correlation"]
        caller_ids = correlation["caller_request_ids"]
        self.assertEqual(len(caller_ids), 4)
        self.assertEqual(caller_ids, correlation["canonical_result_ids"])
        self.assertTrue(correlation["caller_ids_equal_canonical_ids"])
        self.assertEqual(
            caller_ids,
            [
                "c2b-smoke-0001",
                "c2b-smoke-0002",
                "c2b-smoke-0003",
                "c2b-smoke-0004",
            ],
        )

    def test_engine_request_ids_are_diagnostic_only(self) -> None:
        correlation = self.evidence["request_correlation"]
        self.assertTrue(correlation["engine_request_ids_diagnostic_only"])
        self.assertFalse(correlation["engine_request_ids_became_canonical_ids"])

    def test_four_requests_accounted(self) -> None:
        first = self.evidence["first_run"]
        self.assertEqual(first["request_count"], 4)
        self.assertEqual(first["accounted_count"], 4)
        self.assertEqual(first["success_count"], 4)
        self.assertEqual(first["failure_count"], 0)
        self.assertEqual(len(self.evidence["synthetic_input"]["record_ids"]), 4)

    def test_engine_start_count_equals_one(self) -> None:
        self.assertEqual(self.evidence["first_run"]["engine_start_count"], 1)

    def test_generation_batch_call_count_equals_two(self) -> None:
        self.assertEqual(self.evidence["first_run"]["generation_batch_call_count"], 2)

    def test_no_unknown_output_id(self) -> None:
        self.assertEqual(self.evidence["request_correlation"]["unknown_output_id_count"], 0)

    def test_exact_resume_skipped_without_backend_startup(self) -> None:
        resume = self.evidence["exact_resume_probe"]
        self.assertEqual(resume["observed_decision"], "skip_exact_completed")
        self.assertFalse(resume["engine_started"])
        self.assertEqual(resume["engine_start_count"], 0)

    def test_resume_preserved_hashes(self) -> None:
        resume = self.evidence["exact_resume_probe"]
        outputs = self.evidence["outputs"]
        self.assertTrue(resume["output_sha256_unchanged"])
        self.assertTrue(resume["manifest_sha256_unchanged"])
        self.assertEqual(resume["output_sha256"], outputs["output_sha256"])
        self.assertEqual(resume["manifest_sha256"], outputs["manifest_sha256"])

    def test_conflict_blocked_without_backend_startup(self) -> None:
        conflict = self.evidence["completed_conflict_probe"]
        self.assertEqual(conflict["observed_decision"], "block_completed_conflict")
        self.assertFalse(conflict["engine_started"])
        self.assertEqual(conflict["engine_start_count"], 0)

    def test_conflict_reason_contains_backend_config_mismatch(self) -> None:
        conflict = self.evidence["completed_conflict_probe"]
        self.assertIn("completed_conflict:backend_config_hash", conflict["observed_reason"])

    def test_conflict_preserved_hashes(self) -> None:
        conflict = self.evidence["completed_conflict_probe"]
        outputs = self.evidence["outputs"]
        self.assertTrue(conflict["output_sha256_unchanged"])
        self.assertTrue(conflict["manifest_sha256_unchanged"])
        self.assertEqual(conflict["canonical_output_sha256"], outputs["output_sha256"])
        self.assertEqual(conflict["canonical_manifest_sha256"], outputs["manifest_sha256"])

    def test_network_fallback_false(self) -> None:
        self.assertFalse(self.evidence["governance_state"]["network_fallback_used"])
        self.assertFalse(self.evidence["preflight"]["network_fallback"])

    def test_no_stage_d_claim(self) -> None:
        self.assertFalse(self.evidence["governance_state"]["stage_d_performed"])
        self.assertIn("no_stage_d_prompt_contract", self.evidence["non_claims"])
        self.assertNotRegex(self.report.lower(), r"stage d complete|schema-v2 prompt accepted")

    def test_no_research_or_protected_data(self) -> None:
        gov = self.evidence["governance_state"]
        self.assertFalse(gov["protected_data_used"])
        self.assertFalse(gov["research_pool_used"])

    def test_t11_remains_blocked(self) -> None:
        self.assertEqual(self.evidence["governance_state"]["t11_status"], "BLOCKED")

    def test_selected_model_remains_null(self) -> None:
        self.assertIsNone(self.evidence["governance_state"]["selected_model"])
        self.assertIsNone(self.licence_register["selected_model"])

    def test_no_preliminary_backend_run_hashes_reused(self) -> None:
        outputs = self.evidence["outputs"]
        self.assertNotIn(outputs["output_sha256"], PRELIM_HASHES)
        self.assertNotIn(outputs["manifest_sha256"], PRELIM_HASHES)
        self.assertFalse(self.evidence["historical_context"]["preliminary_backend_run_hashes_reused"])
        self.assertFalse(self.evidence["historical_context"]["preliminary_workaround_accepted"])
        self.assertTrue(self.evidence["historical_context"]["preliminary_found_request_id_defect"])

    def test_report_states_committed_source_unchanged(self) -> None:
        lowered = self.report.lower()
        self.assertIn("committed source", lowered)
        self.assertIn("no cluster-side workaround", lowered)
        self.assertIn("not accepted", lowered)

    def test_no_forbidden_personal_paths_or_credentials(self) -> None:
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

    def test_importing_evidence_module_does_not_load_torch_or_vllm(self) -> None:
        for module_name in (
            "ambiguity_manager.model.cluster.identities",
            "ambiguity_manager.model.cluster.path_policy",
        ):
            spec = importlib.util.find_spec(module_name)
            self.assertIsNotNone(spec)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        self.assertNotIn("torch", globals())
        self.assertNotIn("vllm", globals())
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("vllm", sys.modules)


if __name__ == "__main__":
    unittest.main()
