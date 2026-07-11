"""Tests for T12 Stage D-Final cluster generation pipeline runner."""

from __future__ import annotations

import json
import tempfile
import unittest
import unittest.mock as mock
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ambiguity_manager.governance.hashing import sha256_hex
from ambiguity_manager.model.cluster.generation_pipeline_runner import (
    load_d_final_config,
    load_source_identity_manifest,
    run_d_final_smoke,
    validate_d_final_config,
    validate_pipeline_requests_from_records,
    validate_synthetic_records,
    verify_source_identity,
)
from ambiguity_manager.model.generation_pipeline import (
    SEMANTIC_CORRECTNESS_NOT_EVALUATED,
    StructuredDecodeReadiness,
)
from ambiguity_manager.model.structured_decode import (
    StructuredDecodeMetadata,
    load_structured_decode_contract,
    structured_decode_contract_hash,
)
from ambiguity_manager.schema.v2.taxonomies import CPCSlotStatus, RouteLabel

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs/cluster/t12_d_final_smoke.json"
INPUT_PATH = REPO_ROOT / "tests/fixtures/schema_v2/t12_d_final_smoke_inputs.jsonl"
SOURCE_SHA = "ef4e7b0124baac31a77696bb4365535b02c55067"
CONTAINER_SHA = "d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1"


def _preflight(**overrides: object) -> dict[str, Any]:
    payload = {
        "status": "pass",
        "model_repository": "Qwen/Qwen3-8B",
        "model_revision": "b968826d9c46dd6066d109eabc6255188de91218",
        "observed_container_sha256": CONTAINER_SHA,
        "offline_resolution_passed": True,
        "network_fallback": False,
        "snapshot_inventory_status": "pass",
    }
    payload.update(overrides)
    return payload


def _structured_decode_metadata_dict() -> dict[str, Any]:
    contract = load_structured_decode_contract(REPO_ROOT / "configs/model/t12_structured_decode_contract.json")
    return StructuredDecodeMetadata(
        contract_hash=structured_decode_contract_hash(contract),
        schema_hash=contract.semantic_schema_sha256,
        sampling_params_module=contract.sampling_params_module,
        sampling_params_class=contract.sampling_params_class,
        structured_outputs_module=contract.structured_outputs_module,
        structured_outputs_class=contract.structured_outputs_class,
        structured_output_field_name=contract.structured_output_field_name,
        schema_parameter_name=contract.schema_parameter_name,
        required_vllm_version=contract.required_vllm_version,
        detected_vllm_version=contract.required_vllm_version,
        completions_per_request=1,
        construction_status="constructed",
        response_mode_status=contract.response_mode_status,
        engine_time_schema_compilation_status="passed_on_live_generation",
    ).to_dict()


def _readiness() -> StructuredDecodeReadiness:
    contract = load_structured_decode_contract(REPO_ROOT / "configs/model/t12_structured_decode_contract.json")
    metadata = StructuredDecodeMetadata(
        contract_hash=structured_decode_contract_hash(contract),
        schema_hash=contract.semantic_schema_sha256,
        sampling_params_module=contract.sampling_params_module,
        sampling_params_class=contract.sampling_params_class,
        structured_outputs_module=contract.structured_outputs_module,
        structured_outputs_class=contract.structured_outputs_class,
        structured_output_field_name=contract.structured_output_field_name,
        schema_parameter_name=contract.schema_parameter_name,
        required_vllm_version=contract.required_vllm_version,
        detected_vllm_version=contract.required_vllm_version,
        completions_per_request=1,
        construction_status="constructed",
        response_mode_status=contract.response_mode_status,
        engine_time_schema_compilation_status=contract.engine_time_schema_compilation_status,
    )
    return StructuredDecodeReadiness(metadata=metadata)


def _source_identity_bundle(tmp_path: Path) -> tuple[Path, Path]:
    archive = tmp_path / "source.tar.gz"
    archive.write_bytes(b"t12-d-final-test-source-archive")
    manifest_path = tmp_path / "source_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "source_commit_sha": SOURCE_SHA,
                "source_archive_sha256": sha256_hex(archive.read_bytes()),
                "transfer_method": "git_archive",
                "archive_filename": "source.tar.gz",
                "packaging_timestamp": "2026-07-11T22:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    return manifest_path, archive


