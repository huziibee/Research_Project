"""T12 Slice 3C offline checkpoint load validation and evidence."""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ambiguity_manager.governance.model_licence import MANDATORY_CONTEXT_LIMIT
from ambiguity_manager.model.checkpoint_download import (
    AUTHORIZED_CANDIDATE_ENTRY_ID,
    AUTHORIZED_REPOSITORY_ID,
    AUTHORIZED_REVISION_SHA,
    AUTHORIZED_TOKENIZER_REVISION_SHA,
    CACHE_POLICY_ID,
    EVIDENCE_REL as DOWNLOAD_EVIDENCE_REL,
    REGISTER_REL,
    cache_dir_is_wsl_native,
    find_register_entry,
    is_wsl_linux_runtime,
    resolve_hub_cache_dir,
    snapshot_cache_path,
    streaming_sha256_hex,
    validate_candidate_eligibility,
    validate_commit_sha,
    validate_repository_id,
)
from ambiguity_manager.model.context_budget import DEFAULT_SAFETY_MARGIN
from ambiguity_manager.model.environment import INFERENCE_ENV_REL, TRAINING_ENV_REL
from ambiguity_manager.model.errors import ModelClientError
from ambiguity_manager.model.protocol import ModelRuntimeSpec

LOAD_EVIDENCE_REL = "configs/model/evidence/t12_checkpoint_load.json"
RAW_LOG_DIR_REL = "outputs/checkpoint_load"
SMOKE_RAW_DIR_REL = "outputs/model_runs/raw"

VERIFIED_LOAD_FILES: frozenset[str] = frozenset(
    {
        "LICENSE",
        "README.md",
        "config.json",
        "generation_config.json",
        "merges.txt",
        "model.safetensors",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.json",
    }
)

REQUIRED_OFFLINE_ENV = frozenset(
    {
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
    }
)

MIN_AVAILABLE_RAM_MIB = 4096
MIN_FREE_VRAM_MIB = 6144
DEFAULT_TIMEOUT_S = 300.0
NF4_QUANT_TYPE = "nf4"
BACKEND_ID = "hf_transformers_local"
POST_EXIT_VRAM_TOLERANCE_MIB = 256.0

# Official Qwen2.5-1.5B-Instruct model-card totals (not post-quantisation storage).
OFFICIAL_ARCHITECTURAL_PARAMETER_COUNT = 1_543_714_304
OFFICIAL_ARCHITECTURAL_PARAMETER_COUNT_DISPLAY = "1.54B"
OFFICIAL_ARCHITECTURAL_PARAMETER_COUNT_SOURCE = (
    "official_model_card_total_parameters;cross_verified_model_licence_register"
)
OFFICIAL_NON_EMBEDDING_PARAMETER_COUNT_APPROX = 1_310_000_000
OFFICIAL_NON_EMBEDDING_PARAMETER_COUNT_DISPLAY = "1.31B"
OFFICIAL_NON_EMBEDDING_PARAMETER_COUNT_SOURCE = "official_model_card_approximate"

# Observed during Slice 3C NF4 load probes; packed quantised parameter storage only.
OBSERVED_LOADED_QUANTIZED_STORAGE_NUMEL = 888_616_448
LOADED_QUANTIZED_STORAGE_NUMEL_SOURCE = (
    "post_quantisation_nf4_loaded_model_parameters_numel"
)

DEPRECATED_IDENTITY_FIELDS = frozenset({"parameter_count"})

_ABSOLUTE_PATH_PATTERN = re.compile(r"^[A-Za-z]:[\\/]|^/home/|^/Users/|^\\\\")
_USERNAME_PATTERN = re.compile(r"\bhuzii\b", re.IGNORECASE)


class CheckpointLoadError(Exception):
    """Raised when checkpoint load preconditions fail."""


