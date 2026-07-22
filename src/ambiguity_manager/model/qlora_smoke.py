"""QLoRA technical-smoke core module (T27 Phase E).

Proves the mechanical adaptation-training contract (frozen base, trainable
adapter, adapter saved separately from the base, exact-base reload, resume,
and evidence finalisation on both success and failure) before any full QLoRA
training run is attempted.

Hard requirements enforced by this module:

- ``selected_base_model`` must already be populated by Phase D in
  ``configs/model/selected_identities_v1.json``. This module never invents,
  guesses, or accepts an arbitrary base-model identity as a substitute.
- A smoke adapter is always ``technical_smoke_only=True``,
  ``selected_adapter=False``, ``valid_for_official_use=False``. It can never
  become the official ``selected_adapter``.
- The base checkpoint is never merged into the adapter and never mutated;
  adapter weights are always written to a separate output directory.
- Evidence is finalised on both success and failure; failures are never
  hidden by an aborted run leaving an empty/partial result directory.

Heavy ML imports (torch, transformers, peft, bitsandbytes, accelerate) are
strictly lazy: they are only ever attempted inside
:func:`check_qlora_provider_available` (via ``importlib``, caught) or inside
the ``run_real_*`` functions below, which are only reachable once that
availability check has already passed. This keeps this module, and the
CPU-only tests that import it, free of any heavy dependency.

When real training deps are unavailable (the normal case for local
development), :func:`run_smoke_training` falls back to
:class:`MockQloraTrainingHarness`: a tiny, deterministic, CPU-only stand-in
that proves the *software contract* (frozen base / trainable adapter /
separate save / exact-base reload / resume / evidence finalisation) using
plain Python floats instead of real tensors. It does not train a real model
and must never be mistaken for one.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ambiguity_manager.model.base_model_candidates import load_base_model_candidate_registry
from ambiguity_manager.model.qlora_smoke_data import (
    MAX_RECORD_COUNT,
    MIN_RECORD_COUNT,
    dataset_paths as smoke_data_paths,
)
from ambiguity_manager.model.training_target_packaging import (
    TrainingTargetPackage,
    assert_never_fabricates_negative_label,
    batch_loss_mask_summary,
    build_training_target_package,
    load_training_target_policy_strict,
)
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.systems.model_identities import (
    SelectedIdentities,
    checkpoint_identity,
    load_selected_identities,
    parse_checkpoint_identity,
)

PROVIDER_ID = "qlora_smoke_v1"
PROVIDER_VERSION = "1.0.0"

CONFIG_REL = "configs/model/qlora_smoke_v1.json"
SELECTED_IDENTITIES_REL = "configs/model/selected_identities_v1.json"
BASE_MODEL_CANDIDATES_REL = "configs/model/base_model_candidates_v1.json"
TRAINING_TARGET_POLICY_REL = "configs/data/training_target_policy_v1.json"

FORBIDDEN_EAGER_IMPORTS = frozenset({"torch", "transformers", "peft", "bitsandbytes", "accelerate"})

FORBIDDEN_EVIDENCE_KEYS = (
    "password",
    "private_key",
    "key_path",
    "passphrase",
    "token",
    "api_key",
    "secret",
    "hf_token",
    "ssh_key",
)

EVIDENCE_FILES = (
    "qlora_smoke_result.json",
    "adapter_identity.json",
    "loss_mask_summary.json",
    "run_manifest.json",
)


class QloraSmokeError(RuntimeError):
    """Raised for QLoRA smoke validation, guard, or execution failures."""


# --------------------------------------------------------------------------
# Provider availability (lazy heavy-import check only)
# --------------------------------------------------------------------------


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


def check_qlora_provider_available() -> ProviderAvailability:
    """CPU-safe check for whether real QLoRA training deps are importable.

    This is the only place any of ``FORBIDDEN_EAGER_IMPORTS`` is even
    attempted, and only via ``importlib.import_module`` inside a try/except,
    so an ``ImportError`` is caught rather than raised. Never call this from
    module import time.
    """
    import importlib

    missing: list[str] = []
    for name in sorted(FORBIDDEN_EAGER_IMPORTS):
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)
    if missing:
        return ProviderAvailability(
            available=False, reason="provider_unavailable", missing_modules=tuple(missing)
        )
    return ProviderAvailability(available=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_root(root: Path | None = None) -> Path:
    return (root or ProjectPaths.from_repo_root().root).resolve()


# --------------------------------------------------------------------------
# Base-model identity guard: require selected_base_model, reject arbitrary IDs
# --------------------------------------------------------------------------


def require_selected_base_model(
    root: Path | None = None,
    *,
    identities: SelectedIdentities | None = None,
) -> str:
    """Return the frozen ``selected_base_model`` checkpoint identity, or raise.

    Phase D has not run while ``selected_base_model`` is null; this must
    never be worked around by inventing a base model, reading an arbitrary
    repository string from elsewhere, or defaulting to any candidate.
    """
    resolved_identities = identities
    if resolved_identities is None:
        path = _repo_root(root) / SELECTED_IDENTITIES_REL
        resolved_identities = load_selected_identities(path)
    if resolved_identities.selected_base_model is None:
        raise QloraSmokeError(
            "selected_base_model is null in configs/model/selected_identities_v1.json; "
            "the QLoRA technical smoke requires Phase D adaptation-base selection to "
            "run first and must never substitute an arbitrary base model."
        )
    return resolved_identities.selected_base_model


def reject_arbitrary_base_model(
    *,
    candidate_repository: str,
    candidate_revision: str | None,
    selected_base_model: str,
    root: Path | None = None,
) -> str:
    """Validate a caller-supplied repository/revision against the frozen base.

    Raises unless the candidate identity is byte-identical to
    ``selected_base_model`` AND that identity corresponds to an allowlisted
    candidate in the base-model registry. There is no fallback path that
    accepts an unmatched or partially-matched identity.
    """
    if not candidate_repository or not candidate_repository.strip():
        raise QloraSmokeError("candidate_repository must be a non-empty string")
    if candidate_revision:
        candidate_identity = checkpoint_identity(candidate_repository, candidate_revision)
    else:
        candidate_identity = candidate_repository
    if candidate_identity != selected_base_model:
        raise QloraSmokeError(
            f"base_model_identity_mismatch: expected {selected_base_model!r}, "
            f"got {candidate_identity!r}"
        )
    repository, revision = parse_checkpoint_identity(selected_base_model)
    registry_path = _repo_root(root) / BASE_MODEL_CANDIDATES_REL
    registry = load_base_model_candidate_registry(registry_path)
    matches = [
        candidate
        for candidate in registry.candidates
        if candidate.repository == repository and candidate.revision == revision
    ]
    if not matches:
        raise QloraSmokeError(
            f"selected_base_model {selected_base_model!r} is not an allowlisted "
            "candidate checkpoint in the base-model registry"
        )
    return candidate_identity


# --------------------------------------------------------------------------
# Smoke config + dataset loading
# --------------------------------------------------------------------------


def load_smoke_config(root: Path | None = None) -> dict[str, Any]:
    """Load and structurally validate ``configs/model/qlora_smoke_v1.json``."""
    path = _repo_root(root) / CONFIG_REL
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if payload.get("development_only") is not True:
        errors.append("development_only must be true")
    if payload.get("valid_for_official_use") is not False:
        errors.append("valid_for_official_use must be false")
    if payload.get("requires_selected_base_model") is not True:
        errors.append("requires_selected_base_model must be true")
    if payload.get("no_merge_into_base") is not True:
        errors.append("no_merge_into_base must be true")
    if payload.get("forbid_manual_or_protected_eval") is not True:
        errors.append("forbid_manual_or_protected_eval must be true")
    if payload.get("selected_adapter") is not None:
        errors.append("selected_adapter must remain null in the smoke config")
    quantization = payload.get("quantization") or {}
    if int(quantization.get("bits", 0)) != 4:
        errors.append("quantization.bits must be 4")
    if payload.get("base_model_policy", {}).get("frozen") is not True:
        errors.append("base_model_policy.frozen must be true")
    if payload.get("base_model_policy", {}).get("allow_arbitrary_repository") is not False:
        errors.append("base_model_policy.allow_arbitrary_repository must be false")
    training = payload.get("training") or {}
    for required in ("max_steps", "checkpoint_interval_steps", "micro_batch_size", "seed"):
        if required not in training:
            errors.append(f"training.{required} is required")
    if training and int(training.get("max_steps", 0)) > 50:
        errors.append("training.max_steps must stay very small for a technical smoke (<=50)")
    if errors:
        raise QloraSmokeError("invalid qlora_smoke_v1 config:\n- " + "\n- ".join(errors))
    return payload


def load_smoke_dataset(root: Path | None = None) -> list[dict[str, Any]]:
    """Load the deterministic smoke record subset built by ``qlora_smoke_data``."""
    paths = smoke_data_paths(_repo_root(root))
    smoke_path = paths["smoke_records"]
    if not smoke_path.is_file():
        raise QloraSmokeError(
            f"missing {smoke_path}; run 'python scripts/build_qlora_smoke_data.py' first"
        )
    rows: list[dict[str, Any]] = []
    with smoke_path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    if not (MIN_RECORD_COUNT <= len(rows) <= MAX_RECORD_COUNT):
        raise QloraSmokeError(
            f"smoke dataset record count {len(rows)} outside allowed "
            f"[{MIN_RECORD_COUNT}, {MAX_RECORD_COUNT}] range"
        )
    return rows


# --------------------------------------------------------------------------
# Adapter identity (never becomes selected_adapter; never official)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AdapterIdentity:
    adapter_id: str
    base_model: str
    created_at_utc: str
    rank: int
    alpha: int
    target_modules: tuple[str, ...]
    technical_smoke_only: bool = True
    selected_adapter: bool = False
    valid_for_official_use: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "base_model": self.base_model,
            "created_at_utc": self.created_at_utc,
            "rank": self.rank,
            "alpha": self.alpha,
            "target_modules": list(self.target_modules),
            "technical_smoke_only": self.technical_smoke_only,
            "selected_adapter": self.selected_adapter,
            "valid_for_official_use": self.valid_for_official_use,
        }

    def assert_smoke_scope(self) -> None:
        if self.technical_smoke_only is not True:
            raise QloraSmokeError("smoke adapter identity must have technical_smoke_only=True")
        if self.selected_adapter is not False:
            raise QloraSmokeError("smoke adapter identity must have selected_adapter=False")
        if self.valid_for_official_use is not False:
            raise QloraSmokeError("smoke adapter identity must have valid_for_official_use=False")


def assert_cannot_register_smoke_adapter_as_selected(
    identity: AdapterIdentity,
    *,
    proposed_selected_adapter: str | None,
) -> None:
    """Simulate an attempted identity-contract update naming this smoke adapter.

    A ``technical_smoke_only`` adapter must never be accepted as
    ``selected_adapter`` in ``configs/model/selected_identities_v1.json``,
    regardless of caller intent. This guard is independent of whether that
    contract module is actually consulted by a given call site.
    """
    identity.assert_smoke_scope()
    if proposed_selected_adapter is not None and proposed_selected_adapter == identity.adapter_id:
        raise QloraSmokeError(
            f"adapter {identity.adapter_id!r} is technical_smoke_only and can never "
            "become selected_adapter"
        )


def assert_training_run_not_official(result_payload: Mapping[str, Any]) -> None:
    """Guard: a QLoRA smoke run result can never claim official validity."""
    if result_payload.get("valid_for_official_use") is not False:
        raise QloraSmokeError("qlora smoke run must have valid_for_official_use=False")
    if result_payload.get("selected_adapter") is not False:
        raise QloraSmokeError("qlora smoke run must have selected_adapter=False")
    if result_payload.get("technical_smoke_only") is not True:
        raise QloraSmokeError("qlora smoke run must have technical_smoke_only=True")


# --------------------------------------------------------------------------
# Deterministic CPU-only mock harness (proves the mechanical contract)
# --------------------------------------------------------------------------


@dataclass
class MockLinearBase:
    """Tiny deterministic stand-in for a frozen base-model parameter tensor."""

    weights: tuple[float, ...]


@dataclass
class MockLoraAdapter:
    """Tiny deterministic stand-in for a trainable LoRA adapter delta."""

    rank: int
    delta: list[float]

    @classmethod
    def initialise(cls, *, rank: int, dim: int) -> "MockLoraAdapter":
        return cls(rank=rank, delta=[0.0] * dim)

    def update(self, *, gradient: Sequence[float], learning_rate: float) -> None:
        if len(gradient) != len(self.delta):
            raise QloraSmokeError("gradient dimensionality mismatch")
        self.delta = [d - learning_rate * g for d, g in zip(self.delta, gradient)]

    def to_dict(self) -> dict[str, Any]:
        return {"rank": self.rank, "delta": list(self.delta)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MockLoraAdapter":
        return cls(rank=int(data["rank"]), delta=[float(x) for x in data["delta"]])


class MockQloraTrainingHarness:
    """Deterministic, CPU-only stand-in proving the frozen-base / trainable-adapter
    save / reload / resume contract without any real tensors, torch, or GPU.

    This is intentionally a toy fixed-size float-vector contract, not a real
    model. It exists purely to exercise and test the mechanical guarantees
    the real training path (see :func:`run_real_qlora_smoke`) must also
    uphold: the base never changes, the adapter does, weights are saved to a
    directory separate from any base snapshot, and reload validates the
    exact base identity.
    """

    def __init__(self, *, base_model: str, dim: int = 4, rank: int = 2, seed: int = 20260722) -> None:
        self.base_model = base_model
        self.dim = dim
        self.rank = rank
        self.seed = seed
        self.base = MockLinearBase(weights=tuple(float((seed + i) % 7) for i in range(dim)))
        self.adapter = MockLoraAdapter.initialise(rank=rank, dim=dim)
        self.step = 0

    def frozen_base_snapshot(self) -> tuple[float, ...]:
        return tuple(self.base.weights)

    def train_one_step(self, batch: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        if not batch:
            raise QloraSmokeError("cannot train on an empty batch")
        base_before = self.frozen_base_snapshot()
        gradient = [(1.0 + (self.step % 3)) * (index + 1) / self.dim for index in range(self.dim)]
        self.adapter.update(gradient=gradient, learning_rate=0.1)
        self.step += 1
        base_after = self.frozen_base_snapshot()
        if base_before != base_after:
            raise QloraSmokeError("base parameters changed during training (must remain frozen)")
        return {
            "step": self.step,
            "batch_size": len(batch),
            "base_unchanged": base_before == base_after,
            "adapter_delta": list(self.adapter.delta),
        }

    def save_adapter(self, adapter_dir: Path, *, identity: AdapterIdentity) -> Path:
        identity.assert_smoke_scope()
        if identity.base_model != self.base_model:
            raise QloraSmokeError("adapter identity base_model must match harness base_model")
        adapter_dir.mkdir(parents=True, exist_ok=True)
        # The base is never written here as weights, only as an identity
        # reference, so the base snapshot and adapter weights are always
        # stored in physically separate artefacts.
        _atomic_write_json(
            adapter_dir / "base_identity_reference.json",
            {"base_model": self.base_model, "note": "identity_reference_only_not_weights"},
        )
        _atomic_write_json(adapter_dir / "adapter_weights.json", self.adapter.to_dict())
        _atomic_write_json(adapter_dir / "adapter_identity.json", identity.to_dict())
        _atomic_write_json(
            adapter_dir / "training_state.json",
            {"step": self.step, "seed": self.seed, "dim": self.dim, "rank": self.rank},
        )
        return adapter_dir

    @classmethod
    def load_adapter(cls, adapter_dir: Path, *, expected_base_model: str) -> "MockQloraTrainingHarness":
        identity_path = adapter_dir / "adapter_identity.json"
        weights_path = adapter_dir / "adapter_weights.json"
        state_path = adapter_dir / "training_state.json"
        for path in (identity_path, weights_path, state_path):
            if not path.is_file():
                raise QloraSmokeError(f"adapter_checkpoint_incomplete:{path.name}")
        identity_raw = json.loads(identity_path.read_text(encoding="utf-8"))
        if identity_raw.get("base_model") != expected_base_model:
            raise QloraSmokeError(
                f"adapter_base_mismatch: expected {expected_base_model!r}, "
                f"got {identity_raw.get('base_model')!r}"
            )
        state = json.loads(state_path.read_text(encoding="utf-8"))
        harness = cls(
            base_model=expected_base_model,
            dim=int(state["dim"]),
            rank=int(state["rank"]),
            seed=int(state["seed"]),
        )
        harness.adapter = MockLoraAdapter.from_dict(json.loads(weights_path.read_text(encoding="utf-8")))
        harness.step = int(state["step"])
        return harness


def verify_resume_contract(
    adapter_dir: Path,
    *,
    expected_base_model: str,
    expected_step: int,
) -> MockQloraTrainingHarness:
    """Reload a checkpoint and assert its resume state matches expectations."""
    resumed = MockQloraTrainingHarness.load_adapter(adapter_dir, expected_base_model=expected_base_model)
    if resumed.step != expected_step:
        raise QloraSmokeError(
            f"resume_step_mismatch: expected {expected_step}, got {resumed.step}"
        )
    return resumed


# --------------------------------------------------------------------------
# Secrets hygiene
# --------------------------------------------------------------------------


def sanitize_evidence_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Raise if ``payload`` contains a forbidden secret-shaped key.

    Mirrors ``ambiguity_manager.model.cluster.job_operator.sanitize_state``:
    evidence must never persist credentials, tokens, or key material.
    """
    text = json.dumps(dict(payload), default=str).lower()
    for key in FORBIDDEN_EVIDENCE_KEYS:
        if f'"{key}"' in text or f"'{key}'" in text:
            raise QloraSmokeError(f"forbidden_evidence_key:{key}")
    return dict(payload)


