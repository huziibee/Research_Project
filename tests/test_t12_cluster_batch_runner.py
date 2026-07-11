"""CPU-only tests for T12 cluster batch runner orchestration (Stage C2A)."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ambiguity_manager.model.cluster.identities import _EXPECTED
from ambiguity_manager.model.cluster.run_state import ResumeIdentity, ShardRunDecision, evaluate_resume, load_manifest
from ambiguity_manager.paths import ProjectPaths
from tests.test_t12_vllm_batch_backend import FakeEngine

ROOT = ProjectPaths.from_repo_root().root
CONTAINER_SHA = _EXPECTED["container_sha256"]
MODEL_REVISION = _EXPECTED["model_revision"]


@dataclass
class FakeBatchResult:
    request_id: str
    ordinal: int
    raw_text: str
    generation_status: str = "success"
    finish_reason: str | None = "stop"
    prompt_tokens: int | None = 1
    completion_tokens: int | None = 2
    latency_ms: float | None = 1.0
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    backend_identifier: str = "fake-batch"
    model_repository: str = _EXPECTED["model_repository"]
    model_revision: str = MODEL_REVISION
    config_hash: str = "backend-hash"


class FakeBatchBackend:
    instances: list["FakeBatchBackend"] = []

    def __init__(self, **_kwargs: Any) -> None:
        self.start_calls = 0
        self.batch_calls = 0
        self.closed = False
        FakeBatchBackend.instances.append(self)

    @property
    def lifecycle_state(self) -> str:
        return "started" if self.start_calls else "created"

    def start(self) -> None:
        self.start_calls += 1

    def close(self) -> None:
        self.closed = True

    def generate_batch(self, requests: list[Any]) -> list[FakeBatchResult]:
        self.batch_calls += 1
        return [
            FakeBatchResult(
                request_id=req.request_id,
                ordinal=req.ordinal,
                raw_text=f"generated:{req.prompt}",
                metadata=dict(getattr(req, "metadata", {})),
            )
            for req in requests
        ]


def _preflight_pass(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "pass",
        "container_sha_verification_method": "full_sha256",
        "observed_container_sha256": CONTAINER_SHA,
        "model_revision": MODEL_REVISION,
        "model_repository": _EXPECTED["model_repository"],
    }
    payload.update(overrides)
    return payload


def _preflight_sidecar_fail() -> dict[str, Any]:
    return _preflight_pass(container_sha_verification_method="sidecar_sha256")


def _runtime_config_path(base: Path) -> Path:
    path = base / "runtime.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "backend_identifier": "fake-batch",
                "references": {
                    "immutable_selection": "configs/model/immutable_selection.json",
                    "inference_environment": "configs/environments/t12_cluster_inference.json",
                },
                "batch_size": 2,
                "generation": {
                    "temperature": 0.1,
                    "top_p": 1.0,
                    "max_tokens": 128,
                    "verification_status": "unverified_until_stage_c2b",
                },
                "engine": {
                    "tensor_parallel_size": 1,
                    "gpu_memory_utilization": 0.9,
                    "verification_status": "unverified_until_stage_c2b",
                },
                "offline_only": True,
                "network_fallback_permitted": False,
            }
        ),
        encoding="utf-8",
    )
    return path


def _synthetic_declaration(base: Path) -> Path:
    path = base / "synthetic.json"
    path.write_text(json.dumps({"synthetic": True}), encoding="utf-8")
    return path


def _input_jsonl(base: Path) -> Path:
    path = base / "input.jsonl"
    records = [
        {
            "fixture_id": "syn-001",
            "rendered_prompt": "prompt one",
            "synthetic": True,
            "ordinal": 0,
        },
        {
            "fixture_id": "syn-002",
            "rendered_prompt": "prompt two",
            "synthetic": True,
            "ordinal": 1,
        },
        {
            "fixture_id": "syn-003",
            "rendered_prompt": "prompt three",
            "synthetic": True,
            "ordinal": 2,
        },
    ]
    path.write_text("\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")
    return path


def _shard_plan(base: Path, input_path: Path) -> Path:
    from ambiguity_manager.model.cluster.sharding import plan_shards_from_jsonl, plan_to_canonical_json

    plan = plan_shards_from_jsonl(
        input_path,
        id_field="fixture_id",
        shard_count=2,
        created_timestamp="2026-07-11T19:00:00Z",
        input_source=str(input_path),
    )
    path = base / "plan.json"
    path.write_text(plan_to_canonical_json(plan) + "\n", encoding="utf-8")
    return path


class T12ClusterBatchRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeBatchBackend.instances.clear()
        FakeEngine.instances.clear()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.base = Path(self._tmpdir.name)
        self.run_dir = self.base / "runs" / "run-001"
        self.run_dir.mkdir(parents=True)
        self.input_path = _input_jsonl(self.base)
        self.plan_path = _shard_plan(self.base, self.input_path)
        self.runtime_path = _runtime_config_path(self.base)
        self.declaration_path = _synthetic_declaration(self.base)
        from ambiguity_manager.model.cluster import batch_runner

        self.batch_runner = batch_runner

    def _run(self, shard_id: str = "shard-000", **kwargs: Any):
        return self.batch_runner.run_shard_batch(
            repo_root=ROOT,
            runtime_config_path=kwargs.get("runtime_config_path", self.runtime_path),
            shard_plan_path=kwargs.get("shard_plan_path", self.plan_path),
            shard_id=shard_id,
            run_dir=self.run_dir,
            preflight_result=kwargs.get("preflight_result", _preflight_pass()),
            synthetic_declaration_path=kwargs.get(
                "synthetic_declaration_path", self.declaration_path
            ),
            input_jsonl_path=kwargs.get("input_jsonl_path", self.input_path),
            backend_factory=kwargs.get("backend_factory", lambda **_k: FakeBatchBackend()),
            start_timestamp=kwargs.get("start_timestamp", "2026-07-11T19:00:00Z"),
            end_timestamp=kwargs.get("end_timestamp", "2026-07-11T19:01:00Z"),
        )

    def test_preflight_failure_prevents_backend_startup(self) -> None:
        result = self._run(preflight_result={"status": "fail", "rejection_reasons": ["x"]})
        self.assertEqual(result.status, "fail")
        self.assertIn("preflight_not_pass", result.rejection_reasons)
        self.assertEqual(len(FakeBatchBackend.instances), 0)

    def test_sidecar_only_integrity_prevents_backend_startup(self) -> None:
        result = self._run(preflight_result=_preflight_sidecar_fail())
        self.assertEqual(result.status, "fail")
        self.assertIn("container_integrity_not_full_sha256", result.rejection_reasons)
        self.assertEqual(len(FakeBatchBackend.instances), 0)

    def test_full_sha_preflight_permits_fake_backend_startup(self) -> None:
        result = self._run()
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(FakeBatchBackend.instances), 1)
        self.assertEqual(FakeBatchBackend.instances[0].start_calls, 1)

    def test_exact_completed_shard_resumes_without_engine_startup(self) -> None:
        first = self._run()
        self.assertEqual(first.status, "completed")
        second = self._run()
        self.assertEqual(second.status, "completed")
        self.assertTrue(second.skipped)
        self.assertEqual(len(FakeBatchBackend.instances), 1)

    def test_failed_shard_reruns(self) -> None:
        class FailOneBackend(FakeBatchBackend):
            def generate_batch(self, requests):  # type: ignore[no-untyped-def]
                self.batch_calls += 1
                results = []
                for req in requests:
                    if req.request_id == "syn-002":
                        results.append(
                            FakeBatchResult(
                                request_id=req.request_id,
                                ordinal=req.ordinal,
                                raw_text="",
                                generation_status="failure",
                                error_type="generation_failed",
                                error_message="boom",
                            )
                        )
                    else:
                        results.append(
                            FakeBatchResult(
                                request_id=req.request_id,
                                ordinal=req.ordinal,
                                raw_text=f"generated:{req.prompt}",
                            )
                        )
                return results

        result = self._run(backend_factory=lambda **_k: FailOneBackend())
        self.assertEqual(result.status, "failed")
        rerun = self._run(backend_factory=lambda **_k: FakeBatchBackend())
        self.assertFalse(rerun.skipped)
        self.assertEqual(rerun.status, "completed")
        manifest = load_manifest(Path(rerun.manifest_path))
        self.assertGreaterEqual(manifest.retry_count, 1)

    def test_incompatible_completed_shard_blocks_without_backend(self) -> None:
        first = self._run()
        self.assertEqual(first.status, "completed")
        manifest_path = Path(first.manifest_path)
        parsed_path = manifest_path.with_name("shard-000.parsed.jsonl")
        original_manifest = manifest_path.read_bytes()
        original_parsed = parsed_path.read_bytes()
        plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
        plan["input_sha256"] = "deadbeef"
        self.plan_path.write_text(json.dumps(plan) + "\n", encoding="utf-8")
        second = self._run()
        self.assertEqual(second.status, "blocked")
        self.assertFalse(second.skipped)
        self.assertFalse(second.engine_started)
        self.assertEqual(len(FakeBatchBackend.instances), 1)
        self.assertEqual(manifest_path.read_bytes(), original_manifest)
        self.assertEqual(parsed_path.read_bytes(), original_parsed)
        self.assertTrue(any("completed_conflict" in reason for reason in second.rejection_reasons))

    def test_different_run_id_does_not_overwrite_completed_output(self) -> None:
        first = self._run()
        manifest_path = Path(first.manifest_path)
        parsed_path = manifest_path.with_name("shard-000.parsed.jsonl")
        original_manifest = manifest_path.read_bytes()
        original_parsed = parsed_path.read_bytes()
        other_run_dir = self.base / "runs" / "run-002"
        other_run_dir.mkdir(parents=True)
        for name in ("shard-000.manifest.json", "shard-000.parsed.jsonl", "shard-000.raw.jsonl"):
            (self.run_dir / name).replace(other_run_dir / name)
        result = self.batch_runner.run_shard_batch(
            repo_root=ROOT,
            runtime_config_path=self.runtime_path,
            shard_plan_path=self.plan_path,
            shard_id="shard-000",
            run_dir=other_run_dir,
            preflight_result=_preflight_pass(),
            synthetic_declaration_path=self.declaration_path,
            input_jsonl_path=self.input_path,
            backend_factory=lambda **_k: FakeBatchBackend(),
            start_timestamp="2026-07-11T19:00:00Z",
            end_timestamp="2026-07-11T19:01:00Z",
        )
        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.engine_started)
        self.assertEqual(len(FakeBatchBackend.instances), 1)
        self.assertEqual((other_run_dir / "shard-000.manifest.json").read_bytes(), original_manifest)
        self.assertEqual((other_run_dir / "shard-000.parsed.jsonl").read_bytes(), original_parsed)

    def test_corrupted_completed_output_hash_blocks_without_backend(self) -> None:
        first = self._run()
        manifest_path = Path(first.manifest_path)
        parsed_path = manifest_path.with_name("shard-000.parsed.jsonl")
        original_manifest = manifest_path.read_bytes()
        parsed_path.write_text('{"record_id":"tampered"}\n', encoding="utf-8")
        second = self._run()
        self.assertEqual(second.status, "blocked")
        self.assertFalse(second.engine_started)
        self.assertEqual(len(FakeBatchBackend.instances), 1)
        self.assertEqual(manifest_path.read_bytes(), original_manifest)
        self.assertTrue(any("corrupted_completion" in reason for reason in second.rejection_reasons))

    def test_missing_completed_output_file_blocks_without_backend(self) -> None:
        first = self._run()
        manifest_path = Path(first.manifest_path)
        parsed_path = manifest_path.with_name("shard-000.parsed.jsonl")
        original_manifest = manifest_path.read_bytes()
        parsed_path.unlink()
        second = self._run()
        self.assertEqual(second.status, "blocked")
        self.assertFalse(second.engine_started)
        self.assertEqual(manifest_path.read_bytes(), original_manifest)
        self.assertIn("corrupted_completion:parsed_output_missing", second.rejection_reasons)

    def test_failed_shard_retry_preserves_attempt_evidence(self) -> None:
        class FailOneBackend(FakeBatchBackend):
            def generate_batch(self, requests):  # type: ignore[no-untyped-def]
                self.batch_calls += 1
                return [
                    FakeBatchResult(
                        request_id=req.request_id,
                        ordinal=req.ordinal,
                        raw_text="",
                        generation_status="failure",
                        error_type="generation_failed",
                        error_message="boom",
                    )
                    for req in requests
                ]

        first = self._run(backend_factory=lambda **_k: FailOneBackend())
        self.assertEqual(first.status, "failed")
        failed_manifest = load_manifest(self.run_dir / "shard-000.manifest.json")
        self.assertEqual(failed_manifest.status, "failed")
        self.assertEqual(failed_manifest.model_repository, _EXPECTED["model_repository"])
        self.assertTrue(failed_manifest.backend_config_hash)
        second = self._run(backend_factory=lambda **_k: FakeBatchBackend())
        self.assertEqual(second.status, "completed")
        completed = load_manifest(Path(second.manifest_path))
        self.assertEqual(completed.retry_count, 1)
        self.assertEqual(len(completed.attempt_history), 1)
        self.assertEqual(completed.attempt_history[0].status, "failed")
        self.assertTrue(completed.attempt_history[0].prior_manifest_sha256)

    def test_different_model_repository_blocks_completed_without_backend(self) -> None:
        first = self._run()
        manifest_path = Path(first.manifest_path)
        tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
        tampered["model_repository"] = "Other/Model"
        manifest_path.write_text(json.dumps(tampered) + "\n", encoding="utf-8")
        tampered_bytes = manifest_path.read_bytes()
        second = self._run()
        self.assertEqual(second.status, "blocked")
        self.assertFalse(second.engine_started)
        self.assertEqual(manifest_path.read_bytes(), tampered_bytes)
        self.assertIn("completed_conflict:model_repository", second.rejection_reasons)

    def test_different_backend_config_hash_blocks_completed_without_backend(self) -> None:
        first = self._run()
        manifest_path = Path(first.manifest_path)
        original_manifest = manifest_path.read_bytes()
        runtime = json.loads(self.runtime_path.read_text(encoding="utf-8"))
        runtime["batch_size"] = 4
        self.runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
        second = self._run()
        self.assertEqual(second.status, "blocked")
        self.assertFalse(second.engine_started)
        self.assertEqual(manifest_path.read_bytes(), original_manifest)
        self.assertIn("completed_conflict:backend_config_hash", second.rejection_reasons)

    def test_multiple_failed_retries_preserve_all_prior_failures(self) -> None:
        class FailOneBackend(FakeBatchBackend):
            def generate_batch(self, requests):  # type: ignore[no-untyped-def]
                self.batch_calls += 1
                results = []
                for req in requests:
                    if req.request_id == "syn-002":
                        results.append(
                            FakeBatchResult(
                                request_id=req.request_id,
                                ordinal=req.ordinal,
                                raw_text="",
                                generation_status="failure",
                                error_type="generation_failed",
                                error_message="boom",
                            )
                        )
                    else:
                        results.append(
                            FakeBatchResult(
                                request_id=req.request_id,
                                ordinal=req.ordinal,
                                raw_text=f"generated:{req.prompt}",
                            )
                        )
                return results

        self._run(backend_factory=lambda **_k: FailOneBackend())
        self._run(backend_factory=lambda **_k: FailOneBackend())
        manifest = load_manifest(self.run_dir / "shard-000.manifest.json")
        self.assertEqual(manifest.status, "failed")
        self.assertEqual(len(manifest.attempt_history), 1)
        self.assertEqual(manifest.retry_count, 1)

    def test_conflict_does_not_mutate_attempt_history(self) -> None:
        first = self._run()
        manifest_path = Path(first.manifest_path)
        original = json.loads(manifest_path.read_text(encoding="utf-8"))
        plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
        plan["input_sha256"] = "deadbeef"
        self.plan_path.write_text(json.dumps(plan) + "\n", encoding="utf-8")
        second = self._run()
        self.assertEqual(second.status, "blocked")
        unchanged = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(unchanged.get("attempt_history", []), original.get("attempt_history", []))

    def test_temporary_files_not_treated_as_completed(self) -> None:
        from ambiguity_manager.model.cluster.atomic_outputs import is_temporary_output

        temp = self.run_dir / "shard-000.parsed.jsonl.tmp"
        temp.write_text('{"record_id":"syn-001"}\n', encoding="utf-8")
        self.assertTrue(is_temporary_output(temp))
        self.assertFalse((self.run_dir / "shard-000.manifest.json").exists())
        result = self._run()
        self.assertEqual(result.status, "completed")
        self.assertFalse(result.skipped)
        self.assertTrue((self.run_dir / "shard-000.manifest.json").exists())

    def test_engine_starts_once_for_multiple_batches(self) -> None:
        runtime = json.loads(self.runtime_path.read_text(encoding="utf-8"))
        runtime["batch_size"] = 1
        self.runtime_path.write_text(json.dumps(runtime), encoding="utf-8")

        def backend_factory(**kwargs: Any):
            from ambiguity_manager.model.backends.vllm_batch import create_vllm_batch_backend

            return create_vllm_batch_backend(
                kwargs["config"],
                repo_root=kwargs["repo_root"],
                immutable=kwargs["immutable"],
                engine_factory=lambda **_k: FakeEngine(),
                sampling_params_factory=lambda _generation: object(),
            )

        result = self._run(shard_id="shard-000", backend_factory=backend_factory)
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(FakeEngine.instances), 1)
        self.assertGreaterEqual(FakeEngine.instances[0].generate_calls, 2)

    def test_every_input_becomes_success_or_failure(self) -> None:
        result = self._run()
        manifest = load_manifest(Path(result.manifest_path))
        self.assertEqual(len(manifest.expected_ids), manifest.output_record_count)

    def test_incomplete_output_returns_failure(self) -> None:
        class PartialBackend(FakeBatchBackend):
            def generate_batch(self, requests):  # type: ignore[no-untyped-def]
                self.batch_calls += 1
                return [
                    FakeBatchResult(
                        request_id=requests[0].request_id,
                        ordinal=requests[0].ordinal,
                        raw_text="only-first",
                    )
                ]

        result = self._run(backend_factory=lambda **_k: PartialBackend())
        self.assertEqual(result.status, "failed")

    def test_completion_manifest_written_only_after_valid_output(self) -> None:
        result = self._run()
        manifest_path = Path(result.manifest_path)
        parsed_path = manifest_path.with_name("shard-000.parsed.jsonl")
        self.assertTrue(manifest_path.is_file())
        self.assertTrue(parsed_path.is_file())
        manifest = load_manifest(manifest_path)
        self.assertEqual(manifest.status, "completed")

    def test_run_and_model_identities_propagate_into_output(self) -> None:
        result = self._run()
        manifest = load_manifest(Path(result.manifest_path))
        self.assertEqual(manifest.model_revision, MODEL_REVISION)
        self.assertEqual(manifest.container_sha256, CONTAINER_SHA)
        self.assertEqual(manifest.model_repository, _EXPECTED["model_repository"])
        self.assertTrue(manifest.backend_config_hash)
        self.assertEqual(manifest.run_id, "run-001")

    def test_synthetic_marker_is_mandatory(self) -> None:
        bad = self.base / "bad.jsonl"
        bad.write_text(
            json.dumps(
                {
                    "fixture_id": "syn-004",
                    "rendered_prompt": "x",
                    "synthetic": False,
                    "ordinal": 0,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        from ambiguity_manager.model.cluster.sharding import plan_shards_from_jsonl, plan_to_canonical_json

        plan = plan_shards_from_jsonl(
            bad,
            id_field="fixture_id",
            shard_count=1,
            created_timestamp="2026-07-11T19:00:00Z",
            input_source=str(bad),
        )
        bad_plan = self.base / "bad-plan.json"
        bad_plan.write_text(plan_to_canonical_json(plan) + "\n", encoding="utf-8")
        result = self._run(
            shard_plan_path=bad_plan,
            input_jsonl_path=bad,
            shard_id="shard-000",
        )
        self.assertEqual(result.status, "fail")
        self.assertIn("non_synthetic_record", result.rejection_reasons)


if __name__ == "__main__":
    unittest.main()
