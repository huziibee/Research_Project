"""Tests for T12 Slice 3C checkpoint load validation and HF backend."""

from __future__ import annotations

import ast
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ambiguity_manager.governance.ethics import derive_ticket_verdict
from ambiguity_manager.governance.hashing import sha256_hex
from ambiguity_manager.governance.model_licence import MANDATORY_CONTEXT_LIMIT
from ambiguity_manager.model.candidate_evidence import REGISTER_REL
from ambiguity_manager.model.checkpoint_download import (
    AUTHORIZED_REVISION_SHA,
    AUTHORIZED_TOKENIZER_REVISION_SHA,
    EVIDENCE_REL as DOWNLOAD_EVIDENCE_REL,
)
from ambiguity_manager.model.checkpoint_load import (
    BACKEND_ID,
    LOAD_EVIDENCE_REL,
    MIN_AVAILABLE_RAM_MIB,
    MIN_FREE_VRAM_MIB,
    NF4_QUANT_TYPE,
    OBSERVED_LOADED_QUANTIZED_STORAGE_NUMEL,
    OFFICIAL_ARCHITECTURAL_PARAMETER_COUNT,
    VERIFIED_LOAD_FILES,
    build_architectural_parameter_evidence,
    build_cleanup_evidence,
    build_in_process_cleanup_evidence,
    build_load_evidence_scaffold,
    build_process_exit_reclaim_evidence,
    build_quantisation_config,
    build_runtime_spec,
    compute_overall_status,
    derive_config_formula_parameter_count,
    migrate_identity_evidence,
    validate_checkpoint_load_evidence,
    validate_commit_sha,
    validate_download_evidence_for_load,
    validate_identity_evidence,
    validate_offline_flags,
    validate_pre_load_gates,
    validate_register_for_load,
    validate_resource_gates,
    validate_runtime_immutable,
    validate_wsl_cache_policy,
)
from ambiguity_manager.model.context_budget import DEFAULT_SAFETY_MARGIN
from ambiguity_manager.model.environment import (
    INFERENCE_ENV_REL,
    TRAINING_ENV_REL,
    validate_environment_manifest,
)
from ambiguity_manager.model.errors import ModelBackendUnavailableError, ModelClientError
from ambiguity_manager.model.factory import create_model_client
from ambiguity_manager.model.hf_load_helpers import sleeping_worker
from ambiguity_manager.model.parser import extract_and_repair_json
from ambiguity_manager.model.protocol import GenerateJsonRequest, ModelRuntimeSpec
from ambiguity_manager.model.worker_process import run_worker_with_timeout
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema.v2.json_schema import build_prediction_json_schema

ROOT = ProjectPaths.from_repo_root().root
DOWNLOAD_EVIDENCE_PATH = ROOT / DOWNLOAD_EVIDENCE_REL
LOAD_EVIDENCE_PATH = ROOT / LOAD_EVIDENCE_REL
REGISTER_PATH = ROOT / REGISTER_REL
INFERENCE_MANIFEST_PATH = ROOT / INFERENCE_ENV_REL
TRAINING_MANIFEST_PATH = ROOT / TRAINING_ENV_REL
ETHICS_PATH = ROOT / "configs" / "governance" / "human_annotation_governance.json"
SCRIPT_PATH = ROOT / "scripts" / "t12_probe_checkpoint_load.py"
HF_BACKEND_PATH = ROOT / "src" / "ambiguity_manager" / "model" / "backends" / "hf_transformers.py"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _runtime_spec(**overrides: object) -> ModelRuntimeSpec:
    base = {
        "backend": BACKEND_ID,
        "model_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "immutable_revision": AUTHORIZED_REVISION_SHA,
        "tokenizer_revision": AUTHORIZED_TOKENIZER_REVISION_SHA,
        "quantisation": "nf4_4bit",
        "environment_id": "t12-inference-wsl2",
        "device_policy": "cuda:0",
    }
    base.update(overrides)
    return ModelRuntimeSpec(**base)


class CheckpointLoadEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.download_evidence = _load_json(DOWNLOAD_EVIDENCE_PATH)
        cls.load_evidence = _load_json(LOAD_EVIDENCE_PATH)
        cls.register = _load_json(REGISTER_PATH)
        cls.inference_manifest = _load_json(INFERENCE_MANIFEST_PATH)
        cls.training_manifest = _load_json(TRAINING_MANIFEST_PATH)

    def test_download_evidence_verification_complete(self) -> None:
        self.assertEqual(self.download_evidence["overall_status"], "verification_complete")

    def test_all_nine_hashes_present(self) -> None:
        hashed = {
            item["relpath"]
            for item in self.download_evidence["files"]
            if item.get("sha256")
        }
        self.assertEqual(hashed, set(VERIFIED_LOAD_FILES))

    def test_exact_model_sha_required(self) -> None:
        self.assertEqual(
            self.download_evidence["immutable_revision_sha"],
            AUTHORIZED_REVISION_SHA,
        )
        errors = validate_commit_sha("main", field="immutable_revision_sha")
        self.assertTrue(errors)

    def test_exact_tokenizer_sha_required(self) -> None:
        self.assertEqual(
            self.download_evidence["tokenizer_revision_sha"],
            AUTHORIZED_TOKENIZER_REVISION_SHA,
        )

    def test_aliases_rejected(self) -> None:
        errors = validate_commit_sha("v1.0.0", field="immutable_revision_sha")
        self.assertTrue(errors)

    def test_selected_model_null(self) -> None:
        self.assertIsNone(self.download_evidence["selected_model"])
        self.assertIsNone(self.register["selected_model"])
        self.assertIsNone(self.load_evidence["selected_model"])

    def test_candidate_remains_candidate_evaluated(self) -> None:
        entry = next(e for e in self.register["entries"] if e["entry_id"] == "t12-cand-001")
        self.assertEqual(entry["verification_status"], "candidate_evaluated")

    def test_environment_manifests_checkpoint_load_verified_after_slice3c(self) -> None:
        self.assertTrue(self.inference_manifest["checkpoint_load_verified"])
        self.assertTrue(self.training_manifest["checkpoint_load_verified"])

    def test_architectural_and_quantised_counts_are_distinct(self) -> None:
        for key in ("inference_environment_load", "training_environment_load"):
            identity = self.load_evidence[key]["identity_evidence"]
            self.assertEqual(identity["architectural_parameter_count"], OFFICIAL_ARCHITECTURAL_PARAMETER_COUNT)
            self.assertEqual(
                identity["loaded_quantized_storage_numel"],
                OBSERVED_LOADED_QUANTIZED_STORAGE_NUMEL,
            )
            self.assertNotEqual(
                identity["architectural_parameter_count"],
                identity["loaded_quantized_storage_numel"],
            )

    def test_packed_count_cannot_be_labeled_architectural(self) -> None:
        bad = {
            "architectural_parameter_count": OBSERVED_LOADED_QUANTIZED_STORAGE_NUMEL,
            "loaded_quantized_storage_numel": OBSERVED_LOADED_QUANTIZED_STORAGE_NUMEL,
            "architectural_parameter_count_source": "bad",
            "loaded_quantized_storage_numel_source": "bad",
        }
        errors = validate_identity_evidence(bad)
        self.assertTrue(any("must not equal" in e or "must not use" in e for e in errors))

    def test_deprecated_parameter_count_rejected(self) -> None:
        bad = {
            "parameter_count": OBSERVED_LOADED_QUANTIZED_STORAGE_NUMEL,
            "architectural_parameter_count": OFFICIAL_ARCHITECTURAL_PARAMETER_COUNT,
            "loaded_quantized_storage_numel": OBSERVED_LOADED_QUANTIZED_STORAGE_NUMEL,
            "architectural_parameter_count_source": "x",
            "loaded_quantized_storage_numel_source": "y",
        }
        errors = validate_identity_evidence(bad)
        self.assertTrue(any("deprecated field parameter_count" in e for e in errors))

    def test_config_formula_differs_from_packed_numel(self) -> None:
        config = {
            "hidden_size": 1536,
            "num_hidden_layers": 28,
            "intermediate_size": 8960,
            "vocab_size": 151936,
            "num_attention_heads": 12,
            "num_key_value_heads": 2,
        }
        formula = derive_config_formula_parameter_count(config)
        self.assertIsNotNone(formula)
        assert formula is not None
        self.assertNotEqual(formula, OBSERVED_LOADED_QUANTIZED_STORAGE_NUMEL)

    def test_cleanup_distinguishes_in_process_from_process_exit(self) -> None:
        cleanup = self.load_evidence["inference_environment_load"]["cleanup_result"]
        self.assertIn("in_process_post_cleanup_free_vram_mib", cleanup)
        self.assertIn("process_exit_reclaim", cleanup)
        self.assertFalse(cleanup.get("vram_fully_restored_in_process"))
        exit_reclaim = cleanup["process_exit_reclaim"]
        self.assertTrue(exit_reclaim.get("worker_process_exit_completed"))

    def test_cleanup_does_not_claim_full_in_process_vram_restore(self) -> None:
        in_process = build_in_process_cleanup_evidence(
            references_released=True,
            gc_collect_completed=True,
            cuda_empty_cache_completed=True,
            in_process_post_cleanup_free_vram_mib=5963.0,
            baseline_free_vram_mib=7131.0,
        )
        self.assertFalse(in_process["vram_fully_restored_in_process"])

    def test_successful_cleanup_requires_worker_exit(self) -> None:
        cleanup = build_cleanup_evidence(
            in_process=build_in_process_cleanup_evidence(
                references_released=True,
                gc_collect_completed=True,
                cuda_empty_cache_completed=True,
                in_process_post_cleanup_free_vram_mib=5963.0,
                baseline_free_vram_mib=7131.0,
            ),
            process_exit=build_process_exit_reclaim_evidence(
                worker_process_exit_completed=True,
                post_process_exit_free_vram_mib=7100.0,
                baseline_free_vram_mib=7131.0,
                lingering_probe_processes_detected=False,
            ),
        )
        self.assertTrue(cleanup["process_exit_reclaim"]["worker_process_exit_completed"])

    def test_migrate_identity_removes_parameter_count(self) -> None:
        old = {"parameter_count": OBSERVED_LOADED_QUANTIZED_STORAGE_NUMEL}
        migrated = migrate_identity_evidence(old, config=None)
        self.assertNotIn("parameter_count", migrated)
        self.assertEqual(migrated["loaded_quantized_storage_numel"], OBSERVED_LOADED_QUANTIZED_STORAGE_NUMEL)

    def test_nf4_frozen_in_quant_config(self) -> None:
        quant = build_quantisation_config(bf16_supported=True)
        self.assertTrue(quant.load_in_4bit)
        self.assertEqual(quant.bnb_4bit_quant_type, NF4_QUANT_TYPE)
        self.assertTrue(quant.bnb_4bit_use_double_quant)

    def test_bf16_fp16_selection_recorded(self) -> None:
        bf16 = build_quantisation_config(bf16_supported=True)
        self.assertEqual(bf16.bnb_4bit_compute_dtype, "bfloat16")
        self.assertIsNone(bf16.compute_dtype_fallback)
        fp16 = build_quantisation_config(bf16_supported=False)
        self.assertEqual(fp16.bnb_4bit_compute_dtype, "float16")
        self.assertEqual(fp16.compute_dtype_fallback, "float16")

    def test_context_limit_and_safety_margin(self) -> None:
        scaffold = build_load_evidence_scaffold()
        self.assertEqual(scaffold["context_limit"], MANDATORY_CONTEXT_LIMIT)
        self.assertEqual(scaffold["safety_margin_tokens"], DEFAULT_SAFETY_MARGIN)

    def test_no_adapter_or_optimiser_evidence(self) -> None:
        self.assertTrue(self.load_evidence["no_adapter_attached"])
        self.assertTrue(self.load_evidence["no_optimiser_step"])

    def test_tracked_evidence_rejects_username_and_absolute_paths(self) -> None:
        bad = build_load_evidence_scaffold()
        bad["note"] = "/home/huzii/secret"
        errors = validate_checkpoint_load_evidence(bad)
        self.assertTrue(any("absolute path" in e or "username" in e for e in errors))

    def test_checkpoint_load_verified_cannot_be_true_without_passed_evidence(self) -> None:
        bad_manifest = dict(self.inference_manifest)
        bad_manifest["checkpoint_load_verified"] = True
        bad_manifest["candidate_entry_id"] = "t12-cand-001"
        bad_manifest["immutable_revision_sha"] = AUTHORIZED_REVISION_SHA
        bad_manifest["tokenizer_revision_sha"] = AUTHORIZED_TOKENIZER_REVISION_SHA
        bad_manifest["four_bit_load_status"] = "passed"
        bad_manifest["checkpoint_load_evidence_relpath"] = LOAD_EVIDENCE_REL
        pending_evidence = build_load_evidence_scaffold()
        errors = validate_checkpoint_load_evidence(
            pending_evidence,
            inference_manifest=bad_manifest,
        )
        self.assertTrue(
            any("checkpoint_load_verified cannot be true" in e for e in errors)
        )

    def test_overall_pass_requires_both_loads_and_smoke(self) -> None:
        evidence = build_load_evidence_scaffold()
        evidence["inference_environment_load"]["status"] = "passed"
        evidence["inference_environment_load"]["identity_evidence"] = {
            "immutable_revision_sha": AUTHORIZED_REVISION_SHA,
            "tokenizer_revision_sha": AUTHORIZED_TOKENIZER_REVISION_SHA,
            **build_architectural_parameter_evidence(),
            "loaded_quantized_storage_numel": OBSERVED_LOADED_QUANTIZED_STORAGE_NUMEL,
            "loaded_quantized_storage_numel_source": "test",
        }
        evidence["inference_environment_load"]["cleanup_result"] = build_cleanup_evidence(
            in_process=build_in_process_cleanup_evidence(
                references_released=True,
                gc_collect_completed=True,
                cuda_empty_cache_completed=True,
                in_process_post_cleanup_free_vram_mib=5963.0,
                baseline_free_vram_mib=7131.0,
            ),
            process_exit=build_process_exit_reclaim_evidence(
                worker_process_exit_completed=True,
                post_process_exit_free_vram_mib=7120.0,
                baseline_free_vram_mib=7131.0,
                lingering_probe_processes_detected=False,
            ),
        )
        evidence["training_environment_load"]["identity_evidence"] = {
            "immutable_revision_sha": AUTHORIZED_REVISION_SHA,
            "tokenizer_revision_sha": AUTHORIZED_TOKENIZER_REVISION_SHA,
            **build_architectural_parameter_evidence(),
            "loaded_quantized_storage_numel": OBSERVED_LOADED_QUANTIZED_STORAGE_NUMEL,
            "loaded_quantized_storage_numel_source": "test",
        }
        evidence["training_environment_load"]["cleanup_result"] = build_cleanup_evidence(
            in_process=build_in_process_cleanup_evidence(
                references_released=True,
                gc_collect_completed=True,
                cuda_empty_cache_completed=True,
                in_process_post_cleanup_free_vram_mib=5963.0,
                baseline_free_vram_mib=7131.0,
            ),
            process_exit=build_process_exit_reclaim_evidence(
                worker_process_exit_completed=True,
                post_process_exit_free_vram_mib=7120.0,
                baseline_free_vram_mib=7131.0,
                lingering_probe_processes_detected=False,
            ),
        )
        evidence["training_environment_load"]["status"] = "passed"
        evidence["inference_environment_load"]["resource_evidence_before"] = {}
        evidence["inference_environment_load"]["resource_evidence_after"] = {}
        evidence["inference_environment_load"]["load_duration_s"] = 1.0
        evidence["training_environment_load"]["resource_evidence_before"] = {}
        evidence["training_environment_load"]["resource_evidence_after"] = {}
        evidence["training_environment_load"]["load_duration_s"] = 1.0
        evidence["training_environment_load"]["peft_architecture_compatible"] = True
        evidence["smoke_generation"]["status"] = "passed"
        self.assertEqual(compute_overall_status(evidence), "PASS")

    def test_pass_evidence_validates_with_verified_manifests(self) -> None:
        errors = validate_checkpoint_load_evidence(
            self.load_evidence,
            download_evidence=self.download_evidence,
            register=self.register,
            inference_manifest=self.inference_manifest,
            training_manifest=self.training_manifest,
        )
        self.assertEqual(errors, [], msg="\n".join(errors))
        self.assertEqual(self.load_evidence["overall_status"], "PASS")


