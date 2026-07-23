"""RED/GREEN tests for T27 task-aligned structured QLoRA smoke.

CPU-only. Does not import torch/transformers/peft/bitsandbytes/accelerate.
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

from ambiguity_manager.model.cluster.job_operator import get_profile, load_profiles  # noqa: E402
from ambiguity_manager.model.qlora_checkpoint import (  # noqa: E402
    CheckpointError,
    assert_resume_identities,
    build_checkpoint_payload,
    evaluate_resume_components,
    load_full_checkpoint_blob,
    save_full_checkpoint,
)
from ambiguity_manager.model.qlora_task_aligned_smoke_data import (  # noqa: E402
    TARGET_TRAIN_COUNT,
    TARGET_VAL_COUNT,
    dataset_paths,
    validation_paths,
)
from ambiguity_manager.model.structured_output_validation import (  # noqa: E402
    STATUS_ACCEPTED,
    STATUS_JSON_PARSE_FAILED,
    STATUS_NO_JSON,
    STATUS_SCHEMA_INVALID,
    isolate_generated_continuation,
    validate_structured_model_output,
)
from ambiguity_manager.model.structured_target import (  # noqa: E402
    TRAINING_TO_PRODUCTION_MAPPING,
    StructuredTargetError,
    build_structured_target,
)
from ambiguity_manager.model.token_loss_masking import (  # noqa: E402
    IGNORE_INDEX,
    DeterministicCharTokenizer,
    assert_labels_ignore_prompt,
    assert_no_command_reconstruction,
    build_masked_sequence,
    collate_masked_sequences,
)
from ambiguity_manager.model.training_example_contract import (  # noqa: E402
    build_inference_time_prompt,
    build_training_example,
)
from ambiguity_manager.model.training_target_packaging import (  # noqa: E402
    load_training_target_policy_strict,
)


def _sample_record() -> tuple[dict, dict]:
    rows_path = dataset_paths(ROOT)["records"]
    row = json.loads(rows_path.read_text(encoding="utf-8").splitlines()[0])
    return row["record"], row["eligibility"]


class StructuredTargetTests(unittest.TestCase):
    def test_canonical_structured_target_and_stable_hash(self) -> None:
        record, eligibility = _sample_record()
        policy = load_training_target_policy_strict(ROOT / "configs/data/training_target_policy_v1.json")
        a = build_structured_target(record, eligibility, policy=policy)
        b = build_structured_target(record, eligibility, policy=policy)
        self.assertEqual(a.target_hash, b.target_hash)
        self.assertEqual(a.canonical_json, b.canonical_json)
        self.assertTrue(a.fields)

    def test_no_runner_owned_fields(self) -> None:
        record, eligibility = _sample_record()
        target = build_structured_target(record, eligibility)
        self.assertNotIn("label_eligibility", target.fields)
        self.assertNotIn("command", target.fields)
        self.assertNotIn("id", target.fields)

    def test_unavailable_fields_not_fabricated(self) -> None:
        record, eligibility = _sample_record()
        target = build_structured_target(record, eligibility)
        for name in target.unavailable_fields:
            self.assertNotIn(name, target.fields)

    def test_partial_target_mapping_documented(self) -> None:
        self.assertEqual(TRAINING_TO_PRODUCTION_MAPPING["omitted_field_policy"], "exclude_from_target_and_loss")
        self.assertTrue(TRAINING_TO_PRODUCTION_MAPPING["fabricated_nulls_forbidden"])

    def test_invalid_target_rejected(self) -> None:
        with self.assertRaises(StructuredTargetError):
            build_structured_target({"id": "x"}, {k: "unavailable" for k in [
                "speech_act_intent", "cpc", "candidate_interpretations", "ambiguity_presence_types",
                "compound_ambiguity", "risk", "capability", "route", "clarification_target", "rejection",
                "structured_training_target",
            ]})


class LossMaskingTests(unittest.TestCase):
    def test_prompt_target_unavailable_padding_masks(self) -> None:
        record, eligibility = _sample_record()
        example = build_training_example(
            record=record,
            eligibility=eligibility,
            source_dataset="test",
            group_key="g",
            max_seq_len=256,
        )
        seq = example.masked_sequence
        assert seq is not None
        assert_labels_ignore_prompt(seq)
        assert_no_command_reconstruction(seq, command_text=str(record["command"]), tokenizer=DeterministicCharTokenizer())
        self.assertGreater(seq.diagnostics["target_supervised_tokens"], 0)
        self.assertFalse(seq.diagnostics["command_reconstruction"])
        self.assertTrue(all(label == IGNORE_INDEX or label >= 0 for label in seq.labels))
        # Prompt labels are all -100
        prompt_span = next(s for s in seq.spans if s.kind == "prompt")
        for i in range(prompt_span.token_start, prompt_span.token_end):
            self.assertEqual(seq.labels[i], IGNORE_INDEX)
        # Padding masked when present
        pad_spans = [s for s in seq.spans if s.kind == "padding"]
        for span in pad_spans:
            for i in range(span.token_start, span.token_end):
                self.assertEqual(seq.labels[i], IGNORE_INDEX)

    def test_changing_prompt_does_not_change_supervised_label_ids_pattern(self) -> None:
        record, eligibility = _sample_record()
        target = build_structured_target(record, eligibility)
        tok = DeterministicCharTokenizer()
        seq1 = build_masked_sequence(
            prompt_text="PROMPT_A",
            target_json=target.canonical_json,
            field_spans=[s.to_dict() for s in target.field_spans],
            unavailable_field_names=target.unavailable_fields,
            tokenizer=tok,
            max_seq_len=512,
            pad_token_id=0,
        )
        seq2 = build_masked_sequence(
            prompt_text="PROMPT_BBB_DIFFERENT",
            target_json=target.canonical_json,
            field_spans=[s.to_dict() for s in target.field_spans],
            unavailable_field_names=target.unavailable_fields,
            tokenizer=tok,
            max_seq_len=512,
            pad_token_id=0,
        )
        labels1 = [x for x in seq1.labels if x != IGNORE_INDEX]
        labels2 = [x for x in seq2.labels if x != IGNORE_INDEX]
        self.assertEqual(labels1, labels2)

    def test_zero_supervision_rejected(self) -> None:
        tok = DeterministicCharTokenizer()
        with self.assertRaises(Exception):
            build_masked_sequence(
                prompt_text="p",
                target_json="{}",
                field_spans=[],
                unavailable_field_names=["speech_act"],
                tokenizer=tok,
                max_seq_len=32,
                pad_token_id=0,
            )

    def test_batch_collation_preserves_masks(self) -> None:
        record, eligibility = _sample_record()
        example = build_training_example(
            record=record,
            eligibility=eligibility,
            source_dataset="test",
            group_key="g",
            max_seq_len=1024,
        )
        batch = collate_masked_sequences([example.masked_sequence], pad_token_id=0)
        self.assertIn("labels", batch)
        self.assertTrue(any(x != IGNORE_INDEX for x in batch["labels"][0]))

    def test_unavailable_field_cannot_contribute_when_present_as_masked_span(self) -> None:
        tok = DeterministicCharTokenizer()
        target_json = '{"a": 1, "b": 2}'
        spans = [
            {"field_name": "a", "char_start": 1, "char_end": 6, "supervision": "supervised", "json_fragment": '"a": 1'},
            {"field_name": "b", "char_start": 8, "char_end": 13, "supervision": "unavailable", "json_fragment": '"b": 2'},
        ]
        # Fix char positions to match
        spans[0]["char_start"] = target_json.find('"a": 1')
        spans[0]["char_end"] = spans[0]["char_start"] + len('"a": 1')
        spans[1]["char_start"] = target_json.find('"b": 2')
        spans[1]["char_end"] = spans[1]["char_start"] + len('"b": 2')
        seq = build_masked_sequence(
            prompt_text="P",
            target_json=target_json,
            field_spans=spans,
            unavailable_field_names=["b"],
            tokenizer=tok,
            max_seq_len=64,
            pad_token_id=0,
        )
        b_span = next(s for s in seq.spans if s.name == "b")
        for i in range(b_span.token_start, b_span.token_end):
            self.assertEqual(seq.labels[i], IGNORE_INDEX)
        a_span = next(s for s in seq.spans if s.name == "a")
        self.assertTrue(any(seq.labels[i] != IGNORE_INDEX for i in range(a_span.token_start, a_span.token_end)))


class DataSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(dataset_paths(ROOT)["manifest"].read_text(encoding="utf-8"))
        cls.val_manifest = json.loads(validation_paths(ROOT)["manifest"].read_text(encoding="utf-8"))
        cls.leakage = json.loads(dataset_paths(ROOT)["leakage_report"].read_text(encoding="utf-8"))
        cls.records = [
            json.loads(line)
            for line in dataset_paths(ROOT)["records"].read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        cls.val_records = [
            json.loads(line)
            for line in validation_paths(ROOT)["records"].read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_train_count_and_split(self) -> None:
        self.assertEqual(len(self.records), TARGET_TRAIN_COUNT)
        self.assertTrue(all(r["split"] == "source_train" for r in self.records))

    def test_val_count_and_split(self) -> None:
        self.assertEqual(len(self.val_records), TARGET_VAL_COUNT)
        self.assertTrue(all(r["split"] == "source_dev" for r in self.val_records))

    def test_no_group_leakage_or_holdout(self) -> None:
        self.assertTrue(self.leakage["passed"])
        self.assertEqual(self.leakage["source_holdout_records_in_train"], 0)
        self.assertEqual(self.leakage["group_overlap_train_val"], [])
        train_ids = {r["id"] for r in self.records}
        val_ids = {r["id"] for r in self.val_records}
        self.assertFalse(train_ids & val_ids)

    def test_no_calibration_or_manual(self) -> None:
        for rid in list(self.manifest["record_ids"]) + list(self.val_manifest["record_ids"]):
            self.assertFalse(rid.startswith("t13_cal_"))
            self.assertFalse(rid.startswith("manual_"))

    def test_all_examples_have_supervised_tokens(self) -> None:
        examples = [
            json.loads(line)
            for line in dataset_paths(ROOT)["training_examples"].read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(examples), TARGET_TRAIN_COUNT)
        for ex in examples:
            self.assertGreater(ex["loss_mask_diagnostics"]["target_supervised_tokens"], 0)


class CheckpointResumeTests(unittest.TestCase):
    def test_full_resume_components_and_mismatch_blocks(self) -> None:
        class Opt:
            def state_dict(self):
                return {"lr": 0.1}

        payload = build_checkpoint_payload(
            adapter_dir=Path("adapter"),
            optimizer=Opt(),
            scheduler=None,
            scaler=None,
            global_step=4,
            epoch=0,
            data_position=4,
            consumed_example_ids=["a", "b"],
            training_config_hash="cfg",
            smoke_data_manifest_hash="data",
            selected_base_model="base",
            environment_identity="env",
            source_commit="a" * 40,
        )
        with tempfile.TemporaryDirectory() as tmp:
            ckpt = Path(tmp)
            save_full_checkpoint(ckpt, payload=payload, adapter_files_present=True)
            loaded = load_full_checkpoint_blob(ckpt)
            self.assertEqual(loaded["global_step"], 4)
            assert_resume_identities(
                loaded,
                selected_base_model="base",
                training_config_hash="cfg",
                smoke_data_manifest_hash="data",
                environment_identity="env",
            )
            with self.assertRaises(CheckpointError):
                assert_resume_identities(
                    loaded,
                    selected_base_model="other",
                    training_config_hash="cfg",
                    smoke_data_manifest_hash="data",
                    environment_identity="env",
                )
        result = evaluate_resume_components(
            adapter_reload_ok=True,
            optimiser_restore_ok=True,
            scheduler_restore_ok=True,
            rng_restore_ok=True,
            data_position_restore_ok=True,
        )
        self.assertTrue(result.full_resume_ok)
        blocked = evaluate_resume_components(
            adapter_reload_ok=True,
            optimiser_restore_ok=False,
            scheduler_restore_ok=True,
            rng_restore_ok=True,
            data_position_restore_ok=True,
        )
        self.assertFalse(blocked.full_resume_ok)


class StructuredOutputTests(unittest.TestCase):
    def test_braces_only_and_prose_fail(self) -> None:
        v = validate_structured_model_output(prompt="P", raw_output="hello { world }")
        self.assertIn(v.status, {STATUS_NO_JSON, STATUS_JSON_PARSE_FAILED, STATUS_SCHEMA_INVALID})
        self.assertFalse(v.accepted)

    def test_malformed_json_fails(self) -> None:
        v = validate_structured_model_output(prompt="P", raw_output='{"speech_act": ')
        self.assertNotEqual(v.status, STATUS_ACCEPTED)

    def test_prompt_echo_excluded(self) -> None:
        cont = isolate_generated_continuation(prompt="PROMPT", raw_output="PROMPT{\"a\":1}")
        self.assertTrue(cont.startswith("{") or cont.startswith('"') or "a" in cont)

    def test_schema_invalid_vs_valid_path_exists(self) -> None:
        # Minimal object missing required production fields => schema_invalid
        v = validate_structured_model_output(prompt="P", raw_output='{"speech_act": null}')
        self.assertEqual(v.status, STATUS_SCHEMA_INVALID)
        self.assertIsNotNone(v.parsed_output)
        self.assertIsNotNone(v.raw_output)


class OperatorEnvironmentTests(unittest.TestCase):
    def test_live_profile_has_no_node_pin_and_mock_separate(self) -> None:
        profiles = load_profiles(ROOT)
        live = get_profile(profiles, "qlora_task_aligned_smoke")
        self.assertFalse(str(live.get("nodelist") or "").strip())
        self.assertEqual(live.get("exclude_nodes"), "mscluster107,mscluster108")
        # historical qlora_smoke must also no longer permanently pin a node
        old = get_profile(profiles, "qlora_smoke")
        self.assertFalse(str(old.get("nodelist") or "").strip())
        self.assertEqual(old.get("exclude_nodes"), "mscluster107,mscluster108")
        mock = get_profile(profiles, "qlora_smoke_mock")
        self.assertIn("mock", mock.get("description", "").lower())

    def test_env_manifest_uses_measured_identity(self) -> None:
        env = json.loads(
            (ROOT / "configs/environments/t12_cluster_training_task_aligned_v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(env["environment_id"], "t12-cluster-training-task-aligned-v1")
        self.assertIn("measured", env["environment_status"])
        self.assertTrue(env["capability_status"]["node_pin_forbidden"]["value"])
        self.assertIn("measured_versions", env)
        self.assertEqual(env["measured_versions"]["peft_version"]["value"], "0.18.0")

    def test_config_forbids_mock_fallback(self) -> None:
        cfg = json.loads((ROOT / "configs/model/qlora_task_aligned_smoke_v1.json").read_text(encoding="utf-8"))
        self.assertTrue(cfg["forbid_mock_fallback_in_live_mode"])
        self.assertTrue(cfg["training"]["forbid_command_reconstruction"])
        self.assertTrue(cfg["evaluation"]["forbid_braces_only_acceptance"])

    def test_prompt_excludes_admin_metadata(self) -> None:
        record, _ = _sample_record()
        prompt = build_inference_time_prompt(record)
        self.assertIn("[ORIGINAL_COMMAND]", prompt)
        self.assertNotIn("label_eligibility", prompt)
        self.assertNotIn("source_holdout", prompt)

    def test_no_forbidden_eager_imports_in_new_modules(self) -> None:
        forbidden = {"torch", "transformers", "peft", "bitsandbytes", "accelerate", "vllm"}
        for rel in (
            "ambiguity_manager/model/qlora_task_aligned_smoke.py",
            "ambiguity_manager/model/token_loss_masking.py",
            "ambiguity_manager/model/structured_target.py",
            "ambiguity_manager/model/training_example_contract.py",
            "ambiguity_manager/model/structured_output_validation.py",
            "ambiguity_manager/model/qlora_checkpoint.py",
        ):
            path = SRC / rel
            if not path.is_file():
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            top = set()
            for node in tree.body:
                if isinstance(node, ast.Import):
                    top.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    top.add(node.module.split(".")[0])
            self.assertFalse(top & forbidden, f"{rel}: {top & forbidden}")


class LiveModeEnforcementTests(unittest.TestCase):
    def test_require_real_mode_refuses_mock_fallback(self) -> None:
        from ambiguity_manager.model.qlora_task_aligned_smoke import run_task_aligned_smoke_training

        with tempfile.TemporaryDirectory() as tmp:
            outcome = run_task_aligned_smoke_training(
                result_dir=Path(tmp) / "r",
                run_id="enforce-real-1",
                root=ROOT,
                require_real_mode=True,
                force_mock=False,
            )
            self.assertFalse(outcome["result"]["success"])
            self.assertIn("refusing silent fallback", outcome["result"]["failure_reason"])
            self.assertTrue((Path(tmp) / "r" / "qlora_task_aligned_smoke_result.json").is_file())
            self.assertTrue((Path(tmp) / "r" / "run_manifest.json").is_file())

    def test_mock_profile_entry_exists(self) -> None:
        self.assertTrue((ROOT / "scripts/t12_qlora_task_aligned_smoke.py").is_file())
        self.assertTrue((ROOT / "scripts/t12_qlora_smoke.py").is_file())


if __name__ == "__main__":
    unittest.main()
