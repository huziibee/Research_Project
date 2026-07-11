"""Backend-neutral one-shard batch runner for T12 cluster execution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ambiguity_manager.model.backends.vllm_batch import (
    BatchRequest,
    VllmBatchBackend,
    VllmBatchBackendConfig,
    create_vllm_batch_backend,
    load_runtime_config,
)
from ambiguity_manager.model.cluster.atomic_outputs import (
    ShardManifest,
    sha256_text,
    write_shard_outputs,
)
from ambiguity_manager.model.cluster.identities import load_immutable_selection
from ambiguity_manager.model.cluster.run_state import (
    ResumeIdentity,
    ShardRunDecision,
    evaluate_resume,
    load_manifest,
)
from ambiguity_manager.model.cluster.sharding import ShardPlan, plan_to_canonical_json

BackendFactory = Callable[..., Any]


@dataclass(frozen=True)
class ShardRunResult:
    status: str
    run_id: str
    shard_id: str
    skipped: bool
    rejection_reasons: tuple[str, ...]
    manifest_path: str | None
    backend_config_hash: str
    engine_started: bool
    decision: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "status": self.status,
            "run_id": self.run_id,
            "shard_id": self.shard_id,
            "skipped": self.skipped,
            "rejection_reasons": list(self.rejection_reasons),
            "manifest_path": self.manifest_path,
            "backend_config_hash": self.backend_config_hash,
            "engine_started": self.engine_started,
        }
        if self.decision is not None:
            payload["decision"] = self.decision
        return payload


def _validate_preflight(preflight: dict[str, Any]) -> list[str]:
    rejections: list[str] = []
    if preflight.get("status") != "pass":
        rejections.append("preflight_not_pass")
    if preflight.get("container_sha_verification_method") != "full_sha256":
        rejections.append("container_integrity_not_full_sha256")
    return rejections


def _load_plan(path: Path) -> ShardPlan:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ShardPlan(
        schema_version=str(payload["schema_version"]),
        plan_version=str(payload["plan_version"]),
        input_source=str(payload["input_source"]),
        input_sha256=str(payload["input_sha256"]),
        record_count=int(payload["record_count"]),
        shard_count=int(payload["shard_count"]),
        assignment_method=str(payload["assignment_method"]),
        shard_record_ids=tuple(tuple(items) for items in payload["shard_record_ids"]),
        shard_record_counts=tuple(int(item) for item in payload["shard_record_counts"]),
        shard_input_hashes=tuple(str(item) for item in payload["shard_input_hashes"]),
        generator_version=str(payload["generator_version"]),
        created_timestamp=str(payload["created_timestamp"]),
    )


def _shard_index(shard_id: str) -> int:
    if not shard_id.startswith("shard-"):
        raise ValueError(f"invalid_shard_id:{shard_id}")
    return int(shard_id.split("-", 1)[1])


def _require_synthetic_declaration(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("synthetic") is not True:
        raise ValueError("input_not_explicitly_marked_synthetic")


def _load_records(
    path: Path,
    *,
    id_field: str = "fixture_id",
    prompt_field: str = "rendered_prompt",
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        record = json.loads(stripped)
        if not isinstance(record, dict):
            raise ValueError(f"malformed_record_type:{line_number}")
        record_id = str(record.get(id_field, ""))
        if not record_id:
            raise ValueError(f"missing_record_id:{line_number}")
        if record.get("synthetic") is not True:
            raise ValueError("non_synthetic_record")
        if prompt_field not in record or not str(record[prompt_field]).strip():
            raise ValueError(f"missing_prompt:{record_id}")
        if "ordinal" not in record:
            raise ValueError(f"missing_ordinal:{record_id}")
        records[record_id] = record
    return records


def _build_requests(
    expected_ids: tuple[str, ...],
    records: dict[str, dict[str, Any]],
    *,
    id_field: str = "fixture_id",
    prompt_field: str = "rendered_prompt",
) -> list[BatchRequest]:
    requests: list[BatchRequest] = []
    for record_id in expected_ids:
        record = records[record_id]
        requests.append(
            BatchRequest(
                request_id=record_id,
                prompt=str(record[prompt_field]),
                ordinal=int(record["ordinal"]),
                synthetic=True,
                metadata={"record_class": record.get("record_class", "synthetic")},
            )
        )
    return requests


def _results_to_output_records(results: list[Any]) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    output_records: list[dict[str, Any]] = []
    failed_ids: list[str] = []
    for result in results:
        output_records.append(
            {
                "record_id": result.request_id,
                "raw_output": result.raw_text,
                "generation_status": result.generation_status,
                "finish_reason": result.finish_reason,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "latency_ms": result.latency_ms,
                "error_type": result.error_type,
                "error_message": result.error_message,
                "backend_identifier": result.backend_identifier,
                "model_revision": result.model_revision,
                "config_hash": result.config_hash,
            }
        )
        if result.generation_status != "success":
            failed_ids.append(result.request_id)
    return output_records, tuple(failed_ids)


def run_shard_batch(
    *,
    repo_root: Path,
    runtime_config_path: Path,
    shard_plan_path: Path,
    shard_id: str,
    run_dir: Path,
    preflight_result: dict[str, Any],
    synthetic_declaration_path: Path,
    input_jsonl_path: Path,
    backend_factory: BackendFactory | None = None,
    start_timestamp: str,
    end_timestamp: str,
    id_field: str = "fixture_id",
    prompt_field: str = "rendered_prompt",
) -> ShardRunResult:
    run_id = run_dir.name
    rejections = _validate_preflight(preflight_result)
    if rejections:
        return ShardRunResult(
            status="fail",
            run_id=run_id,
            shard_id=shard_id,
            skipped=False,
            rejection_reasons=tuple(rejections),
            manifest_path=None,
            backend_config_hash="",
            engine_started=False,
        )

    try:
        _require_synthetic_declaration(synthetic_declaration_path)
        runtime_config = load_runtime_config(runtime_config_path, repo_root=repo_root)
        plan = _load_plan(shard_plan_path)
        shard_index = _shard_index(shard_id)
        expected_ids = plan.shard_record_ids[shard_index]
        input_plan_hash = sha256_text(plan_to_canonical_json(plan))
        input_shard_hash = plan.shard_input_hashes[shard_index]
        records = _load_records(input_jsonl_path, id_field=id_field, prompt_field=prompt_field)
    except (ValueError, json.JSONDecodeError, KeyError, IndexError) as exc:
        return ShardRunResult(
            status="fail",
            run_id=run_id,
            shard_id=shard_id,
            skipped=False,
            rejection_reasons=(str(exc),),
            manifest_path=None,
            backend_config_hash="",
            engine_started=False,
        )

    immutable = load_immutable_selection(repo_root)
    manifest_path = run_dir / f"{shard_id}.manifest.json"
    parsed_output_path = run_dir / f"{shard_id}.parsed.jsonl"
    resume_allows_overwrite = False
    existing_failure_reasons: tuple[str, ...] = ()

    if manifest_path.is_file():
        existing = load_manifest(manifest_path)
        identity = ResumeIdentity(
            run_id=run_id,
            shard_id=shard_id,
            input_plan_hash=input_plan_hash,
            input_shard_hash=input_shard_hash,
            expected_record_ids=expected_ids,
            output_record_count=existing.output_record_count,
            output_sha256=existing.output_sha256,
            backend_identifier=runtime_config.backend_identifier,
            backend_config_hash=runtime_config.config_hash,
            model_repository=immutable.model_repository,
            model_revision=immutable.model_revision,
            container_sha256=immutable.container_sha256,
        )
        decision = evaluate_resume(existing, identity=identity, parsed_output_path=parsed_output_path)
        if decision.skip:
            return ShardRunResult(
                status="completed",
                run_id=run_id,
                shard_id=shard_id,
                skipped=True,
                rejection_reasons=(),
                manifest_path=str(manifest_path),
                backend_config_hash=runtime_config.config_hash,
                engine_started=False,
                decision=decision.decision.value,
            )
        if not decision.starts_backend:
            return ShardRunResult(
                status="blocked",
                run_id=run_id,
                shard_id=shard_id,
                skipped=False,
                rejection_reasons=(decision.reason,),
                manifest_path=str(manifest_path),
                backend_config_hash=runtime_config.config_hash,
                engine_started=False,
                decision=decision.decision.value,
            )
        resume_allows_overwrite = decision.allow_overwrite
        if existing.failed_ids:
            existing_failure_reasons = tuple(f"failed_id:{item}" for item in existing.failed_ids)
        elif existing.status != "completed":
            existing_failure_reasons = (f"status:{existing.status}",)

    if backend_factory is None:
        backend: Any = create_vllm_batch_backend(runtime_config, repo_root=repo_root)
    else:
        backend = backend_factory(
            config=runtime_config,
            repo_root=repo_root,
            immutable=immutable,
        )

    engine_started = False
    try:
        backend.start()
        engine_started = True
        requests = _build_requests(expected_ids, records, id_field=id_field, prompt_field=prompt_field)
        results = list(backend.generate_batch(requests))
        observed_ids = {item.request_id for item in results}
        for record_id in expected_ids:
            if record_id not in observed_ids:
                results.append(
                    _missing_result(record_id, records[record_id], runtime_config, immutable)
                )
        output_records, failed_ids = _results_to_output_records(results)
        shard_status = "completed" if not failed_ids and len(output_records) == len(expected_ids) else "failed"
        if shard_status != "completed":
            failure_reasons = tuple(f"missing_or_failed:{item}" for item in failed_ids) or ("incomplete_output",)
            write_shard_outputs(
                output_dir=run_dir,
                run_id=run_id,
                shard_id=shard_id,
                input_plan_hash=input_plan_hash,
                input_shard_hash=input_shard_hash,
                expected_ids=expected_ids,
                output_records=output_records,
                status=shard_status,
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                backend_identifier=runtime_config.backend_identifier,
                backend_config_hash=runtime_config.config_hash,
                model_repository=immutable.model_repository,
                model_revision=immutable.model_revision,
                container_sha256=immutable.container_sha256,
                failed_ids=failed_ids,
                failure_reasons=failure_reasons,
                allow_overwrite=resume_allows_overwrite,
            )
            return ShardRunResult(
                status="failed",
                run_id=run_id,
                shard_id=shard_id,
                skipped=False,
                rejection_reasons=tuple(f"missing_or_failed:{item}" for item in failed_ids) or ("incomplete_output",),
                manifest_path=str(run_dir / f"{shard_id}.manifest.json"),
                backend_config_hash=runtime_config.config_hash,
                engine_started=engine_started,
                decision=ShardRunDecision.RETRY_FAILED.value if resume_allows_overwrite else ShardRunDecision.RUN_NEW.value,
            )

        manifest = write_shard_outputs(
            output_dir=run_dir,
            run_id=run_id,
            shard_id=shard_id,
            input_plan_hash=input_plan_hash,
            input_shard_hash=input_shard_hash,
            expected_ids=expected_ids,
            output_records=output_records,
            status=shard_status,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            backend_identifier=runtime_config.backend_identifier,
            backend_config_hash=runtime_config.config_hash,
            model_repository=immutable.model_repository,
            model_revision=immutable.model_revision,
            container_sha256=immutable.container_sha256,
            failed_ids=failed_ids,
            failure_reasons=existing_failure_reasons,
            allow_overwrite=resume_allows_overwrite,
        )
        return ShardRunResult(
            status=shard_status,
            run_id=run_id,
            shard_id=shard_id,
            skipped=False,
            rejection_reasons=(),
            manifest_path=str(run_dir / f"{shard_id}.manifest.json"),
            backend_config_hash=runtime_config.config_hash,
            engine_started=engine_started,
            decision=ShardRunDecision.RETRY_FAILED.value
            if resume_allows_overwrite and existing_failure_reasons
            else ShardRunDecision.RUN_NEW.value,
        )
    finally:
        if hasattr(backend, "close"):
            backend.close()


def _missing_result(
    record_id: str,
    record: dict[str, Any],
    runtime_config: VllmBatchBackendConfig,
    immutable: Any,
) -> Any:
    from ambiguity_manager.model.backends.vllm_batch import BatchGenerationResult

    return BatchGenerationResult(
        request_id=record_id,
        ordinal=int(record["ordinal"]),
        raw_text="",
        backend_identifier=runtime_config.backend_identifier,
        model_repository=immutable.model_repository,
        model_revision=immutable.model_revision,
        generation_status="failure",
        finish_reason=None,
        prompt_tokens=None,
        completion_tokens=None,
        latency_ms=None,
        error_type="missing_generation_result",
        error_message="no backend result returned for request",
        metadata={},
        config_hash=runtime_config.config_hash,
    )
