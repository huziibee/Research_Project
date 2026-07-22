"""CPU-only tests for the T27 Phase E QLoRA technical smoke scaffolding.

Every test here uses either the real, currently-null-selection
``configs/model/selected_identities_v1.json`` contract, a constructed
synthetic :class:`SelectedIdentities` (to exercise the "base already
selected" branches without waiting for Phase D), or the deterministic
:class:`MockQloraTrainingHarness`. No test in this file imports or loads a
real model, tokenizer, or any of ``torch``/``transformers``/``peft``/
``bitsandbytes``/``accelerate``.

Run with::

    python -m unittest tests.test_t27_qlora_smoke -v
"""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.model import qlora_smoke as qs  # noqa: E402
from ambiguity_manager.model.cluster.job_operator import get_profile, load_profiles  # noqa: E402
from ambiguity_manager.model.qlora_smoke_data import (  # noqa: E402
    MAX_RECORD_COUNT,
    MIN_RECORD_COUNT,
    dataset_paths as smoke_data_paths,
)
from ambiguity_manager.model.training_target_packaging import (  # noqa: E402
    TrainingTargetPackagingError,
    assert_never_fabricates_negative_label,
    batch_loss_mask_summary,
    build_training_target_package,
    load_training_target_policy_strict,
)
from ambiguity_manager.systems.model_identities import SelectedIdentities, checkpoint_identity  # noqa: E402

QWEN_IDENTITY = "Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218"


def _synthetic_identities(*, selected_base_model: str | None) -> SelectedIdentities:
    return SelectedIdentities(
        contract_id="selected_identities_v1",
        version="test-only",
        zero_shot_candidate_status="rejected",
        adaptation_base_status="selected_for_qlora_development" if selected_base_model else None,
        selected_base_model=selected_base_model,
        selected_adapter=None,
        selected_model_strategy=None,
        status="development_base_selected" if selected_base_model else "adaptation_base_pending",
        valid_for_official_use=False,
    )


