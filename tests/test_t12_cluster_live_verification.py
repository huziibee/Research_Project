"""CPU-only validation tests for T12 Stage B2/B2R live verification evidence."""

from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

from ambiguity_manager.model.cluster.identities import IMMUTABLE_SELECTION_REL, _EXPECTED
from ambiguity_manager.model.cluster.manifest_schemas import (
    CLUSTER_CHECKPOINT_SNAPSHOT_REL,
    CLUSTER_HARDWARE_EVIDENCE_REL,
    CLUSTER_INFERENCE_ENV_REL,
    CLUSTER_INFERENCE_EVIDENCE_REL,
    CLUSTER_LIVE_VERIFICATION_REL,
    validate_cluster_checkpoint_snapshot,
    validate_cluster_environment_manifest,
    validate_cluster_hardware_evidence,
    validate_cluster_inference_evidence,
    validate_cluster_live_verification,
)
from ambiguity_manager.model.cluster.path_policy import scan_forbidden_paths
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root
LICENCE_REGISTER_REL = "configs/licences/model_licence_register.json"
EXECUTION_POLICY_REL = "configs/model/cluster_execution_policy.json"
REPORT_REL = "docs/reports/ticket_T12_stage_b2_live_verification.md"

MODEL_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
CONTAINER_SHA = "d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1"
CONTAINER_SIZE = 7657443328
SNAPSHOT_BYTES = 16397461266
HF_HUB_SNAPSHOT = (
    f"${{T12_HF_CACHE}}/hub/models--Qwen--Qwen3-8B/snapshots/{MODEL_REVISION}"
)
FORBIDDEN_PATTERNS = (
    r"\bmbangie\b",
    r"\bhuzii\b",
    r"\bhuziiee\b",
    r"C:\\Users\\",
    r"/mnt/c/Users/",
    r"/home-mscluster/mbangie/",
)


def _load(relpath: str) -> dict:
    return json.loads((ROOT / relpath).read_text(encoding="utf-8"))


def _all_b3_relpaths() -> tuple[str, ...]:
    return (
        CLUSTER_INFERENCE_ENV_REL,
        CLUSTER_HARDWARE_EVIDENCE_REL,
        CLUSTER_INFERENCE_EVIDENCE_REL,
        CLUSTER_CHECKPOINT_SNAPSHOT_REL,
        CLUSTER_LIVE_VERIFICATION_REL,
        REPORT_REL,
    )