@dataclass(frozen=True)
class QuantisationConfig:
    load_in_4bit: bool
    bnb_4bit_quant_type: str
    bnb_4bit_use_double_quant: bool
    bnb_4bit_compute_dtype: str
    compute_dtype_fallback: str | None
    device_map: str
    trust_remote_code: bool
    low_cpu_mem_usage: bool
    attn_implementation: str
    use_cache: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "load_in_4bit": self.load_in_4bit,
            "bnb_4bit_quant_type": self.bnb_4bit_quant_type,
            "bnb_4bit_use_double_quant": self.bnb_4bit_use_double_quant,
            "bnb_4bit_compute_dtype": self.bnb_4bit_compute_dtype,
            "compute_dtype_fallback": self.compute_dtype_fallback,
            "device_map": self.device_map,
            "trust_remote_code": self.trust_remote_code,
            "low_cpu_mem_usage": self.low_cpu_mem_usage,
            "attn_implementation": self.attn_implementation,
            "use_cache": self.use_cache,
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def derive_config_formula_parameter_count(config: dict[str, Any]) -> int | None:
    """Deterministic Qwen2 GQA parameter estimate from verified config.json fields."""
    try:
        hidden = int(config["hidden_size"])
        layers = int(config["num_hidden_layers"])
        intermediate = int(config["intermediate_size"])
        vocab = int(config["vocab_size"])
        num_heads = int(config["num_attention_heads"])
        num_kv_heads = int(config["num_key_value_heads"])
    except (KeyError, TypeError, ValueError):
        return None
    if num_heads <= 0:
        return None
    head_dim = hidden // num_heads
    embed = vocab * hidden
    attn = hidden * hidden + 2 * hidden * num_kv_heads * head_dim + hidden * hidden
    mlp = 3 * hidden * intermediate
    layer_params = attn + mlp + 2 * hidden
    return embed + layers * layer_params + hidden


def build_architectural_parameter_evidence(
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "architectural_parameter_count": OFFICIAL_ARCHITECTURAL_PARAMETER_COUNT,
        "architectural_parameter_count_display": OFFICIAL_ARCHITECTURAL_PARAMETER_COUNT_DISPLAY,
        "architectural_parameter_count_source": OFFICIAL_ARCHITECTURAL_PARAMETER_COUNT_SOURCE,
        "architectural_parameter_count_is_exact": True,
        "architectural_non_embedding_parameter_count": OFFICIAL_NON_EMBEDDING_PARAMETER_COUNT_APPROX,
        "architectural_non_embedding_parameter_count_display": (
            OFFICIAL_NON_EMBEDDING_PARAMETER_COUNT_DISPLAY
        ),
        "architectural_non_embedding_parameter_count_is_approximate": True,
        "architectural_non_embedding_parameter_count_source": (
            OFFICIAL_NON_EMBEDDING_PARAMETER_COUNT_SOURCE
        ),
    }
    if config is not None:
        formula_count = derive_config_formula_parameter_count(config)
        if formula_count is not None:
            evidence["verified_config_formula_parameter_count"] = formula_count
            evidence["verified_config_formula_parameter_count_source"] = (
                "verified_config.json:deterministic_qwen2_gqa_formula"
            )
            evidence["verified_config_formula_matches_official_exact"] = (
                formula_count == OFFICIAL_ARCHITECTURAL_PARAMETER_COUNT
            )
    return evidence


def validate_identity_evidence(identity: dict[str, Any], *, prefix: str = "identity_evidence") -> list[str]:
    errors: list[str] = []
    for deprecated in DEPRECATED_IDENTITY_FIELDS:
        if deprecated in identity:
            errors.append(f"{prefix} must not contain deprecated field {deprecated}")

    arch = identity.get("architectural_parameter_count")
    packed = identity.get("loaded_quantized_storage_numel")
    if not isinstance(arch, int):
        errors.append(f"{prefix}.architectural_parameter_count required")
    if not isinstance(packed, int):
        errors.append(f"{prefix}.loaded_quantized_storage_numel required")
    if isinstance(arch, int) and isinstance(packed, int) and arch == packed:
        errors.append(
            f"{prefix}.loaded_quantized_storage_numel must not equal architectural_parameter_count"
        )
    if isinstance(arch, int) and arch == OBSERVED_LOADED_QUANTIZED_STORAGE_NUMEL:
        errors.append(
            f"{prefix}.architectural_parameter_count must not use post-quantisation storage numel"
        )
    if not identity.get("architectural_parameter_count_source"):
        errors.append(f"{prefix}.architectural_parameter_count_source required")
    if not identity.get("loaded_quantized_storage_numel_source"):
        errors.append(f"{prefix}.loaded_quantized_storage_numel_source required")
    return errors


def gpu_free_vram_mib() -> float | None:
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        free_bytes, _total = torch.cuda.mem_get_info(0)
        return round(free_bytes / (1024 * 1024), 3)
    except ImportError:
        return None


def build_in_process_cleanup_evidence(
    *,
    references_released: bool,
    gc_collect_completed: bool,
    cuda_empty_cache_completed: bool,
    in_process_post_cleanup_free_vram_mib: float | None,
    baseline_free_vram_mib: float | None,
) -> dict[str, Any]:
    vram_restored = None
    if (
        isinstance(in_process_post_cleanup_free_vram_mib, (int, float))
        and isinstance(baseline_free_vram_mib, (int, float))
    ):
        vram_restored = in_process_post_cleanup_free_vram_mib >= baseline_free_vram_mib
    return {
        "in_process_cleanup_completed": bool(
            references_released and gc_collect_completed and cuda_empty_cache_completed
        ),
        "references_released": references_released,
        "gc_collect_completed": gc_collect_completed,
        "cuda_empty_cache_completed": cuda_empty_cache_completed,
        "in_process_post_cleanup_free_vram_mib": in_process_post_cleanup_free_vram_mib,
        "vram_fully_restored_in_process": vram_restored,
        "vram_fully_restored_in_process_note": (
            "CUDA context may retain VRAM until process exit; "
            "in-process empty_cache does not guarantee baseline restoration"
        ),
    }