def _empty_cpc() -> dict[str, Any]:
    slot = {"value": None, "status": CPCSlotStatus.UNKNOWN.value}
    return {name: dict(slot) for name in (
        "action", "actor", "object", "object_attributes", "destination",
        "spatial_relation", "quantity", "time", "recipient", "tool",
        "conditions", "constraints", "negation",
    )}


def _semantic(**overrides: object) -> str:
    payload: dict[str, Any] = {
        "cpc": _empty_cpc(),
        "speech_act": None,
        "intent_summary": None,
        "candidate_interpretations": [],
        "selected_interpretation": None,
        "unresolved_slots": [],
        "supporting_evidence": [],
        "ambiguity_present": False,
        "ambiguity_types": [],
        "primary_ambiguity_type": None,
        "compound_ambiguity": False,
        "compound_ambiguity_count": 0,
        "risk_relevant": False,
        "risk_level": None,
        "capability_status": None,
        "recommended_strategy": RouteLabel.EXECUTE.value,
        "strategy_sequence": [],
        "clarification_question": None,
        "clarification_subtype": None,
        "clarification_targets": [],
        "rejection_reason": None,
        "resolved_slots": [],
        "resolution_method": None,
        "resolution_evidence": [],
        "context_sampling_uncertainty": None,
    }
    payload.update(overrides)
    return json.dumps(payload, sort_keys=True)


def _record_output(record_id: str) -> str:
    if record_id == "dfinal-001":
        return _semantic(recommended_strategy=RouteLabel.EXECUTE.value)
    if record_id == "dfinal-002":
        return _semantic(
            recommended_strategy=RouteLabel.CLARIFY.value,
            ambiguity_present=True,
            clarification_question="Which cup should I pick up?",
            clarification_targets=["object"],
        )
    if record_id == "dfinal-003":
        return _semantic(
            recommended_strategy=RouteLabel.CLARIFY.value,
            ambiguity_present=True,
            clarification_question="Which mug should I bring?",
            clarification_targets=["object"],
        )
    if record_id == "dfinal-004":
        return _semantic(
            recommended_strategy=RouteLabel.MULTI_STEP.value,
            ambiguity_present=True,
            ambiguity_types=["temporal", "referential"],
            primary_ambiguity_type="temporal",
            compound_ambiguity=True,
            compound_ambiguity_count=2,
            strategy_sequence=[RouteLabel.EXECUTE.value, RouteLabel.EXECUTE.value],
        )
    raise KeyError(record_id)


