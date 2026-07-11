"""T12 Slice 3B deterministic checkpoint download and integrity verification."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from ambiguity_manager.model.candidate_evidence import (
    MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES,
    REGISTER_REL,
    SHA_PATTERN,
)

EVIDENCE_REL = "configs/model/evidence/t12_checkpoint_download.json"
CANDIDATES_EVIDENCE_REL = "configs/model/evidence/t12_model_candidates.json"
RAW_LOG_DIR_REL = "outputs/model_downloads/raw"

AUTHORIZED_CANDIDATE_ENTRY_ID = "t12-cand-001"
AUTHORIZED_REPOSITORY_ID = "Qwen/Qwen2.5-1.5B-Instruct"
AUTHORIZED_REVISION_SHA = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
AUTHORIZED_TOKENIZER_REVISION_SHA = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
EXPECTED_DOWNLOAD_BYTES = 3098955668
DOWNLOAD_SIZE_TOLERANCE_BYTES = 104_857_600
MINIMUM_FREE_DISK_BYTES = 50 * 1024 * 1024 * 1024
CUMULATIVE_DOWNLOAD_CAP_DISPLAY = "30 GiB"
CACHE_POLICY_ID = "single_wsl_cache"

INCLUDE_PATTERNS: tuple[str, ...] = (
    "*.safetensors",
    "model.safetensors.index.json",
    "config.json",
    "generation_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.json",
    "merges.txt",
    "*.model",
    "LICENSE*",
    "README.md",
)

EXCLUDE_PATTERNS: tuple[str, ...] = (
    "pytorch_model*.bin",
    "tf_model*.h5",
    "flax_model*.msgpack",
    "*.onnx",
    "onnx/**",
    "*.gguf",
    "*.ggml",
    "*GPTQ*",
    "*gptq*",
    "*AWQ*",
    "*awq*",
    "original/**",
)

REQUIRED_CHECKPOINT_FILES: frozenset[str] = frozenset(
    {
        "config.json",
        "model.safetensors",
        "tokenizer.json",
        "tokenizer_config.json",
    }
)

OPTIONAL_MANIFEST_FILES: frozenset[str] = frozenset(
    {
        "generation_config.json",
        "special_tokens_map.json",
        "vocab.json",
        "merges.txt",
        "model.safetensors.index.json",
        "README.md",
    }
)

_REPO_WEIGHT_SUFFIXES = frozenset({".safetensors", ".bin", ".gguf", ".pt", ".pth", ".onnx", ".ckpt"})
_REPO_WEIGHT_GLOBS = ("pytorch_model*.bin", "model*.safetensors", "tf_model*.h5", "flax_model*.msgpack")
_REPO_EXCLUDED_PREFIXES = ("tests/", "external/", "outputs/", "data/raw/", ".venv", ".git/")
_WINDOWS_PATH_PATTERN = re.compile(r"^[A-Za-z]:[\\/]|^\\\\")
_ABSOLUTE_PATH_PATTERN = re.compile(r"^[A-Za-z]:[\\/]|^/home/|^/Users/|^\\\\")
_USERNAME_PATTERN = re.compile(r"\bhuzii\b", re.IGNORECASE)
_BRANCH_TAG_ONLY_PATTERN = re.compile(r"^(main|master|HEAD|v[\d.]+)$", re.IGNORECASE)
_THIRD_PARTY_QUANT_MARKERS = ("TheBloke/", "GPTQ", "gptq", "AWQ", "awq", "-gguf", "-GGUF")

SHA256_STREAM_CHUNK_BYTES = 1024 * 1024


class HubClient(Protocol):
    def model_info(self, repo_id: str, *, revision: str) -> Any: ...

    def list_repo_files(self, repo_id: str, *, revision: str) -> list[str]: ...

    def repo_info(self, repo_id: str, *, revision: str) -> Any: ...


@dataclass(frozen=True)
class RepoFileEntry:
    relpath: str
    size_bytes: int


@dataclass(frozen=True)
class DryRunResult:
    inventory: list[RepoFileEntry]
    files_already_cached: list[str]
    files_requiring_download: list[str]
    total_required_bytes: int
    pre_existing_cached_bytes: int
    cumulative_cache_bytes: int
    resolved_commit_sha: str
    gated_access: bool


@dataclass(frozen=True)
class PreflightResult:
    checks: dict[str, bool]
    errors: list[str]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def validate_commit_sha(value: Any, *, field: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, str) or not SHA_PATTERN.match(value):
        errors.append(f"{field} must be a 40-character lowercase hex commit SHA")
    elif _BRANCH_TAG_ONLY_PATTERN.match(value):
        errors.append(f"{field} must not be a branch or tag alias")
    return errors


def validate_repository_id(value: Any, *, field: str = "official_repository_id") -> list[str]:
    errors: list[str] = []
    if value != AUTHORIZED_REPOSITORY_ID:
        errors.append(f"{field} must be {AUTHORIZED_REPOSITORY_ID}")
    for marker in _THIRD_PARTY_QUANT_MARKERS:
        if isinstance(value, str) and marker in value:
            errors.append(f"{field} must not reference third-party or quantised repository")
    return errors


def _path_matches_pattern(relpath: str, pattern: str) -> bool:
    normalized = relpath.replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1]
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return True
    if fnmatch.fnmatch(normalized, pattern):
        return True
    if fnmatch.fnmatch(basename, pattern):
        return True
    return False


def matches_exclude_pattern(relpath: str) -> bool:
    return any(_path_matches_pattern(relpath, pattern) for pattern in EXCLUDE_PATTERNS)


def matches_include_pattern(relpath: str) -> bool:
    return any(_path_matches_pattern(relpath, pattern) for pattern in INCLUDE_PATTERNS)


def filter_allowed_repo_files(files: list[str]) -> list[str]:
    allowed: list[str] = []
    for relpath in sorted(files):
        if matches_exclude_pattern(relpath):
            continue
        if matches_include_pattern(relpath):
            allowed.append(relpath)
    return allowed


def streaming_sha256_hex(path: Path, *, chunk_bytes: int = SHA256_STREAM_CHUNK_BYTES) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_bytes)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def is_wsl_linux_runtime() -> bool:
    if os.name != "posix":
        return False
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    proc_version = Path("/proc/version")
    if proc_version.is_file():
        content = proc_version.read_text(encoding="utf-8", errors="ignore").lower()
        return "microsoft" in content or "wsl" in content
    return False


def resolve_hub_cache_dir() -> Path:
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(hf_home).expanduser().resolve() / "hub"
    hub_cache = os.environ.get("HF_HUB_CACHE")
    if hub_cache:
        return Path(hub_cache).expanduser().resolve()
    transformers_cache = os.environ.get("TRANSFORMERS_CACHE")
    if transformers_cache:
        return Path(transformers_cache).expanduser().resolve()
    return Path.home().expanduser().resolve() / ".cache" / "huggingface" / "hub"


def cache_dir_is_wsl_native(cache_dir: Path) -> bool:
    cache_posix = cache_dir.as_posix()
    if _WINDOWS_PATH_PATTERN.match(cache_posix):
        return False
    if cache_posix.startswith("/mnt/c/") or cache_posix.startswith("/mnt/C/"):
        return False
    return True


def free_disk_bytes(path: Path) -> int:
    usage = shutil.disk_usage(path)
    return int(usage.free)


def directory_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    if path.is_file():
        return path.stat().st_size
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def repo_contains_checkpoint_weights(repo_root: Path) -> list[str]:
    violations: list[str] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root).as_posix()
        if any(rel.startswith(prefix) for prefix in _REPO_EXCLUDED_PREFIXES):
            continue
        if path.suffix.lower() in _REPO_WEIGHT_SUFFIXES:
            violations.append(rel)
            continue
        basename = path.name
        if any(fnmatch.fnmatch(basename, pattern) for pattern in _REPO_WEIGHT_GLOBS):
            violations.append(rel)
    return violations


def load_register(repo_root: Path) -> dict[str, Any]:
    return json.loads((repo_root / REGISTER_REL).read_text(encoding="utf-8"))


def find_register_entry(register: dict[str, Any], entry_id: str) -> dict[str, Any] | None:
    for entry in register.get("entries", []):
        if isinstance(entry, dict) and entry.get("entry_id") == entry_id:
            return entry
    return None


def validate_candidate_eligibility(entry: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    if entry is None:
        errors.append(f"candidate entry {AUTHORIZED_CANDIDATE_ENTRY_ID} not found")
        return errors
    if entry.get("verification_status") != "candidate_evaluated":
        errors.append("candidate entry must remain candidate_evaluated")
    if entry.get("gated_access") is not False:
        errors.append("candidate entry must be ungated")
    if entry.get("model_id") != AUTHORIZED_REPOSITORY_ID:
        errors.append("candidate entry model_id mismatch")
    if entry.get("immutable_revision_sha") != AUTHORIZED_REVISION_SHA:
        errors.append("candidate entry immutable_revision_sha mismatch")
    for field in (
        "local_inference_permitted",
        "academic_research_permitted",
        "adapter_training_permitted",
    ):
        if entry.get(field) is not True:
            errors.append(f"candidate entry {field} must be true")
    return errors


def validate_no_token_for_ungated(*, token: str | None) -> list[str]:
    if token:
        return ["access token must not be supplied for ungated checkpoint download"]
    return []


def validate_dry_run_before_download(manifest: dict[str, Any]) -> list[str]:
    dry_run_status = manifest.get("dry_run_status")
    if dry_run_status != "completed":
        return ["dry-run must complete before download"]
    inventory = manifest.get("dry_run_file_inventory")
    if not isinstance(inventory, list) or not inventory:
        return ["dry_run_file_inventory must be populated by dry-run"]
    return []


def validate_download_approval(*, approve: bool) -> list[str]:
    if not approve:
        return ["download requires explicit --approve-dry-run flag after human review"]
    return []


def validate_size_tolerance(*, required_bytes: int, estimated_bytes: int = EXPECTED_DOWNLOAD_BYTES) -> list[str]:
    if required_bytes > estimated_bytes + DOWNLOAD_SIZE_TOLERANCE_BYTES:
        return [
            "required download bytes exceed estimated_download_bytes plus size tolerance",
        ]
    return []


def validate_cumulative_cap(*, cumulative_bytes: int, additional_bytes: int = 0) -> list[str]:
    projected = cumulative_bytes + additional_bytes
    if projected > MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES:
        return ["cumulative cache bytes would exceed 30 GiB cap"]
    return []


def validate_free_disk(*, free_bytes: int, minimum_bytes: int = MINIMUM_FREE_DISK_BYTES) -> list[str]:
    if free_bytes < minimum_bytes:
        return ["free disk below 50 GiB minimum"]
    return []


def build_file_inventory(
    hub: HubClient,
    *,
    repo_id: str,
    revision: str,
    file_size_lookup: Callable[[str], int] | None = None,
) -> list[RepoFileEntry]:
    repo_files = hub.list_repo_files(repo_id, revision=revision)
    allowed = filter_allowed_repo_files(repo_files)
    inventory: list[RepoFileEntry] = []
    for relpath in allowed:
        size = 0 if file_size_lookup is None else file_size_lookup(relpath)
        inventory.append(RepoFileEntry(relpath=relpath, size_bytes=size))
    return inventory


def perform_dry_run(
    hub: HubClient,
    *,
    repo_id: str,
    revision: str,
    cache_dir: Path,
    file_size_lookup: Callable[[str], int],
    cached_file_lookup: Callable[[str], bool],
    cumulative_cache_bytes: int | None = None,
) -> DryRunResult:
    errors: list[str] = []
    errors.extend(validate_repository_id(repo_id))
    errors.extend(validate_commit_sha(revision, field="revision"))
    if revision != AUTHORIZED_REVISION_SHA:
        errors.append("revision must equal authorised immutable SHA")

    info = hub.model_info(repo_id, revision=revision)
    resolved_sha = getattr(info, "sha", None) or getattr(getattr(info, "id", None), "sha", None)
    if not isinstance(resolved_sha, str):
        resolved_sha = revision
    if resolved_sha != AUTHORIZED_REVISION_SHA:
        errors.append("resolved Hub commit must equal authorised immutable SHA")

    gated = getattr(info, "gated", None)
    gated_access = bool(gated)
    if gated_access:
        errors.append("repository metadata reports gated access")

    inventory = build_file_inventory(
        hub,
        repo_id=repo_id,
        revision=revision,
        file_size_lookup=file_size_lookup,
    )
    if not inventory:
        errors.append("allowlist produced empty file inventory")

    already_cached: list[str] = []
    requiring_download: list[str] = []
    total_required = 0
    for entry in inventory:
        if cached_file_lookup(entry.relpath):
            already_cached.append(entry.relpath)
        else:
            requiring_download.append(entry.relpath)
            total_required += entry.size_bytes

    pre_existing = cumulative_cache_bytes
    if pre_existing is None:
        pre_existing = directory_size_bytes(cache_dir)

    errors.extend(validate_size_tolerance(required_bytes=total_required))
    errors.extend(validate_cumulative_cap(cumulative_bytes=pre_existing, additional_bytes=total_required))
    if errors:
        raise ValueError("; ".join(errors))

    return DryRunResult(
        inventory=inventory,
        files_already_cached=already_cached,
        files_requiring_download=requiring_download,
        total_required_bytes=total_required,
        pre_existing_cached_bytes=pre_existing,
        cumulative_cache_bytes=pre_existing + total_required,
        resolved_commit_sha=resolved_sha,
        gated_access=gated_access,
    )


def snapshot_cache_path(cache_dir: Path, *, repo_id: str, revision: str) -> Path:
    safe_repo = repo_id.replace("/", "--")
    return cache_dir / f"models--{safe_repo}" / "snapshots" / revision


def perform_preflight(
    repo_root: Path,
    *,
    repo_id: str,
    revision: str,
    cache_dir: Path,
    token: str | None = None,
    hub: HubClient | None = None,
    free_bytes: int | None = None,
    cumulative_cache_bytes: int | None = None,
) -> PreflightResult:
    checks: dict[str, bool] = {}
    errors: list[str] = []

    register = load_register(repo_root)
    entry = find_register_entry(register, AUTHORIZED_CANDIDATE_ENTRY_ID)
    candidate_errors = validate_candidate_eligibility(entry)
    checks["candidate_entry_eligible"] = not candidate_errors
    errors.extend(candidate_errors)

    checks["selected_model_null"] = register.get("selected_model") is None
    if not checks["selected_model_null"]:
        errors.append("selected_model must remain null")

    repo_errors = validate_repository_id(repo_id)
    checks["repository_id_authorised"] = not repo_errors
    errors.extend(repo_errors)

    revision_errors = validate_commit_sha(revision, field="revision")
    if revision != AUTHORIZED_REVISION_SHA:
        revision_errors.append("revision must equal authorised immutable SHA")
    checks["revision_authorised"] = not revision_errors
    errors.extend(revision_errors)

    token_errors = validate_no_token_for_ungated(token=token)
    checks["no_token_required"] = not token_errors
    errors.extend(token_errors)

    checks["wsl_runtime"] = is_wsl_linux_runtime()
    if not checks["wsl_runtime"]:
        errors.append("cache policy requires WSL Linux runtime")

    checks["wsl_native_cache"] = cache_dir_is_wsl_native(cache_dir)
    if not checks["wsl_native_cache"]:
        errors.append("cache directory must be on WSL Linux filesystem")

    measured_free = free_bytes if free_bytes is not None else free_disk_bytes(cache_dir.parent)
    disk_errors = validate_free_disk(free_bytes=measured_free)
    checks["free_disk_50gib"] = not disk_errors
    errors.extend(disk_errors)

    measured_cache = cumulative_cache_bytes
    if measured_cache is None:
        measured_cache = directory_size_bytes(cache_dir)
    cap_errors = validate_cumulative_cap(
        cumulative_bytes=measured_cache,
        additional_bytes=EXPECTED_DOWNLOAD_BYTES,
    )
    checks["cumulative_cap_headroom"] = not cap_errors
    errors.extend(cap_errors)

    weight_violations = repo_contains_checkpoint_weights(repo_root)
    checks["no_repo_local_weights"] = not weight_violations
    if weight_violations:
        errors.append("model-weight files must not exist inside repository")

    if hub is not None:
        info = hub.model_info(repo_id, revision=revision)
        resolved_sha = getattr(info, "sha", revision)
        checks["resolved_sha_matches"] = resolved_sha == AUTHORIZED_REVISION_SHA
        if not checks["resolved_sha_matches"]:
            errors.append("resolved Hub commit must equal authorised immutable SHA")
        gated = getattr(info, "gated", None)
        checks["ungated_metadata"] = not bool(gated)
        if not checks["ungated_metadata"]:
            errors.append("repository metadata reports gated access")
    else:
        checks["resolved_sha_matches"] = False
        checks["ungated_metadata"] = False

    return PreflightResult(checks=checks, errors=errors)


def _inventory_to_manifest_files(inventory: list[RepoFileEntry]) -> list[dict[str, Any]]:
    return [
        {"relpath": entry.relpath, "size_bytes": entry.size_bytes, "sha256": None}
        for entry in inventory
    ]


def build_scaffold_manifest() -> dict[str, Any]:
    return {
        "manifest_schema_version": "1.0.0",
        "ticket": "T12",
        "slice": "3B",
        "candidate_entry_id": AUTHORIZED_CANDIDATE_ENTRY_ID,
        "official_repository_id": AUTHORIZED_REPOSITORY_ID,
        "immutable_revision_sha": AUTHORIZED_REVISION_SHA,
        "tokenizer_revision_sha": AUTHORIZED_TOKENIZER_REVISION_SHA,
        "retrieval_timestamp": None,
        "cache_policy_identifier": CACHE_POLICY_ID,
        "dry_run_status": "not_executed",
        "dry_run_file_inventory": [],
        "expected_bytes": EXPECTED_DOWNLOAD_BYTES,
        "actual_downloaded_bytes": 0,
        "pre_existing_cached_bytes": 0,
        "cumulative_cache_bytes": 0,
        "remaining_cap_headroom_bytes": MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES,
        "free_disk_before_bytes": None,
        "free_disk_after_bytes": None,
        "allow_patterns": list(INCLUDE_PATTERNS),
        "ignore_patterns": list(EXCLUDE_PATTERNS),
        "resolved_commit_sha": None,
        "files": [],
        "required_file_checks": {},
        "excluded_file_checks": {"excluded_present": False, "violations": []},
        "gated_access": False,
        "no_token_used": True,
        "no_model_load": True,
        "no_gpu_allocation": True,
        "checkpoint_load_verified": False,
        "selected_model": None,
        "overall_status": "pending",
    }


def manifest_from_dry_run(
    dry_run: DryRunResult,
    *,
    free_disk_before_bytes: int,
    retrieval_timestamp: str | None = None,
) -> dict[str, Any]:
    manifest = build_scaffold_manifest()
    manifest.update(
        {
            "retrieval_timestamp": retrieval_timestamp or utc_now_iso(),
            "dry_run_status": "completed",
            "dry_run_file_inventory": _inventory_to_manifest_files(dry_run.inventory),
            "pre_existing_cached_bytes": dry_run.pre_existing_cached_bytes,
            "cumulative_cache_bytes": dry_run.cumulative_cache_bytes,
            "remaining_cap_headroom_bytes": MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES
            - dry_run.cumulative_cache_bytes,
            "free_disk_before_bytes": free_disk_before_bytes,
            "resolved_commit_sha": dry_run.resolved_commit_sha,
            "gated_access": dry_run.gated_access,
            "overall_status": "dry_run_complete",
            "download_required_bytes": dry_run.total_required_bytes,
            "files_already_cached": dry_run.files_already_cached,
            "files_requiring_download": dry_run.files_requiring_download,
        }
    )
    return manifest


def verify_downloaded_snapshot(
    snapshot_dir: Path,
    *,
    dry_run_inventory: list[dict[str, Any]],
    revision: str = AUTHORIZED_REVISION_SHA,
) -> dict[str, Any]:
    if snapshot_dir.name != revision:
        raise ValueError("snapshot directory revision mismatch")

    inventory_paths = {item["relpath"] for item in dry_run_inventory}
    observed_files: list[str] = []
    for path in snapshot_dir.rglob("*"):
        if path.is_file():
            observed_files.append(path.relative_to(snapshot_dir).as_posix())

    observed_set = set(observed_files)
    if observed_set != inventory_paths:
        missing = sorted(inventory_paths - observed_set)
        extra = sorted(observed_set - inventory_paths)
        raise ValueError(f"inventory mismatch missing={missing} extra={extra}")

    excluded_violations = [relpath for relpath in observed_files if matches_exclude_pattern(relpath)]
    if excluded_violations:
        raise ValueError(f"excluded files present: {excluded_violations}")

    required_checks: dict[str, bool] = {}
    for required in sorted(REQUIRED_CHECKPOINT_FILES):
        required_checks[required] = required in observed_set

    missing_required = [name for name, present in required_checks.items() if not present]
    if missing_required:
        raise ValueError(f"required files missing: {missing_required}")

    optional_checks: dict[str, bool | None] = {}
    for optional in sorted(OPTIONAL_MANIFEST_FILES):
        optional_checks[optional] = optional in observed_set

    file_records: list[dict[str, Any]] = []
    total_bytes = 0
    hash_targets = (
        "config.json",
        "generation_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "vocab.json",
        "merges.txt",
        "model.safetensors.index.json",
    )
    for relpath in sorted(observed_files):
        path = snapshot_dir / relpath
        size = path.stat().st_size
        total_bytes += size
        sha256 = None
        should_hash = (
            relpath.endswith(".safetensors")
            or relpath in hash_targets
            or fnmatch.fnmatch(path.name, "LICENSE*")
            or path.name.endswith(".model")
        )
        if should_hash:
            sha256 = streaming_sha256_hex(path)
        file_records.append({"relpath": relpath, "size_bytes": size, "sha256": sha256})

    return {
        "required_file_checks": required_checks,
        "optional_file_checks": optional_checks,
        "excluded_file_checks": {"excluded_present": False, "violations": []},
        "files": file_records,
        "snapshot_total_bytes": total_bytes,
    }


def validate_checkpoint_download_evidence(
    data: dict[str, Any],
    *,
    register: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []

    if data.get("manifest_schema_version") != "1.0.0":
        errors.append("manifest_schema_version must be 1.0.0")
    if data.get("ticket") != "T12":
        errors.append("ticket must be T12")
    if data.get("slice") != "3B":
        errors.append("slice must be 3B")

    if data.get("candidate_entry_id") != AUTHORIZED_CANDIDATE_ENTRY_ID:
        errors.append("candidate_entry_id must be t12-cand-001")

    errors.extend(validate_repository_id(data.get("official_repository_id")))
    errors.extend(
        validate_commit_sha(data.get("immutable_revision_sha"), field="immutable_revision_sha")
    )
    if data.get("immutable_revision_sha") != AUTHORIZED_REVISION_SHA:
        errors.append("immutable_revision_sha must equal authorised SHA")
    errors.extend(
        validate_commit_sha(data.get("tokenizer_revision_sha"), field="tokenizer_revision_sha")
    )
    if data.get("tokenizer_revision_sha") != AUTHORIZED_TOKENIZER_REVISION_SHA:
        errors.append("tokenizer_revision_sha must equal authorised SHA")

    if data.get("cache_policy_identifier") != CACHE_POLICY_ID:
        errors.append("cache_policy_identifier must be single_wsl_cache")

    if data.get("expected_bytes") != EXPECTED_DOWNLOAD_BYTES:
        errors.append("expected_bytes must be 3098955668")

    if data.get("allow_patterns") != list(INCLUDE_PATTERNS):
        errors.append("allow_patterns must match Slice 3B allowlist")
    if data.get("ignore_patterns") != list(EXCLUDE_PATTERNS):
        errors.append("ignore_patterns must match Slice 3B ignore list")

    if data.get("no_model_load") is not True:
        errors.append("no_model_load must be true")
    if data.get("no_gpu_allocation") is not True:
        errors.append("no_gpu_allocation must be true")
    if data.get("checkpoint_load_verified") is not False:
        errors.append("checkpoint_load_verified must be false")
    if data.get("selected_model") is not None:
        errors.append("selected_model must remain null")

    overall = data.get("overall_status")
    valid_statuses = {"pending", "dry_run_complete", "download_complete", "verified"}
    if overall not in valid_statuses:
        errors.append("overall_status invalid")

    dry_run_status = data.get("dry_run_status")
    if dry_run_status not in {"not_executed", "completed"}:
        errors.append("dry_run_status invalid")

    if overall in {"dry_run_complete", "download_complete", "verified"}:
        if dry_run_status != "completed":
            errors.append("dry_run_status must be completed once dry-run evidence exists")
        inventory = data.get("dry_run_file_inventory")
        if not isinstance(inventory, list) or not inventory:
            errors.append("dry_run_file_inventory required after dry-run")
        if data.get("resolved_commit_sha") != AUTHORIZED_REVISION_SHA:
            errors.append("resolved_commit_sha must equal authorised SHA")
        if data.get("gated_access") is not False:
            errors.append("gated_access must be false")
        if data.get("no_token_used") is not True:
            errors.append("no_token_used must be true")

    if register is not None:
        if register.get("selected_model") is not None:
            errors.append("licence register selected_model must remain null")
        entry = find_register_entry(register, AUTHORIZED_CANDIDATE_ENTRY_ID)
        errors.extend(validate_candidate_eligibility(entry))

    cumulative = data.get("cumulative_cache_bytes")
    if isinstance(cumulative, int) and cumulative > MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES:
        errors.append("cumulative_cache_bytes exceeds 30 GiB cap")

    _scan_forbidden_identifiers(data, "evidence", errors)
    return errors