def build_process_exit_reclaim_evidence(
    *,
    worker_process_exit_completed: bool,
    post_process_exit_free_vram_mib: float | None,
    baseline_free_vram_mib: float | None,
    lingering_probe_processes_detected: bool,
    measurement_tolerance_mib: float = POST_EXIT_VRAM_TOLERANCE_MIB,
) -> dict[str, Any]:
    reclaimed = None
    within_tolerance = None
    if (
        isinstance(post_process_exit_free_vram_mib, (int, float))
        and isinstance(baseline_free_vram_mib, (int, float))
    ):
        delta = abs(post_process_exit_free_vram_mib - baseline_free_vram_mib)
        within_tolerance = delta <= measurement_tolerance_mib
        reclaimed = worker_process_exit_completed and not lingering_probe_processes_detected
    return {
        "worker_process_exit_completed": worker_process_exit_completed,
        "post_process_exit_free_vram_mib": post_process_exit_free_vram_mib,
        "baseline_free_vram_mib": baseline_free_vram_mib,
        "measurement_tolerance_mib": measurement_tolerance_mib,
        "post_exit_within_baseline_tolerance": within_tolerance,
        "model_vram_reclaimed_after_process_exit": reclaimed,
        "lingering_probe_processes_detected": lingering_probe_processes_detected,
    }


def build_cleanup_evidence(
    *,
    in_process: dict[str, Any],
    process_exit: dict[str, Any],
) -> dict[str, Any]:
    return {
        **in_process,
        "process_exit_reclaim": process_exit,
    }


