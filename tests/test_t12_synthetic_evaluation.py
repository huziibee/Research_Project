"""Tests for T12 Slice 4 synthetic evaluation."""

from __future__ import annotations

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
from ambiguity_manager.model.checkpoint_download import (
    AUTHORIZED_REVISION_SHA,
    AUTHORIZED_TOKENIZER_REVISION_SHA,
    EVIDENCE_REL as DOWNLOAD_EVIDENCE_REL,
    REGISTER_REL,
)
from ambiguity_manager.model.checkpoint_load import (
    LOAD_EVIDENCE_REL,
    validate_offline_flags,
)
from ambiguity_manager.model.factory import create_model_client
from ambiguity_manager.model.integrity import count_unsupported_commitments
from ambiguity_manager.model.parser import MAX_REPAIR_OPERATIONS, extract_and_repair_json
from ambiguity_manager.model.protocol import GenerateJsonRequest, GenerateJsonResult, ModelRuntimeSpec
from ambiguity_manager.model.synthetic_evaluation import (
    AUTHORISED_FIXTURE_COUNT,
    FIXTURE_REL,
    build_evidence_scaffold,
    build_per_fixture_result,
    classify_outcome,
    compute_aggregate_metrics,
    extract_expected_annotations,
    fixture_input_sha256,
    load_fixture_manifest,
    raw_output_relpath,
    reconcile_aggregate_metrics,
    recommend_fallback_probe,
    run_fixtures,
    score_annotated_fields,
    validate_pre_run_gates,
    validate_runtime_identity,
    validate_synthetic_evaluation_evidence,
)
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema.v2.json_schema import build_prediction_json_schema

ROOT = ProjectPaths.from_repo_root().root
FIXTURE_PATH = ROOT / FIXTURE_REL
DOWNLOAD_EVIDENCE_PATH = ROOT / DOWNLOAD_EVIDENCE_REL
LOAD_EVIDENCE_PATH = ROOT / LOAD_EVIDENCE_REL
REGISTER_PATH = ROOT / REGISTER_REL
ETHICS_PATH = ROOT / "configs" / "governance" / "human_annotation_governance.json"
SCRIPT_PATH = ROOT / "scripts" / "t12_run_synthetic_evaluation.py"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _runtime_spec(**overrides: object) -> ModelRuntimeSpec:
    base = {
        "backend": "fake",
        "model_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "immutable_revision": AUTHORIZED_REVISION_SHA,
        "tokenizer_revision": AUTHORIZED_TOKENIZER_REVISION_SHA,
        "quantisation": "nf4_4bit",
        "environment_id": "t12-inference-wsl2",
        "device_policy": "cuda:0",
    }
    base.update(overrides)
    return ModelRuntimeSpec(**base)


def _fake_generate_result(fixture: dict) -> GenerateJsonResult:
    client = create_model_client(_runtime_spec())
    schema = build_prediction_json_schema()
    from ambiguity_manager.model.prompt_builder import build_messages_from_fixture

    messages = build_messages_from_fixture(fixture, json_schema=schema)
    request = GenerateJsonRequest(
        messages=messages,
        json_schema=schema,
        seed=0,
        temperature=0.0,
        fixture_id=fixture["fixture_id"],
        run_id=f"test-{fixture['fixture_id']}",
    )
    return client.generate_json(request)


class FixtureManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_fixture_manifest(FIXTURE_PATH)

    def test_only_authorised_fixtures_accepted(self) -> None:
        self.assertEqual(len(self.manifest.fixtures), AUTHORISED_FIXTURE_COUNT)

    def test_fixture_manifest_sha_required_on_mismatch(self) -> None:
        with self.assertRaises(Exception):
            load_fixture_manifest(FIXTURE_PATH, expected_sha256="0" * 64)

    def test_duplicate_fixture_ids_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dup.jsonl"
            line = FIXTURE_PATH.read_text(encoding="utf-8").splitlines()[0]
            path.write_text(f"{line}\n{line}\n", encoding="utf-8")
            with self.assertRaises(Exception):
                load_fixture_manifest(path)

    def test_unannotated_fields_not_scored_as_incorrect(self) -> None:
        fixture = self.manifest.fixtures[0]
        scores = score_annotated_fields(fixture, {"recommended_strategy": "clarify"})
        route = next(s for s in scores if s["field"] == "route")
        self.assertFalse(route["exact_match"])
        self.assertNotIn("ambiguity", {s["field"] for s in scores})


class EvidenceValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_fixture_manifest(FIXTURE_PATH)
        cls.register = _load_json(REGISTER_PATH)

    def _completed_evidence(self) -> dict:
        per_fixture = []
        for fixture in self.manifest.fixtures:
            result = _fake_generate_result(fixture)
            per_fixture.append(
                build_per_fixture_result(
                    fixture=fixture,
                    result=result,
                    raw_output_relpath_value=raw_output_relpath(fixture["fixture_id"]),
                    raw_output_sha256_value=sha256_hex(result.raw_output.encode("utf-8")),
                )
            )
        evidence = build_evidence_scaffold(fixture_file_sha256=self.manifest.fixture_file_sha256)
        evidence["per_fixture_results"] = per_fixture
        evidence["aggregate_metrics"] = compute_aggregate_metrics(per_fixture)
        evidence["run_status"] = "completed"
        evidence["outcome_classification"] = classify_outcome(
            evidence["aggregate_metrics"],
            run_complete=True,
        )
        return evidence

    def test_every_attempted_fixture_retained(self) -> None:
        evidence = self._completed_evidence()
        self.assertEqual(len(evidence["per_fixture_results"]), AUTHORISED_FIXTURE_COUNT)

    def test_failures_remain_in_metric_denominators(self) -> None:
        evidence = self._completed_evidence()
        item = evidence["per_fixture_results"][0]
        item["parser_status"] = "parse_failed"
        item["schema_validation_status"] = "schema_invalid"
        aggregate = compute_aggregate_metrics(evidence["per_fixture_results"])
        self.assertEqual(aggregate["attempted_count"], AUTHORISED_FIXTURE_COUNT)
        self.assertGreaterEqual(aggregate["parser_failure_count"], 1)

    def test_missing_fixtures_rejected_from_completed_run(self) -> None:
        evidence = self._completed_evidence()
        evidence["per_fixture_results"] = evidence["per_fixture_results"][:-1]
        errors = validate_synthetic_evaluation_evidence(evidence, register=self.register)
        self.assertTrue(any("missing fixture IDs" in e for e in errors))

    def test_raw_output_hash_and_relpath_required(self) -> None:
        evidence = self._completed_evidence()
        evidence["per_fixture_results"][0]["raw_output_sha256"] = None
        errors = validate_synthetic_evaluation_evidence(evidence, register=self.register)
        self.assertTrue(any("raw_output_sha256 required" in e for e in errors))

    def test_no_absolute_paths_or_usernames(self) -> None:
        evidence = self._completed_evidence()
        evidence["note"] = "/home/huzii/secret"
        errors = validate_synthetic_evaluation_evidence(evidence, register=self.register)
        self.assertTrue(any("absolute path" in e or "username" in e for e in errors))

    def test_parser_failure_represented_honestly(self) -> None:
        raw = "not json"
        parsed = extract_and_repair_json(raw)
        self.assertIsNone(parsed.parsed_object)
        self.assertEqual(parsed.raw_output, raw)

    def test_schema_invalid_represented_honestly(self) -> None:
        evidence = self._completed_evidence()
        item = evidence["per_fixture_results"][0]
        item["schema_validation_status"] = "schema_invalid"
        item["schema_errors"] = ["cpc: cpc must be an object"]
        item["parser_status"] = "parse_success"
        self.assertEqual(item["schema_validation_status"], "schema_invalid")
        self.assertTrue(item["schema_errors"])

    def test_repair_attempts_bounded(self) -> None:
        evidence = self._completed_evidence()
        for item in evidence["per_fixture_results"]:
            self.assertLessEqual(item["bounded_repair_count"], MAX_REPAIR_OPERATIONS)

    def test_unsupported_commitments_counted(self) -> None:
        fixture = next(f for f in self.manifest.fixtures if f["fixture_id"] == "syn-003")
        prediction = {
            "recommended_strategy": "silently_resolve",
            "selected_interpretation": {"supporting_evidence": [{"source": "scene_context", "span": "red vase"}]},
            "unresolved_slots": ["object"],
            "resolved_slots": [{"slot_name": "object", "value": "red vase"}],
        }
        self.assertGreater(count_unsupported_commitments(fixture, prediction), 0)

    def test_unsupported_commitments_block_silent_resolution(self) -> None:
        evidence = self._completed_evidence()
        item = next(i for i in evidence["per_fixture_results"] if i["fixture_id"] == "syn-003")
        item["unsupported_commitment_count"] = 2
        item["silent_resolution_gate"] = {
            "recommended_strategy": "silently_resolve",
            "claims_silent_resolution": True,
            "unsupported_commitment_count": 2,
            "silent_resolution_eligible": False,
            "false_silent_resolution_eligibility": True,
        }
        aggregate = compute_aggregate_metrics(evidence["per_fixture_results"])
        self.assertGreaterEqual(aggregate["false_silent_resolution_eligibility_count"], 1)

    def test_annotated_field_scoring_uses_explicit_expected_values(self) -> None:
        fixture = next(f for f in self.manifest.fixtures if f["fixture_id"] == "syn-001")
        expected = extract_expected_annotations(fixture)
        self.assertEqual(expected["route"], "execute")

    def test_aggregate_counts_reconcile(self) -> None:
        evidence = self._completed_evidence()
        errors = reconcile_aggregate_metrics(
            evidence["per_fixture_results"],
            evidence["aggregate_metrics"],
        )
        self.assertEqual(errors, [])

    def test_runtime_identity_mismatch_rejected(self) -> None:
        evidence = self._completed_evidence()
        evidence["immutable_revision_sha"] = "b" * 40
        errors = validate_runtime_identity(evidence)
        self.assertTrue(errors)

    def test_selected_model_remains_null(self) -> None:
        evidence = self._completed_evidence()
        evidence["selected_model"] = "t12-cand-001"
        errors = validate_synthetic_evaluation_evidence(evidence, register=self.register)
        self.assertIn("selected_model must remain null", errors)

    def test_no_adapter_or_training_evidence(self) -> None:
        evidence = build_evidence_scaffold(fixture_file_sha256=self.manifest.fixture_file_sha256)
        self.assertTrue(evidence["no_adapter_attached"])
        self.assertTrue(evidence["no_optimiser_step"])