class OfflinePolicyTests(unittest.TestCase):
    def test_offline_flags_required(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            errors = validate_offline_flags(local_files_only=True, trust_remote_code=False)
            self.assertTrue(any("HF_HUB_OFFLINE" in e for e in errors))

    def test_local_files_only_required(self) -> None:
        with mock.patch.dict(os.environ, {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}):
            errors = validate_offline_flags(local_files_only=False, trust_remote_code=False)
            self.assertIn("local_files_only must be true", errors)

    def test_trust_remote_code_false_required(self) -> None:
        with mock.patch.dict(os.environ, {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}):
            errors = validate_offline_flags(local_files_only=True, trust_remote_code=True)
            self.assertIn("trust_remote_code must be false", errors)


class PreLoadGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.download_evidence = _load_json(DOWNLOAD_EVIDENCE_PATH)
        cls.register = _load_json(REGISTER_PATH)

    def test_resource_gates(self) -> None:
        errors = validate_resource_gates({"available_ram_mib": 1000, "gpu_free_vram_mib": 1000})
        self.assertTrue(any(str(MIN_AVAILABLE_RAM_MIB) in e for e in errors))
        self.assertTrue(any(str(MIN_FREE_VRAM_MIB) in e for e in errors))

    def test_verified_download_evidence_required(self) -> None:
        bad = dict(self.download_evidence)
        bad["overall_status"] = "pending"
        errors = validate_download_evidence_for_load(bad)
        self.assertTrue(errors)


class RuntimeBindingTests(unittest.TestCase):
    def test_runtime_cannot_use_wrong_backend(self) -> None:
        spec = _runtime_spec(backend="fake")
        with self.assertRaises(ModelClientError):
            validate_runtime_immutable(spec)

    def test_runtime_rejects_revision_mismatch(self) -> None:
        spec = _runtime_spec(immutable_revision="b" * 40)
        with self.assertRaises(ModelClientError):
            validate_runtime_immutable(spec)

    def test_runtime_spec_from_builder(self) -> None:
        spec = build_runtime_spec(environment_id="t12-inference-wsl2")
        self.assertEqual(spec.backend, BACKEND_ID)
        self.assertEqual(spec.immutable_revision, AUTHORIZED_REVISION_SHA)


class WorkerTimeoutTests(unittest.TestCase):
    def test_sleeping_worker_terminated_on_timeout(self) -> None:
        result = run_worker_with_timeout(sleeping_worker, args=({},), timeout_s=0.5)
        self.assertEqual(result.status, "timeout")


class ParserRetentionTests(unittest.TestCase):
    def test_raw_output_retained_on_parser_failure(self) -> None:
        raw = "this is not json at all"
        parsed = extract_and_repair_json(raw)
        self.assertEqual(parsed.raw_output, raw)
        self.assertIsNone(parsed.parsed_object)

    def test_schema_invalid_represented_honestly(self) -> None:
        raw = '{"schema_version":"2.0.0","record_class":"prediction"}'
        parsed = extract_and_repair_json(raw)
        self.assertIsNotNone(parsed.parsed_object)


class HfBackendUnitTests(unittest.TestCase):
    def test_hf_backend_unavailable_without_torch(self) -> None:
        import builtins

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object):  # noqa: ANN001
            if name == "torch":
                raise ImportError("no torch")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(ModelBackendUnavailableError):
                create_model_client(_runtime_spec())

    def test_request_has_no_runtime_fields(self) -> None:
        fields = {f.name for f in GenerateJsonRequest.__dataclass_fields__.values()}
        forbidden = {
            "backend",
            "model_id",
            "immutable_revision",
            "tokenizer_revision",
            "quantisation",
            "environment_id",
            "device_policy",
        }
        self.assertFalse(forbidden & fields)

    @mock.patch("ambiguity_manager.model.backends.hf_transformers.run_worker_with_timeout")
    def test_non_empty_smoke_output_required(self, mock_worker: mock.Mock) -> None:
        from ambiguity_manager.model.backends.hf_transformers import HfTransformersBackend
        from ambiguity_manager.model.worker_process import WorkerResult

        mock_worker.return_value = WorkerResult(
            status="success",
            payload={"raw_output": "generated text", "prompt_tokens": 10, "completion_tokens": 5},
        )
        backend = HfTransformersBackend(_runtime_spec())
        request = GenerateJsonRequest(
            messages=[{"role": "user", "content": "test"}],
            json_schema=build_prediction_json_schema(),
            temperature=0.0,
        )
        result = backend.generate_json(request)
        self.assertTrue(result.raw_output)
        self.assertEqual(result.final_status, "parse_failed")

    @mock.patch("ambiguity_manager.model.backends.hf_transformers.run_worker_with_timeout")
    def test_timeout_returns_explicit_backend_result(self, mock_worker: mock.Mock) -> None:
        from ambiguity_manager.model.backends.hf_transformers import HfTransformersBackend
        from ambiguity_manager.model.worker_process import WorkerResult

        mock_worker.return_value = WorkerResult(status="timeout")
        backend = HfTransformersBackend(_runtime_spec())
        request = GenerateJsonRequest(
            messages=[{"role": "user", "content": "test"}],
            json_schema=build_prediction_json_schema(),
            temperature=0.0,
            timeout_s=1.0,
        )
        result = backend.generate_json(request)
        self.assertEqual(result.final_status, "timeout")