@dataclass
class FakeTokenizer:
    def apply_chat_template(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        suffix = "|enable_thinking=False" if kwargs.get("enable_thinking") is False else ""
        body = "\n".join(f"{item['role']}: {item['content']}" for item in messages)
        if kwargs.get("add_generation_prompt"):
            body += "\nassistant:"
        return body + suffix


@dataclass
class FakeBackend:
    started: bool = False
    start_calls: int = 0
    close_calls: int = 0
    _last_structured_decode_metadata: dict[str, Any] = field(default_factory=_structured_decode_metadata_dict)

    @property
    def last_structured_decode_metadata(self) -> dict[str, Any] | None:
        return self._last_structured_decode_metadata

    def start(self) -> None:
        self.start_calls += 1
        self.started = True

    def close(self) -> None:
        self.close_calls += 1
        self.started = False

    def generate_batch(self, requests: list[Any]) -> list[Any]:
        from ambiguity_manager.model.backends.vllm_batch import BatchGenerationResult

        results = []
        for request in requests:
            results.append(
                BatchGenerationResult(
                    request_id=request.request_id,
                    ordinal=request.ordinal,
                    raw_text=_semantic(),
                    backend_identifier="fake",
                    model_repository="Qwen/Qwen3-8B",
                    model_revision="b968826d9c46dd6066d109eabc6255188de91218",
                    generation_status="success",
                    finish_reason="stop",
                    prompt_tokens=10,
                    completion_tokens=5,
                    latency_ms=1.0,
                    error_type=None,
                    error_message=None,
                    metadata={},
                    config_hash="c" * 64,
                    engine_request_id="engine-1",
                )
            )
        return results


class T12ClusterGenerationPipelineRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_d_final_config(CONFIG_PATH, root=REPO_ROOT)

    def _run(self, tmp_path: Path, **overrides: Any):
        manifest_path, archive = _source_identity_bundle(tmp_path)
        backend = FakeBackend()
        defaults: dict[str, Any] = {
            "run_dir": tmp_path / "run-test",
            "preflight_result": _preflight(),
            "config": self.config,
            "root": REPO_ROOT,
            "source_identity_manifest_path": manifest_path,
            "source_archive": archive,
            "extracted_source_root": tmp_path / "extracted",
            "slurm_log_path": "/cluster/logs/t12-d-final-smoke.log",
            "backend_factory": lambda *_args, **_kwargs: backend,
            "tokenizer_factory": lambda **_kwargs: FakeTokenizer(),
            "probe_generator": lambda **_kwargs: _semantic(),
            "record_generator": lambda record_id, **_kwargs: _record_output(record_id),
            "structured_decode_readiness_override": _readiness(),
            "measurement_timestamp": "2026-07-11T22:00:00Z",
            "snapshot_path": tmp_path / "tokenizer",
        }
        defaults.update(overrides)
        (tmp_path / "extracted").mkdir(exist_ok=True)
        return run_d_final_smoke(**defaults)

    def test_committed_config_has_no_concrete_source_commit(self) -> None:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertNotIn("source_commit_sha", payload)
        self.assertEqual(payload["source_identity_mode"], "runtime_source_manifest_required")

    def test_extracted_source_without_git_passes_source_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path, archive = _source_identity_bundle(tmp_path)
            extracted = tmp_path / "extracted"
            extracted.mkdir()
            manifest = load_source_identity_manifest(manifest_path)
            identity, rejections = verify_source_identity(
                manifest,
                archive,
                extracted_root=extracted,
            )
            self.assertEqual(rejections, [])
            self.assertEqual(identity["source_commit_sha"], SOURCE_SHA)

    def test_archive_hash_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path, archive = _source_identity_bundle(tmp_path)
            archive.write_bytes(b"tampered")
            manifest = load_source_identity_manifest(manifest_path)
            _, rejections = verify_source_identity(manifest, archive)
            self.assertIn("source_archive_hash_mismatch", rejections)

    def test_malformed_source_manifest_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_manifest = Path(tmp) / "bad.json"
            bad_manifest.write_text('{"schema_version":"1.0.0"}', encoding="utf-8")
            with self.assertRaises(Exception):
                load_source_identity_manifest(bad_manifest)

    def test_invalid_commit_sha_blocks(self) -> None:
        errors = validate_d_final_config(
            {
                **json.loads(CONFIG_PATH.read_text(encoding="utf-8")),
                "source_commit_sha": "not-a-sha",
            },
            root=REPO_ROOT,
        )
        self.assertTrue(any("source_commit_sha" in item for item in errors))

    def test_exactly_four_synthetic_records_required(self) -> None:
        records = [
            json.loads(line)
            for line in INPUT_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        errors = validate_synthetic_records(records, config=self.config)
        self.assertEqual(errors, [])
        self.assertEqual(len(records), 4)

    def test_all_valid_requests_prebuilt_before_engine_startup(self) -> None:
        records = [
            json.loads(line)
            for line in INPUT_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        requests, errors = validate_pipeline_requests_from_records(
            records,
            container_sha=CONTAINER_SHA,
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(requests), 4)

    def test_null_provenance_blocks_before_startup(self) -> None:
        record = json.loads(INPUT_PATH.read_text(encoding="utf-8").splitlines()[0])
        record["provenance_policy"] = None
        _, errors = validate_pipeline_requests_from_records([record], container_sha=CONTAINER_SHA)
        self.assertTrue(errors)

    def test_missing_provenance_field_blocks(self) -> None:
        record = json.loads(INPUT_PATH.read_text(encoding="utf-8").splitlines()[0])
        del record["provenance_policy"]["policy_version"]
        _, errors = validate_pipeline_requests_from_records([record], container_sha=CONTAINER_SHA)
        self.assertTrue(errors)

    def test_missing_eligibility_flag_blocks(self) -> None:
        record = json.loads(INPUT_PATH.read_text(encoding="utf-8").splitlines()[0])
        del record["label_eligibility"]["routing"]
        _, errors = validate_pipeline_requests_from_records([record], container_sha=CONTAINER_SHA)
        self.assertTrue(errors)

    def test_non_boolean_eligibility_blocks(self) -> None:
        record = json.loads(INPUT_PATH.read_text(encoding="utf-8").splitlines()[0])
        record["label_eligibility"]["routing"] = "yes"
        _, errors = validate_pipeline_requests_from_records([record], container_sha=CONTAINER_SHA)
        self.assertTrue(errors)

    def test_unknown_eligibility_flag_blocks(self) -> None:
        record = json.loads(INPUT_PATH.read_text(encoding="utf-8").splitlines()[0])
        record["label_eligibility"]["extra_flag"] = True
        _, errors = validate_pipeline_requests_from_records([record], container_sha=CONTAINER_SHA)
        self.assertTrue(errors)

    def test_malformed_integrity_context_blocks(self) -> None:
        record = json.loads(INPUT_PATH.read_text(encoding="utf-8").splitlines()[0])
        record["integrity_context"] = {"support_declarations": "bad"}
        _, errors = validate_pipeline_requests_from_records([record], container_sha=CONTAINER_SHA)
        self.assertTrue(errors)

    def test_existing_run_directory_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            run_dir = tmp_path / "run-test"
            run_dir.mkdir()
            result = self._run(tmp_path)
            self.assertEqual(result.status, "BLOCKED")
            self.assertIn("run_directory_exists", result.rejection_reasons)

    def test_non_synthetic_record_blocks_before_engine_startup(self) -> None:
        bad_records = [{"record_id": "x", "synthetic": False, "ordinal": 0}]
        errors = validate_synthetic_records(bad_records, config=self.config)
        self.assertTrue(errors)

    def test_response_probe_occurs_before_record_pipeline(self) -> None:
        from ambiguity_manager.model.generation_pipeline import GenerationPipelineResult

        call_order: list[str] = []

        def _probe_gen(**_kwargs: object) -> str:
            call_order.append("probe")
            return _semantic()

        def _record_gen(record_id: str, **_kwargs: object) -> str:
            call_order.append(f"record:{record_id}")
            return _record_output(record_id)

        def _fake_pipeline(*_args, **_kwargs):
            call_order.append("pipeline")
            return GenerationPipelineResult(
                request_id="pred:dfinal-001",
                final_status="accepted",
                accepted_canonical_prediction={"id": "pred:dfinal-001", "command": "x"},
                attempt_entries=(),
                attempts_used=1,
                attempts_exhausted=False,
                failure_categories=(),
                failure_reasons=(),
                semantic_schema_hash="a" * 64,
                structured_decode_contract_hash="b" * 64,
                caller_command_hash="c" * 64,
                integrity_context_hash="d" * 64,
                accepted_raw_attempt_index=0,
            )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path, archive = _source_identity_bundle(tmp_path)
            (tmp_path / "extracted").mkdir()
            with mock.patch(
                "ambiguity_manager.model.cluster.generation_pipeline_runner.run_generation_pipeline",
                side_effect=_fake_pipeline,
            ):
                run_d_final_smoke(
                    run_dir=tmp_path / "run-test",
                    preflight_result=_preflight(),
                    config=self.config,
                    root=REPO_ROOT,
                    source_identity_manifest_path=manifest_path,
                    source_archive=archive,
                    extracted_source_root=tmp_path / "extracted",
                    slurm_log_path="/cluster/logs/t12-d-final-smoke.log",
                    backend_factory=lambda *_a, **_k: FakeBackend(),
                    tokenizer_factory=lambda **_k: FakeTokenizer(),
                    probe_generator=_probe_gen,
                    record_generator=_record_gen,
                    structured_decode_readiness_override=_readiness(),
                    measurement_timestamp="2026-07-11T22:00:00Z",
                    snapshot_path=tmp_path / "tokenizer",
                )
        self.assertIn("probe", call_order)
        self.assertIn("pipeline", call_order)
        self.assertLess(call_order.index("probe"), call_order.index("pipeline"))

    def test_no_passing_response_mode_blocks_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                Path(tmp),
                probe_generator=lambda **_kwargs: "not-json",
            )
            self.assertEqual(result.status, "BLOCKED")
            self.assertIn("no_passing_response_mode", result.rejection_reasons)
            run_dir = Path(tmp) / "run-test"
            self.assertTrue((run_dir / "raw_attempts.jsonl").is_file())
            self.assertTrue((run_dir / "run_manifest.json").is_file())

    def test_same_selected_mode_used_for_all_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(Path(tmp))
            self.assertIn(result.response_mode, ("default", "enable_thinking_false"))
            probe = json.loads((Path(tmp) / "run-test" / "response_mode_probe.json").read_text())
            self.assertEqual(probe["selected_mode"], result.response_mode)

    def test_one_engine_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            backend = FakeBackend()
            manifest_path, archive = _source_identity_bundle(tmp_path)
            (tmp_path / "extracted").mkdir()
            run_d_final_smoke(
                run_dir=tmp_path / "run-test",
                preflight_result=_preflight(),
                config=self.config,
                root=REPO_ROOT,
                source_identity_manifest_path=manifest_path,
                source_archive=archive,
                extracted_source_root=tmp_path / "extracted",
                slurm_log_path="/cluster/logs/t12-d-final-smoke.log",
                backend_factory=lambda *_a, **_k: backend,
                tokenizer_factory=lambda **_k: FakeTokenizer(),
                probe_generator=lambda **_k: _semantic(),
                record_generator=lambda record_id, **_k: _record_output(record_id),
                structured_decode_readiness_override=_readiness(),
                measurement_timestamp="2026-07-11T22:00:00Z",
                snapshot_path=tmp_path / "tokenizer",
            )
            self.assertEqual(backend.start_calls, 1)

    def test_raw_attempts_always_retained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._run(Path(tmp))
            raw_path = Path(tmp) / "run-test" / "raw_attempts.jsonl"
            self.assertTrue(raw_path.is_file())
            lines = [line for line in raw_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4)

    def test_invalid_final_prediction_prevents_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                Path(tmp),
                record_generator=lambda **_k: '{"cpc": {}}',
            )
            self.assertEqual(result.status, "BLOCKED")

    def test_unsupported_commitment_prevents_pass(self) -> None:
        silent = _semantic(
            recommended_strategy=RouteLabel.SILENTLY_RESOLVE.value,
            resolved_slots=[{"slot_name": "object", "value": "mug"}],
            resolution_method="context_supported",
            resolution_evidence=[{"source": "scene_context", "span": "mug", "note": None}],
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                Path(tmp),
                record_generator=lambda record_id, **_k: (
                    silent if record_id == "dfinal-003" else _record_output(record_id)
                ),
            )
            self.assertEqual(result.status, "BLOCKED")

    def test_semantic_correctness_remains_not_evaluated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(Path(tmp))
            self.assertEqual(result.semantic_correctness_status, SEMANTIC_CORRECTNESS_NOT_EVALUATED)
            summary = json.loads((Path(tmp) / "run-test" / "summary.json").read_text())
            self.assertEqual(summary["semantic_correctness_status"], SEMANTIC_CORRECTNESS_NOT_EVALUATED)

    def test_manifest_hashes_match_output_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._run(Path(tmp))
            run_dir = Path(tmp) / "run-test"
            manifest = json.loads((run_dir / "run_manifest.json").read_text())
            for filename, entry in manifest["output_file_hashes"].items():
                observed = sha256_hex((run_dir / filename).read_bytes())
                self.assertEqual(entry["sha256"], observed)

    def test_slurm_log_path_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._run(Path(tmp))
            manifest = json.loads((Path(tmp) / "run-test" / "run_manifest.json").read_text())
            self.assertEqual(manifest["slurm_log_path"], "/cluster/logs/t12-d-final-smoke.log")

    def test_source_identity_in_final_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._run(Path(tmp))
            manifest = json.loads((Path(tmp) / "run-test" / "run_manifest.json").read_text())
            self.assertIn("source_identity", manifest)
            self.assertEqual(manifest["source_identity"]["source_commit_sha"], SOURCE_SHA)

    def test_blocked_run_files_are_hashed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(Path(tmp), probe_generator=lambda **_k: "bad")
            self.assertEqual(result.status, "BLOCKED")
            manifest = json.loads((Path(tmp) / "run-test" / "run_manifest.json").read_text())
            self.assertIn("response_mode_probe.json", manifest["output_file_hashes"])

    def test_full_pass_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(Path(tmp))
            self.assertEqual(result.status, "PASS")
            self.assertEqual(result.accepted_count, 4)
            manifest = json.loads((Path(tmp) / "run-test" / "run_manifest.json").read_text())
            self.assertIn("response_mode_verification.json", manifest["output_file_hashes"])


if __name__ == "__main__":
    unittest.main()
