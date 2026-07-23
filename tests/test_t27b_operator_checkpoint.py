"""T27B operator profile + checkpoint / orchestrator guard tests (CPU-only)."""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.model.cluster.job_operator import get_profile, load_profiles  # noqa: E402
from ambiguity_manager.model.qlora_checkpoint import (  # noqa: E402
    CheckpointError,
    assert_resume_identities,
    build_checkpoint_payload,
    evaluate_resume_components,
    load_full_checkpoint_blob,
    save_full_checkpoint,
)
from ambiguity_manager.model.qlora_structured_emission_recovery import (  # noqa: E402
    FORBIDDEN_EAGER_IMPORTS,
    PROVIDER_ID,
    load_emission_recovery_config,
    load_emission_recovery_diagnostic_records,
    load_emission_recovery_sealed_records,
    load_emission_recovery_train_records,
    run_structured_emission_recovery_training,
)


class T27BOperatorCheckpointTests(unittest.TestCase):
    def test_profile_allowlisted_and_not_pinned(self) -> None:
        profiles = load_profiles(ROOT)
        live = get_profile(profiles, "qlora_structured_emission_recovery")
        self.assertEqual(
            live["entry_point"], "scripts/t12_qlora_structured_emission_recovery.py"
        )
        self.assertEqual(live["job_name"], "t12-qlora-emission-recovery")
        self.assertEqual(live["run_id_prefix"], "t12-qlora-emission-recovery")
        self.assertTrue(live["gpus_required"])
        self.assertEqual(live["container_role"], "training")
        self.assertNotIn("nodelist", live)
        self.assertIn("mscluster107", live.get("exclude_nodes", ""))
        expected = set(live["expected_result_files"])
        self.assertTrue(
            {
                "qlora_structured_emission_recovery_result.json",
                "adapter_identity.json",
                "loss_mask_summary.json",
                "structured_output_results.json",
                "resume_components.json",
                "run_manifest.json",
                "source_identity_manifest.json",
            }.issubset(expected)
        )
        self.assertTrue((ROOT / "scripts/t12_qlora_structured_emission_recovery.py").is_file())

    def test_config_frozen_thresholds_and_null_adapter(self) -> None:
        cfg = load_emission_recovery_config(ROOT)
        self.assertEqual(cfg["envelope_id"], "full_schema_envelope_v1")
        self.assertIsNone(cfg["selected_adapter"])
        self.assertFalse(cfg["valid_for_official_use"])
        self.assertTrue(cfg["technical_smoke_only"])
        self.assertTrue(cfg["pass_thresholds"]["frozen_before_live_results"])
        self.assertEqual(int(cfg["training"]["max_steps"]), 24)
        notes = " ".join(cfg.get("notes") or [])
        self.assertNotIn("intentionally deferred", notes.lower())

    def test_manifest_counts(self) -> None:
        self.assertEqual(len(load_emission_recovery_train_records(ROOT)), 128)
        self.assertEqual(len(load_emission_recovery_sealed_records(ROOT)), 8)
        self.assertEqual(len(load_emission_recovery_diagnostic_records(ROOT)), 12)

    def test_no_eager_ml_imports(self) -> None:
        path = ROOT / "src/ambiguity_manager/model/qlora_structured_emission_recovery.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif node.module:
                    names = [node.module.split(".")[0]]
                for name in names:
                    self.assertNotIn(name, FORBIDDEN_EAGER_IMPORTS)
        for name in FORBIDDEN_EAGER_IMPORTS:
            self.assertNotIn(name, sys.modules)

    def test_checkpoint_roundtrip_and_identity_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter_dir = Path(tmp) / "adapter"
            adapter_dir.mkdir()
            (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")
            ckpt = Path(tmp) / "ckpt"
            ckpt.mkdir()

            class _Opt:
                def state_dict(self) -> dict:
                    return {"step": 12}

            payload = build_checkpoint_payload(
                adapter_dir=adapter_dir,
                optimizer=_Opt(),
                scheduler=None,
                scaler=None,
                global_step=12,
                epoch=0,
                data_position=3,
                consumed_example_ids=["a", "b"],
                training_config_hash="cfghash",
                smoke_data_manifest_hash="datahash",
                selected_base_model="Qwen/Qwen3-8B@deadbeef",
                environment_identity="env",
                source_commit="abc",
            )
            save_full_checkpoint(ckpt, payload=payload, adapter_files_present=True)
            loaded = load_full_checkpoint_blob(ckpt)
            assert_resume_identities(
                loaded,
                selected_base_model="Qwen/Qwen3-8B@deadbeef",
                training_config_hash="cfghash",
                smoke_data_manifest_hash="datahash",
                environment_identity="env",
            )
            with self.assertRaises(CheckpointError):
                assert_resume_identities(
                    loaded,
                    selected_base_model="other",
                    training_config_hash="cfghash",
                    smoke_data_manifest_hash="datahash",
                    environment_identity="env",
                )
            resume = evaluate_resume_components(
                adapter_reload_ok=True,
                optimiser_restore_ok=True,
                scheduler_restore_ok=True,
                rng_restore_ok=True,
                data_position_restore_ok=True,
            )
            self.assertTrue(resume.full_resume_ok)

    def test_require_real_mode_refuses_force_mock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "r"
            outcome = run_structured_emission_recovery_training(
                result_dir=result_dir,
                run_id="t27b-test-refuse-mock",
                root=ROOT,
                require_real_mode=True,
                force_mock=True,
            )
            self.assertFalse(outcome["success"])
            self.assertTrue(
                (result_dir / "qlora_structured_emission_recovery_result.json").is_file()
            )
            payload = json.loads(
                (result_dir / "qlora_structured_emission_recovery_result.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(payload["provider_id"], PROVIDER_ID)
            self.assertIsNone(payload["selected_adapter"])
            self.assertFalse(payload["valid_for_official_use"])

    def test_mock_contract_proof_writes_evidence_without_live_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "r"
            with mock.patch(
                "ambiguity_manager.model.qlora_structured_emission_recovery.require_selected_base_model",
                return_value="Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218",
            ), mock.patch(
                "ambiguity_manager.model.qlora_structured_emission_recovery.check_qlora_provider_available",
            ) as avail:
                avail.return_value.available = False
                avail.return_value.reason = "cpu_test"
                avail.return_value.missing_modules = ["torch"]
                avail.return_value.to_dict.return_value = {
                    "available": False,
                    "reason": "cpu_test",
                    "missing_modules": ["torch"],
                }
                outcome = run_structured_emission_recovery_training(
                    result_dir=result_dir,
                    run_id="t27b-mock-proof",
                    root=ROOT,
                    require_real_mode=False,
                    force_mock=True,
                )
            self.assertTrue(outcome["success"])
            result = outcome["result"]
            self.assertEqual(result["mode"], "mock_contract_proof")
            self.assertFalse(result.get("live_gate_evaluated"))
            for name in (
                "qlora_structured_emission_recovery_result.json",
                "adapter_identity.json",
                "loss_mask_summary.json",
                "structured_output_results.json",
                "resume_components.json",
                "run_manifest.json",
            ):
                self.assertTrue((result_dir / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