class GovernanceIsolationTests(unittest.TestCase):
    def test_t11_remains_blocked(self) -> None:
        ethics = _load_json(ETHICS_PATH)
        self.assertEqual(derive_ticket_verdict(ethics), "BLOCKED")

    def test_import_ambiguity_manager_without_ml(self) -> None:
        for name in (
            "torch",
            "transformers",
            "peft",
            "trl",
            "accelerate",
            "bitsandbytes",
            "datasets",
        ):
            sys.modules.pop(name, None)
        import ambiguity_manager

        importlib.reload(ambiguity_manager)
        loaded = {
            k
            for k in sys.modules
            if k.startswith(("torch", "transformers", "peft", "trl", "bitsandbytes", "datasets"))
        }
        self.assertEqual(loaded, set())


class EnvironmentSlice3Tests(unittest.TestCase):
    def test_slice3_manifest_allows_checkpoint_load_verified_with_fields(self) -> None:
        manifest = _load_json(INFERENCE_MANIFEST_PATH)
        manifest["checkpoint_load_verified"] = True
        manifest["candidate_entry_id"] = "t12-cand-001"
        manifest["immutable_revision_sha"] = AUTHORIZED_REVISION_SHA
        manifest["tokenizer_revision_sha"] = AUTHORIZED_TOKENIZER_REVISION_SHA
        manifest["four_bit_load_status"] = "passed"
        manifest["checkpoint_load_evidence_relpath"] = LOAD_EVIDENCE_REL
        errors = validate_environment_manifest(manifest, slice_number=3)
        self.assertEqual(errors, [])


class ThirdPartyCheckpointRejectionTests(unittest.TestCase):
    def test_third_party_repository_rejected(self) -> None:
        from ambiguity_manager.model.checkpoint_download import validate_repository_id

        errors = validate_repository_id("TheBloke/Qwen-GPTQ")
        self.assertTrue(errors)


class ProbeScriptStaticTests(unittest.TestCase):
    def test_probe_script_has_no_from_pretrained_at_module_level(self) -> None:
        tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
        imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module
            and "transformers" in node.module
        ]
        self.assertEqual(imports, [])


class RegisterPreLoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.register = _load_json(REGISTER_PATH)

    def test_register_pre_load_validation(self) -> None:
        errors = validate_register_for_load(self.register)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