class LazyImportIsolationTests(unittest.TestCase):
    """Item: lazy local import isolation."""

    def test_no_forbidden_module_is_imported_at_module_top_level(self) -> None:
        source = (SRC / "ambiguity_manager" / "model" / "qlora_smoke.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        top_level_imports: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                top_level_imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_level_imports.add(node.module.split(".")[0])
        self.assertFalse(top_level_imports & qs.FORBIDDEN_EAGER_IMPORTS, top_level_imports)

    def test_provider_availability_check_never_raises(self) -> None:
        availability = qs.check_qlora_provider_available()
        self.assertIsInstance(availability.available, bool)
        self.assertIn(availability.reason, (None, "provider_unavailable"))

    def test_importing_module_does_not_pull_in_heavy_deps(self) -> None:
        for name in qs.FORBIDDEN_EAGER_IMPORTS:
            self.assertNotIn(
                name,
                sys.modules,
                f"{name} must not already be imported as a side effect of importing qlora_smoke",
            )


class RequireSelectedBaseModelTests(unittest.TestCase):
    """Item: require selected_base_model."""

    def test_raises_while_selected_base_model_is_null(self) -> None:
        identities = _synthetic_identities(selected_base_model=None)
        with self.assertRaises(qs.QloraSmokeError):
            qs.require_selected_base_model(identities=identities)

    def test_returns_identity_once_selected(self) -> None:
        identities = _synthetic_identities(selected_base_model=QWEN_IDENTITY)
        self.assertEqual(qs.require_selected_base_model(identities=identities), QWEN_IDENTITY)

    def test_real_repo_contract_requires_selected_qwen_base(self) -> None:
        # Phase D selected Qwen3-8B as the immutable QLoRA development base.
        identity = qs.require_selected_base_model(ROOT)
        self.assertEqual(identity, QWEN_IDENTITY)


class RejectArbitraryBaseModelTests(unittest.TestCase):
    """Item: reject arbitrary repo IDs."""

    def test_accepts_exact_allowlisted_match(self) -> None:
        repository, revision = "Qwen/Qwen3-8B", "b968826d9c46dd6066d109eabc6255188de91218"
        result = qs.reject_arbitrary_base_model(
            candidate_repository=repository,
            candidate_revision=revision,
            selected_base_model=checkpoint_identity(repository, revision),
            root=ROOT,
        )
        self.assertEqual(result, QWEN_IDENTITY)

    def test_rejects_arbitrary_unlisted_repository(self) -> None:
        with self.assertRaises(qs.QloraSmokeError):
            qs.reject_arbitrary_base_model(
                candidate_repository="some-org/not-allowlisted-model",
                candidate_revision="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                selected_base_model="some-org/not-allowlisted-model@deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                root=ROOT,
            )

    def test_rejects_mismatched_revision(self) -> None:
        with self.assertRaises(qs.QloraSmokeError):
            qs.reject_arbitrary_base_model(
                candidate_repository="Qwen/Qwen3-8B",
                candidate_revision="0000000000000000000000000000000000000000",
                selected_base_model=QWEN_IDENTITY,
                root=ROOT,
            )

    def test_rejects_empty_repository(self) -> None:
        with self.assertRaises(qs.QloraSmokeError):
            qs.reject_arbitrary_base_model(
                candidate_repository="   ",
                candidate_revision="b968826d9c46dd6066d109eabc6255188de91218",
                selected_base_model=QWEN_IDENTITY,
                root=ROOT,
            )


class SmokeConfigTests(unittest.TestCase):
    """Item: smoke config structural validation."""

    def test_real_config_loads_and_validates(self) -> None:
        config = qs.load_smoke_config(ROOT)
        self.assertTrue(config["development_only"])
        self.assertFalse(config["valid_for_official_use"])
        self.assertIsNone(config["selected_adapter"])
        self.assertEqual(config["quantization"]["bits"], 4)
        self.assertLessEqual(config["training"]["max_steps"], 50)

    def test_rejects_config_missing_development_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_config = json.loads((ROOT / qs.CONFIG_REL).read_text(encoding="utf-8"))
            bad_config["development_only"] = False
            config_path = root / qs.CONFIG_REL
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(bad_config), encoding="utf-8")
            with self.assertRaises(qs.QloraSmokeError):
                qs.load_smoke_config(root)

    def test_rejects_config_with_selected_adapter_populated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_config = json.loads((ROOT / qs.CONFIG_REL).read_text(encoding="utf-8"))
            bad_config["selected_adapter"] = "some-adapter"
            config_path = root / qs.CONFIG_REL
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(bad_config), encoding="utf-8")
            with self.assertRaises(qs.QloraSmokeError):
                qs.load_smoke_config(root)


class SmokeDatasetLoadingTests(unittest.TestCase):
    """Item: load smoke subset."""

    @classmethod
    def setUpClass(cls) -> None:
        paths = smoke_data_paths(ROOT)
        if not paths["smoke_records"].is_file():
            raise AssertionError(
                f"missing built artefact {paths['smoke_records']}; run "
                "'python scripts/build_qlora_smoke_data.py' first"
            )

    def test_loads_within_bounds(self) -> None:
        rows = qs.load_smoke_dataset(ROOT)
        self.assertGreaterEqual(len(rows), MIN_RECORD_COUNT)
        self.assertLessEqual(len(rows), MAX_RECORD_COUNT)

    def test_rows_carry_eligibility_and_record(self) -> None:
        rows = qs.load_smoke_dataset(ROOT)
        for row in rows[:5]:
            self.assertIn("eligibility", row)
            self.assertIn("record", row)
            self.assertIn("source_dataset", row)

    def test_missing_dataset_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(qs.QloraSmokeError):
                qs.load_smoke_dataset(Path(tmp))