def detect_lingering_probe_processes() -> list[int]:
    """Return PIDs of probe/worker python processes other than the current process."""
    import subprocess

    current = os.getpid()
    patterns = (
        "t12_probe_checkpoint_load.py",
        "generation_worker",
        "hf_load_helpers",
    )
    try:
        completed = subprocess.run(
            ["ps", "-eo", "pid,args"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    lingering: list[int] = []
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("pid"):
            continue
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if pid == current:
            continue
        args = parts[1]
        if "python" in args and any(pattern in args for pattern in patterns):
            lingering.append(pid)
    return lingering


def load_verified_config_dict(snapshot_dir: Path) -> dict[str, Any]:
    config_path = snapshot_dir / "config.json"
    return json.loads(config_path.read_text(encoding="utf-8"))


def migrate_identity_evidence(identity: dict[str, Any], *, config: dict[str, Any] | None) -> dict[str, Any]:
    migrated = dict(identity)
    migrated.pop("parameter_count", None)
    migrated.update(build_architectural_parameter_evidence(config=config))
    packed = identity.get("loaded_quantized_storage_numel")
    if not isinstance(packed, int):
        packed = identity.get("parameter_count")
    if isinstance(packed, int):
        migrated["loaded_quantized_storage_numel"] = packed
    elif OBSERVED_LOADED_QUANTIZED_STORAGE_NUMEL:
        migrated["loaded_quantized_storage_numel"] = OBSERVED_LOADED_QUANTIZED_STORAGE_NUMEL
    migrated["loaded_quantized_storage_numel_source"] = LOADED_QUANTIZED_STORAGE_NUMEL_SOURCE
    if "loaded_model_memory_footprint_bytes" not in migrated:
        peak_mib = identity.get("peak_allocated_vram_mib")
        if isinstance(peak_mib, (int, float)):
            migrated["loaded_model_memory_footprint_bytes"] = int(round(peak_mib * 1024 * 1024))
    return migrated


def migrate_cleanup_evidence(
    section: dict[str, Any],
    *,
    post_process_exit_free_vram_mib: float | None,
    lingering_probe_processes_detected: bool,
    worker_process_exit_completed: bool = True,
) -> dict[str, Any]:
    before = section.get("resource_evidence_before") or {}
    after = section.get("resource_evidence_after") or {}
    baseline = before.get("gpu_free_vram_mib")
    in_process_free = after.get("gpu_free_vram_mib")

    old = section.get("cleanup_result") or {}
    in_process = build_in_process_cleanup_evidence(
        references_released=bool(old.get("references_released", True)),
        gc_collect_completed=bool(old.get("gc_collect_completed", True)),
        cuda_empty_cache_completed=bool(
            old.get("cuda_empty_cache_completed", old.get("torch_cuda_empty_cache_completed", True))
        ),
        in_process_post_cleanup_free_vram_mib=in_process_free,
        baseline_free_vram_mib=baseline,
    )
    process_exit = build_process_exit_reclaim_evidence(
        worker_process_exit_completed=worker_process_exit_completed,
        post_process_exit_free_vram_mib=post_process_exit_free_vram_mib,
        baseline_free_vram_mib=baseline,
        lingering_probe_processes_detected=lingering_probe_processes_detected,
    )
    return build_cleanup_evidence(in_process=in_process, process_exit=process_exit)


def _scan_forbidden_identifiers(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, str):
        if _ABSOLUTE_PATH_PATTERN.search(value):
            errors.append(f"{path} contains absolute path")
        if _USERNAME_PATTERN.search(value):
            errors.append(f"{path} contains username")
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            _scan_forbidden_identifiers(nested, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _scan_forbidden_identifiers(nested, f"{path}[{index}]", errors)


def validate_offline_flags(*, local_files_only: bool, trust_remote_code: bool) -> list[str]:
    errors: list[str] = []
    for var in REQUIRED_OFFLINE_ENV:
        if os.environ.get(var) != "1":
            errors.append(f"{var} must be 1")
    if not local_files_only:
        errors.append("local_files_only must be true")
    if trust_remote_code is not False:
        errors.append("trust_remote_code must be false")
    return errors


def build_quantisation_config(*, bf16_supported: bool, for_training: bool = False) -> QuantisationConfig:
    if bf16_supported:
        compute_dtype = "bfloat16"
        fallback = None
    else:
        compute_dtype = "float16"
        fallback = "float16"
    return QuantisationConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type=NF4_QUANT_TYPE,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
        compute_dtype_fallback=fallback,
        device_map="cuda:0",
        trust_remote_code=False,
        low_cpu_mem_usage=True,
        attn_implementation="eager",
        use_cache=not for_training,
    )


def build_runtime_spec(*, environment_id: str) -> ModelRuntimeSpec:
    return ModelRuntimeSpec(
        backend=BACKEND_ID,
        model_id=AUTHORIZED_REPOSITORY_ID,
        immutable_revision=AUTHORIZED_REVISION_SHA,
        tokenizer_revision=AUTHORIZED_TOKENIZER_REVISION_SHA,
        quantisation="nf4_4bit",
        environment_id=environment_id,
        device_policy="cuda:0",
    )


def locate_snapshot(cache_dir: Path) -> Path:
    snapshot = snapshot_cache_path(
        cache_dir,
        repo_id=AUTHORIZED_REPOSITORY_ID,
        revision=AUTHORIZED_REVISION_SHA,
    )
    if not snapshot.is_dir():
        raise CheckpointLoadError("cached snapshot directory not found")
    return snapshot


def verify_snapshot_file_hashes(
    snapshot_dir: Path,
    download_evidence: dict[str, Any],
) -> dict[str, str]:
    if snapshot_dir.name != AUTHORIZED_REVISION_SHA:
        raise CheckpointLoadError("snapshot revision mismatch")

    file_records = download_evidence.get("files")
    if not isinstance(file_records, list):
        raise CheckpointLoadError("download evidence files list missing")

    expected_hashes: dict[str, str] = {}
    for record in file_records:
        if not isinstance(record, dict):
            continue
        relpath = record.get("relpath")
        digest = record.get("sha256")
        if isinstance(relpath, str) and isinstance(digest, str):
            expected_hashes[relpath] = digest

    missing_hashes = sorted(VERIFIED_LOAD_FILES - set(expected_hashes))
    if missing_hashes:
        raise CheckpointLoadError(f"missing stored hashes for: {missing_hashes}")

    observed_files: list[str] = []
    for path in snapshot_dir.rglob("*"):
        if path.is_file():
            observed_files.append(path.relative_to(snapshot_dir).as_posix())

    observed_set = set(observed_files)
    inventory_paths = set(expected_hashes)
    if observed_set != inventory_paths:
        missing = sorted(inventory_paths - observed_set)
        extra = sorted(observed_set - inventory_paths)
        raise CheckpointLoadError(f"snapshot inventory mismatch missing={missing} extra={extra}")

    verified: dict[str, str] = {}
    for relpath in sorted(VERIFIED_LOAD_FILES):
        path = snapshot_dir / relpath
        actual = streaming_sha256_hex(path)
        expected = expected_hashes[relpath]
        if actual != expected:
            raise CheckpointLoadError(f"hash mismatch for {relpath}")
        verified[relpath] = actual
    return verified


def validate_download_evidence_for_load(download_evidence: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if download_evidence.get("overall_status") != "verification_complete":
        errors.append("checkpoint download evidence must be verification_complete")
    if download_evidence.get("verification_status") != "completed":
        errors.append("checkpoint download verification_status must be completed")
    if download_evidence.get("candidate_entry_id") != AUTHORIZED_CANDIDATE_ENTRY_ID:
        errors.append("candidate_entry_id must be t12-cand-001")
    errors.extend(validate_repository_id(download_evidence.get("official_repository_id")))
    errors.extend(
        validate_commit_sha(download_evidence.get("immutable_revision_sha"), field="immutable_revision_sha")
    )
    if download_evidence.get("immutable_revision_sha") != AUTHORIZED_REVISION_SHA:
        errors.append("immutable_revision_sha must equal authorised SHA")
    errors.extend(
        validate_commit_sha(download_evidence.get("tokenizer_revision_sha"), field="tokenizer_revision_sha")
    )
    if download_evidence.get("tokenizer_revision_sha") != AUTHORIZED_TOKENIZER_REVISION_SHA:
        errors.append("tokenizer_revision_sha must equal authorised SHA")
    if download_evidence.get("selected_model") is not None:
        errors.append("selected_model must remain null")
    files = download_evidence.get("files")
    if not isinstance(files, list):
        errors.append("files list required")
    else:
        hashed = {
            item["relpath"]
            for item in files
            if isinstance(item, dict) and item.get("sha256")
        }
        missing = sorted(VERIFIED_LOAD_FILES - hashed)
        if missing:
            errors.append(f"missing sha256 for required files: {missing}")
    return errors


def validate_register_for_load(register: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if register.get("selected_model") is not None:
        errors.append("licence register selected_model must remain null")
    entry = find_register_entry(register, AUTHORIZED_CANDIDATE_ENTRY_ID)
    if entry is None:
        errors.append("candidate entry t12-cand-001 not found")
        return errors
    if entry.get("verification_status") != "candidate_evaluated":
        errors.append("candidate entry must remain candidate_evaluated")
    errors.extend(validate_candidate_eligibility(entry))
    return errors


def collect_resource_snapshot(
    *,
    cache_dir: Path,
    include_gpu: bool = True,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    try:
        with Path("/proc/meminfo").open(encoding="utf-8") as handle:
            meminfo = handle.read()
        available_kb = None
        swap_total_kb = None
        swap_free_kb = None
        for line in meminfo.splitlines():
            if line.startswith("MemAvailable:"):
                available_kb = int(line.split()[1])
            elif line.startswith("SwapTotal:"):
                swap_total_kb = int(line.split()[1])
            elif line.startswith("SwapFree:"):
                swap_free_kb = int(line.split()[1])
        if available_kb is not None:
            snapshot["available_ram_mib"] = round(available_kb / 1024, 3)
        if swap_total_kb is not None:
            snapshot["swap_total_mib"] = round(swap_total_kb / 1024, 3)
        if swap_total_kb is not None and swap_free_kb is not None:
            snapshot["swap_used_mib"] = round((swap_total_kb - swap_free_kb) / 1024, 3)
    except OSError:
        snapshot["meminfo_status"] = "unavailable"

    try:
        usage = shutil.disk_usage(cache_dir)
        snapshot["free_disk_bytes"] = int(usage.free)
    except OSError:
        snapshot["free_disk_status"] = "unavailable"

    from ambiguity_manager.model.checkpoint_download import physical_cache_bytes

    snapshot["physical_cache_bytes"] = physical_cache_bytes(cache_dir)

    if include_gpu:
        try:
            import torch

            if torch.cuda.is_available():
                free_bytes, total_bytes = torch.cuda.mem_get_info(0)
                snapshot["gpu_total_vram_mib"] = round(total_bytes / (1024 * 1024), 3)
                snapshot["gpu_free_vram_mib"] = round(free_bytes / (1024 * 1024), 3)
            else:
                snapshot["gpu_status"] = "cuda_unavailable"
        except ImportError:
            snapshot["gpu_status"] = "torch_unavailable"

    return snapshot


def validate_resource_gates(resource_snapshot: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    available = resource_snapshot.get("available_ram_mib")
    if isinstance(available, (int, float)) and available < MIN_AVAILABLE_RAM_MIB:
        errors.append(f"available RAM {available} MiB below {MIN_AVAILABLE_RAM_MIB} MiB gate")
    free_vram = resource_snapshot.get("gpu_free_vram_mib")
    if isinstance(free_vram, (int, float)) and free_vram < MIN_FREE_VRAM_MIB:
        errors.append(f"free GPU VRAM {free_vram} MiB below {MIN_FREE_VRAM_MIB} MiB gate")
    return errors


def validate_pre_load_gates(
    *,
    download_evidence: dict[str, Any],
    register: dict[str, Any],
    resource_snapshot: dict[str, Any],
    local_files_only: bool = True,
    trust_remote_code: bool = False,
) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_download_evidence_for_load(download_evidence))
    errors.extend(validate_register_for_load(register))
    errors.extend(validate_offline_flags(local_files_only=local_files_only, trust_remote_code=trust_remote_code))
    errors.extend(validate_resource_gates(resource_snapshot))
    if download_evidence.get("selected_model") is not None:
        errors.append("selected_model must be null before load")
    return errors


def validate_runtime_immutable(runtime: ModelRuntimeSpec, request_backend: str | None = None) -> None:
    if runtime.backend != BACKEND_ID:
        raise ModelClientError(f"backend must be {BACKEND_ID}")
    if request_backend is not None and request_backend != runtime.backend:
        raise ModelClientError("request-level runtime switching is not permitted")
    if runtime.immutable_revision != AUTHORIZED_REVISION_SHA:
        raise ModelClientError("immutable_revision must match authorised checkpoint SHA")
    if runtime.tokenizer_revision != AUTHORIZED_TOKENIZER_REVISION_SHA:
        raise ModelClientError("tokenizer_revision must match authorised checkpoint SHA")
    if runtime.model_id != AUTHORIZED_REPOSITORY_ID:
        raise ModelClientError("model_id must match authorised repository")


def validate_wsl_cache_policy(cache_dir: Path) -> list[str]:
    errors: list[str] = []
    if not is_wsl_linux_runtime():
        errors.append("checkpoint load requires WSL Linux runtime")
    if not cache_dir_is_wsl_native(cache_dir):
        errors.append("hub cache must be on WSL-native filesystem")
    return errors


def build_load_evidence_scaffold() -> dict[str, Any]:
    return {
        "manifest_schema_version": "1.0.0",
        "ticket": "T12",
        "slice": "3C",
        "candidate_entry_id": AUTHORIZED_CANDIDATE_ENTRY_ID,
        "official_repository_id": AUTHORIZED_REPOSITORY_ID,
        "immutable_revision_sha": AUTHORIZED_REVISION_SHA,
        "tokenizer_revision_sha": AUTHORIZED_TOKENIZER_REVISION_SHA,
        "checkpoint_download_evidence_sha256": None,
        "inference_environment_manifest_sha256": None,
        "training_environment_manifest_sha256": None,
        "inference_lockfile_sha256": None,
        "training_lockfile_sha256": None,
        "offline_flags": {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
        "local_files_only": True,
        "trust_remote_code": False,
        "quantisation_configuration": build_quantisation_config(bf16_supported=True).as_dict(),
        "context_limit": MANDATORY_CONTEXT_LIMIT,
        "safety_margin_tokens": DEFAULT_SAFETY_MARGIN,
        "timeout_policy_s": DEFAULT_TIMEOUT_S,
        "inference_environment_load": {
            "environment_id": "t12-inference-wsl2",
            "status": "pending",
            "identity_evidence": None,
            "resource_evidence_before": None,
            "resource_evidence_after": None,
            "load_duration_s": None,
            "cleanup_result": None,
        },
        "training_environment_load": {
            "environment_id": "t12-training-wsl2",
            "status": "pending",
            "identity_evidence": None,
            "peft_architecture_compatible": None,
            "resource_evidence_before": None,
            "resource_evidence_after": None,
            "load_duration_s": None,
            "cleanup_result": None,
        },
        "smoke_generation": {
            "status": "pending",
            "fixture_id": "syn-001",
            "seed": 0,
            "do_sample": False,
            "requested_max_new_tokens": 512,
            "raw_output_relpath": None,
            "raw_output_sha256": None,
            "parse_result": None,
            "schema_result": None,
            "final_status": None,
        },
        "no_research_data_access": True,
        "no_adapter_attached": True,
        "no_optimiser_step": True,
        "selected_model": None,
        "overall_status": "pending",
    }


def _validate_load_section(
    section: dict[str, Any],
    *,
    prefix: str,
    environment_id: str,
    require_peft: bool = False,
) -> list[str]:
    errors: list[str] = []
    if section.get("environment_id") != environment_id:
        errors.append(f"{prefix}.environment_id must be {environment_id}")
    status = section.get("status")
    if status not in {"pending", "passed", "failed", "blocked"}:
        errors.append(f"{prefix}.status invalid")
    if status == "passed":
        for field in (
            "identity_evidence",
            "resource_evidence_before",
            "resource_evidence_after",
            "load_duration_s",
            "cleanup_result",
        ):
            if section.get(field) is None:
                errors.append(f"{prefix}.{field} required when status is passed")
        identity = section.get("identity_evidence")
        if isinstance(identity, dict):
            if identity.get("immutable_revision_sha") != AUTHORIZED_REVISION_SHA:
                errors.append(f"{prefix}.identity_evidence.immutable_revision_sha mismatch")
            if identity.get("tokenizer_revision_sha") != AUTHORIZED_TOKENIZER_REVISION_SHA:
                errors.append(f"{prefix}.identity_evidence.tokenizer_revision_sha mismatch")
            errors.extend(validate_identity_evidence(identity, prefix=f"{prefix}.identity_evidence"))
        cleanup = section.get("cleanup_result")
        if isinstance(cleanup, dict) and status == "passed":
            if cleanup.get("vram_fully_restored_in_process") is True:
                errors.append(
                    f"{prefix}.cleanup_result must not claim vram_fully_restored_in_process=true"
                )
            exit_reclaim = cleanup.get("process_exit_reclaim")
            if not isinstance(exit_reclaim, dict):
                errors.append(f"{prefix}.cleanup_result.process_exit_reclaim required when passed")
            elif exit_reclaim.get("worker_process_exit_completed") is not True:
                errors.append(
                    f"{prefix}.cleanup_result.process_exit_reclaim.worker_process_exit_completed "
                    "must be true when passed"
                )
    if require_peft and status == "passed" and section.get("peft_architecture_compatible") is not True:
        errors.append(f"{prefix}.peft_architecture_compatible must be true when passed")
    return errors


def validate_checkpoint_load_evidence(
    data: dict[str, Any],
    *,
    download_evidence: dict[str, Any] | None = None,
    register: dict[str, Any] | None = None,
    inference_manifest: dict[str, Any] | None = None,
    training_manifest: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []

    if data.get("manifest_schema_version") != "1.0.0":
        errors.append("manifest_schema_version must be 1.0.0")
    if data.get("ticket") != "T12":
        errors.append("ticket must be T12")
    if data.get("slice") != "3C":
        errors.append("slice must be 3C")

    if data.get("candidate_entry_id") != AUTHORIZED_CANDIDATE_ENTRY_ID:
        errors.append("candidate_entry_id must be t12-cand-001")
    errors.extend(validate_repository_id(data.get("official_repository_id")))
    errors.extend(validate_commit_sha(data.get("immutable_revision_sha"), field="immutable_revision_sha"))
    if data.get("immutable_revision_sha") != AUTHORIZED_REVISION_SHA:
        errors.append("immutable_revision_sha must equal authorised SHA")
    errors.extend(validate_commit_sha(data.get("tokenizer_revision_sha"), field="tokenizer_revision_sha"))
    if data.get("tokenizer_revision_sha") != AUTHORIZED_TOKENIZER_REVISION_SHA:
        errors.append("tokenizer_revision_sha must equal authorised SHA")

    if data.get("local_files_only") is not True:
        errors.append("local_files_only must be true")
    if data.get("trust_remote_code") is not False:
        errors.append("trust_remote_code must be false")
    if data.get("selected_model") is not None:
        errors.append("selected_model must remain null")
    if data.get("no_research_data_access") is not True:
        errors.append("no_research_data_access must be true")
    if data.get("no_adapter_attached") is not True:
        errors.append("no_adapter_attached must be true")
    if data.get("no_optimiser_step") is not True:
        errors.append("no_optimiser_step must be true")

    offline = data.get("offline_flags")
    if not isinstance(offline, dict):
        errors.append("offline_flags must be an object")
    else:
        for var in REQUIRED_OFFLINE_ENV:
            if offline.get(var) != "1":
                errors.append(f"offline_flags.{var} must be 1")

    quant = data.get("quantisation_configuration")
    if not isinstance(quant, dict):
        errors.append("quantisation_configuration required")
    else:
        if quant.get("load_in_4bit") is not True:
            errors.append("quantisation_configuration.load_in_4bit must be true")
        if quant.get("bnb_4bit_quant_type") != NF4_QUANT_TYPE:
            errors.append("quantisation_configuration.bnb_4bit_quant_type must be nf4")
        if quant.get("bnb_4bit_use_double_quant") is not True:
            errors.append("quantisation_configuration.bnb_4bit_use_double_quant must be true")
        if quant.get("trust_remote_code") is not False:
            errors.append("quantisation_configuration.trust_remote_code must be false")

    if data.get("context_limit") != MANDATORY_CONTEXT_LIMIT:
        errors.append(f"context_limit must be {MANDATORY_CONTEXT_LIMIT}")
    if data.get("safety_margin_tokens") != DEFAULT_SAFETY_MARGIN:
        errors.append(f"safety_margin_tokens must be {DEFAULT_SAFETY_MARGIN}")

    inference = data.get("inference_environment_load")
    training = data.get("training_environment_load")
    smoke = data.get("smoke_generation")
    if isinstance(inference, dict):
        errors.extend(
            _validate_load_section(
                inference,
                prefix="inference_environment_load",
                environment_id="t12-inference-wsl2",
            )
        )
    else:
        errors.append("inference_environment_load required")
    if isinstance(training, dict):
        errors.extend(
            _validate_load_section(
                training,
                prefix="training_environment_load",
                environment_id="t12-training-wsl2",
                require_peft=True,
            )
        )
    else:
        errors.append("training_environment_load required")

    overall = data.get("overall_status")
    valid_overall = {"pending", "PASS", "PARTIALLY_VERIFIED", "BLOCKED", "FAIL"}
    if overall not in valid_overall:
        errors.append("overall_status invalid")

    if overall in {"PASS", "PARTIALLY_VERIFIED"}:
        if not isinstance(inference, dict) or inference.get("status") != "passed":
            errors.append("inference_environment_load must be passed for PASS/PARTIALLY_VERIFIED")
        if not isinstance(training, dict) or training.get("status") != "passed":
            errors.append("training_environment_load must be passed for PASS/PARTIALLY_VERIFIED")
        if overall == "PASS" and (not isinstance(smoke, dict) or smoke.get("status") != "passed"):
            errors.append("smoke_generation must be passed for PASS")

    if download_evidence is not None:
        errors.extend(validate_download_evidence_for_load(download_evidence))
        digest = data.get("checkpoint_download_evidence_sha256")
        if overall != "pending" and not isinstance(digest, str):
            errors.append("checkpoint_download_evidence_sha256 required after probes")

    if register is not None:
        errors.extend(validate_register_for_load(register))

    if inference_manifest is not None:
        if inference_manifest.get("checkpoint_load_verified") is True:
            if not isinstance(inference, dict) or inference.get("status") != "passed":
                errors.append(
                    "inference manifest checkpoint_load_verified cannot be true without passed load evidence"
                )
        elif overall == "PASS":
            errors.append("inference manifest checkpoint_load_verified must be true when overall PASS")

    if training_manifest is not None:
        if training_manifest.get("checkpoint_load_verified") is True:
            if not isinstance(training, dict) or training.get("status") != "passed":
                errors.append(
                    "training manifest checkpoint_load_verified cannot be true without passed load evidence"
                )
        elif overall == "PASS":
            errors.append("training manifest checkpoint_load_verified must be true when overall PASS")

    _scan_forbidden_identifiers(data, "evidence", errors)
    return errors


def compute_overall_status(evidence: dict[str, Any]) -> str:
    inference = evidence.get("inference_environment_load", {})
    training = evidence.get("training_environment_load", {})
    smoke = evidence.get("smoke_generation", {})
    inf_ok = isinstance(inference, dict) and inference.get("status") == "passed"
    train_ok = isinstance(training, dict) and training.get("status") == "passed"
    smoke_ok = isinstance(smoke, dict) and smoke.get("status") == "passed"
    if not inf_ok or not train_ok:
        if (
            isinstance(inference, dict)
            and inference.get("status") == "failed"
            or isinstance(training, dict)
            and training.get("status") == "failed"
        ):
            return "BLOCKED"
        return "pending"
    if smoke_ok:
        return "PASS"
    if isinstance(smoke, dict) and smoke.get("status") == "failed":
        return "PARTIALLY_VERIFIED"
    return "pending"


def resolve_load_paths(repo_root: Path) -> dict[str, Path]:
    return {
        "repo_root": repo_root.resolve(),
        "download_evidence": (repo_root / DOWNLOAD_EVIDENCE_REL).resolve(),
        "load_evidence": (repo_root / LOAD_EVIDENCE_REL).resolve(),
        "register": (repo_root / REGISTER_REL).resolve(),
        "inference_manifest": (repo_root / INFERENCE_ENV_REL).resolve(),
        "training_manifest": (repo_root / TRAINING_ENV_REL).resolve(),
        "raw_log_dir": (repo_root / RAW_LOG_DIR_REL).resolve(),
        "smoke_raw_dir": (repo_root / SMOKE_RAW_DIR_REL).resolve(),
        "hub_cache_dir": resolve_hub_cache_dir(),
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