# --------------------------------------------------------------------------
# Evidence finalisation (both success and failure)
# --------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(dict(payload), indent=2, sort_keys=True) + "\n"
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
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _refuse_nonempty_result_dir(result_dir: Path) -> None:
    result_dir.mkdir(parents=True, exist_ok=True)
    existing = [name for name in EVIDENCE_FILES if (result_dir / name).exists()]
    if existing:
        raise QloraSmokeError(f"result_dir_not_empty:{','.join(existing)}")


def finalize_smoke_run_manifest(
    result_dir: Path,
    *,
    run_id: str,
    success: bool,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write ``run_manifest.json`` covering every evidence file, pass or fail.

    Called exactly once per run, after evidence files (including any
    partial adapter directory) have already been written, regardless of
    whether the run succeeded.
    """
    files: list[dict[str, Any]] = []
    for path in sorted(result_dir.rglob("*")):
        if not path.is_file() or path.name == "run_manifest.json":
            continue
        files.append(
            {
                "relative_path": path.relative_to(result_dir).as_posix(),
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    manifest = sanitize_evidence_payload(
        {
            "schema_version": "1.0.0",
            "provider_id": PROVIDER_ID,
            "provider_version": PROVIDER_VERSION,
            "run_id": run_id,
            "hostname": socket.gethostname(),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
            "python_version": platform.python_version(),
            "timestamp_utc": _utc_now(),
            "success": success,
            "development_only": True,
            "valid_for_official_use": False,
            "technical_smoke_only": True,
            "selected_adapter": False,
            "files": files,
            **(dict(extra) if extra else {}),
        }
    )
    _atomic_write_json(result_dir / "run_manifest.json", manifest)
    return manifest


# --------------------------------------------------------------------------
# Local (mock) orchestrator
# --------------------------------------------------------------------------


def _packages_for_dataset(
    dataset_rows: Sequence[Mapping[str, Any]],
    *,
    policy: Mapping[str, Any],
) -> list[TrainingTargetPackage]:
    packages: list[TrainingTargetPackage] = []
    for row in dataset_rows:
        package = build_training_target_package(dict(row["record"]), dict(row["eligibility"]), policy=dict(policy))
        assert_never_fabricates_negative_label(package)
        packages.append(package)
    return packages


def run_smoke_training(
    *,
    result_dir: Path,
    run_id: str,
    root: Path | None = None,
    force_mock: bool = True,
    training_step_fn: Callable[[Sequence[Mapping[str, Any]]], dict[str, Any]] | None = None,
    dataset_rows: Sequence[Mapping[str, Any]] | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the QLoRA technical smoke and always finalise evidence.

    Preconditions (missing ``selected_base_model``, an already non-empty
    result directory, or an invalid config) raise immediately, before any
    training attempt, because no run has actually started yet. Once the
    training loop itself begins, any exception is caught, evidence is still
    finalised with ``success=False`` and the failure reason recorded, and the
    result dict is returned rather than the exception propagating; this
    guarantees a failed run still leaves inspectable evidence.

    ``force_mock`` defaults to ``True`` so importing/using this function
    locally never attempts a real GPU/4-bit path; pass ``force_mock=False``
    only from the cluster entry script after confirming
    :func:`check_qlora_provider_available`.
    """
    repo = _repo_root(root)
    selected_base_model = require_selected_base_model(repo)
    resolved_config = dict(config) if config is not None else load_smoke_config(repo)
    _refuse_nonempty_result_dir(result_dir)

    resolved_rows = list(dataset_rows) if dataset_rows is not None else load_smoke_dataset(repo)
    policy = load_training_target_policy_strict(repo / TRAINING_TARGET_POLICY_REL)
    packages = _packages_for_dataset(resolved_rows, policy=policy)
    loss_summary = batch_loss_mask_summary(packages)

    availability = check_qlora_provider_available()
    adapter_id = f"qlora-smoke-adapter-{run_id}"
    adapter_dir = result_dir / "adapter"
    started = _utc_now()
    failure: str | None = None
    training_events: list[dict[str, Any]] = []
    resumed_step: int | None = None
    use_real_pipeline = availability.available and not force_mock
    mode = "real_cluster_training" if use_real_pipeline else "mock_contract_proof"

    try:
        training_cfg = resolved_config["training"]
        adapter_cfg = resolved_config["adapter"]
        if use_real_pipeline:
            training_events = run_real_qlora_smoke(
                selected_base_model=selected_base_model,
                dataset_rows=resolved_rows,
                config=resolved_config,
                adapter_dir=adapter_dir,
                adapter_id=adapter_id,
            )
        else:
            harness = MockQloraTrainingHarness(base_model=selected_base_model, seed=int(training_cfg["seed"]))
            batch_size = max(1, int(training_cfg["micro_batch_size"]))
            batch = [package.to_dict() for package in packages[:batch_size]]
            step_fn = training_step_fn or harness.train_one_step
            checkpoint_interval = max(1, int(training_cfg["checkpoint_interval_steps"]))
            for step_index in range(int(training_cfg["max_steps"])):
                event = step_fn(batch)
                training_events.append(event)
                if (step_index + 1) % checkpoint_interval == 0:
                    identity = AdapterIdentity(
                        adapter_id=adapter_id,
                        base_model=selected_base_model,
                        created_at_utc=_utc_now(),
                        rank=int(adapter_cfg["rank"]),
                        alpha=int(adapter_cfg["alpha"]),
                        target_modules=tuple(adapter_cfg["target_modules"]),
                    )
                    harness.save_adapter(adapter_dir, identity=identity)
            if training_cfg.get("resume_test", True) and (adapter_dir / "adapter_identity.json").is_file():
                resumed = verify_resume_contract(
                    adapter_dir,
                    expected_base_model=selected_base_model,
                    expected_step=harness.step,
                )
                resumed_step = resumed.step
        success = True
    except Exception as exc:  # noqa: BLE001 - evidence must be finalised regardless
        success = False
        failure = f"{type(exc).__name__}: {exc}"

    ended = _utc_now()
    result_dir.mkdir(parents=True, exist_ok=True)

    result_payload = sanitize_evidence_payload(
        {
            "schema_version": "1.0.0",
            "provider_id": PROVIDER_ID,
            "provider_version": PROVIDER_VERSION,
            "run_id": run_id,
            "mode": mode,
            "success": success,
            "failure_reason": failure,
            "selected_base_model": selected_base_model,
            "adapter_id": adapter_id,
            "technical_smoke_only": True,
            "selected_adapter": False,
            "valid_for_official_use": False,
            "record_count": len(resolved_rows),
            "training_events": training_events,
            "resumed_step": resumed_step,
            "start_timestamp_utc": started,
            "end_timestamp_utc": ended,
            "provider_availability": availability.to_dict(),
        }
    )
    assert_training_run_not_official(result_payload)
    _atomic_write_json(result_dir / "qlora_smoke_result.json", result_payload)
    _atomic_write_json(result_dir / "loss_mask_summary.json", loss_summary)
    adapter_identity_path = adapter_dir / "adapter_identity.json"
    if adapter_identity_path.is_file():
        (result_dir / "adapter_identity.json").write_text(
            adapter_identity_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

    manifest = finalize_smoke_run_manifest(result_dir, run_id=run_id, success=success)
    return {"result": result_payload, "manifest": manifest, "loss_mask_summary": loss_summary}


# --------------------------------------------------------------------------
# Real cluster pipeline (lazy heavy imports; unreachable locally)
# --------------------------------------------------------------------------


def run_real_qlora_smoke(
    *,
    selected_base_model: str,
    dataset_rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    adapter_dir: Path,
    adapter_id: str,
) -> list[dict[str, Any]]:
    """Real 4-bit QLoRA smoke path: forward/backward, one adapter update, save.

    Lazy-imports torch/transformers/peft/bitsandbytes. Only reachable when
    :func:`check_qlora_provider_available` has already reported
    ``available=True``, i.e. inside the pinned training container on the
    cluster (see ``configs/environments/t12_cluster_training.json``). This
    path is not exercised by local CPU-only tests: loading real model
    weights locally is explicitly out of scope for this phase, and the live
    cluster smoke is blocked until the training container exists (see
    ``docs/reports/qlora_technical_smoke.md``).
    """
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    repository, revision = parse_checkpoint_identity(selected_base_model)
    quant = config["quantization"]
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type=quant.get("quant_type", "nf4"),
        bnb_4bit_compute_dtype=getattr(torch, quant.get("compute_dtype", "bfloat16")),
        bnb_4bit_use_double_quant=bool(quant.get("double_quant", True)),
    )
    tokenizer = AutoTokenizer.from_pretrained(repository, revision=revision, local_files_only=True)
    base_model = AutoModelForCausalLM.from_pretrained(
        repository,
        revision=revision,
        local_files_only=True,
        quantization_config=bnb_config,
        device_map="auto",
    )
    for param in base_model.parameters():
        param.requires_grad_(False)

    adapter_cfg = config["adapter"]
    lora_config = LoraConfig(
        r=int(adapter_cfg["rank"]),
        lora_alpha=int(adapter_cfg["alpha"]),
        target_modules=list(adapter_cfg["target_modules"]),
        lora_dropout=float(adapter_cfg.get("dropout", 0.0)),
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(base_model, lora_config)
    optimizer = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad),
        lr=float(config["training"].get("learning_rate", 1e-4)),
    )

    training_cfg = config["training"]
    max_seq_len = int(config["sequence"]["max_seq_len"])
    checkpoint_interval = max(1, int(training_cfg["checkpoint_interval_steps"]))
    events: list[dict[str, Any]] = []
    for step_index in range(int(training_cfg["max_steps"])):
        row = dataset_rows[step_index % len(dataset_rows)]
        command = str(row["record"].get("command", ""))
        encoded = tokenizer(command, truncation=True, max_length=max_seq_len, return_tensors="pt")
        outputs = model(**encoded, labels=encoded["input_ids"])
        loss = outputs.loss
        loss.backward()
        optimizer.step()
        optimizer.zero_grad()
        events.append({"step": step_index + 1, "loss": float(loss.detach().cpu().item())})
        if (step_index + 1) % checkpoint_interval == 0:
            model.save_pretrained(str(adapter_dir))
    model.save_pretrained(str(adapter_dir))
    _atomic_write_json(
        adapter_dir / "adapter_identity.json",
        AdapterIdentity(
            adapter_id=adapter_id,
            base_model=selected_base_model,
            created_at_utc=_utc_now(),
            rank=int(adapter_cfg["rank"]),
            alpha=int(adapter_cfg["alpha"]),
            target_modules=tuple(adapter_cfg["target_modules"]),
        ).to_dict(),
    )
    return events


