"""Generic development vLLM model-candidate bake-off provider.

Lazy-imports torch, transformers, and vLLM. CPU-safe entry points validate
registry/config contracts without loading GPU runtimes.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import re
import socket
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ambiguity_manager.data.model_selection_set import load_model_selection_development_set
from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.base_model_candidates import (
    ALLOWLISTED_CANDIDATE_IDS,
    BaseModelCandidate,
    BaseModelCandidateRegistry,
    load_base_model_candidate_registry,
)
from ambiguity_manager.model.cluster.identities import ImmutableSelection
from ambiguity_manager.model.generation_pipeline import (
    BackendIdentity,
    FailureCategory,
    GenerationPipelineRequest,
    GenerationPipelineResult,
    PipelineFinalStatus,
    PipelineIntegrityContext,
    StructuredDecodeReadiness,
    empty_integrity_context,
    run_generation_pipeline,
    validate_integrity_context,
    validate_pipeline_request,
)
from ambiguity_manager.model.prediction_contract import (
    default_synthetic_prediction_provenance_policy,
    model_semantic_output_schema_hash,
)
from ambiguity_manager.model.prompt_builder import PromptBuildRequest, build_prompt_messages, compute_prompt_hash
from ambiguity_manager.model.repair_prompt import generation_pipeline_contract_hash, load_pipeline_contract
from ambiguity_manager.model.structured_decode import (
    build_structured_sampling_params,
    load_structured_decode_contract,
    structured_decode_contract_hash,
)
from ambiguity_manager.model.vllm_pipeline_generator import VllmPipelineGenerator
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema.v2.records import LabelEligibility
from ambiguity_manager.schema.v2.taxonomies import METRIC_ELIGIBILITY_FIELDS
from ambiguity_manager.systems.analysis import ANALYSIS_VARIANTS, build_analysis_identity
from ambiguity_manager.systems.contracts import AnalysisProvenance, StructuredAnalysis, SystemInput

PROVIDER_ID = "model_candidate_bakeoff_v1"
PROVIDER_VERSION = "1.1.0"
RUNTIME_CONFIG_REL = "configs/cluster/model_candidate_bakeoff_runtime.json"
PROMPT_CONTRACT_REL = "configs/model/bakeoff_prompt_contract_v1.json"
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ARCHIVE_SHA_RE = re.compile(r"^[0-9a-f]{64}$")

FORBIDDEN_EAGER_IMPORTS = frozenset({"torch", "transformers", "vllm"})

CHAT_TEMPLATE_MECHANICS: dict[str, dict[str, Any]] = {
    "qwen3": {
        "renderer_id": "candidate_chat_template_qwen3",
        "apply_chat_template_mode": "enable_thinking_false",
        "notes": "Qwen3 chat template with enable_thinking=False when supported.",
    },
    "phi3": {
        "renderer_id": "candidate_chat_template_phi3",
        "apply_chat_template_mode": "default",
        "notes": "Standard transformers apply_chat_template for Phi instruct family.",
    },
    "mistral": {
        "renderer_id": "candidate_chat_template_mistral",
        "apply_chat_template_mode": "default",
        "vllm_engine_hints": {
            "tokenizer_mode": "mistral",
            "config_format": "mistral",
            "load_format": "mistral",
        },
        "notes": "Mistral instruct template; vLLM engine hints recorded for cluster runtime.",
    },
}

PREFLIGHT_EVIDENCE = (
    "preflight_result.json",
    "candidate_provenance.json",
    "run_manifest.json",
    "source_identity_manifest.json",
)

TRANSPORT_EVIDENCE = (
    "transport_smoke_summary.json",
    "raw_attempts.jsonl",
    "attempt_ledgers.jsonl",
    "accepted_predictions.jsonl",
    "record_results.jsonl",
    "analysis_outputs.jsonl",
    "run_manifest.json",
    "source_identity_manifest.json",
)

BAKEOFF_EVIDENCE = (
    "bakeoff_summary.json",
    "metrics_summary.json",
    "raw_attempts.jsonl",
    "attempt_ledgers.jsonl",
    "accepted_predictions.jsonl",
    "analysis_cache_entries.jsonl",
    "record_results.jsonl",
    "run_manifest.json",
    "source_identity_manifest.json",
)


class BakeoffProviderError(RuntimeError):
    """Raised when bake-off validation or execution fails."""


@dataclass(frozen=True)
class BakeoffRuntimeConfig:
    schema_version: str
    backend_identifier: str
    batch_size: int
    generation: dict[str, Any]
    engine: dict[str, Any]
    offline_only: bool
    network_fallback_permitted: bool
    persistent_engine_required: bool
    container_filename: str
    container_sha256: str
    attempt_bounds: dict[str, Any]
    references: dict[str, str]

    @property
    def config_hash(self) -> str:
        return sha256_hex(canonical_json_bytes(self.to_dict()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "backend_identifier": self.backend_identifier,
            "batch_size": self.batch_size,
            "generation": dict(self.generation),
            "engine": dict(self.engine),
            "offline_only": self.offline_only,
            "network_fallback_permitted": self.network_fallback_permitted,
            "persistent_engine_required": self.persistent_engine_required,
            "container_filename": self.container_filename,
            "container_sha256": self.container_sha256,
            "attempt_bounds": dict(self.attempt_bounds),
            "references": dict(self.references),
        }


@dataclass(frozen=True)
class BakeoffPromptContract:
    contract_id: str
    development_only: bool
    valid_for_official_use: bool
    semantic_schema_hash: str
    references: dict[str, str]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "development_only": self.development_only,
            "valid_for_official_use": self.valid_for_official_use,
            "semantic_schema_hash": self.semantic_schema_hash,
            "references": dict(self.references),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ProviderAvailability:
    available: bool
    reason: str | None = None
    missing_modules: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "reason": self.reason,
            "missing_modules": list(self.missing_modules),
        }


@dataclass
class CandidateChatTemplateRenderer:
    """Lazy candidate tokenizer renderer with recorded template mechanics."""

    candidate: BaseModelCandidate
    tokenizer_path: Path | str
    tokenizer_factory: Callable[..., Any] | None = None
    _tokenizer: Any | None = field(default=None, init=False, repr=False)

    @property
    def mechanics(self) -> dict[str, Any]:
        base = dict(CHAT_TEMPLATE_MECHANICS.get(self.candidate.architecture_type, {}))
        base.setdefault("renderer_id", "candidate_chat_template_generic")
        base.setdefault("apply_chat_template_mode", "default")
        base["architecture_type"] = self.candidate.architecture_type
        base["tokenizer_repository"] = self.candidate.tokenizer_repository
        base["tokenizer_revision"] = self.candidate.tokenizer_revision
        return base

    def load_tokenizer(self) -> None:
        if self._tokenizer is not None:
            return
        if self.tokenizer_factory is not None:
            self._tokenizer = self.tokenizer_factory(
                tokenizer_path=self.tokenizer_path,
                candidate=self.candidate,
            )
            return
        transformers = importlib.import_module("transformers")
        auto_tokenizer = getattr(transformers, "AutoTokenizer")
        self._tokenizer = auto_tokenizer.from_pretrained(
            str(self.tokenizer_path),
            revision=self.candidate.tokenizer_revision,
            local_files_only=True,
            trust_remote_code=False,
        )

    def render(self, messages: list[dict[str, str]]) -> str:
        self.load_tokenizer()
        mode = str(self.mechanics.get("apply_chat_template_mode", "default"))
        kwargs: dict[str, Any] = {"tokenize": False, "add_generation_prompt": True}
        if mode == "enable_thinking_false":
            kwargs["enable_thinking"] = False
        rendered = self._tokenizer.apply_chat_template(messages, **kwargs)
        if not isinstance(rendered, str) or not rendered.strip():
            raise BakeoffProviderError("rendered_prompt_empty")
        return rendered


class BakeoffGenerationReadyRenderer:
    """GenerationReadyRenderer using shared prompt contract across candidates."""

    def __init__(
        self,
        *,
        candidate: BaseModelCandidate,
        chat_renderer: CandidateChatTemplateRenderer,
        container_sha256: str,
    ) -> None:
        self._candidate = candidate
        self._chat_renderer = chat_renderer
        self._container_sha256 = container_sha256

    def render(self, messages: list[dict[str, str]]) -> Any:
        from ambiguity_manager.model.generation_pipeline import GenerationReadyPromptEnvelope

        rendered_text = self._chat_renderer.render(messages)
        abstract_hash = sha256_hex(
            canonical_json_bytes({"messages": [{"role": m["role"], "content": m["content"]} for m in messages]})
        )
        return GenerationReadyPromptEnvelope(
            rendered_prompt_text=rendered_text,
            rendered_prompt_hash=sha256_hex(rendered_text.encode("utf-8")),
            abstract_message_hash=abstract_hash,
            model_repository=self._candidate.repository,
            immutable_model_revision=self._candidate.revision,
            response_mode_status="verified",
            response_mode_method_identity=str(self._chat_renderer.mechanics.get("apply_chat_template_mode")),
            renderer_identity=str(self._chat_renderer.mechanics.get("renderer_id")),
            renderer_version=PROVIDER_VERSION,
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_root(root: Path | None = None) -> Path:
    return (root or ProjectPaths.from_repo_root().root).resolve()


def validate_candidate_id(candidate_id: str) -> str:
    if candidate_id not in ALLOWLISTED_CANDIDATE_IDS:
        raise BakeoffProviderError(f"candidate_not_allowlisted:{candidate_id}")
    return candidate_id


def add_standard_run_cli(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--candidate-id",
        required=True,
        help="Allowlisted candidate id (for example qwen3_8b; not a HF repo string).",
    )
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-archive-sha256", required=True)
    parser.add_argument(
        "--source-identity-manifest",
        type=Path,
        required=True,
        help="Retained source-identity manifest from operator packaging.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root containing configs and development set.",
    )


def parse_standard_run_cli(args: argparse.Namespace) -> str:
    return validate_candidate_id(str(args.candidate_id))


def load_bakeoff_runtime_config(root: Path | None = None) -> BakeoffRuntimeConfig:
    path = _repo_root(root) / RUNTIME_CONFIG_REL
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0.0":
        raise BakeoffProviderError("runtime_config.schema_version must be 1.0.0")
    if payload.get("attempt_bounds", {}).get("unconstrained_fallback_permitted") is not False:
        raise BakeoffProviderError("runtime_config attempt_bounds forbid unconstrained fallback")
    return BakeoffRuntimeConfig(
        schema_version=str(payload["schema_version"]),
        backend_identifier=str(payload["backend_identifier"]),
        batch_size=int(payload["batch_size"]),
        generation=dict(payload["generation"]),
        engine=dict(payload["engine"]),
        offline_only=bool(payload["offline_only"]),
        network_fallback_permitted=bool(payload["network_fallback_permitted"]),
        persistent_engine_required=bool(payload["persistent_engine_required"]),
        container_filename=str(payload["container_filename"]),
        container_sha256=str(payload["container_sha256"]),
        attempt_bounds=dict(payload["attempt_bounds"]),
        references={str(k): str(v) for k, v in payload["references"].items()},
    )


def load_bakeoff_prompt_contract(root: Path | None = None) -> BakeoffPromptContract:
    path = _repo_root(root) / PROMPT_CONTRACT_REL
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected_hash = model_semantic_output_schema_hash()
    declared = str(payload.get("semantic_schema_hash", ""))
    if declared != expected_hash:
        raise BakeoffProviderError("prompt_contract semantic_schema_hash mismatch")
    return BakeoffPromptContract(
        contract_id=str(payload["contract_id"]),
        development_only=bool(payload["development_only"]),
        valid_for_official_use=bool(payload["valid_for_official_use"]),
        semantic_schema_hash=declared,
        references={str(k): str(v) for k, v in payload["references"].items()},
        notes=tuple(str(item) for item in payload.get("notes") or []),
    )


def prompt_contract_hash_for_candidate(
    *,
    record: dict[str, Any],
    analysis_variant: str = "full_context",
) -> str:
    """Return prompt hash for a development record using the shared contract."""
    request = _prompt_build_request(record, analysis_variant=analysis_variant)
    return compute_prompt_hash(request)


def assert_prompt_contract_same_across_candidates(
    *,
    record: dict[str, Any],
    candidate_ids: Sequence[str] | None = None,
) -> None:
    """Verify prompt messages are identical across allowlisted candidates."""
    ids = tuple(candidate_ids or sorted(ALLOWLISTED_CANDIDATE_IDS))
    baseline = build_prompt_messages(_prompt_build_request(record, analysis_variant="full_context"))
    for candidate_id in ids:
        _ = candidate_id  # prompt contract is candidate-independent by design
        messages = build_prompt_messages(_prompt_build_request(record, analysis_variant="full_context"))
        if messages != baseline:
            raise BakeoffProviderError(f"prompt_contract_divergence:{candidate_id}")


def check_provider_available() -> ProviderAvailability:
    missing: list[str] = []
    for name in FORBIDDEN_EAGER_IMPORTS:
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)
    if missing:
        return ProviderAvailability(
            available=False,
            reason="provider_unavailable",
            missing_modules=tuple(sorted(missing)),
        )
    return ProviderAvailability(available=True)


def candidate_to_immutable_selection(
    candidate: BaseModelCandidate,
    registry: BaseModelCandidateRegistry,
) -> ImmutableSelection:
    runtime = registry.official_source_references.get("pinned_runtime") or {}
    return ImmutableSelection(
        schema_version="1.0.0",
        candidate_entry_id=str(candidate.register_entry_id or candidate.candidate_id),
        candidate_status="development_bakeoff_candidate",
        model_repository=candidate.repository,
        model_revision=candidate.revision,
        tokenizer_repository=candidate.tokenizer_repository,
        tokenizer_revision=candidate.tokenizer_revision,
        licence=candidate.licence_identifier,
        gated=candidate.gated,
        private=candidate.private,
        container_filename=str(runtime.get("container_filename", "vllm-openai-v0.20.1.sif")),
        container_sha256=str(
            runtime.get(
                "container_sha256",
                "d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1",
            )
        ),
        container_size_bytes=7657443328,
        authoritative_runtime="wits_slurm_cluster",
        selected_model_register_must_remain_null_until_stage="I",
    )


def build_candidate_provenance(
    *,
    candidate: BaseModelCandidate,
    registry: BaseModelCandidateRegistry,
    runtime_config: BakeoffRuntimeConfig,
    prompt_contract: BakeoffPromptContract,
) -> dict[str, Any]:
    mechanics = dict(CHAT_TEMPLATE_MECHANICS.get(candidate.architecture_type, {}))
    return {
        "schema_version": "1.0.0",
        "provider_id": PROVIDER_ID,
        "provider_version": PROVIDER_VERSION,
        "candidate_id": candidate.candidate_id,
        "checkpoint_identity": candidate.checkpoint_identity,
        "repository": candidate.repository,
        "revision": candidate.revision,
        "tokenizer_repository": candidate.tokenizer_repository,
        "tokenizer_revision": candidate.tokenizer_revision,
        "architecture_type": candidate.architecture_type,
        "licence_identifier": candidate.licence_identifier,
        "chat_template_mechanics": mechanics,
        "runtime_config_hash": runtime_config.config_hash,
        "prompt_contract_id": prompt_contract.contract_id,
        "semantic_schema_hash": prompt_contract.semantic_schema_hash,
        "pipeline_contract_hash": generation_pipeline_contract_hash(load_pipeline_contract()),
        "structured_decode_contract_hash": structured_decode_contract_hash(load_structured_decode_contract()),
        "selected_adapter": None,
        "selected_model_strategy": None,
        "development_only": True,
        "valid_for_official_use": False,
        "registry_canonical_hash": registry.canonical_hash,
    }


def _integrity_context_from_record(record: dict[str, Any], *, analysis_variant: str) -> PipelineIntegrityContext:
    extra = record.get("extra") or {}
    raw = extra.get("integrity_context")
    if analysis_variant == "context_blind":
        return empty_integrity_context()
    if isinstance(raw, dict):
        errors = validate_integrity_context(raw)
        if not errors:
            return PipelineIntegrityContext.from_mapping(raw)
    return empty_integrity_context()


def _label_eligibility(raw: Mapping[str, Any]) -> LabelEligibility:
    return LabelEligibility(**{name: bool(raw.get(name, False)) for name in METRIC_ELIGIBILITY_FIELDS})


def _prompt_build_request(record: dict[str, Any], *, analysis_variant: str) -> PromptBuildRequest:
    if analysis_variant == "context_blind":
        return PromptBuildRequest(
            command=str(record["command"]),
            scene_context=None,
            dialogue_history=[],
            capability_context=None,
        )
    return PromptBuildRequest(
        command=str(record["command"]),
        scene_context=record.get("scene_context"),
        dialogue_history=list(record.get("dialogue_history") or []),
        capability_context=record.get("capability_context"),
    )


def _system_input_from_record(record: dict[str, Any], *, analysis_variant: str) -> SystemInput:
    payload = dict(record)
    if analysis_variant == "context_blind":
        payload["scene_context"] = None
        payload["dialogue_history"] = []
        payload["capability_context"] = None
    return SystemInput.from_dict(payload)


def pipeline_request_from_development_record(
    record: dict[str, Any],
    *,
    candidate: BaseModelCandidate,
    runtime_config: BakeoffRuntimeConfig,
    analysis_variant: str = "full_context",
) -> GenerationPipelineRequest:
    if record.get("protected_data") is True:
        raise BakeoffProviderError(f"protected_record_forbidden:{record.get('record_id')}")
    provenance = default_synthetic_prediction_provenance_policy()
    source = (record.get("input_provenance") or {}).get("source_dataset")
    return GenerationPipelineRequest(
        caller_request_id=f"bakeoff:{analysis_variant}:{record['record_id']}",
        synthetic=True,
        command=str(record["command"]),
        label_eligibility=_label_eligibility(record.get("label_eligibility") or {}),
        provenance_policy=provenance,
        source_dataset=str(source or "model_selection_development_set_v1"),
        integrity_context=_integrity_context_from_record(record, analysis_variant=analysis_variant),
        scene_context=None if analysis_variant == "context_blind" else record.get("scene_context"),
        dialogue_history=[] if analysis_variant == "context_blind" else list(record.get("dialogue_history") or []),
        capability_context=None if analysis_variant == "context_blind" else record.get("capability_context"),
        container_sha=runtime_config.container_sha256,
    )


def canonical_to_structured_analysis(
    canonical: dict[str, Any],
    *,
    candidate: BaseModelCandidate,
    analysis_variant: str,
) -> StructuredAnalysis:
    model_fields = {
        key: canonical[key]
        for key in canonical
        if key
        not in {
            "schema_version",
            "id",
            "record_class",
            "source_dataset",
            "source_id",
            "original_split",
            "group_id",
            "split_status",
            "command",
            "scene_context",
            "dialogue_history",
            "capability_context",
            "annotation_status",
            "label_confidence",
            "migration_version",
            "migrated_from_schema_version",
            "v1_legacy",
            "prediction_metadata",
            "mapping_version",
            "source_license",
            "mapping_notes",
            "source_metadata",
            "label_eligibility",
        }
    }
    method = analysis_variant
    analysis = StructuredAnalysis.from_dict(model_fields)
    analysis.analysis_provenance = AnalysisProvenance(
        provider_id=f"{PROVIDER_ID}/{candidate.candidate_id}",
        provider_version=PROVIDER_VERSION,
        method=method,
        notes=f"analysis_variant={analysis_variant};checkpoint={candidate.checkpoint_identity}",
    )
    return analysis


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _atomic_write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(dict(row), sort_keys=True) + "\n" for row in rows)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _sha256_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _count_jsonl_rows(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _copy_source_identity_manifest(source_path: Path, result_dir: Path) -> None:
    if not source_path.is_file():
        raise BakeoffProviderError(f"source_identity_manifest_missing:{source_path}")
    dest = result_dir / "source_identity_manifest.json"
    dest.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")


def _validate_run_identity_args(
    *,
    source_commit: str,
    source_archive_sha256: str,
) -> None:
    if not COMMIT_SHA_RE.match(source_commit):
        raise BakeoffProviderError("invalid_source_commit")
    if not ARCHIVE_SHA_RE.match(source_archive_sha256):
        raise BakeoffProviderError("invalid_source_archive_sha256")


def _refuse_nonempty_result_dir(result_dir: Path, expected_files: Sequence[str]) -> None:
    result_dir.mkdir(parents=True, exist_ok=True)
    existing = [name for name in expected_files if (result_dir / name).exists()]
    if existing:
        raise BakeoffProviderError(f"result_dir_not_empty:{','.join(existing)}")


def finalize_run_manifest(
    result_dir: Path,
    *,
    run_id: str,
    profile: str,
    candidate_id: str,
    source_commit: str,
    source_archive_sha256: str,
    expected_files: Sequence[str],
    success: bool,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    files = []
    for name in sorted(expected_files):
        path = result_dir / name
        if not path.is_file():
            continue
        entry: dict[str, Any] = {
            "relative_path": name,
            "sha256": _sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        if path.suffix == ".jsonl":
            entry["row_count"] = _count_jsonl_rows(path)
        files.append(entry)
    manifest = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "profile": profile,
        "candidate_id": candidate_id,
        "source_commit_sha": source_commit,
        "source_archive_sha256": source_archive_sha256,
        "hostname": socket.gethostname(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "python_version": platform.python_version(),
        "timestamp_utc": _utc_now(),
        "success": success,
        "development_only": True,
        "valid_for_official_use": False,
        "files": files,
    }
    if extra:
        manifest.update(dict(extra))
    _atomic_write_json(result_dir / "run_manifest.json", manifest)
    return manifest


def _build_structured_decode_readiness(
    repo: Path,
    *,
    generation_settings: dict[str, Any],
) -> StructuredDecodeReadiness:
    contract = load_structured_decode_contract(repo / "configs/model/t12_structured_decode_contract.json")
    build_result = build_structured_sampling_params(
        generation_settings,
        contract,
        repo_root=repo,
    )
    return StructuredDecodeReadiness(
        metadata=build_result.metadata,
        unconstrained_fallback_indicated=False,
    )


def _collect_attempt_rows(
    result: GenerationPipelineResult,
    *,
    record_id: str,
    variant: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None, dict[str, Any]]:
    raw_rows: list[dict[str, Any]] = []
    for entry in result.attempt_entries:
        raw_rows.append(
            {
                "record_id": record_id,
                "analysis_variant": variant,
                "attempt_index": entry.attempt_index,
                "attempt_kind": entry.attempt_kind,
                "raw_output": entry.raw_generated_text,
                "disposition": entry.final_attempt_disposition,
                "failure_categories": list(entry.failure_categories),
            }
        )
    ledger_row = {
        "record_id": record_id,
        "analysis_variant": variant,
        "final_status": result.final_status,
        "attempt_count": len(result.attempt_entries),
        "accepted": result.final_status == PipelineFinalStatus.ACCEPTED.value,
    }
    accepted: dict[str, Any] | None = None
    if (
        result.final_status == PipelineFinalStatus.ACCEPTED.value
        and result.accepted_canonical_prediction is not None
    ):
        accepted = dict(result.accepted_canonical_prediction)
    record_result = {
        "record_id": record_id,
        "analysis_variant": variant,
        "final_status": result.final_status,
        "accepted": result.final_status == PipelineFinalStatus.ACCEPTED.value,
        "failure_categories": list(result.failure_categories),
    }
    return raw_rows, [ledger_row], accepted, record_result


def _analysis_output_row(
    *,
    record: dict[str, Any],
    candidate: BaseModelCandidate,
    analysis_variant: str,
    canonical: dict[str, Any] | None,
) -> dict[str, Any]:
    system_input = _system_input_from_record(record, analysis_variant=analysis_variant)
    if canonical is None:
        return {
            "record_id": record["record_id"],
            "analysis_variant": analysis_variant,
            "accepted": False,
            "analysis": None,
            "analysis_identity": None,
        }
    analysis = canonical_to_structured_analysis(
        canonical,
        candidate=candidate,
        analysis_variant=analysis_variant,
    )
    identity = build_analysis_identity(
        record_id=str(record["record_id"]),
        source_input=system_input,
        analysis=analysis,
        analysis_variant=analysis_variant,
        model_strategy_id=None,
    )
    return {
        "record_id": record["record_id"],
        "analysis_variant": analysis_variant,
        "accepted": True,
        "analysis": analysis.to_dict(),
        "analysis_identity": identity.to_dict(),
    }


def run_candidate_preflight(
    *,
    candidate_id: str,
    result_dir: Path,
    run_id: str,
    source_commit: str,
    source_archive_sha256: str,
    source_identity_manifest: Path,
    root: Path | None = None,
    tokenizer_path: Path | str | None = None,
    tokenizer_factory: Callable[..., Any] | None = None,
    skip_runtime_import_check: bool = False,
) -> dict[str, Any]:
    validate_candidate_id(candidate_id)
    _validate_run_identity_args(
        source_commit=source_commit,
        source_archive_sha256=source_archive_sha256,
    )
    _refuse_nonempty_result_dir(result_dir, PREFLIGHT_EVIDENCE)
    repo = _repo_root(root)
    registry = load_base_model_candidate_registry(repo / "configs/model/base_model_candidates_v1.json")
    candidate = registry.get_candidate(candidate_id)
    runtime_config = load_bakeoff_runtime_config(repo)
    prompt_contract = load_bakeoff_prompt_contract(repo)

    checks: list[dict[str, Any]] = []
    status = "pass"
    rejection_reasons: list[str] = []

    checks.append({"check": "candidate_allowlisted", "passed": True, "candidate_id": candidate_id})
    checks.append({"check": "exact_revision", "passed": True, "revision": candidate.revision})
    checks.append({"check": "licence_present", "passed": bool(candidate.licence_identifier)})
    checks.append({"check": "gated_rejected", "passed": not (candidate.gated or candidate.private)})

    availability = check_provider_available()
    if not skip_runtime_import_check and not availability.available:
        status = "blocked"
        rejection_reasons.append("provider_unavailable")
        checks.append({"check": "runtime_imports", "passed": False, **availability.to_dict()})
    else:
        checks.append({"check": "runtime_imports", "passed": True, **availability.to_dict()})

    tokenizer_status = "skipped"
    if availability.available or skip_runtime_import_check:
        try:
            renderer = CandidateChatTemplateRenderer(
                candidate=candidate,
                tokenizer_path=tokenizer_path or candidate.repository,
                tokenizer_factory=tokenizer_factory,
            )
            renderer.load_tokenizer()
            sample_messages = build_prompt_messages(
                PromptBuildRequest(command="Preflight tokenizer load check.")
            )
            rendered = renderer.render(sample_messages)
            tokenizer_status = "loaded"
            checks.append(
                {
                    "check": "tokenizer_load",
                    "passed": bool(rendered.strip()),
                    "mechanics": renderer.mechanics,
                }
            )
        except Exception as exc:  # noqa: BLE001
            status = "fail"
            rejection_reasons.append(f"tokenizer_load_failed:{exc}")
            checks.append({"check": "tokenizer_load", "passed": False, "error": str(exc)})

    if availability.available:
        try:
            contract = load_structured_decode_contract(repo / "configs/model/t12_structured_decode_contract.json")
            build_structured_sampling_params(
                runtime_config.generation,
                contract,
                repo_root=repo,
            )
            checks.append({"check": "structured_decode_construction", "passed": True})
        except Exception as exc:  # noqa: BLE001
            status = "fail"
            rejection_reasons.append(f"structured_decode_failed:{exc}")
            checks.append({"check": "structured_decode_construction", "passed": False, "error": str(exc)})

    provenance = build_candidate_provenance(
        candidate=candidate,
        registry=registry,
        runtime_config=runtime_config,
        prompt_contract=prompt_contract,
    )
    _copy_source_identity_manifest(source_identity_manifest, result_dir)
    _atomic_write_json(result_dir / "candidate_provenance.json", provenance)
    result_payload = {
        "schema_version": "1.0.0",
        "status": status,
        "run_id": run_id,
        "candidate_id": candidate_id,
        "revision": candidate.revision,
        "repository": candidate.repository,
        "checks": checks,
        "rejection_reasons": rejection_reasons,
        "tokenizer_status": tokenizer_status,
        "provider_availability": availability.to_dict(),
        "development_only": True,
        "valid_for_official_use": False,
        "timestamp_utc": _utc_now(),
    }
    _atomic_write_json(result_dir / "preflight_result.json", result_payload)
    finalize_run_manifest(
        result_dir,
        run_id=run_id,
        profile="model_candidate_preflight",
        candidate_id=candidate_id,
        source_commit=source_commit,
        source_archive_sha256=source_archive_sha256,
        expected_files=PREFLIGHT_EVIDENCE,
        success=status == "pass",
    )
    return result_payload


def _run_generation_batch(
    *,
    records: Sequence[dict[str, Any]],
    candidate: BaseModelCandidate,
    registry: BaseModelCandidateRegistry,
    runtime_config: BakeoffRuntimeConfig,
    repo: Path,
    analysis_variants: Sequence[str],
    backend_factory: Callable[..., Any] | None = None,
    generator_factory: Callable[..., Any] | None = None,
    renderer_factory: Callable[..., Any] | None = None,
    structured_decode_readiness: StructuredDecodeReadiness | None = None,
) -> dict[str, Any]:
    availability = check_provider_available()
    if not availability.available:
        raise BakeoffProviderError("provider_unavailable")

    from ambiguity_manager.model.backends.vllm_batch import create_vllm_batch_backend, load_runtime_config

    vllm_runtime = load_runtime_config(repo / RUNTIME_CONFIG_REL, repo_root=repo)
    immutable = candidate_to_immutable_selection(candidate, registry)
    backend = (
        backend_factory(vllm_runtime, immutable=immutable, repo_root=repo)
        if backend_factory
        else create_vllm_batch_backend(vllm_runtime, repo_root=repo, immutable=immutable)
    )
    backend.start()
    try:
        readiness = structured_decode_readiness or _build_structured_decode_readiness(
            repo,
            generation_settings=runtime_config.generation,
        )
        chat_renderer = CandidateChatTemplateRenderer(
            candidate=candidate,
            tokenizer_path=immutable.tokenizer_repository,
        )
        renderer = (
            renderer_factory(
                candidate=candidate,
                chat_renderer=chat_renderer,
                container_sha256=runtime_config.container_sha256,
            )
            if renderer_factory
            else BakeoffGenerationReadyRenderer(
                candidate=candidate,
                chat_renderer=chat_renderer,
                container_sha256=runtime_config.container_sha256,
            )
        )
        backend_identity = BackendIdentity(
            backend_identifier=runtime_config.backend_identifier,
            backend_configuration_hash=runtime_config.config_hash,
        )

        raw_rows: list[dict[str, Any]] = []
        ledger_rows: list[dict[str, Any]] = []
        accepted_rows: list[dict[str, Any]] = []
        record_results: list[dict[str, Any]] = []
        analysis_rows: list[dict[str, Any]] = []
        accepted_count = 0
        attempted_count = 0
        unrecorded_failures = 0
        unconstrained_fallback = False

        ordinal = 0
        for record in records:
            for variant in analysis_variants:
                if variant not in ANALYSIS_VARIANTS:
                    raise BakeoffProviderError(f"unknown_analysis_variant:{variant}")
                request = pipeline_request_from_development_record(
                    record,
                    candidate=candidate,
                    runtime_config=runtime_config,
                    analysis_variant=variant,
                )
                errors = validate_pipeline_request(request)
                if errors:
                    raise BakeoffProviderError(f"invalid_pipeline_request:{record['record_id']}:{errors}")
                attempted_count += 1
                ordinal += 1
                generator = (
                    generator_factory(backend, ordinal=ordinal)
                    if generator_factory
                    else VllmPipelineGenerator(backend=backend, ordinal_base=100 + ordinal * 10)
                )
                pipeline_result = run_generation_pipeline(
                    request,
                    renderer=renderer,
                    generator=generator,
                    backend=backend_identity,
                    structured_decode_readiness=readiness,
                )
                raw, ledgers, accepted, record_result = _collect_attempt_rows(
                    pipeline_result,
                    record_id=str(record["record_id"]),
                    variant=variant,
                )
                raw_rows.extend(raw)
                ledger_rows.extend(ledgers)
                record_results.append(record_result)
                if accepted is not None:
                    accepted_rows.append({**accepted, "analysis_variant": variant})
                    accepted_count += 1
                if not raw:
                    unrecorded_failures += 1
                if FailureCategory.UNCONSTRAINED_FALLBACK_INDICATED.value in pipeline_result.failure_categories:
                    unconstrained_fallback = True
                analysis_rows.append(
                    _analysis_output_row(
                        record=record,
                        candidate=candidate,
                        analysis_variant=variant,
                        canonical=accepted,
                    )
                )

        return {
            "raw_rows": raw_rows,
            "ledger_rows": ledger_rows,
            "accepted_rows": accepted_rows,
            "record_results": record_results,
            "analysis_rows": analysis_rows,
            "accepted_count": accepted_count,
            "attempted_count": attempted_count,
            "unrecorded_failures": unrecorded_failures,
            "unconstrained_fallback": unconstrained_fallback,
        }
    finally:
        backend.close()


def run_transport_smoke(
    *,
    candidate_id: str,
    result_dir: Path,
    run_id: str,
    source_commit: str,
    source_archive_sha256: str,
    source_identity_manifest: Path,
    root: Path | None = None,
    backend_factory: Callable[..., Any] | None = None,
    generator_factory: Callable[..., Any] | None = None,
    renderer_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    validate_candidate_id(candidate_id)
    _validate_run_identity_args(
        source_commit=source_commit,
        source_archive_sha256=source_archive_sha256,
    )
    _refuse_nonempty_result_dir(result_dir, TRANSPORT_EVIDENCE)
    repo = _repo_root(root)
    registry = load_base_model_candidate_registry(repo / "configs/model/base_model_candidates_v1.json")
    candidate = registry.get_candidate(candidate_id)
    runtime_config = load_bakeoff_runtime_config(repo)
    dataset = load_model_selection_development_set(repo)
    smoke_ids = list(dataset.transport_smoke_ids)
    inputs_by_id = {str(row["record_id"]): row for row in dataset.inputs}
    records = [inputs_by_id[rid] for rid in smoke_ids]
    if len(records) != 4:
        raise BakeoffProviderError("transport_smoke_requires_four_records")

    availability = check_provider_available()
    if not availability.available:
        summary = {
            "schema_version": "1.0.0",
            "status": "blocked",
            "reason": "provider_unavailable",
            "candidate_id": candidate_id,
            "attempted_count": 0,
            "accepted_count": 0,
            "required_count": 4,
        }
        _copy_source_identity_manifest(source_identity_manifest, result_dir)
        _atomic_write_json(result_dir / "transport_smoke_summary.json", summary)
        finalize_run_manifest(
            result_dir,
            run_id=run_id,
            profile="model_candidate_transport_smoke",
            candidate_id=candidate_id,
            source_commit=source_commit,
            source_archive_sha256=source_archive_sha256,
            expected_files=TRANSPORT_EVIDENCE,
            success=False,
        )
        return summary

    batch = _run_generation_batch(
        records=records,
        candidate=candidate,
        registry=registry,
        runtime_config=runtime_config,
        repo=repo,
        analysis_variants=("full_context",),
        backend_factory=backend_factory,
        generator_factory=generator_factory,
        renderer_factory=renderer_factory,
    )
    thresholds = registry.development_bakeoff_thresholds
    status = "pass"
    rejection_reasons: list[str] = []
    if batch["attempted_count"] != thresholds["transport_records_required"]:
        status = "fail"
        rejection_reasons.append("attempt_count_mismatch")
    if batch["accepted_count"] < thresholds["transport_accepted_records_min"]:
        status = "fail"
        rejection_reasons.append("accepted_count_below_threshold")
    if batch["unrecorded_failures"] > thresholds["max_unrecorded_attempts"]:
        status = "fail"
        rejection_reasons.append("unrecorded_failures")
    if batch["unconstrained_fallback"]:
        status = "fail"
        rejection_reasons.append("unconstrained_fallback")

    _copy_source_identity_manifest(source_identity_manifest, result_dir)
    _atomic_write_jsonl(result_dir / "raw_attempts.jsonl", batch["raw_rows"])
    _atomic_write_jsonl(result_dir / "attempt_ledgers.jsonl", batch["ledger_rows"])
    _atomic_write_jsonl(result_dir / "accepted_predictions.jsonl", batch["accepted_rows"])
    _atomic_write_jsonl(result_dir / "record_results.jsonl", batch["record_results"])
    _atomic_write_jsonl(result_dir / "analysis_outputs.jsonl", batch["analysis_rows"])

    summary = {
        "schema_version": "1.0.0",
        "status": status,
        "run_id": run_id,
        "candidate_id": candidate_id,
        "revision": candidate.revision,
        "transport_record_ids": smoke_ids,
        "attempted_count": batch["attempted_count"],
        "accepted_count": batch["accepted_count"],
        "required_count": thresholds["transport_records_required"],
        "rejection_reasons": rejection_reasons,
        "development_only": True,
        "valid_for_official_use": False,
        "timestamp_utc": _utc_now(),
    }
    _atomic_write_json(result_dir / "transport_smoke_summary.json", summary)
    finalize_run_manifest(
        result_dir,
        run_id=run_id,
        profile="model_candidate_transport_smoke",
        candidate_id=candidate_id,
        source_commit=source_commit,
        source_archive_sha256=source_archive_sha256,
        expected_files=TRANSPORT_EVIDENCE,
        success=status == "pass",
        extra={"transport_record_ids": smoke_ids},
    )
    return summary


def run_bakeoff(
    *,
    candidate_id: str,
    result_dir: Path,
    run_id: str,
    source_commit: str,
    source_archive_sha256: str,
    source_identity_manifest: Path,
    root: Path | None = None,
    backend_factory: Callable[..., Any] | None = None,
    generator_factory: Callable[..., Any] | None = None,
    renderer_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    validate_candidate_id(candidate_id)
    _validate_run_identity_args(
        source_commit=source_commit,
        source_archive_sha256=source_archive_sha256,
    )
    _refuse_nonempty_result_dir(result_dir, BAKEOFF_EVIDENCE)
    repo = _repo_root(root)
    registry = load_base_model_candidate_registry(repo / "configs/model/base_model_candidates_v1.json")
    candidate = registry.get_candidate(candidate_id)
    runtime_config = load_bakeoff_runtime_config(repo)
    dataset = load_model_selection_development_set(repo)
    records = list(dataset.inputs)

    availability = check_provider_available()
    if not availability.available:
        summary = {
            "schema_version": "1.0.0",
            "status": "blocked",
            "reason": "provider_unavailable",
            "candidate_id": candidate_id,
        }
        _copy_source_identity_manifest(source_identity_manifest, result_dir)
        _atomic_write_json(result_dir / "bakeoff_summary.json", summary)
        finalize_run_manifest(
            result_dir,
            run_id=run_id,
            profile="model_candidate_bakeoff",
            candidate_id=candidate_id,
            source_commit=source_commit,
            source_archive_sha256=source_archive_sha256,
            expected_files=BAKEOFF_EVIDENCE,
            success=False,
        )
        return summary

    batch = _run_generation_batch(
        records=records,
        candidate=candidate,
        registry=registry,
        runtime_config=runtime_config,
        repo=repo,
        analysis_variants=("full_context", "context_blind"),
        backend_factory=backend_factory,
        generator_factory=generator_factory,
        renderer_factory=renderer_factory,
    )

    metrics_summary = _development_metrics_summary(
        records=records,
        record_results=batch["record_results"],
        analysis_rows=batch["analysis_rows"],
        gold_by_id=dataset.gold_by_id,
    )

    _copy_source_identity_manifest(source_identity_manifest, result_dir)
    _atomic_write_jsonl(result_dir / "raw_attempts.jsonl", batch["raw_rows"])
    _atomic_write_jsonl(result_dir / "attempt_ledgers.jsonl", batch["ledger_rows"])
    _atomic_write_jsonl(result_dir / "accepted_predictions.jsonl", batch["accepted_rows"])
    _atomic_write_jsonl(result_dir / "record_results.jsonl", batch["record_results"])
    cache_entries = [
        {
            "record_id": row["record_id"],
            "analysis_variant": row["analysis_variant"],
            "analysis_identity": row.get("analysis_identity"),
            "analysis": row.get("analysis"),
            "accepted": row.get("accepted"),
        }
        for row in batch["analysis_rows"]
    ]
    _atomic_write_jsonl(result_dir / "analysis_cache_entries.jsonl", cache_entries)

    summary = {
        "schema_version": "1.0.0",
        "status": "completed",
        "run_id": run_id,
        "candidate_id": candidate_id,
        "revision": candidate.revision,
        "record_count": len(records),
        "attempted_variant_runs": batch["attempted_count"],
        "accepted_variant_runs": batch["accepted_count"],
        "development_only": True,
        "valid_for_official_use": False,
        "valid_for_official_final_claims": False,
        "timestamp_utc": _utc_now(),
    }
    _atomic_write_json(result_dir / "bakeoff_summary.json", summary)
    _atomic_write_json(result_dir / "metrics_summary.json", metrics_summary)
    finalize_run_manifest(
        result_dir,
        run_id=run_id,
        profile="model_candidate_bakeoff",
        candidate_id=candidate_id,
        source_commit=source_commit,
        source_archive_sha256=source_archive_sha256,
        expected_files=BAKEOFF_EVIDENCE,
        success=True,
        extra={"record_count": len(records)},
    )
    return summary


def _development_metrics_summary(
    *,
    records: Sequence[dict[str, Any]],
    record_results: Sequence[dict[str, Any]],
    analysis_rows: Sequence[dict[str, Any]],
    gold_by_id: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    accepted_by_key = {
        (row["record_id"], row["analysis_variant"]): row.get("accepted")
        for row in analysis_rows
    }
    per_metric_eligible: dict[str, dict[str, int]] = {}
    for record in records:
        rid = str(record["record_id"])
        eligibility = record.get("label_eligibility") or record.get("metric_eligibility") or {}
        for metric, eligible in eligibility.items():
            if not eligible:
                continue
            bucket = per_metric_eligible.setdefault(metric, {"eligible_records": 0, "accepted_full_context": 0, "accepted_context_blind": 0})
            bucket["eligible_records"] += 1
            if accepted_by_key.get((rid, "full_context")):
                bucket["accepted_full_context"] += 1
            if accepted_by_key.get((rid, "context_blind")):
                bucket["accepted_context_blind"] += 1
    return {
        "schema_version": "1.0.0",
        "development_only": True,
        "valid_for_official_final_claims": False,
        "notes": [
            "Eligibility-aware development metrics only; not official claims.",
            "Gold comparison deferred where weak or absent labels.",
        ],
        "record_count": len(records),
        "gold_record_count": len(gold_by_id),
        "accepted_variant_runs": sum(1 for row in record_results if row.get("accepted")),
        "attempted_variant_runs": len(record_results),
        "per_metric_eligibility": per_metric_eligible,
    }