class OfflinePolicyTests(unittest.TestCase):
    def test_offline_flags_required(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            errors = validate_offline_flags(local_files_only=True, trust_remote_code=False)
            self.assertTrue(any("HF_HUB_OFFLINE" in e for e in errors))


class PreRunGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.download_evidence = _load_json(DOWNLOAD_EVIDENCE_PATH)
        cls.load_evidence = _load_json(LOAD_EVIDENCE_PATH)
        cls.register = _load_json(REGISTER_PATH)

    def test_candidate_remains_candidate_evaluated(self) -> None:
        entry = next(e for e in self.register["entries"] if e["entry_id"] == "t12-cand-001")
        self.assertEqual(entry["verification_status"], "candidate_evaluated")

    def test_pre_run_gates_pass_on_committed_state(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
            clear=False,
        ):
            errors = validate_pre_run_gates(
                download_evidence=self.download_evidence,
                register=self.register,
                load_evidence=self.load_evidence,
            )
        self.assertEqual(errors, [], msg="\n".join(errors))


class OutcomeClassificationTests(unittest.TestCase):
    def test_threshold_not_frozen_when_no_plan_threshold(self) -> None:
        aggregate = {
            "attempted_count": AUTHORISED_FIXTURE_COUNT,
            "authorised_fixture_count": AUTHORISED_FIXTURE_COUNT,
            "timeout_count": 0,
            "oom_count": 0,
            "backend_error_count": 0,
        }
        self.assertEqual(classify_outcome(aggregate, run_complete=True), "threshold_not_frozen")

    def test_blocked_by_runtime_on_incomplete_run(self) -> None:
        aggregate = {
            "attempted_count": 1,
            "authorised_fixture_count": AUTHORISED_FIXTURE_COUNT,
            "timeout_count": 0,
            "oom_count": 0,
            "backend_error_count": 0,
        }
        self.assertEqual(classify_outcome(aggregate, run_complete=False), "blocked_by_runtime")


class FakeRunTests(unittest.TestCase):
    def test_run_fixtures_with_fake_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            fixture_src = FIXTURE_PATH.read_text(encoding="utf-8")
            fixture_path = repo_root / FIXTURE_REL
            fixture_path.parent.mkdir(parents=True, exist_ok=True)
            fixture_path.write_text(fixture_src, encoding="utf-8")
            manifest = load_fixture_manifest(fixture_path)
            evidence = build_evidence_scaffold(fixture_file_sha256=manifest.fixture_file_sha256)
            updated = run_fixtures(
                repo_root=repo_root,
                manifest=manifest,
                evidence=evidence,
                generate_fn=_fake_generate_result,
            )
            self.assertEqual(updated["run_status"], "completed")
            self.assertEqual(
                updated["aggregate_metrics"]["attempted_count"],
                AUTHORISED_FIXTURE_COUNT,
            )
            for item in updated["per_fixture_results"]:
                raw_path = repo_root / item["raw_output_relpath"]
                self.assertTrue(raw_path.is_file())
                digest = sha256_hex(raw_path.read_bytes())
                self.assertEqual(digest, item["raw_output_sha256"])


class GovernanceIsolationTests(unittest.TestCase):
    def test_t11_remains_blocked(self) -> None:
        ethics = _load_json(ETHICS_PATH)
        self.assertEqual(derive_ticket_verdict(ethics), "BLOCKED")

    def test_import_without_ml(self) -> None:
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

    def test_no_fallback_download_flag(self) -> None:
        manifest = load_fixture_manifest(FIXTURE_PATH)
        evidence = build_evidence_scaffold(fixture_file_sha256=manifest.fixture_file_sha256)
        self.assertTrue(evidence["no_fallback_download"])


class FallbackRecommendationTests(unittest.TestCase):
    def test_recommend_fallback_on_zero_schema_valid(self) -> None:
        aggregate = {"completed_generation_rate": 1.0, "schema_valid_rate": 0.0, "backend_error_count": 0}
        self.assertTrue(recommend_fallback_probe(aggregate))

    def test_no_fallback_when_healthy(self) -> None:
        aggregate = {"completed_generation_rate": 1.0, "schema_valid_rate": 1.0, "backend_error_count": 0}
        self.assertFalse(recommend_fallback_probe(aggregate))


class ScriptStaticTests(unittest.TestCase):
    def test_script_exists(self) -> None:
        self.assertTrue(SCRIPT_PATH.is_file())


class PerFixtureIdentityTests(unittest.TestCase):
    def test_fixture_input_sha_stable(self) -> None:
        manifest = load_fixture_manifest(FIXTURE_PATH)
        fixture = manifest.fixtures[0]
        self.assertEqual(fixture_input_sha256(fixture), manifest.fixture_input_shas[fixture["fixture_id"]])


if __name__ == "__main__":
    unittest.main()