def run_real_inference_and_diff_smoke(
    *,
    selected_base_model: str,
    adapter_dir: Path,
    prompt: str,
    max_new_tokens: int = 32,
) -> dict[str, Any]:
    """Real on-cluster inference smoke: base-only vs base+adapter generation diff.

    Loads the frozen base once, generates with the base alone, loads the
    saved smoke adapter on top of that same base, generates again, and
    reports whether the two outputs differ (proving the adapter has a
    measurable effect) plus a best-effort structured-output JSON parse
    check. Lazy-imports torch/transformers/peft; only reachable on the
    training container with real weights, never in local CPU-only tests.
    """
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    repository, revision = parse_checkpoint_identity(selected_base_model)
    tokenizer = AutoTokenizer.from_pretrained(repository, revision=revision, local_files_only=True)
    base_model = AutoModelForCausalLM.from_pretrained(
        repository, revision=revision, local_files_only=True, device_map="auto"
    )
    encoded = tokenizer(prompt, return_tensors="pt")
    with torch.no_grad():
        base_ids = base_model.generate(**encoded, max_new_tokens=max_new_tokens)
    base_text = tokenizer.decode(base_ids[0], skip_special_tokens=True)

    adapted_model = PeftModel.from_pretrained(base_model, str(adapter_dir))
    with torch.no_grad():
        adapted_ids = adapted_model.generate(**encoded, max_new_tokens=max_new_tokens)
    adapted_text = tokenizer.decode(adapted_ids[0], skip_special_tokens=True)

    structured_output_parses = False
    try:
        json.loads(adapted_text)
        structured_output_parses = True
    except ValueError:
        structured_output_parses = False

    return {
        "base_text": base_text,
        "adapted_text": adapted_text,
        "base_and_adapter_differ": base_text != adapted_text,
        "structured_output_parses": structured_output_parses,
    }