class TrainingTargetPackagingStrategyDTests(unittest.TestCase):
    """Item: training-target packaging respects strategy D masking."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_training_target_policy_strict(ROOT / qs.TRAINING_TARGET_POLICY_REL)

    def test_unavailable_and_ineligible_are_masked_never_negative(self) -> None:
        record = {"id": "rec-1", "speech_act": "request", "capability_status": None}
        eligibility = {
            spec["eligibility_task"]: "unavailable" for spec in self.policy["field_groups"]
        }
        eligibility["speech_act_intent"] = "eligible"
        package = build_training_target_package(record, eligibility, policy=self.policy)
        assert_never_fabricates_negative_label(package)
        masked = [g for g in package.field_groups if g.masked]
        self.assertTrue(masked)
        for group in masked:
            self.assertEqual(group.loss_weight, 0.0)
        active = [g for g in package.field_groups if not g.masked]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].field_group, "speech_act_intent")

    def test_weakly_eligible_gets_half_weight(self) -> None:
        record = {"id": "rec-2", "speech_act": "inform"}
        eligibility = {spec["eligibility_task"]: "unavailable" for spec in self.policy["field_groups"]}
        eligibility["speech_act_intent"] = "weakly_eligible"
        package = build_training_target_package(record, eligibility, policy=self.policy)
        group = next(g for g in package.field_groups if g.field_group == "speech_act_intent")
        self.assertEqual(group.loss_weight, 0.5)
        self.assertFalse(group.masked)

    def test_unknown_status_raises(self) -> None:
        record = {"id": "rec-3"}
        eligibility = {spec["eligibility_task"]: "unavailable" for spec in self.policy["field_groups"]}
        eligibility["speech_act_intent"] = "not_a_real_status"
        with self.assertRaises(TrainingTargetPackagingError):
            build_training_target_package(record, eligibility, policy=self.policy)

    def test_guard_rejects_a_hand_built_bad_package(self) -> None:
        from ambiguity_manager.model.training_target_packaging import (
            FieldGroupTarget,
            TrainingTargetPackage,
        )

        bad_group = FieldGroupTarget(
            field_group="risk",
            eligibility_task="risk",
            loss_type="ordinal_classification",
            eligibility_status="unavailable",
            loss_weight=1.0,  # invalid: unavailable must be 0.0
            masked=False,
            fields={"risk_relevant": True},
        )
        bad_package = TrainingTargetPackage(record_id="rec-bad", field_groups=(bad_group,))
        with self.assertRaises(TrainingTargetPackagingError):
            assert_never_fabricates_negative_label(bad_package)

    def test_batch_loss_mask_summary_counts_active_and_masked(self) -> None:
        record = {"id": "rec-4", "speech_act": "request"}
        eligibility = {spec["eligibility_task"]: "unavailable" for spec in self.policy["field_groups"]}
        eligibility["speech_act_intent"] = "eligible"
        package = build_training_target_package(record, eligibility, policy=self.policy)
        summary = batch_loss_mask_summary([package])
        self.assertEqual(summary["record_count"], 1)
        self.assertEqual(summary["field_groups"]["speech_act_intent"]["active"], 1)
        self.assertGreater(summary["field_groups"]["risk"]["masked"], 0)


class AdapterIdentityScopeTests(unittest.TestCase):
    """Items: smoke adapter cannot become selected_adapter / training cannot be official."""

    def _identity(self) -> qs.AdapterIdentity:
        return qs.AdapterIdentity(
            adapter_id="qlora-smoke-adapter-test",
            base_model=QWEN_IDENTITY,
            created_at_utc="2026-07-22T00:00:00Z",
            rank=8,
            alpha=16,
            target_modules=("q_proj", "k_proj", "v_proj", "o_proj"),
        )

    def test_smoke_adapter_identity_defaults_are_scoped(self) -> None:
        identity = self._identity()
        identity.assert_smoke_scope()
        self.assertTrue(identity.technical_smoke_only)
        self.assertFalse(identity.selected_adapter)
        self.assertFalse(identity.valid_for_official_use)

    def test_cannot_register_smoke_adapter_as_selected(self) -> None:
        identity = self._identity()
        with self.assertRaises(qs.QloraSmokeError):
            qs.assert_cannot_register_smoke_adapter_as_selected(
                identity, proposed_selected_adapter=identity.adapter_id
            )

    def test_registering_a_different_adapter_id_does_not_raise(self) -> None:
        identity = self._identity()
        qs.assert_cannot_register_smoke_adapter_as_selected(
            identity, proposed_selected_adapter="some-other-adapter"
        )

    def test_tampered_identity_fails_smoke_scope_assertion(self) -> None:
        import dataclasses

        identity = dataclasses.replace(self._identity(), selected_adapter=True)
        with self.assertRaises(qs.QloraSmokeError):
            identity.assert_smoke_scope()

    def test_training_run_result_must_stay_non_official(self) -> None:
        good = {"valid_for_official_use": False, "selected_adapter": False, "technical_smoke_only": True}
        qs.assert_training_run_not_official(good)
        for bad_key in ("valid_for_official_use", "selected_adapter", "technical_smoke_only"):
            bad = dict(good)
            bad[bad_key] = not bad[bad_key] if bad_key != "technical_smoke_only" else False
            with self.assertRaises(qs.QloraSmokeError):
                qs.assert_training_run_not_official(bad)


class MockHarnessContractTests(unittest.TestCase):
    """Items: base frozen / adapter trainable / save separately / reload validates
    exact base / mismatched base rejects / resume verifies contract."""

    def test_base_is_frozen_while_adapter_changes(self) -> None:
        harness = qs.MockQloraTrainingHarness(base_model=QWEN_IDENTITY)
        base_before = harness.frozen_base_snapshot()
        adapter_before = list(harness.adapter.delta)
        batch = [{"id": "rec-1"}, {"id": "rec-2"}]
        event = harness.train_one_step(batch)
        self.assertTrue(event["base_unchanged"])
        self.assertEqual(harness.frozen_base_snapshot(), base_before)
        self.assertNotEqual(harness.adapter.delta, adapter_before)

    def test_train_one_step_rejects_empty_batch(self) -> None:
        harness = qs.MockQloraTrainingHarness(base_model=QWEN_IDENTITY)
        with self.assertRaises(qs.QloraSmokeError):
            harness.train_one_step([])

    def test_save_writes_adapter_and_base_reference_separately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter_dir = Path(tmp) / "adapter"
            harness = qs.MockQloraTrainingHarness(base_model=QWEN_IDENTITY)
            harness.train_one_step([{"id": "rec-1"}])
            identity = qs.AdapterIdentity(
                adapter_id="qlora-smoke-adapter-save-test",
                base_model=QWEN_IDENTITY,
                created_at_utc="2026-07-22T00:00:00Z",
                rank=2,
                alpha=4,
                target_modules=("q_proj",),
            )
            harness.save_adapter(adapter_dir, identity=identity)
            self.assertTrue((adapter_dir / "adapter_weights.json").is_file())
            self.assertTrue((adapter_dir / "base_identity_reference.json").is_file())
            base_ref = json.loads((adapter_dir / "base_identity_reference.json").read_text(encoding="utf-8"))
            self.assertEqual(base_ref["note"], "identity_reference_only_not_weights")
            self.assertNotIn("weights", base_ref)

    def test_save_rejects_base_model_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter_dir = Path(tmp) / "adapter"
            harness = qs.MockQloraTrainingHarness(base_model=QWEN_IDENTITY)
            identity = qs.AdapterIdentity(
                adapter_id="qlora-smoke-adapter-mismatch",
                base_model="some-other-org/other-model@1111111111111111111111111111111111111111",
                created_at_utc="2026-07-22T00:00:00Z",
                rank=2,
                alpha=4,
                target_modules=("q_proj",),
            )
            with self.assertRaises(qs.QloraSmokeError):
                harness.save_adapter(adapter_dir, identity=identity)

    def test_reload_validates_exact_base_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter_dir = Path(tmp) / "adapter"
            harness = qs.MockQloraTrainingHarness(base_model=QWEN_IDENTITY, seed=42)
            harness.train_one_step([{"id": "rec-1"}])
            harness.train_one_step([{"id": "rec-2"}])
            identity = qs.AdapterIdentity(
                adapter_id="qlora-smoke-adapter-reload",
                base_model=QWEN_IDENTITY,
                created_at_utc="2026-07-22T00:00:00Z",
                rank=2,
                alpha=4,
                target_modules=("q_proj",),
            )
            harness.save_adapter(adapter_dir, identity=identity)
            reloaded = qs.MockQloraTrainingHarness.load_adapter(adapter_dir, expected_base_model=QWEN_IDENTITY)
            self.assertEqual(reloaded.step, 2)
            self.assertEqual(reloaded.adapter.delta, harness.adapter.delta)
            self.assertEqual(reloaded.frozen_base_snapshot(), harness.frozen_base_snapshot())

    def test_reload_rejects_mismatched_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter_dir = Path(tmp) / "adapter"
            harness = qs.MockQloraTrainingHarness(base_model=QWEN_IDENTITY)
            harness.train_one_step([{"id": "rec-1"}])
            identity = qs.AdapterIdentity(
                adapter_id="qlora-smoke-adapter-reload-mismatch",
                base_model=QWEN_IDENTITY,
                created_at_utc="2026-07-22T00:00:00Z",
                rank=2,
                alpha=4,
                target_modules=("q_proj",),
            )
            harness.save_adapter(adapter_dir, identity=identity)
            with self.assertRaises(qs.QloraSmokeError):
                qs.MockQloraTrainingHarness.load_adapter(
                    adapter_dir,
                    expected_base_model="different-org/different-model@2222222222222222222222222222222222222222",
                )

    def test_load_adapter_rejects_incomplete_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter_dir = Path(tmp) / "adapter"
            adapter_dir.mkdir(parents=True)
            with self.assertRaises(qs.QloraSmokeError):
                qs.MockQloraTrainingHarness.load_adapter(adapter_dir, expected_base_model=QWEN_IDENTITY)

    def test_resume_contract_matches_expected_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter_dir = Path(tmp) / "adapter"
            harness = qs.MockQloraTrainingHarness(base_model=QWEN_IDENTITY)
            for _ in range(3):
                harness.train_one_step([{"id": "rec-1"}])
            identity = qs.AdapterIdentity(
                adapter_id="qlora-smoke-adapter-resume",
                base_model=QWEN_IDENTITY,
                created_at_utc="2026-07-22T00:00:00Z",
                rank=2,
                alpha=4,
                target_modules=("q_proj",),
            )
            harness.save_adapter(adapter_dir, identity=identity)
            resumed = qs.verify_resume_contract(adapter_dir, expected_base_model=QWEN_IDENTITY, expected_step=3)
            self.assertEqual(resumed.step, 3)

    def test_resume_contract_rejects_wrong_expected_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter_dir = Path(tmp) / "adapter"
            harness = qs.MockQloraTrainingHarness(base_model=QWEN_IDENTITY)
            harness.train_one_step([{"id": "rec-1"}])
            identity = qs.AdapterIdentity(
                adapter_id="qlora-smoke-adapter-resume-wrong",
                base_model=QWEN_IDENTITY,
                created_at_utc="2026-07-22T00:00:00Z",
                rank=2,
                alpha=4,
                target_modules=("q_proj",),
            )
            harness.save_adapter(adapter_dir, identity=identity)
            with self.assertRaises(qs.QloraSmokeError):
                qs.verify_resume_contract(adapter_dir, expected_base_model=QWEN_IDENTITY, expected_step=99)


class SecretsHygieneTests(unittest.TestCase):
    """Item: secrets not persisted."""

    def test_sanitize_passes_clean_payload(self) -> None:
        payload = {"run_id": "abc", "success": True}
        self.assertEqual(qs.sanitize_evidence_payload(payload), payload)

    def test_sanitize_rejects_forbidden_keys(self) -> None:
        for key in qs.FORBIDDEN_EVIDENCE_KEYS:
            with self.assertRaises(qs.QloraSmokeError):
                qs.sanitize_evidence_payload({key: "shhh"})

    def test_sanitize_rejects_nested_forbidden_keys(self) -> None:
        with self.assertRaises(qs.QloraSmokeError):
            qs.sanitize_evidence_payload({"nested": {"hf_token": "shhh"}})


class RunSmokeTrainingOrchestrationTests(unittest.TestCase):
    """End-to-end orchestration using the mock harness only.

    Items: load smoke subset (integration), base frozen/adapter trainable
    (integration), save separately (integration), resume test, failed
    training still finalises evidence, training cannot be official
    (integration).
    """

    def _real_dataset_rows(self, count: int = 4) -> list[dict]:
        rows = qs.load_smoke_dataset(ROOT)
        return rows[:count]

    def _real_policy(self) -> dict:
        return load_training_target_policy_strict(ROOT / qs.TRAINING_TARGET_POLICY_REL)

    def _real_config(self) -> dict:
        config = qs.load_smoke_config(ROOT)
        # Keep the integration test itself even smaller/faster than the
        # already-tiny shipped config, without mutating the shipped file.
        config = json.loads(json.dumps(config))
        config["training"]["max_steps"] = 4
        config["training"]["checkpoint_interval_steps"] = 2
        return config

    def test_successful_mock_run_finalises_full_evidence(self) -> None:
        identities = _synthetic_identities(selected_base_model=QWEN_IDENTITY)
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "result"

            import unittest.mock as mock

            with mock.patch.object(qs, "require_selected_base_model", return_value=QWEN_IDENTITY):
                outcome = qs.run_smoke_training(
                    result_dir=result_dir,
                    run_id="test-run-success",
                    root=ROOT,
                    dataset_rows=self._real_dataset_rows(),
                    config=self._real_config(),
                )
            del identities

            result = outcome["result"]
            self.assertTrue(result["success"])
            self.assertIsNone(result["failure_reason"])
            self.assertEqual(result["mode"], "mock_contract_proof")
            self.assertTrue((result_dir / "qlora_smoke_result.json").is_file())
            self.assertTrue((result_dir / "loss_mask_summary.json").is_file())
            self.assertTrue((result_dir / "run_manifest.json").is_file())
            self.assertTrue((result_dir / "adapter_identity.json").is_file())
            self.assertIsNotNone(result["resumed_step"])
            qs.assert_training_run_not_official(result)

    def test_failed_training_still_finalises_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "result"

            def _boom(batch):
                raise RuntimeError("synthetic training failure for the smoke test")

            import unittest.mock as mock

            with mock.patch.object(qs, "require_selected_base_model", return_value=QWEN_IDENTITY):
                outcome = qs.run_smoke_training(
                    result_dir=result_dir,
                    run_id="test-run-failure",
                    root=ROOT,
                    dataset_rows=self._real_dataset_rows(),
                    config=self._real_config(),
                    training_step_fn=_boom,
                )

            result = outcome["result"]
            self.assertFalse(result["success"])
            self.assertIn("synthetic training failure", result["failure_reason"])
            # Evidence must still exist despite the failure.
            self.assertTrue((result_dir / "qlora_smoke_result.json").is_file())
            self.assertTrue((result_dir / "run_manifest.json").is_file())
            self.assertTrue((result_dir / "loss_mask_summary.json").is_file())
            manifest = json.loads((result_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["success"])
            qs.assert_training_run_not_official(result)

    def test_run_raises_before_any_evidence_when_base_model_not_selected(self) -> None:
        import unittest.mock as mock

        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "result"
            with mock.patch.object(
                qs,
                "require_selected_base_model",
                side_effect=qs.QloraSmokeError("selected_base_model_required"),
            ):
                with self.assertRaises(qs.QloraSmokeError):
                    qs.run_smoke_training(
                        result_dir=result_dir,
                        run_id="test-run-no-base",
                        root=ROOT,
                        dataset_rows=self._real_dataset_rows(),
                        config=self._real_config(),
                    )
            self.assertFalse((result_dir / "qlora_smoke_result.json").exists())

    def test_run_refuses_nonempty_result_dir(self) -> None:
        import unittest.mock as mock

        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "result"
            result_dir.mkdir(parents=True)
            (result_dir / "qlora_smoke_result.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(qs, "require_selected_base_model", return_value=QWEN_IDENTITY):
                with self.assertRaises(qs.QloraSmokeError):
                    qs.run_smoke_training(
                        result_dir=result_dir,
                        run_id="test-run-nonempty",
                        root=ROOT,
                        dataset_rows=self._real_dataset_rows(),
                        config=self._real_config(),
                    )

    def test_run_never_reaches_real_pipeline_when_force_mock_true(self) -> None:
        import unittest.mock as mock

        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "result"
            with mock.patch.object(qs, "require_selected_base_model", return_value=QWEN_IDENTITY), mock.patch.object(
                qs, "check_qlora_provider_available", return_value=qs.ProviderAvailability(available=True)
            ), mock.patch.object(qs, "run_real_qlora_smoke") as fake_real:
                outcome = qs.run_smoke_training(
                    result_dir=result_dir,
                    run_id="test-run-force-mock",
                    root=ROOT,
                    dataset_rows=self._real_dataset_rows(),
                    config=self._real_config(),
                    force_mock=True,
                )
            fake_real.assert_not_called()
            self.assertEqual(outcome["result"]["mode"], "mock_contract_proof")


class EvidenceFinalisationTests(unittest.TestCase):
    """Item: failed training still finalises evidence (unit-level on the helper)."""

    def test_finalize_manifest_lists_all_written_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "result"
            result_dir.mkdir(parents=True)
            (result_dir / "qlora_smoke_result.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
            manifest = qs.finalize_smoke_run_manifest(result_dir, run_id="test-manifest", success=True)
            self.assertTrue(manifest["success"])
            self.assertTrue(manifest["development_only"])
            self.assertFalse(manifest["valid_for_official_use"])
            relpaths = {entry["relative_path"] for entry in manifest["files"]}
            self.assertIn("qlora_smoke_result.json", relpaths)

    def test_finalize_manifest_on_failure_still_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "result"
            result_dir.mkdir(parents=True)
            manifest = qs.finalize_smoke_run_manifest(result_dir, run_id="test-manifest-fail", success=False)
            self.assertFalse(manifest["success"])
            self.assertTrue((result_dir / "run_manifest.json").is_file())


class OperatorProfileTests(unittest.TestCase):
    """Item: qlora_smoke operator profile allowlisted and GPU/training-container safe."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.profiles_doc = load_profiles(ROOT)
        cls.profile = get_profile(cls.profiles_doc, "qlora_smoke")

    def test_profile_requires_one_gpu(self) -> None:
        self.assertTrue(self.profile["gpus_required"])
        self.assertEqual(self.profile.get("gpus", 1), 1)

    def test_profile_entry_point_matches_cluster_script(self) -> None:
        self.assertEqual(self.profile["entry_point"], "scripts/t12_qlora_smoke.py")
        self.assertTrue((ROOT / self.profile["entry_point"]).is_file())

    def test_profile_never_defaults_to_pinned_inference_sif(self) -> None:
        container_relpath = self.profile.get("container_sif_default_relpath")
        self.assertIsNotNone(container_relpath)
        self.assertNotIn("vllm-openai", str(container_relpath))

    def test_profile_lists_expected_evidence_files(self) -> None:
        expected = set(self.profile["expected_result_files"])
        self.assertEqual(
            expected,
            {
                "qlora_smoke_result.json",
                "adapter_identity.json",
                "loss_mask_summary.json",
                "run_manifest.json",
                "source_identity_manifest.json",
            },
        )

    def test_rendered_sbatch_uses_training_container_not_inference_sif(self) -> None:
        from ambiguity_manager.model.cluster.job_operator import ClusterJobOperator

        operator = ClusterJobOperator(repo_root=ROOT, runner=lambda *a, **k: None)
        rendered = operator._render_sbatch(  # noqa: SLF001
            profile=self.profile,
            run_id="t12-qlora-smoke-test-0000000",
            head_sha="0" * 40,
            archive_sha="0" * 64,
            archive_filename="t12-src.tar.gz",
        )
        self.assertIn("t12-training-v1.sif", rendered)
        self.assertNotIn("vllm-openai-v0.20.1.sif", rendered)

    def test_other_gpu_profiles_still_default_to_inference_sif(self) -> None:
        # Backward-compatibility guard for the shared _render_sbatch change.
        from ambiguity_manager.model.cluster.job_operator import ClusterJobOperator

        gpu_profile_name = next(
            name
            for name, profile in self.profiles_doc["profiles"].items()
            if profile.get("gpus_required") and "container_sif_default_relpath" not in profile
        )
        profile = get_profile(self.profiles_doc, gpu_profile_name)
        operator = ClusterJobOperator(repo_root=ROOT, runner=lambda *a, **k: None)
        rendered = operator._render_sbatch(  # noqa: SLF001
            profile=profile,
            run_id="t12-other-test-0000000",
            head_sha="0" * 40,
            archive_sha="0" * 64,
            archive_filename="t12-src.tar.gz",
            candidate_id="qwen3_8b" if profile.get("requires_candidate_id") else None,
        )
        self.assertIn("vllm-openai-v0.20.1.sif", rendered)


