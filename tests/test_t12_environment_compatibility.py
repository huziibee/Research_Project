"""Tests for T12 Slice 2 environment compatibility evidence and validation."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.governance.hashing import sha256_hex
from ambiguity_manager.model.environment import (
    INFERENCE_ENV_REL,
    TRAINING_ENV_REL,
    validate_environment_manifest,
)
from ambiguity_manager.model.environment_evidence import (
    EVIDENCE_REL,
    INFERENCE_LOCK_REL,
    INFERENCE_REQ_REL,
    TRAINING_LOCK_REL,
    TRAINING_REQ_REL,
    parse_probe_result,
    validate_environment_evidence,
)
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root


def _file_sha256(relpath: str) -> str:
    return sha256_hex((ROOT / relpath).read_bytes())


def _minimal_probe(
    environment_id: str,
    *,
    role: str = "inference",
    bitsandbytes_status: str = "cuda_operation_verified",
) -> dict:
    base = {
        "probe_schema_version": "1.0.0",
        "environment_id": environment_id,
        "role": role,
        "python_implementation": "CPython",
        "python_version": "3.11.11",
        "os_name": "Linux",
        "os_architecture": "x86_64",
        "uv_version": "0.11.19",
        "torch_version": "2.7.0",
        "torch_cuda_build": "cu118",
        "torch_cuda_is_available": True,
        "cuda_device_count": 1,
        "gpu_name": "NVIDIA GeForce RTX 3070 Laptop GPU",
        "compute_capability": "8.6",
        "vram_total_mib": 8192,
        "vram_free_mib": 7900,
        "bf16_supported": True,
        "transformers_version": "5.13.0",
        "tokenizers_version": "0.22.2",
        "safetensors_version": "0.8.0",
        "accelerate_version": "1.14.0",
        "bitsandbytes_version": "0.49.2",
        "bitsandbytes_status": bitsandbytes_status,
        "cuda_computation": {
            "status": "passed",
            "max_abs_diff": 0.0,
            "tolerance": 1e-4,
            "peak_allocated_mib": 8,
            "peak_reserved_mib": 20,
        },
        "imports": {
            "torch": {"status": "ok"},
            "transformers": {"status": "ok"},
            "tokenizers": {"status": "ok"},
            "safetensors": {"status": "ok"},
            "accelerate": {"status": "ok"},
            "bitsandbytes": {"status": "ok"},
        },
        "no_model_download": True,
        "no_absolute_paths": True,
        "import_failures": [],
    }
    if role == "training":
        base.update(
            {
                "peft_version": "0.19.1",
                "trl_version": "1.8.0",
                "datasets_version": "5.0.0",
                "imports": {
                    **base["imports"],
                    "peft": {"status": "ok"},
                    "trl": {"status": "ok"},
                    "datasets": {"status": "ok"},
                },
            }
        )
    return base


def _verified_env_block(environment_id: str, role: str) -> dict:
    lock_rel = INFERENCE_LOCK_REL if role == "inference" else TRAINING_LOCK_REL
    req_rel = INFERENCE_REQ_REL if role == "inference" else TRAINING_REQ_REL
    probe = _minimal_probe(environment_id, role=role)
    packages = {
        "pytorch_version": probe["torch_version"],
        "transformers_version": probe["transformers_version"],
        "tokenizers_version": probe["tokenizers_version"],
        "accelerate_version": probe["accelerate_version"],
        "safetensors_version": probe["safetensors_version"],
        "bitsandbytes_version": probe["bitsandbytes_version"],
        "peft_version": probe.get("peft_version"),
        "trl_version": probe.get("trl_version"),
        "datasets_version": probe.get("datasets_version"),
    }
    return {
        "environment_id": environment_id,
        "role": role,
        "overall_status": "verified_compatible",
        "lockfile_relpath": lock_rel,
        "lockfile_sha256": _file_sha256(lock_rel),
        "requirements_input_relpath": req_rel,
        "requirements_input_sha256": _file_sha256(req_rel),
        "cuda_compatibility": "passed",
        "gpu_computation": "passed",
        "bf16_supported": True,
        "bitsandbytes_status": probe["bitsandbytes_status"],
        "checkpoint_load_verified": False,
        "packages": packages,
        "imports": probe["imports"],
        "probe": probe,
    }


class T12EnvironmentCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inference_manifest = json.loads((ROOT / INFERENCE_ENV_REL).read_text(encoding="utf-8"))
        cls.training_manifest = json.loads((ROOT / TRAINING_ENV_REL).read_text(encoding="utf-8"))
        cls.evidence = json.loads((ROOT / EVIDENCE_REL).read_text(encoding="utf-8"))

    def test_platform_specific_environment_identifiers(self) -> None:
        self.assertEqual(self.inference_manifest["environment_id"], "t12-inference-wsl2")
        self.assertEqual(self.training_manifest["environment_id"], "t12-training-wsl2")

    def test_wsl_lockfile_paths_exist(self) -> None:
        self.assertTrue((ROOT / INFERENCE_LOCK_REL).is_file())
        self.assertTrue((ROOT / TRAINING_LOCK_REL).is_file())

    def test_windows_lockfiles_absent(self) -> None:
        locks = ROOT / "requirements" / "locks"
        for name in locks.glob("*.lock"):
            self.assertIn("wsl2", name.name)
            self.assertNotIn("windows", name.name.lower())

    def test_requirement_inputs_exist(self) -> None:
        self.assertTrue((ROOT / INFERENCE_REQ_REL).is_file())
        self.assertTrue((ROOT / TRAINING_REQ_REL).is_file())

    def test_verified_compatible_requires_lockfile_hash(self) -> None:
        bad = dict(self.inference_manifest)
        bad["environment_status"] = "verified_compatible"
        bad["lockfile_relpath"] = INFERENCE_LOCK_REL
        bad["lockfile_sha256"] = None
        errors = validate_environment_manifest(bad, slice_number=2)
        self.assertTrue(any("lockfile_sha256" in e for e in errors))

    def test_verified_compatible_requires_cuda_computation(self) -> None:
        env = dict(self.evidence["environments"]["t12-inference-wsl2"])
        env["overall_status"] = "verified_compatible"
        env["gpu_computation"] = "failed"
        env["bitsandbytes_status"] = "cuda_operation_verified"
        bad = dict(self.evidence)
        bad["environments"] = dict(self.evidence["environments"])
        bad["environments"]["t12-inference-wsl2"] = env
        errors = validate_environment_evidence(bad, repo_root=ROOT)
        self.assertTrue(any("gpu_computation" in e for e in errors))

    def test_verified_compatible_requires_mandatory_imports(self) -> None:
        env = dict(self.evidence["environments"]["t12-inference-wsl2"])
        env["overall_status"] = "verified_compatible"
        env["bitsandbytes_status"] = "cuda_operation_verified"
        imports = dict(env["imports"])
        imports["torch"] = {"status": "failed", "error": "missing"}
        env["imports"] = imports
        bad = dict(self.evidence)
        bad["environments"] = dict(self.evidence["environments"])
        bad["environments"]["t12-inference-wsl2"] = env
        errors = validate_environment_evidence(bad, repo_root=ROOT)
        self.assertTrue(any("imports" in e for e in errors))

    def test_checkpoint_load_verified_remains_false_slice2(self) -> None:
        self.assertFalse(self.inference_manifest["checkpoint_load_verified"])
        self.assertFalse(self.training_manifest["checkpoint_load_verified"])
        if self.evidence:
            for env_id in ("t12-inference-wsl2", "t12-training-wsl2"):
                self.assertFalse(self.evidence["environments"][env_id]["checkpoint_load_verified"])

    def test_no_model_identity_populated(self) -> None:
        for manifest in (self.inference_manifest, self.training_manifest):
            self.assertIsNone(manifest.get("model_id"))
            self.assertIsNone(manifest.get("model_revision"))

    def test_package_versions_not_claimed_before_probe(self) -> None:
        for env_id, manifest in (
            ("t12-inference-wsl2", self.inference_manifest),
            ("t12-training-wsl2", self.training_manifest),
        ):
            self.assertIsNotNone(manifest["packages"]["pytorch_version"])
            self.assertEqual(
                manifest["packages"]["pytorch_version"],
                self.evidence["environments"][env_id]["packages"]["pytorch_version"],
            )

    def test_probe_json_parsing(self) -> None:
        probe = _minimal_probe("t12-inference-wsl2")
        parsed = parse_probe_result(probe)
        self.assertEqual(parsed["environment_id"], "t12-inference-wsl2")
        self.assertEqual(parsed["cuda_computation"]["status"], "passed")

    def test_explicit_import_failure_representation(self) -> None:
        probe = _minimal_probe("t12-inference-wsl2")
        probe["imports"]["bitsandbytes"] = {"status": "failed", "error": "ImportError"}
        probe["import_failures"] = ["bitsandbytes"]
        parsed = parse_probe_result(probe)
        self.assertIn("bitsandbytes", parsed["import_failures"])

    def test_absolute_path_rejection(self) -> None:
        bad = json.loads(json.dumps(self.evidence))
        bad["notes"] = "/home/someone/.local/t12-environments"
        errors = validate_environment_evidence(bad, repo_root=ROOT)
        self.assertTrue(any("absolute" in e.lower() for e in errors))

    def test_username_rejection(self) -> None:
        bad = json.loads(json.dumps(self.evidence))
        bad["notes"] = "huzii environment"
        errors = validate_environment_evidence(bad, repo_root=ROOT)
        self.assertTrue(any("username" in e.lower() for e in errors))

    def test_lockfile_sha256_verification(self) -> None:
        errors = validate_environment_evidence(self.evidence, repo_root=ROOT)
        self.assertFalse(any("lockfile_sha256 mismatch" in e for e in errors))

    def test_requirement_input_sha256_verification(self) -> None:
        errors = validate_environment_evidence(self.evidence, repo_root=ROOT)
        self.assertFalse(any("requirements_input_sha256 mismatch" in e for e in errors))

    def test_evidence_contains_no_raw_model_outputs(self) -> None:
        text = (ROOT / EVIDENCE_REL).read_text(encoding="utf-8").lower()
        for forbidden in ("generated_text", "model_output", "from_pretrained"):
            self.assertNotIn(forbidden, text)

    def test_evidence_validation_when_present(self) -> None:
        errors = validate_environment_evidence(self.evidence, repo_root=ROOT)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_manifest_validation_slice2_when_verified(self) -> None:
        slice_number = 2
        for manifest in (self.inference_manifest, self.training_manifest):
            errors = validate_environment_manifest(manifest, slice_number=slice_number)
            self.assertEqual(errors, [], msg="\n".join(errors))

    def test_verified_compatible_requires_bitsandbytes_cuda_operation(self) -> None:
        bad = dict(self.inference_manifest)
        bad["environment_status"] = "verified_compatible"
        bad["bitsandbytes_compatibility"] = "import_only"
        errors = validate_environment_manifest(bad, slice_number=2)
        self.assertTrue(any("cuda_operation_verified" in e for e in errors))

    def test_import_only_insufficient_for_verified_compatible_evidence(self) -> None:
        env = dict(self.evidence["environments"]["t12-inference-wsl2"])
        env["overall_status"] = "verified_compatible"
        env["bitsandbytes_status"] = "import_only"
        bad = dict(self.evidence)
        bad["environments"] = dict(self.evidence["environments"])
        bad["environments"]["t12-inference-wsl2"] = env
        errors = validate_environment_evidence(bad, repo_root=ROOT)
        self.assertTrue(any("cuda_operation_verified" in e for e in errors))

    def test_failed_bitsandbytes_cannot_produce_verified_compatible(self) -> None:
        env = dict(self.evidence["environments"]["t12-inference-wsl2"])
        env["overall_status"] = "verified_compatible"
        env["bitsandbytes_status"] = "failed"
        bad = dict(self.evidence)
        bad["environments"] = dict(self.evidence["environments"])
        bad["environments"]["t12-inference-wsl2"] = env
        errors = validate_environment_evidence(bad, repo_root=ROOT)
        self.assertTrue(any("cuda_operation_verified" in e for e in errors))

    def test_os_compiler_dependencies_recorded_separately(self) -> None:
        os_deps = self.evidence["os_compiler_dependencies"]
        self.assertFalse(os_deps["tracked_in_python_lockfiles"])
        names = {pkg["name"] for pkg in os_deps["packages"]}
        self.assertEqual(names, {"build-essential", "gcc", "g++", "make"})
        self.assertEqual(os_deps["cc"], "/usr/bin/gcc")
        self.assertEqual(os_deps["cxx"], "/usr/bin/g++")
        lock_text = (ROOT / INFERENCE_LOCK_REL).read_text(encoding="utf-8").lower()
        self.assertNotIn("build-essential", lock_text)
        self.assertNotIn("gcc==", lock_text)

    def test_verified_compatible_bitsandbytes_status_in_evidence(self) -> None:
        for env_id in ("t12-inference-wsl2", "t12-training-wsl2"):
            env = self.evidence["environments"][env_id]
            self.assertEqual(env["overall_status"], "verified_compatible")
            self.assertEqual(env["bitsandbytes_status"], "cuda_operation_verified")
            self.assertEqual(env["packages"]["bitsandbytes_version"], "0.49.2")
            self.assertEqual(env["import_failures"], [])

    def test_manifest_verified_compatible_not_planned(self) -> None:
        self.assertEqual(self.inference_manifest["environment_status"], "verified_compatible")
        self.assertEqual(self.training_manifest["environment_status"], "verified_compatible")
        self.assertEqual(
            self.inference_manifest["bitsandbytes_compatibility"], "cuda_operation_verified"
        )
        self.assertEqual(
            self.training_manifest["bitsandbytes_compatibility"], "cuda_operation_verified"
        )

    def test_ambiguity_manager_import_ml_free(self) -> None:
        import importlib
        import sys

        ml_modules = [name for name in sys.modules if name in {"torch", "transformers", "peft"}]
        self.assertEqual(ml_modules, [])
        importlib.import_module("ambiguity_manager")
        for name in ("torch", "transformers", "peft", "trl", "bitsandbytes"):
            self.assertNotIn(name, sys.modules)

    def test_selected_model_remains_null(self) -> None:
        register = json.loads(
            (ROOT / "configs" / "licences" / "model_licence_register.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIsNone(register["selected_model"])

    def test_licence_register_has_no_selected_entry(self) -> None:
        register = json.loads(
            (ROOT / "configs" / "licences" / "model_licence_register.json").read_text(
                encoding="utf-8"
            )
        )
        selected_entries = [
            entry
            for entry in register["entries"]
            if entry.get("verification_status") == "selected"
        ]
        self.assertEqual(selected_entries, [])

    def test_manifest_not_planned_unverified_after_slice2(self) -> None:
        self.assertNotEqual(self.inference_manifest["environment_status"], "planned_unverified")
        self.assertNotEqual(self.training_manifest["environment_status"], "planned_unverified")


if __name__ == "__main__":
    unittest.main()