class T12ClusterLiveVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inference_env = _load(CLUSTER_INFERENCE_ENV_REL)
        cls.hardware = _load(CLUSTER_HARDWARE_EVIDENCE_REL)
        cls.inference_evidence = _load(CLUSTER_INFERENCE_EVIDENCE_REL)
        cls.snapshot = _load(CLUSTER_CHECKPOINT_SNAPSHOT_REL)
        cls.live = _load(CLUSTER_LIVE_VERIFICATION_REL)
        cls.execution_policy = _load(EXECUTION_POLICY_REL)
        cls.licence_register = _load(LICENCE_REGISTER_REL)
        cls.report = (ROOT / REPORT_REL).read_text(encoding="utf-8")

    # --- schema validation ---

    def test_inference_environment_validates(self) -> None:
        errors = validate_cluster_environment_manifest(self.inference_env)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_hardware_evidence_validates(self) -> None:
        errors = validate_cluster_hardware_evidence(self.hardware)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_inference_evidence_validates(self) -> None:
        errors = validate_cluster_inference_evidence(self.inference_evidence)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_checkpoint_snapshot_validates(self) -> None:
        errors = validate_cluster_checkpoint_snapshot(self.snapshot)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_live_verification_validates(self) -> None:
        errors = validate_cluster_live_verification(self.live)
        self.assertEqual(errors, [], msg="\n".join(errors))

    # --- cache semantics regression ---

    def test_hf_home_refers_to_parent_cache_root(self) -> None:
        semantics = self.inference_env["hf_cache_semantics"]
        self.assertEqual(semantics["hf_home_template"], "${T12_HF_CACHE}")

    def test_derived_hub_cache_is_hf_cache_slash_hub(self) -> None:
        semantics = self.inference_env["hf_cache_semantics"]
        self.assertEqual(semantics["hf_hub_cache_derived_template"], "${T12_HF_CACHE}/hub")
        self.assertEqual(self.inference_env["paths"]["hf_hub_cache"], "${T12_HF_CACHE}/hub")

    def test_explicit_cache_dir_must_point_to_hub_cache(self) -> None:
        semantics = self.inference_env["hf_cache_semantics"]
        self.assertEqual(
            semantics["explicit_snapshot_download_cache_dir_must_be"],
            "${T12_HF_CACHE}/hub",
        )
        probe_a = self.snapshot["offline_resolution"]["probes"]["probe_a"]
        self.assertEqual(probe_a["cache_dir"], "${T12_HF_CACHE}/hub")

    def test_snapshot_template_contains_hub_models_path(self) -> None:
        template = self.inference_env["model_identity"]["snapshot_path_template"]["value"]
        self.assertIn("/hub/models--Qwen--Qwen3-8B/", template)
        self.assertEqual(self.snapshot["snapshot_path_template"], HF_HUB_SNAPSHOT)

    def test_missing_refs_not_treated_as_failure(self) -> None:
        semantics = self.inference_env["hf_cache_semantics"]
        offline = self.snapshot["offline_resolution"]
        self.assertFalse(semantics["refs_directory_required"])
        self.assertFalse(offline["refs_directory_causal"])
        self.assertEqual(offline["status"], "passed")

    def test_root_cause_is_incorrect_cache_dir(self) -> None:
        self.assertEqual(
            self.inference_env["hf_cache_semantics"]["offline_resolution_root_cause"],
            "INCORRECT_CACHE_DIR",
        )
        self.assertEqual(
            self.snapshot["offline_resolution"]["root_cause_classification"],
            "INCORRECT_CACHE_DIR",
        )

    def test_offline_flags_required_for_acceptance(self) -> None:
        flags = set(self.inference_env["hf_cache_semantics"]["offline_flags_required"])
        self.assertEqual(flags, {"HF_HUB_OFFLINE=1", "TRANSFORMERS_OFFLINE=1"})
        offline_flags = self.snapshot["offline_resolution"]["offline_flags_required"]
        self.assertEqual(offline_flags["HF_HUB_OFFLINE"], "1")
        self.assertEqual(offline_flags["TRANSFORMERS_OFFLINE"], "1")

    def test_network_fallback_is_false(self) -> None:
        self.assertFalse(self.inference_env["hf_cache_semantics"]["network_fallback_permitted"])
        self.assertFalse(self.snapshot["offline_resolution"]["network_fallback_used"])
        self.assertFalse(self.live["governance_state"]["network_fallback_used"])

    # --- SIF integrity ---

    def test_expected_container_sha_equals_immutable_selection(self) -> None:
        integrity = self.inference_env["container"]["integrity"]
        self.assertEqual(integrity["expected_immutable_sha256"], CONTAINER_SHA)
        self.assertEqual(integrity["expected_immutable_sha256"], _EXPECTED["container_sha256"])

    def test_sidecar_sha_equals_expected_sha(self) -> None:
        integrity = self.inference_env["container"]["integrity"]
        self.assertEqual(integrity["observed_sidecar_sha256"], CONTAINER_SHA)
        self.assertTrue(integrity["sidecar_sha256_match"])

    def test_container_size_equals_observed(self) -> None:
        self.assertEqual(self.inference_env["container"]["size_bytes"]["value"], CONTAINER_SIZE)
        self.assertEqual(
            self.inference_evidence["container_integrity"]["exact_size_bytes"],
            CONTAINER_SIZE,
        )

    def test_live_sha256_recomputed_during_b2_is_false(self) -> None:
        integrity = self.inference_env["container"]["integrity"]
        self.assertFalse(integrity["live_sha256_recomputed_during_b2"])

    def test_live_sha256_status_is_deferred(self) -> None:
        integrity = self.inference_env["container"]["integrity"]
        self.assertEqual(integrity["live_sha256_status"], "deferred")
        self.assertEqual(self.live["status_summary"]["fresh_sif_live_hash"], "deferred")

    def test_evidence_does_not_claim_fresh_hash_pass(self) -> None:
        combined = json.dumps(
            {
                "inference_env": self.inference_env,
                "inference_evidence": self.inference_evidence,
                "live": self.live,
            }
        )
        self.assertNotIn('"live_hash_verified": true', combined)
        self.assertNotIn("live_hash_verified", combined)

    def test_future_live_hash_may_upgrade_without_changing_selection(self) -> None:
        caveat = self.inference_evidence["container_integrity"]["integrity_caveat"]
        self.assertIn("upgrade", caveat.lower())
        self.assertEqual(
            self.inference_env["container"]["sha256"]["value"],
            _EXPECTED["container_sha256"],
        )

    def test_container_execution_does_not_substitute_for_content_hash(self) -> None:
        integrity = self.inference_evidence["container_integrity"]
        self.assertTrue(integrity["container_execution_verified"])
        self.assertEqual(integrity["live_sha256_status"], "deferred")
        self.assertIn("does not", integrity["integrity_caveat"].lower())

    # --- hardware and scheduler ---

    def test_gpu_name_matches_configured_class(self) -> None:
        gpu_name = self.hardware["gpu"]["name"]["value"]
        pattern = self.execution_policy["allowed_gpu_classes"][0]["name_pattern"]
        self.assertIn(pattern.replace("NVIDIA ", ""), gpu_name)

    def test_vram_satisfies_minimum(self) -> None:
        minimum = self.execution_policy["allowed_gpu_classes"][0]["minimum_vram_mib"]
        observed = self.hardware["gpu"]["nvidia_smi_vram_mib"]["value"]
        self.assertGreaterEqual(observed, minimum)

    def test_compute_capability_satisfies_minimum(self) -> None:
        minimum = self.execution_policy["allowed_gpu_classes"][0]["minimum_compute_capability"]
        observed = self.hardware["gpu"]["compute_capability"]["value"]
        self.assertGreaterEqual(tuple(map(int, observed.split("."))), tuple(map(int, minimum.split("."))))

    def test_tensor_result_exact(self) -> None:
        probe = self.hardware["gpu_tensor_probe"]
        self.assertEqual(probe["input_tensor"], [1.0, 2.0, 3.0])
        self.assertEqual(probe["result_tensor"], [2.0, 4.0, 6.0])
        self.assertEqual(probe["status"], "PASS")

    def test_partition_is_biggpu(self) -> None:
        self.assertEqual(self.hardware["scheduling_observation"]["partition"]["value"], "biggpu")
        self.assertEqual(self.execution_policy["required_partition"], "biggpu")

    def test_exclusive_node_policy_enabled(self) -> None:
        self.assertTrue(self.execution_policy["require_exclusive_node"])
        self.assertTrue(
            self.hardware["scheduling_observation"]["exclusive_node_required"]["value"]
        )

    def test_measured_gres_state_is_null_not_configured(self) -> None:
        scheduling = self.hardware["scheduling_observation"]
        self.assertIsNone(scheduling["slurm_gres_types"])
        self.assertEqual(
            scheduling["gpu_gres_mode"]["value"],
            "not_configured_at_measurement_time",
        )

    def test_probe_node_not_permanent_allowlist_requirement(self) -> None:
        probe = self.hardware["gpu_tensor_probe"]
        self.assertFalse(probe["probe_node_is_permanent_requirement"])
        self.assertEqual(self.execution_policy["node_allowlist"], [])

    def test_node_states_labelled_dynamic(self) -> None:
        states = self.hardware["scheduling_observation"]["observed_node_states_at_measurement"]
        self.assertTrue(states["dynamic"])
        self.assertTrue(self.live["scheduler_summary"]["node_states_dynamic"])

    def test_qos_evidence_partial(self) -> None:
        self.assertEqual(
            self.hardware["scheduling_observation"]["qos_evidence_status"],
            "partial",
        )
        self.assertFalse(
            self.hardware["scheduling_observation"]["permanent_job_limit_claim"]
        )

    # --- snapshot ---

    def test_exact_model_repository(self) -> None:
        self.assertEqual(self.snapshot["model_repository"]["value"], "Qwen/Qwen3-8B")

    def test_exact_immutable_revision(self) -> None:
        self.assertEqual(self.snapshot["model_revision"]["value"], MODEL_REVISION)

    def test_fifteen_resolved_files(self) -> None:
        self.assertEqual(self.snapshot["repository_metadata"]["repository_files"], 15)

    def test_resolved_bytes_exact(self) -> None:
        self.assertEqual(self.snapshot["repository_metadata"]["total_size_bytes"], SNAPSHOT_BYTES)

    def test_five_safetensors_shards(self) -> None:
        self.assertEqual(self.snapshot["repository_metadata"]["weight_shards"], 5)

    def test_zero_broken_symlinks(self) -> None:
        self.assertEqual(self.snapshot["repository_metadata"]["broken_symlinks"], 0)

    def test_model_type_qwen3(self) -> None:
        self.assertEqual(
            self.snapshot["configuration_inspection"]["model_type"],
            "qwen3",
        )

    def test_architecture_qwen3_for_causal_lm(self) -> None:
        self.assertIn(
            "Qwen3ForCausalLM",
            self.snapshot["configuration_inspection"]["architectures"],
        )

    def test_tokenizer_class_and_vocabulary_recorded(self) -> None:
        tokenizer = self.snapshot["tokenizer_inspection"]
        self.assertEqual(tokenizer["tokenizer_class"], "Qwen2Tokenizer")
        self.assertEqual(tokenizer["vocabulary_size"], 151669)

    def test_model_weights_not_loaded_during_b2r(self) -> None:
        probe_c = self.snapshot["offline_resolution"]["probes"]["probe_c"]
        self.assertFalse(probe_c["model_weights_loaded"])
        self.assertFalse(self.live["governance_state"]["model_weights_loaded"])

    def test_direct_snapshot_config_tokenizer_probe_passed(self) -> None:
        verification = self.snapshot["snapshot_verification"]
        self.assertTrue(verification["direct_snapshot_config_tokenizer_probe_passed"])
        self.assertEqual(self.snapshot["offline_resolution"]["probes"]["probe_c"]["status"], "PASS")

    # --- licence and governance ---

    def test_selected_model_remains_null(self) -> None:
        self.assertIsNone(self.licence_register["selected_model"])

    def test_qwen3_candidate_exists_provisional(self) -> None:
        entry = next(
            e for e in self.licence_register["entries"] if e["entry_id"] == "t12-cand-qwen3-8b"
        )
        self.assertEqual(entry["immutable_revision_sha"], MODEL_REVISION)
        self.assertEqual(
            entry["candidate_status"],
            "provisionally_selected_for_cluster_validation",
        )

    def test_t11_remains_blocked_in_evidence(self) -> None:
        self.assertEqual(self.live["governance_state"]["t11_status"], "BLOCKED")
        self.assertEqual(self.live["status_summary"]["t11"], "BLOCKED")
        self.assertIn("BLOCKED", self.report)

    def test_cross_references_present(self) -> None:
        refs = self.live["cross_references"]
        for key in (
            "immutable_selection",
            "execution_policy",
            "hardware_manifest",
            "inference_environment",
            "checkpoint_snapshot",
            "adr",
            "deviation_record",
        ):
            self.assertIn(key, refs)
            self.assertTrue((ROOT / refs[key]).is_file(), msg=refs[key])

    def test_report_exists_with_required_sections(self) -> None:
        for heading in (
            "## 1. Purpose",
            "## 11. Corrected root cause",
            "## 15. SIF hash caveat",
            "## 20. Clear non-claims",
        ):
            self.assertIn(heading, self.report)

    # --- path sanitisation ---

    def test_no_forbidden_paths_in_active_evidence(self) -> None:
        for relpath in _all_b3_relpaths():
            if relpath.endswith(".md"):
                text = (ROOT / relpath).read_text(encoding="utf-8")
                for pattern in FORBIDDEN_PATTERNS:
                    self.assertIsNone(
                        re.search(pattern, text, re.IGNORECASE),
                        msg=f"{relpath} matched forbidden pattern {pattern}",
                    )
                continue
            data = _load(relpath)
            errors = scan_forbidden_paths(data)
            self.assertEqual(errors, [], msg=f"{relpath}: " + "\n".join(errors))

    def test_no_ml_libraries_imported_by_validation_modules(self) -> None:
        forbidden = ("torch", "transformers", "vllm", "huggingface_hub", "bitsandbytes")
        for module_name in (
            "ambiguity_manager.model.cluster.manifest_schemas",
            "ambiguity_manager.model.cluster.path_policy",
        ):
            spec = importlib.util.find_spec(module_name)
            self.assertIsNotNone(spec)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            for name in forbidden:
                self.assertNotIn(name, module.__dict__)


if __name__ == "__main__":
    unittest.main()