class TrainingEnvironmentConfigTests(unittest.TestCase):
    """Item: training environment config documents a pinned, separate stack."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(
            (ROOT / "configs" / "environments" / "t12_cluster_training.json").read_text(encoding="utf-8")
        )

    def test_pinned_versions_present(self) -> None:
        pinned = self.config["qlora_smoke_pinned_versions"]
        for key in (
            "python_version",
            "pytorch_version",
            "cuda_version",
            "transformers_version",
            "peft_version",
            "bitsandbytes_version",
            "accelerate_version",
        ):
            self.assertIn(key, pinned)
            self.assertIn("value", pinned[key])

    def test_separation_from_inference_declared(self) -> None:
        separation = self.config["separation_from_inference_env"]
        self.assertTrue(separation["inference_and_training_envs_are_separate"])
        self.assertTrue(separation["inference_container_untouched_by_training"])

    def test_container_recipe_documented_but_not_built(self) -> None:
        recipe = self.config["container_recipe"]
        self.assertEqual(recipe["status"], "recipe_only_not_built")
        recipe_path = ROOT / recipe["recipe_relpath"]
        self.assertTrue(recipe_path.is_file())


class SmokeDataExclusionTests(unittest.TestCase):
    """Item: smoke data builder excludes forbidden splits/sources."""

    @classmethod
    def setUpClass(cls) -> None:
        paths = smoke_data_paths(ROOT)
        cls.manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))

    def test_only_source_train_used(self) -> None:
        self.assertEqual(self.manifest["source_split_used"], "source_train")

    def test_forbidden_splits_and_sources_recorded(self) -> None:
        self.assertIn("source_dev", self.manifest["forbidden_splits"])
        self.assertIn("source_holdout", self.manifest["forbidden_splits"])
        for excluded in (
            "model_selection_development_set_v1",
            "t13_calibration",
            "future_manual_namespace",
            "protected_data",
        ):
            self.assertIn(excluded, self.manifest["excluded_sources"])

    def test_record_count_within_bounds(self) -> None:
        self.assertGreaterEqual(self.manifest["record_count"], MIN_RECORD_COUNT)
        self.assertLessEqual(self.manifest["record_count"], MAX_RECORD_COUNT)

    def test_never_selects_a_model(self) -> None:
        self.assertNotIn("selected_base_model", self.manifest)
        self.assertNotIn("selected_adapter", self.manifest)


if __name__ == "__main__":
    unittest.main()
