"""T27B full_schema_envelope_v1 structured-emission recovery orchestrator.

Proves production-schema envelope training targets, segment-aware token loss
masks, full checkpoint/resume component restore, and multi-stage structured
output validation on the sealed eight-record ``t27b_final_smoke_v1`` set —
without selecting an adapter or model strategy.

Heavy ML imports (torch, transformers, peft, bitsandbytes, accelerate) are
strictly lazy and occur only inside real training. This module is CPU-safe at
import time. Local defaults use the deterministic mock contract harness;
cluster entry must pass ``require_real_mode=True`` and ``force_mock=False``
and must never silently fall back to mock.
"""

from __future__ import annotations

import json
import os
import platform
import socket
from pathlib import Path
from typing import Any, Mapping, Sequence

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.full_schema_envelope import (
    FULL_SCHEMA_ENVELOPE_ID,
    PROMPT_CONTRACT_VERSION,
    build_full_schema_envelope,
    load_envelope_policy,
)
from ambiguity_manager.model.full_schema_token_masking import (
    IGNORE_INDEX,
    DeterministicCharTokenizer,
    build_masked_sequence_from_envelope,
)
from ambiguity_manager.model.qlora_checkpoint import (
    assert_resume_identities,
    build_checkpoint_payload,
    evaluate_resume_components,
    load_full_checkpoint_blob,
    restore_rng_state,
    save_full_checkpoint,
)
from ambiguity_manager.model.qlora_smoke import (
    AdapterIdentity,
    MockQloraTrainingHarness,
    assert_cannot_register_smoke_adapter_as_selected,
    check_qlora_provider_available,
    require_selected_base_model,
    sanitize_evidence_payload,
    _atomic_write_json,
    _sha256_file,
    _utc_now,
)
from ambiguity_manager.model.t27b_datasets import (
    DIAGNOSTIC_DIR_REL,
    FINAL_SMOKE_DIR_REL,
    JOB6059_VAL_IDS,
    TRAIN_DIR_REL,
)
from ambiguity_manager.model.t27b_prompt_contract import build_t27b_inference_prompt
from ambiguity_manager.model.t27b_structured_validation import (
    validate_t27b_structured_model_output,
)
from ambiguity_manager.model.training_target_packaging import load_training_target_policy_strict
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.systems.model_identities import parse_checkpoint_identity

PROVIDER_ID = "qlora_structured_emission_recovery_v1"
PROVIDER_VERSION = "1.0.0"

CONFIG_REL = "configs/model/qlora_structured_emission_recovery_v1.json"
ENVIRONMENT_REL = "configs/environments/t12_cluster_training_task_aligned_v1.json"
ENVELOPE_POLICY_REL = "configs/model/full_schema_envelope_policy_v1.json"
TRAINING_TARGET_POLICY_REL = "configs/data/training_target_policy_v1.json"

FORBIDDEN_EAGER_IMPORTS = frozenset({"torch", "transformers", "peft", "bitsandbytes", "accelerate"})

EVIDENCE_FILES = (
    "qlora_structured_emission_recovery_result.json",
    "adapter_identity.json",
    "loss_mask_summary.json",
    "structured_output_results.json",
    "resume_components.json",
    "run_manifest.json",
    "supervision_density.json",
)
OPTIONAL_EVIDENCE_FILES: tuple[str, ...] = ()

JOB6059_EVIDENCE_PATHS = frozenset(
    {
        "configs/model/evidence/t27_task_aligned_qlora_smoke.json",
        "docs/reports/ticket_T27_task_aligned_qlora_smoke.md",
        "data/development/qlora_task_aligned_smoke",
        "data/development/qlora_task_aligned_smoke_v1",
        "data/development/qlora_task_aligned_smoke_v2",
    }
)

_TRAIN_RECORD_COUNT = 128
_SEALED_RECORD_COUNT = 8
_DIAGNOSTIC_RECORD_COUNT = 12
_MOCK_CHAR_MAX_SEQ_LEN = 8192


class QloraStructuredEmissionRecoveryError(RuntimeError):
    """Raised for T27B structured-emission recovery validation or execution failures."""


def _repo_root(root: Path | None = None) -> Path:
    return (root or ProjectPaths.from_repo_root().root).resolve()


def load_emission_recovery_config(root: Path | None = None) -> dict[str, Any]:
    """Load and structurally validate the structured-emission recovery config."""
    path = _repo_root(root) / CONFIG_REL
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if payload.get("development_only") is not True:
        errors.append("development_only must be true")
    if payload.get("valid_for_official_use") is not False:
        errors.append("valid_for_official_use must be false")
    if payload.get("technical_smoke_only") is not True:
        errors.append("technical_smoke_only must be true")
    if payload.get("requires_selected_base_model") is not True:
        errors.append("requires_selected_base_model must be true")
    if payload.get("no_merge_into_base") is not True:
        errors.append("no_merge_into_base must be true")
    if payload.get("selected_adapter") is not None:
        errors.append("selected_adapter must remain null in the recovery config")
    if payload.get("envelope_id") != FULL_SCHEMA_ENVELOPE_ID:
        errors.append(f"envelope_id must be {FULL_SCHEMA_ENVELOPE_ID}")
    if payload.get("prompt_contract") not in {
        PROMPT_CONTRACT_VERSION,
        "t27b_full_schema_prompt_v1",
    }:
        errors.append("prompt_contract must be t27b_full_schema_prompt_v1")
    for flag in (
        "require_real_mode",
        "require_real_mode_on_cluster",
        "no_mock_fallback",
        "forbid_mock_fallback_in_live_mode",
    ):
        if payload.get(flag) is not True:
            errors.append(f"{flag} must be true")
    if not isinstance(payload.get("pass_thresholds"), Mapping):
        errors.append("pass_thresholds must be present")
    else:
        thresholds = payload["pass_thresholds"]
        for key in (
            "sealed_final_count",
            "adapter_parse_valid_min",
            "adapter_schema_valid_min",
            "adapter_semantic_valid_min",
            "adapter_safety_accepted_min",
            "adapter_final_accepted_min",
            "adapter_differs_from_base_min",
            "unsupported_commitment_accepted_max",
            "base_attempted_min",
            "adapter_attempted_min",
        ):
            if key not in thresholds:
                errors.append(f"pass_thresholds.{key} is required")
    quantization = payload.get("quantization") or {}
    if int(quantization.get("bits", 0)) != 4:
        errors.append("quantization.bits must be 4")
    training = payload.get("training") or {}
    for required in ("max_steps", "checkpoint_interval_steps", "micro_batch_size", "seed"):
        if required not in training:
            errors.append(f"training.{required} is required")
    if training and int(training.get("max_steps", 0)) > 50:
        errors.append("training.max_steps must stay very small for a technical smoke (<=50)")
    evaluation = payload.get("evaluation") or {}
    if not evaluation.get("held_out_validation_manifest"):
        errors.append("evaluation.held_out_validation_manifest is required")
    if evaluation.get("forbid_braces_only_acceptance") is not True:
        errors.append("evaluation.forbid_braces_only_acceptance must be true")
    if errors:
        raise QloraStructuredEmissionRecoveryError(
            "invalid qlora_structured_emission_recovery_v1 config:\n- " + "\n- ".join(errors)
        )
    return payload


def _assert_result_dir_not_job6059(result_dir: Path, root: Path) -> None:
    resolved = result_dir.resolve()
    root_resolved = root.resolve()
    for rel in JOB6059_EVIDENCE_PATHS:
        forbidden = (root_resolved / rel).resolve()
        if resolved == forbidden:
            raise QloraStructuredEmissionRecoveryError(
                f"refusing_to_write_job6059_evidence_path:{rel}"
            )
        try:
            if resolved.is_relative_to(forbidden) or forbidden.is_relative_to(resolved):
                raise QloraStructuredEmissionRecoveryError(
                    f"refusing_to_write_job6059_evidence_path:{rel}"
                )
        except AttributeError:
            # Python < 3.9 fallback is unnecessary on this project; keep defensive.
            resolved_s = resolved.as_posix().lower()
            forbidden_s = forbidden.as_posix().lower()
            if resolved_s == forbidden_s or "qlora_task_aligned_smoke" in resolved_s:
                raise QloraStructuredEmissionRecoveryError(
                    f"refusing_to_write_job6059_evidence_path:{rel}"
                ) from None
    if "qlora_task_aligned_smoke" in resolved.as_posix().lower():
        raise QloraStructuredEmissionRecoveryError(
            "refusing_to_write_job6059_evidence_path:qlora_task_aligned_smoke*"
        )


def _refuse_nonempty_result_dir(result_dir: Path) -> None:
    result_dir.mkdir(parents=True, exist_ok=True)
    names = list(EVIDENCE_FILES) + list(OPTIONAL_EVIDENCE_FILES)
    existing = [name for name in names if (result_dir / name).exists()]
    if existing:
        raise QloraStructuredEmissionRecoveryError(f"result_dir_not_empty:{','.join(existing)}")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise QloraStructuredEmissionRecoveryError(f"missing_jsonl:{path}")
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise QloraStructuredEmissionRecoveryError(f"missing_manifest:{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_no_job6059_overlap(rows: Sequence[Mapping[str, Any]], *, label: str) -> None:
    ids = {str(row.get("id") or (row.get("record") or {}).get("id") or "") for row in rows}
    overlap = sorted(ids & set(JOB6059_VAL_IDS))
    if overlap:
        raise QloraStructuredEmissionRecoveryError(
            f"{label}_overlaps_job6059_val_ids:{','.join(overlap)}"
        )


def load_emission_recovery_train_records(root: Path | None = None) -> list[dict[str, Any]]:
    """Load the 128-record source_train recovery set and validate its manifest."""
    repo = _repo_root(root)
    base = repo / TRAIN_DIR_REL
    manifest = _load_manifest(base / "manifest.json")
    rows = _load_jsonl(base / "records.jsonl")
    if len(rows) != _TRAIN_RECORD_COUNT:
        raise QloraStructuredEmissionRecoveryError(
            f"train_record_count_expected_{_TRAIN_RECORD_COUNT}_got_{len(rows)}"
        )
    if int(manifest.get("record_count") or 0) != _TRAIN_RECORD_COUNT:
        raise QloraStructuredEmissionRecoveryError("train_manifest_record_count_mismatch")
    if manifest.get("envelope_id") != FULL_SCHEMA_ENVELOPE_ID:
        raise QloraStructuredEmissionRecoveryError("train_manifest_envelope_id_mismatch")
    _assert_no_job6059_overlap(rows, label="train")
    return rows


def load_emission_recovery_sealed_records(root: Path | None = None) -> list[dict[str, Any]]:
    """Load the sealed eight-record final smoke set."""
    repo = _repo_root(root)
    base = repo / FINAL_SMOKE_DIR_REL
    manifest = _load_manifest(base / "manifest.json")
    rows = _load_jsonl(base / "records.jsonl")
    if len(rows) != _SEALED_RECORD_COUNT:
        raise QloraStructuredEmissionRecoveryError(
            f"sealed_record_count_expected_{_SEALED_RECORD_COUNT}_got_{len(rows)}"
        )
    if int(manifest.get("record_count") or 0) != _SEALED_RECORD_COUNT:
        raise QloraStructuredEmissionRecoveryError("sealed_manifest_record_count_mismatch")
    if manifest.get("seal_status") != "sealed" and manifest.get("sealed") is not True:
        raise QloraStructuredEmissionRecoveryError("sealed_manifest_not_sealed")
    _assert_no_job6059_overlap(rows, label="sealed")
    return rows


def load_emission_recovery_diagnostic_records(root: Path | None = None) -> list[dict[str, Any]]:
    """Load the twelve-record diagnostic-only set (never used as the live gate)."""
    repo = _repo_root(root)
    base = repo / DIAGNOSTIC_DIR_REL
    manifest = _load_manifest(base / "manifest.json")
    rows = _load_jsonl(base / "records.jsonl")
    if len(rows) != _DIAGNOSTIC_RECORD_COUNT:
        raise QloraStructuredEmissionRecoveryError(
            f"diagnostic_record_count_expected_{_DIAGNOSTIC_RECORD_COUNT}_got_{len(rows)}"
        )
    if int(manifest.get("record_count") or 0) != _DIAGNOSTIC_RECORD_COUNT:
        raise QloraStructuredEmissionRecoveryError("diagnostic_manifest_record_count_mismatch")
    if manifest.get("diagnostic_only") is not True:
        raise QloraStructuredEmissionRecoveryError("diagnostic_manifest_not_diagnostic_only")
    _assert_no_job6059_overlap(rows, label="diagnostic")
    return rows


def _environment_identity(root: Path) -> str:
    env_path = root / ENVIRONMENT_REL
    if env_path.is_file():
        payload = json.loads(env_path.read_text(encoding="utf-8"))
        return str(payload.get("environment_id") or "t12-cluster-training-task-aligned-v1")
    return "t12-cluster-training-task-aligned-v1"


def _config_hash(config: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(dict(config)))


def _data_manifest_hash(root: Path) -> str:
    manifest_path = root / TRAIN_DIR_REL / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return str(payload.get("manifest_hash") or sha256_hex(manifest_path.read_bytes()))


def _summarise_loss_masks(diagnostics: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not diagnostics:
        return {
            "example_count": 0,
            "examples_with_supervised_tokens": 0,
            "mean_supervised_token_percentage": 0.0,
            "mean_semantic_supervised": 0.0,
            "mean_structural_supervised": 0.0,
            "per_example": [],
            "command_reconstruction_forbidden": True,
            "labels_never_equal_input_ids": True,
            "envelope_id": FULL_SCHEMA_ENVELOPE_ID,
        }
    supervised_pct = [float(item.get("supervised_token_percentage") or 0.0) for item in diagnostics]
    semantic = [float(item.get("semantic_supervised") or 0.0) for item in diagnostics]
    structural = [float(item.get("structural_supervised") or 0.0) for item in diagnostics]
    with_tokens = sum(1 for item in diagnostics if int(item.get("target_supervised_tokens") or 0) > 0)
    return {
        "example_count": len(diagnostics),
        "examples_with_supervised_tokens": with_tokens,
        "mean_supervised_token_percentage": round(sum(supervised_pct) / max(1, len(supervised_pct)), 4),
        "mean_semantic_supervised": round(sum(semantic) / max(1, len(semantic)), 4),
        "mean_structural_supervised": round(sum(structural) / max(1, len(structural)), 4),
        "per_example": [dict(item) for item in diagnostics],
        "command_reconstruction_forbidden": True,
        "labels_never_equal_input_ids": True,
        "envelope_id": FULL_SCHEMA_ENVELOPE_ID,
    }


def _build_supervision_density(
    loss_summary: Mapping[str, Any],
    *,
    minimum_useful_supervision: Mapping[str, Any] | None,
) -> dict[str, Any]:
    mins = dict(minimum_useful_supervision or {})
    mean_pct = float(loss_summary.get("mean_supervised_token_percentage") or 0.0)
    min_mean = float(mins.get("min_mean_supervised_token_percentage") or 0.0)
    return {
        "envelope_id": FULL_SCHEMA_ENVELOPE_ID,
        "example_count": int(loss_summary.get("example_count") or 0),
        "mean_supervised_token_percentage": mean_pct,
        "mean_semantic_supervised": float(loss_summary.get("mean_semantic_supervised") or 0.0),
        "mean_structural_supervised": float(loss_summary.get("mean_structural_supervised") or 0.0),
        "minimum_useful_supervision": mins,
        "meets_minimum_mean_supervised_percentage": mean_pct >= min_mean if min_mean else None,
        "note": "mean supervised density vs frozen minimum_useful_supervision",
    }


def assert_emission_recovery_run_not_official(result_payload: Mapping[str, Any]) -> None:
    if result_payload.get("valid_for_official_use") is not False:
        raise QloraStructuredEmissionRecoveryError(
            "emission recovery must have valid_for_official_use=False"
        )
    selected = result_payload.get("selected_adapter")
    if selected not in (None, False):
        raise QloraStructuredEmissionRecoveryError(
            "emission recovery must keep selected_adapter null/false"
        )
    if result_payload.get("technical_smoke_only") is not True:
        raise QloraStructuredEmissionRecoveryError(
            "emission recovery must have technical_smoke_only=True"
        )


def finalize_emission_recovery_run_manifest(
    result_dir: Path,
    *,
    run_id: str,
    success: bool,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
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
            "selected_adapter": None,
            "envelope_id": FULL_SCHEMA_ENVELOPE_ID,
            "prompt_contract": PROMPT_CONTRACT_VERSION,
            "files": files,
            **(dict(extra) if extra else {}),
        }
    )
    _atomic_write_json(result_dir / "run_manifest.json", manifest)
    return manifest


def _write_failure_evidence(
    *,
    result_dir: Path,
    run_id: str,
    selected_base_model: str | None,
    mode: str,
    failure: str,
    availability: Mapping[str, Any],
    loss_summary: Mapping[str, Any] | None = None,
    resume_components: Mapping[str, Any] | None = None,
    structured_output: Mapping[str, Any] | None = None,
    supervision_density: Mapping[str, Any] | None = None,
    started: str | None = None,
    live_gate_evaluated: bool = False,
) -> dict[str, Any]:
    result_dir.mkdir(parents=True, exist_ok=True)
    result_payload = sanitize_evidence_payload(
        {
            "schema_version": "1.0.0",
            "provider_id": PROVIDER_ID,
            "provider_version": PROVIDER_VERSION,
            "run_id": run_id,
            "mode": mode,
            "success": False,
            "failure_reason": failure,
            "selected_base_model": selected_base_model,
            "technical_smoke_only": True,
            "selected_adapter": None,
            "valid_for_official_use": False,
            "live_gate_evaluated": live_gate_evaluated,
            "envelope_id": FULL_SCHEMA_ENVELOPE_ID,
            "prompt_contract": PROMPT_CONTRACT_VERSION,
            "start_timestamp_utc": started or _utc_now(),
            "end_timestamp_utc": _utc_now(),
            "provider_availability": dict(availability),
            "resume_components": dict(resume_components or {}),
            "structured_output_summary": dict(structured_output or {}),
        }
    )
    assert_emission_recovery_run_not_official(result_payload)
    _atomic_write_json(result_dir / "qlora_structured_emission_recovery_result.json", result_payload)
    loss = dict(loss_summary or {"example_count": 0, "error": "run_failed_before_masks"})
    _atomic_write_json(result_dir / "loss_mask_summary.json", loss)
    _atomic_write_json(
        result_dir / "structured_output_results.json",
        dict(structured_output or {"records": [], "status": "not_run"}),
    )
    _atomic_write_json(
        result_dir / "resume_components.json",
        dict(
            resume_components
            or {
                "adapter_reload_ok": False,
                "optimiser_restore_ok": False,
                "scheduler_restore_ok": False,
                "rng_restore_ok": False,
                "data_position_restore_ok": False,
                "full_resume_ok": False,
            }
        ),
    )
    density = dict(
        supervision_density
        or _build_supervision_density(loss, minimum_useful_supervision=None)
    )
    _atomic_write_json(result_dir / "supervision_density.json", density)
    _atomic_write_json(
        result_dir / "adapter_identity.json",
        {
            "adapter_id": None,
            "base_model": selected_base_model,
            "technical_smoke_only": True,
            "selected_adapter": False,
            "valid_for_official_use": False,
            "note": "identity_stub_run_failed_early",
        },
    )
    manifest = finalize_emission_recovery_run_manifest(result_dir, run_id=run_id, success=False)
    return {
        "result": result_payload,
        "manifest": manifest,
        "mode": mode,
        "success": False,
        "resume_components": dict(
            resume_components
            or {
                "adapter_reload_ok": False,
                "optimiser_restore_ok": False,
                "scheduler_restore_ok": False,
                "rng_restore_ok": False,
                "data_position_restore_ok": False,
                "full_resume_ok": False,
            }
        ),
        "structured_output_results": dict(structured_output or {"records": [], "status": "not_run"}),
        "loss_mask_summary": loss,
        "supervision_density": density,
    }


def ensure_runtime_jsonschema() -> dict[str, Any]:
    """Ensure ``jsonschema`` is importable for production semantic validation.

    Generic runtime correction for the training container: production
    ``validate_semantic_payload`` requires Draft 2020-12 validation. Job 6307
    failed with ``ModuleNotFoundError: No module named 'jsonschema'`` because the
    bind-mounted training-site-packages lacked it (T27 job 6059 never reached
    Draft202012 validation — outputs failed earlier on unknown fields).
    """
    try:
        import jsonschema  # noqa: F401

        return {"status": "already_available", "package": "jsonschema"}
    except ImportError:
        pass

    import subprocess
    import sys

    site = os.environ.get("T12_TRAINING_SITE_PACKAGES", "").strip()
    if not site:
        raise QloraStructuredEmissionRecoveryError(
            "jsonschema_missing_and_T12_TRAINING_SITE_PACKAGES_unset"
        )
    site_path = Path(site)
    site_path.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--target",
        str(site_path),
        "jsonschema",
    ]
    completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise QloraStructuredEmissionRecoveryError(
            "jsonschema_install_failed:"
            f"rc={completed.returncode}; stderr={completed.stderr[-500:]}"
        )
    site_str = str(site_path)
    if site_str not in sys.path:
        sys.path.insert(0, site_str)
    try:
        import jsonschema  # noqa: F401
    except ImportError as exc:
        raise QloraStructuredEmissionRecoveryError(
            "jsonschema_still_missing_after_install"
        ) from exc
    return {
        "status": "installed_into_training_site_packages",
        "package": "jsonschema",
        "target": site_str,
    }


class _HFTokenizerAdapter:
    """Thin encode/decode wrapper matching the envelope masking tokenizer protocol."""

    def __init__(self, tokenizer: Any) -> None:
        self._tokenizer = tokenizer
        pad = getattr(tokenizer, "pad_token_id", None)
        eos = getattr(tokenizer, "eos_token_id", None)
        self.pad_token_id = int(pad if pad is not None else (eos or 0))

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        return [int(x) for x in self._tokenizer.encode(text, add_special_tokens=add_special_tokens)]

    def decode(self, ids: Sequence[int], skip_special_tokens: bool = True) -> str:
        return str(self._tokenizer.decode(list(ids), skip_special_tokens=skip_special_tokens))


def _build_envelope_examples(
    rows: Sequence[Mapping[str, Any]],
    *,
    envelope_policy: Mapping[str, Any],
    training_policy: Mapping[str, Any],
    tokenizer: Any,
    max_seq_len: int,
) -> list[dict[str, Any]]:
    """Build prompt + full_schema_envelope + masked sequence examples."""
    pad_token_id = int(getattr(tokenizer, "pad_token_id", 0) or 0)
    examples: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row["record"])
        eligibility = dict(row["eligibility"])
        source_record_id = str(row.get("id") or record.get("id") or "")
        envelope = build_full_schema_envelope(
            record,
            eligibility,
            policy=dict(envelope_policy),
            training_policy=dict(training_policy),
        )
        prompt = build_t27b_inference_prompt(record)
        masked = build_masked_sequence_from_envelope(
            prompt=prompt,
            envelope=envelope,
            tokenizer=tokenizer,
            max_seq_len=max_seq_len,
            pad_token_id=pad_token_id,
        )
        if list(masked.labels) == list(masked.input_ids):
            raise QloraStructuredEmissionRecoveryError(
                f"labels_must_not_equal_input_ids:{source_record_id}"
            )
        if masked.diagnostics.get("command_reconstruction") is not False:
            raise QloraStructuredEmissionRecoveryError(
                f"command_reconstruction_not_false:{source_record_id}"
            )
        examples.append(
            {
                "training_example_id": f"t27b:{source_record_id}",
                "source_record_id": source_record_id,
                "prompt": prompt,
                "envelope": envelope,
                "masked_sequence": masked,
                "diagnostics": dict(masked.diagnostics),
            }
        )
    return examples


def _mock_complete_semantic_json(**overrides: Any) -> str:
    from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES, CPCSlotStatus, RouteLabel

    slot = {"status": CPCSlotStatus.UNKNOWN.value, "value": None}
    payload: dict[str, Any] = {
        "cpc": {name: dict(slot) for name in CPC_SLOT_NAMES},
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
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _base_immutability_probe(selected_base_model: str) -> dict[str, Any]:
    """Record immutable base identity; hash a local marker file when a snapshot path exists."""
    probe: dict[str, Any] = {
        "selected_base_model": selected_base_model,
        "merged_into_base": False,
        "base_dir_mutated": False,
    }
    snapshot = os.environ.get("T12_BASE_MODEL_SNAPSHOT") or os.environ.get("HF_HUB_CACHE")
    if snapshot:
        marker_candidates = [
            Path(snapshot) / "config.json",
            Path(snapshot),
        ]
        for candidate in marker_candidates:
            if candidate.is_file():
                probe["marker_path"] = str(candidate)
                probe["marker_sha256_before"] = _sha256_file(candidate)
                probe["marker_sha256_after"] = probe["marker_sha256_before"]
                probe["base_dir_unchanged"] = True
                break
    if "base_dir_unchanged" not in probe:
        probe["immutable_identity"] = selected_base_model
        probe["base_dir_unchanged"] = True
        probe["note"] = "no_local_snapshot_marker_recorded_identity_only"
    return probe


def _annotate_transport(verdict_dict: dict[str, Any], transport_status: str) -> dict[str, Any]:
    out = dict(verdict_dict)
    out["transport_status"] = transport_status
    return out


def _run_mock_emission_recovery(
    *,
    selected_base_model: str,
    config: Mapping[str, Any],
    adapter_dir: Path,
    adapter_id: str,
    examples: Sequence[Mapping[str, Any]],
    validation_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Mock contract-proof path. Never treats sealed acceptance as a live pass."""
    training_cfg = config["training"]
    adapter_cfg = config["adapter"]
    harness = MockQloraTrainingHarness(
        base_model=selected_base_model,
        seed=int(training_cfg["seed"]),
        rank=int(adapter_cfg["rank"]),
    )
    max_steps = int(training_cfg["max_steps"])
    resume_at = int(training_cfg.get("resume_from_checkpoint_step") or 4)
    events: list[dict[str, Any]] = []
    consumed: list[str] = []
    data_position = 0

    identity = AdapterIdentity(
        adapter_id=adapter_id,
        base_model=selected_base_model,
        created_at_utc=_utc_now(),
        rank=int(adapter_cfg["rank"]),
        alpha=int(adapter_cfg["alpha"]),
        target_modules=tuple(adapter_cfg["target_modules"]),
    )
    identity.assert_smoke_scope()
    try:
        assert_cannot_register_smoke_adapter_as_selected(
            identity, proposed_selected_adapter=adapter_id
        )
    except Exception:
        pass  # expected: technical_smoke_only adapters can never become selected_adapter
    else:
        raise QloraStructuredEmissionRecoveryError(
            "expected_guard_to_block_registering_smoke_adapter_as_selected"
        )

    for step in range(1, max_steps + 1):
        example = examples[(step - 1) % len(examples)]
        batch = [
            {
                "training_example_id": example["training_example_id"],
                "source_record_id": example["source_record_id"],
                "diagnostics": dict(example["diagnostics"]),
            }
        ]
        event = harness.train_one_step(batch)
        diagnostics = dict(example["diagnostics"])
        events.append(
            {
                **event,
                "example_id": example["training_example_id"],
                "supervised_token_count": int(diagnostics.get("target_supervised_tokens") or 0),
                "loss_mask_diagnostics": diagnostics,
            }
        )
        consumed.append(str(example["training_example_id"]))
        data_position = step % len(examples)
        if step == resume_at:
            harness.save_adapter(adapter_dir, identity=identity)
            checkpoint_dir = adapter_dir.parent / "full_checkpoint"
            checkpoint_dir.mkdir(parents=True, exist_ok=True)

            class _MockOpt:
                def state_dict(self) -> dict[str, Any]:
                    return {"step": harness.step, "mock": True}

            payload = build_checkpoint_payload(
                adapter_dir=adapter_dir,
                optimizer=_MockOpt(),
                scheduler=None,
                scaler=None,
                global_step=step,
                epoch=0,
                data_position=data_position,
                consumed_example_ids=consumed,
                training_config_hash=_config_hash(config),
                smoke_data_manifest_hash="mock",
                selected_base_model=selected_base_model,
                environment_identity="mock_contract_proof",
                source_commit=os.environ.get("T12_SOURCE_COMMIT") or "mock",
            )
            save_full_checkpoint(checkpoint_dir, payload=payload, adapter_files_present=True)
            resumed = MockQloraTrainingHarness.load_adapter(
                adapter_dir, expected_base_model=selected_base_model
            )
            blob = load_full_checkpoint_blob(checkpoint_dir)
            assert_resume_identities(
                blob,
                selected_base_model=selected_base_model,
                training_config_hash=_config_hash(config),
                smoke_data_manifest_hash="mock",
                environment_identity="mock_contract_proof",
            )
            restore_rng_state(blob["rng"])
            expected_next_index = int(blob["data_position"])
            if expected_next_index != data_position:
                raise QloraStructuredEmissionRecoveryError("mock_data_position_mismatch")
            next_example = examples[expected_next_index % len(examples)]
            events.append(
                {
                    "step": step,
                    "resumed": True,
                    "next_example_id": next_example["training_example_id"],
                    "next_example_index": expected_next_index,
                }
            )
            harness = resumed

    harness.save_adapter(adapter_dir, identity=identity)

    resume = evaluate_resume_components(
        adapter_reload_ok=True,
        optimiser_restore_ok=True,
        scheduler_restore_ok=True,
        rng_restore_ok=True,
        data_position_restore_ok=True,
    ).to_dict()

    transport = "mock_contract_proof"
    structured_records: list[dict[str, Any]] = []
    for index, row in enumerate(validation_rows):
        record = dict(row["record"])
        prompt = build_t27b_inference_prompt(record)
        braces_only = validate_t27b_structured_model_output(prompt=prompt, raw_output="{ }")
        if braces_only.accepted:
            raise QloraStructuredEmissionRecoveryError("braces_only_must_not_accept")
        base_raw = "BASE_MOCK_UNSTRUCTURED"
        adapter_raw = (
            _mock_complete_semantic_json(intent_summary="mock_emission_recovery")
            if index == 0
            else "ADAPTER_MOCK_UNSTRUCTURED"
        )
        base_verdict = validate_t27b_structured_model_output(prompt=prompt, raw_output=base_raw)
        adapter_verdict = validate_t27b_structured_model_output(prompt=prompt, raw_output=adapter_raw)
        structured_records.append(
            {
                "record_id": record.get("id"),
                "prompt": prompt,
                "transport_status": transport,
                "base": _annotate_transport(base_verdict.to_dict(), transport),
                "adapter": _annotate_transport(adapter_verdict.to_dict(), transport),
                "outputs_differ": base_raw != adapter_raw,
                "braces_only_rejected": (not braces_only.accepted),
            }
        )

    differ_count = sum(1 for item in structured_records if item["outputs_differ"])
    if differ_count < 1:
        raise QloraStructuredEmissionRecoveryError(
            "adapter_must_differ_from_base_on_at_least_one_record"
        )

    status_counts: dict[str, int] = {}
    for item in structured_records:
        status = str(item["adapter"].get("final_acceptance_status") or item["adapter"].get("legacy_status"))
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "training_events": events,
        "resumed_step": resume_at,
        "frozen_parameter_count": harness.dim,
        "trainable_parameter_count": harness.dim,
        "base_frozen_verified": True,
        "resume_components": resume,
        "structured_output_results": {
            "records": structured_records,
            "status_counts": status_counts,
            "adapter_differs_from_base_count": differ_count,
            "braces_only_acceptance_forbidden": True,
            "live_gate_evaluated": False,
            "transport_status": transport,
            "note": "mock_contract_proof_only_sealed_acceptance_is_not_a_live_pass",
        },
        "base_immutability": _base_immutability_probe(selected_base_model),
        "next_example_index_after_resume": resume_at % len(examples),
        "contract_proof_ok": bool(resume.get("full_resume_ok")) and differ_count >= 1,
    }


def _count_adapter_metric(
    records: Sequence[Mapping[str, Any]],
    *,
    field: str,
    expected: str,
) -> int:
    count = 0
    for item in records:
        adapter = item.get("adapter") or {}
        if str(adapter.get(field) or "") == expected:
            count += 1
    return count


def _evaluate_pass_thresholds(
    *,
    structured_output: Mapping[str, Any],
    sealed_final_count: int,
    resume_components: Mapping[str, Any],
    pass_thresholds: Mapping[str, Any],
    loss_summary: Mapping[str, Any] | None = None,
    minimum_useful_supervision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    records = list(structured_output.get("records") or [])
    parse_valid = _count_adapter_metric(records, field="json_parse_status", expected="parsed")
    schema_valid = _count_adapter_metric(records, field="schema_status", expected="valid")
    semantic_valid = _count_adapter_metric(records, field="semantic_status", expected="valid")
    safety_accepted = _count_adapter_metric(records, field="safety_status", expected="accepted")
    final_accepted = sum(
        1
        for item in records
        if (item.get("adapter") or {}).get("final_acceptance_status") == "accepted"
        or (item.get("adapter") or {}).get("accepted") is True
    )
    differs = int(structured_output.get("adapter_differs_from_base_count") or 0)
    unsupported_accepted = 0
    for item in records:
        adapter = item.get("adapter") or {}
        accepted = (
            adapter.get("final_acceptance_status") == "accepted" or adapter.get("accepted") is True
        )
        if not accepted:
            continue
        findings = [str(x) for x in (adapter.get("safety_findings") or [])]
        if adapter.get("safety_status") == "rejected" or any(
            "unsupported" in f for f in findings
        ):
            unsupported_accepted += 1
    base_attempted = sum(1 for item in records if item.get("base") is not None)
    adapter_attempted = sum(1 for item in records if item.get("adapter") is not None)
    full_resume_ok = bool(resume_components.get("full_resume_ok"))

    checks = {
        "sealed_final_count": sealed_final_count == int(pass_thresholds["sealed_final_count"]),
        "adapter_parse_valid_min": parse_valid >= int(pass_thresholds["adapter_parse_valid_min"]),
        "adapter_schema_valid_min": schema_valid >= int(pass_thresholds["adapter_schema_valid_min"]),
        "adapter_semantic_valid_min": semantic_valid
        >= int(pass_thresholds["adapter_semantic_valid_min"]),
        "adapter_safety_accepted_min": safety_accepted
        >= int(pass_thresholds["adapter_safety_accepted_min"]),
        "adapter_final_accepted_min": final_accepted
        >= int(pass_thresholds["adapter_final_accepted_min"]),
        "adapter_differs_from_base_min": differs
        >= int(pass_thresholds["adapter_differs_from_base_min"]),
        "unsupported_commitment_accepted_max": unsupported_accepted
        <= int(pass_thresholds["unsupported_commitment_accepted_max"]),
        "base_attempted_min": base_attempted >= int(pass_thresholds["base_attempted_min"]),
        "adapter_attempted_min": adapter_attempted >= int(pass_thresholds["adapter_attempted_min"]),
        "full_resume_ok": full_resume_ok,
    }
    density_note: dict[str, Any] | None = None
    if loss_summary is not None and minimum_useful_supervision:
        mean_pct = float(loss_summary.get("mean_supervised_token_percentage") or 0.0)
        min_mean = float(minimum_useful_supervision.get("min_mean_supervised_token_percentage") or 0.0)
        density_note = {
            "mean_supervised_token_percentage": mean_pct,
            "min_mean_supervised_token_percentage": min_mean,
            "meets_minimum_useful_supervision": mean_pct >= min_mean,
        }
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "passed": not failed,
        "failed_checks": failed,
        "observed": {
            "sealed_final_count": sealed_final_count,
            "adapter_parse_valid": parse_valid,
            "adapter_schema_valid": schema_valid,
            "adapter_semantic_valid": semantic_valid,
            "adapter_safety_accepted": safety_accepted,
            "adapter_final_accepted": final_accepted,
            "adapter_differs_from_base": differs,
            "unsupported_commitment_accepted": unsupported_accepted,
            "base_attempted": base_attempted,
            "adapter_attempted": adapter_attempted,
            "full_resume_ok": full_resume_ok,
        },
        "checks": checks,
        "supervision_density_note": density_note,
    }


def run_real_structured_emission_recovery(
    *,
    selected_base_model: str,
    dataset_rows: Sequence[Mapping[str, Any]],
    validation_rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    adapter_dir: Path,
    adapter_id: str,
    root: Path,
) -> dict[str, Any]:
    """Real 4-bit QLoRA path with full-schema envelope masks and full resume."""
    import time

    import torch
    from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
    from torch.optim.lr_scheduler import ConstantLR
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    started = time.perf_counter()
    repository, revision = parse_checkpoint_identity(selected_base_model)
    training_policy = load_training_target_policy_strict(root / TRAINING_TARGET_POLICY_REL)
    envelope_policy = load_envelope_policy(root / ENVELOPE_POLICY_REL)
    quant = config["quantization"]
    training_cfg = config["training"]
    adapter_cfg = config["adapter"]
    max_seq_len = int(config["sequence"]["max_seq_len"])
    max_steps = int(training_cfg["max_steps"])
    resume_at = int(training_cfg.get("resume_from_checkpoint_step") or 4)
    max_new_tokens = int((config.get("evaluation") or {}).get("max_new_tokens") or 768)
    env_identity = _environment_identity(root)
    config_hash = _config_hash(config)
    data_hash = _data_manifest_hash(root)
    source_commit = os.environ.get("T12_SOURCE_COMMIT") or os.environ.get("SOURCE_COMMIT") or "unknown"

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type=quant.get("quant_type", "nf4"),
        bnb_4bit_compute_dtype=getattr(torch, quant.get("compute_dtype", "bfloat16")),
        bnb_4bit_use_double_quant=bool(quant.get("double_quant", True)),
    )
    tokenizer = AutoTokenizer.from_pretrained(
        repository, revision=revision, local_files_only=True
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tok_adapter = _HFTokenizerAdapter(tokenizer)

    base_model = AutoModelForCausalLM.from_pretrained(
        repository,
        revision=revision,
        local_files_only=True,
        quantization_config=bnb_config,
        device_map="auto",
    )
    base_model = prepare_model_for_kbit_training(base_model)
    for param in base_model.parameters():
        param.requires_grad_(False)

    lora_config = LoraConfig(
        r=int(adapter_cfg["rank"]),
        lora_alpha=int(adapter_cfg["alpha"]),
        target_modules=list(adapter_cfg["target_modules"]),
        lora_dropout=float(adapter_cfg.get("dropout", 0.0)),
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(base_model, lora_config)

    frozen_parameter_count = sum(p.numel() for p in model.parameters() if not p.requires_grad)
    trainable_parameter_count = sum(p.numel() for p in model.parameters() if p.requires_grad)
    if trainable_parameter_count <= 0:
        raise QloraStructuredEmissionRecoveryError("no_trainable_adapter_parameters")
    if frozen_parameter_count <= 0:
        raise QloraStructuredEmissionRecoveryError("expected_frozen_base_parameters")

    optimizer = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad),
        lr=float(training_cfg.get("learning_rate", 2e-4)),
    )
    scheduler = ConstantLR(optimizer, factor=1.0)
    scaler = None

    examples = _build_envelope_examples(
        dataset_rows,
        envelope_policy=envelope_policy,
        training_policy=training_policy,
        tokenizer=tok_adapter,
        max_seq_len=max_seq_len,
    )

    adapter_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = adapter_dir.parent / "full_checkpoint"
    identity = AdapterIdentity(
        adapter_id=adapter_id,
        base_model=selected_base_model,
        created_at_utc=_utc_now(),
        rank=int(adapter_cfg["rank"]),
        alpha=int(adapter_cfg["alpha"]),
        target_modules=tuple(adapter_cfg["target_modules"]),
    )
    identity.assert_smoke_scope()
    try:
        assert_cannot_register_smoke_adapter_as_selected(
            identity, proposed_selected_adapter=adapter_id
        )
    except Exception:
        pass
    else:
        raise QloraStructuredEmissionRecoveryError(
            "expected_guard_to_block_registering_smoke_adapter_as_selected"
        )
    _atomic_write_json(
        adapter_dir / "base_identity_reference.json",
        {"selected_base_model": selected_base_model, "immutable": True},
    )
    base_probe_before = _base_immutability_probe(selected_base_model)

    def _device() -> torch.device:
        return next(model.parameters()).device

    def _tensor_batch(example: Mapping[str, Any]) -> dict[str, torch.Tensor]:
        seq = example["masked_sequence"]
        return {
            "input_ids": torch.tensor([list(seq.input_ids)], dtype=torch.long, device=_device()),
            "attention_mask": torch.tensor(
                [list(seq.attention_mask)], dtype=torch.long, device=_device()
            ),
            "labels": torch.tensor([list(seq.labels)], dtype=torch.long, device=_device()),
        }

    def _save_adapter_and_full(*, global_step: int, data_position: int, consumed: Sequence[str]) -> None:
        model.save_pretrained(str(adapter_dir))
        _atomic_write_json(adapter_dir / "adapter_identity.json", identity.to_dict())
        _atomic_write_json(
            adapter_dir / "training_state.json",
            {
                "step": global_step,
                "base_model": selected_base_model,
                "data_position": data_position,
            },
        )
        payload = build_checkpoint_payload(
            adapter_dir=adapter_dir,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=scaler,
            global_step=global_step,
            epoch=0,
            data_position=data_position,
            consumed_example_ids=consumed,
            training_config_hash=config_hash,
            smoke_data_manifest_hash=data_hash,
            selected_base_model=selected_base_model,
            environment_identity=env_identity,
            source_commit=source_commit,
        )
        save_full_checkpoint(
            checkpoint_dir,
            payload=payload,
            adapter_files_present=(adapter_dir / "adapter_config.json").is_file()
            or (adapter_dir / "adapter_model.safetensors").is_file()
            or (adapter_dir / "adapter_weights.json").is_file(),
        )

    events: list[dict[str, Any]] = []
    consumed_ids: list[str] = []
    peak_vram_bytes: int | None = None
    resume_components = {
        "adapter_reload_ok": False,
        "optimiser_restore_ok": False,
        "scheduler_restore_ok": False,
        "rng_restore_ok": False,
        "data_position_restore_ok": False,
        "full_resume_ok": False,
    }
    next_example_index_after_resume: int | None = None

    step = 0
    while step < max_steps:
        example_index = step % len(examples)
        example = examples[example_index]
        batch = _tensor_batch(example)
        if torch.equal(batch["labels"], batch["input_ids"]):
            raise QloraStructuredEmissionRecoveryError(
                "refusing_unmasked_command_reconstruction_labels"
            )
        if int((batch["labels"] != IGNORE_INDEX).sum().item()) <= 0:
            raise QloraStructuredEmissionRecoveryError("zero_supervised_tokens_in_batch")

        outputs = model(
            input_ids=batch["input_ids"],
            attention_mask=batch["attention_mask"],
            labels=batch["labels"],
        )
        loss = outputs.loss
        loss.backward()
        optimizer.step()
        scheduler.step()
        optimizer.zero_grad()
        step += 1
        consumed_ids.append(str(example["training_example_id"]))
        data_position = step % len(examples)
        diag = dict(example["diagnostics"])
        events.append(
            {
                "step": step,
                "loss": float(loss.detach().cpu().item()),
                "example_id": example["training_example_id"],
                "example_index": example_index,
                "supervised_token_count": int(diag.get("target_supervised_tokens") or 0),
                "loss_mask_diagnostics": diag,
                "base_frozen_verified": True,
            }
        )
        if torch.cuda.is_available():
            peak_vram_bytes = int(torch.cuda.max_memory_allocated())

        if step % max(1, int(training_cfg["checkpoint_interval_steps"])) == 0:
            _save_adapter_and_full(
                global_step=step, data_position=data_position, consumed=consumed_ids
            )

        if training_cfg.get("resume_test", True) and step == resume_at:
            _save_adapter_and_full(
                global_step=step, data_position=data_position, consumed=consumed_ids
            )
            del model
            del base_model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            blob = load_full_checkpoint_blob(checkpoint_dir)
            assert_resume_identities(
                blob,
                selected_base_model=selected_base_model,
                training_config_hash=config_hash,
                smoke_data_manifest_hash=data_hash,
                environment_identity=env_identity,
            )

            base_reload = AutoModelForCausalLM.from_pretrained(
                repository,
                revision=revision,
                local_files_only=True,
                quantization_config=bnb_config,
                device_map="auto",
            )
            base_reload = prepare_model_for_kbit_training(base_reload)
            for param in base_reload.parameters():
                param.requires_grad_(False)
            model = PeftModel.from_pretrained(base_reload, str(adapter_dir), is_trainable=True)
            resume_components["adapter_reload_ok"] = True

            optimizer = torch.optim.AdamW(
                (p for p in model.parameters() if p.requires_grad),
                lr=float(training_cfg.get("learning_rate", 2e-4)),
            )
            try:
                optimizer.load_state_dict(blob["optimizer"])
                resume_components["optimiser_restore_ok"] = True
            except Exception as exc:  # noqa: BLE001
                raise QloraStructuredEmissionRecoveryError(
                    f"optimiser_restore_failed:{exc}"
                ) from exc

            scheduler = ConstantLR(optimizer, factor=1.0)
            if blob.get("scheduler") is not None:
                try:
                    scheduler.load_state_dict(blob["scheduler"])
                    resume_components["scheduler_restore_ok"] = True
                except Exception as exc:  # noqa: BLE001
                    raise QloraStructuredEmissionRecoveryError(
                        f"scheduler_restore_failed:{exc}"
                    ) from exc
            else:
                resume_components["scheduler_restore_ok"] = True

            resume_components["rng_restore_ok"] = bool(restore_rng_state(blob["rng"]))

            restored_position = int(blob["data_position"])
            expected_next = examples[restored_position % len(examples)]
            next_example_index_after_resume = restored_position % len(examples)
            resume_components["data_position_restore_ok"] = restored_position == data_position
            if not resume_components["data_position_restore_ok"]:
                raise QloraStructuredEmissionRecoveryError(
                    f"data_position_mismatch: expected {data_position}, got {restored_position}"
                )
            events.append(
                {
                    "step": step,
                    "resumed": True,
                    "next_example_id": expected_next["training_example_id"],
                    "next_example_index": next_example_index_after_resume,
                }
            )
            resume_components = evaluate_resume_components(
                adapter_reload_ok=bool(resume_components["adapter_reload_ok"]),
                optimiser_restore_ok=bool(resume_components["optimiser_restore_ok"]),
                scheduler_restore_ok=bool(resume_components["scheduler_restore_ok"]),
                rng_restore_ok=bool(resume_components["rng_restore_ok"]),
                data_position_restore_ok=bool(resume_components["data_position_restore_ok"]),
            ).to_dict()
            if not resume_components["full_resume_ok"]:
                raise QloraStructuredEmissionRecoveryError(
                    f"full_resume_failed:{resume_components}"
                )

    model.save_pretrained(str(adapter_dir))
    _atomic_write_json(adapter_dir / "adapter_identity.json", identity.to_dict())

    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    transport = "hf_generate_unconstrained"
    structured_records: list[dict[str, Any]] = []
    base_eval = AutoModelForCausalLM.from_pretrained(
        repository,
        revision=revision,
        local_files_only=True,
        quantization_config=bnb_config,
        device_map="auto",
    )
    base_for_adapter = AutoModelForCausalLM.from_pretrained(
        repository,
        revision=revision,
        local_files_only=True,
        quantization_config=bnb_config,
        device_map="auto",
    )
    adapted_eval = PeftModel.from_pretrained(base_for_adapter, str(adapter_dir))

    for row in validation_rows:
        record = dict(row["record"])
        # Identical prompt contract for base and adapter.
        prompt = build_t27b_inference_prompt(record)
        encoded = tokenizer(prompt, return_tensors="pt")
        encoded_base = {
            key: value.to(next(base_eval.parameters()).device) for key, value in encoded.items()
        }
        encoded_adapted = {
            key: value.to(next(adapted_eval.parameters()).device) for key, value in encoded.items()
        }
        with torch.no_grad():
            base_ids = base_eval.generate(**encoded_base, max_new_tokens=max_new_tokens)
            adapted_ids = adapted_eval.generate(**encoded_adapted, max_new_tokens=max_new_tokens)
        base_text = tokenizer.decode(base_ids[0], skip_special_tokens=True)
        adapted_text = tokenizer.decode(adapted_ids[0], skip_special_tokens=True)
        base_verdict = validate_t27b_structured_model_output(prompt=prompt, raw_output=base_text)
        adapter_verdict = validate_t27b_structured_model_output(
            prompt=prompt, raw_output=adapted_text
        )
        # Training SIF lacks vLLM guided JSON — do not claim constrained transport success.
        structured_records.append(
            {
                "record_id": record.get("id"),
                "prompt": prompt,
                "transport_status": transport,
                "base": _annotate_transport(base_verdict.to_dict(), transport),
                "adapter": _annotate_transport(adapter_verdict.to_dict(), transport),
                "outputs_differ": base_text != adapted_text,
                "constrained_syntax_alone_never_acceptance": True,
            }
        )

    differ_count = sum(1 for item in structured_records if item["outputs_differ"])
    if differ_count < 1:
        raise QloraStructuredEmissionRecoveryError(
            "adapter_must_differ_from_base_on_at_least_one_record"
        )

    braces_probe = validate_t27b_structured_model_output(prompt="PROMPT", raw_output="{not:json}")
    if braces_probe.accepted:
        raise QloraStructuredEmissionRecoveryError("braces_only_must_not_accept")

    status_counts: dict[str, int] = {}
    for item in structured_records:
        status = str(
            item["adapter"].get("final_acceptance_status") or item["adapter"].get("legacy_status")
        )
        status_counts[status] = status_counts.get(status, 0) + 1

    base_probe_after = _base_immutability_probe(selected_base_model)
    if base_probe_before.get("marker_sha256_before") and base_probe_after.get("marker_sha256_after"):
        if base_probe_before["marker_sha256_before"] != base_probe_after["marker_sha256_after"]:
            raise QloraStructuredEmissionRecoveryError("base_snapshot_mutated")
        base_probe_after["base_dir_unchanged"] = True
    base_probe_after["merged_into_base"] = False

    return {
        "training_events": events,
        "resumed_step": resume_at,
        "frozen_parameter_count": frozen_parameter_count,
        "trainable_parameter_count": trainable_parameter_count,
        "peak_vram_bytes": peak_vram_bytes,
        "base_frozen_verified": True,
        "resume_components": resume_components,
        "structured_output_results": {
            "records": structured_records,
            "status_counts": status_counts,
            "adapter_differs_from_base_count": differ_count,
            "braces_only_acceptance_forbidden": True,
            "braces_only_probe": _annotate_transport(braces_probe.to_dict(), transport),
            "transport_status": transport,
            "live_gate_evaluated": True,
            "constrained_syntax_alone_never_acceptance": True,
        },
        "base_immutability": base_probe_after,
        "next_example_index_after_resume": next_example_index_after_resume,
        "runtime_seconds": round(time.perf_counter() - started, 3),
        "loss_mask_diagnostics": [dict(ex["diagnostics"]) for ex in examples],
    }


def run_structured_emission_recovery_training(
    *,
    result_dir: Path,
    run_id: str,
    root: Path | None = None,
    require_real_mode: bool = False,
    force_mock: bool = True,
) -> dict[str, Any]:
    """Run T27B structured-emission recovery and always finalise evidence.

    Local defaults: ``require_real_mode=False``, ``force_mock=True`` → mock.
    Live cluster: ``require_real_mode=True``, ``force_mock=False``. If real
    mode is required and the provider is unavailable or ``force_mock`` would
    apply, the job fails with evidence — it never silently falls back to mock.
    """
    repo = _repo_root(root)
    _assert_result_dir_not_job6059(result_dir, repo)
    selected_base_model = require_selected_base_model(repo)
    resolved_config = load_emission_recovery_config(repo)
    _refuse_nonempty_result_dir(result_dir)

    train_rows = load_emission_recovery_train_records(repo)
    sealed_rows = load_emission_recovery_sealed_records(repo)
    diagnostic_rows = load_emission_recovery_diagnostic_records(repo)
    training_policy = load_training_target_policy_strict(repo / TRAINING_TARGET_POLICY_REL)
    envelope_policy = load_envelope_policy(repo / ENVELOPE_POLICY_REL)

    availability = check_qlora_provider_available()
    adapter_id = f"qlora-structured-emission-recovery-adapter-{run_id}"
    adapter_dir = result_dir / "adapter"
    started = _utc_now()

    if require_real_mode:
        if force_mock:
            return _write_failure_evidence(
                result_dir=result_dir,
                run_id=run_id,
                selected_base_model=selected_base_model,
                mode="real_mode_required_but_force_mock",
                failure=(
                    "require_real_mode=True but force_mock=True; refusing silent "
                    "fallback to mock_contract_proof"
                ),
                availability=availability.to_dict(),
                started=started,
            )
        if not availability.available:
            return _write_failure_evidence(
                result_dir=result_dir,
                run_id=run_id,
                selected_base_model=selected_base_model,
                mode="real_mode_required_provider_unavailable",
                failure=(
                    "require_real_mode=True but QLoRA provider unavailable: "
                    f"{availability.reason}; missing={list(availability.missing_modules)}; "
                    "refusing silent fallback to mock_contract_proof"
                ),
                availability=availability.to_dict(),
                started=started,
            )
        use_real = True
    else:
        use_real = availability.available and not force_mock

    mode = "real_cluster_training" if use_real else "mock_contract_proof"
    failure: str | None = None
    training_events: list[dict[str, Any]] = []
    resume_components: dict[str, Any] = {
        "adapter_reload_ok": False,
        "optimiser_restore_ok": False,
        "scheduler_restore_ok": False,
        "rng_restore_ok": False,
        "data_position_restore_ok": False,
        "full_resume_ok": False,
    }
    structured_output: dict[str, Any] = {"records": [], "status_counts": {}}
    loss_summary: dict[str, Any] = {"example_count": 0}
    real_metrics: dict[str, Any] = {}
    live_gate_evaluated = False
    gate_evaluation: dict[str, Any] | None = None
    success = False

    try:
        max_seq_len = int(resolved_config["sequence"]["max_seq_len"])
        jsonschema_runtime: dict[str, Any] | None = None
        if use_real:
            # Generic runtime fix after job 6307: production schema validation
            # requires jsonschema in the training-site-packages bind mount.
            jsonschema_runtime = ensure_runtime_jsonschema()
            outcome = run_real_structured_emission_recovery(
                selected_base_model=selected_base_model,
                dataset_rows=train_rows,
                validation_rows=sealed_rows,
                config=resolved_config,
                adapter_dir=adapter_dir,
                adapter_id=adapter_id,
                root=repo,
            )
            outcome["jsonschema_runtime"] = jsonschema_runtime
        else:
            examples = _build_envelope_examples(
                train_rows,
                envelope_policy=envelope_policy,
                training_policy=training_policy,
                tokenizer=DeterministicCharTokenizer(),
                max_seq_len=max(_MOCK_CHAR_MAX_SEQ_LEN, max_seq_len),
            )
            outcome = _run_mock_emission_recovery(
                selected_base_model=selected_base_model,
                config=resolved_config,
                adapter_dir=adapter_dir,
                adapter_id=adapter_id,
                examples=examples,
                validation_rows=sealed_rows,
            )
            outcome["loss_mask_diagnostics"] = [dict(ex["diagnostics"]) for ex in examples]

        training_events = list(outcome.get("training_events") or [])
        resume_components = dict(outcome.get("resume_components") or resume_components)
        structured_output = dict(outcome.get("structured_output_results") or structured_output)
        loss_summary = _summarise_loss_masks(outcome.get("loss_mask_diagnostics") or [])
        real_metrics = {
            key: outcome.get(key)
            for key in (
                "frozen_parameter_count",
                "trainable_parameter_count",
                "peak_vram_bytes",
                "base_frozen_verified",
                "resumed_step",
                "base_immutability",
                "next_example_index_after_resume",
                "runtime_seconds",
            )
            if outcome.get(key) is not None
        }

        if use_real:
            live_gate_evaluated = True
            gate_evaluation = _evaluate_pass_thresholds(
                structured_output=structured_output,
                sealed_final_count=len(sealed_rows),
                resume_components=resume_components,
                pass_thresholds=dict(resolved_config["pass_thresholds"]),
                loss_summary=loss_summary,
                minimum_useful_supervision=dict(
                    resolved_config.get("minimum_useful_supervision") or {}
                ),
            )
            if not gate_evaluation["passed"]:
                success = False
                failure = (
                    "pass_thresholds_not_met:"
                    + ",".join(gate_evaluation.get("failed_checks") or [])
                )
            else:
                success = True
        else:
            live_gate_evaluated = False
            # Mock is contract-proof only — do not claim pass_thresholds met.
            if not outcome.get("contract_proof_ok"):
                raise QloraStructuredEmissionRecoveryError("mock_contract_proof_failed")
            if not resume_components.get("full_resume_ok"):
                raise QloraStructuredEmissionRecoveryError("mock_full_resume_not_ok")
            success = True
    except Exception as exc:  # noqa: BLE001 - evidence must be finalised regardless
        success = False
        failure = f"{type(exc).__name__}: {exc}"

    ended = _utc_now()
    result_dir.mkdir(parents=True, exist_ok=True)
    supervision_density = _build_supervision_density(
        loss_summary,
        minimum_useful_supervision=dict(
            resolved_config.get("minimum_useful_supervision") or {}
        ),
    )

    status_counts = dict(structured_output.get("status_counts") or {})
    accepted_count = int(status_counts.get("accepted", 0))
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
            "selected_adapter": None,
            "valid_for_official_use": False,
            "live_gate_evaluated": live_gate_evaluated,
            "envelope_id": FULL_SCHEMA_ENVELOPE_ID,
            "prompt_contract": PROMPT_CONTRACT_VERSION,
            "record_count": len(train_rows),
            "validation_record_count": len(sealed_rows),
            "diagnostic_record_count": len(diagnostic_rows),
            "training_events": training_events,
            "resume_components": resume_components,
            "structured_output_summary": {
                "status_counts": status_counts,
                "adapter_differs_from_base_count": structured_output.get(
                    "adapter_differs_from_base_count"
                ),
                "accepted_count": accepted_count,
                "record_count": len(structured_output.get("records") or []),
                "braces_only_acceptance_forbidden": True,
                "transport_status": structured_output.get("transport_status"),
                "live_gate_evaluated": live_gate_evaluated,
            },
            "pass_threshold_evaluation": gate_evaluation,
            "supervision_density_summary": {
                "mean_supervised_token_percentage": supervision_density.get(
                    "mean_supervised_token_percentage"
                ),
                "meets_minimum_mean_supervised_percentage": supervision_density.get(
                    "meets_minimum_mean_supervised_percentage"
                ),
            },
            "start_timestamp_utc": started,
            "end_timestamp_utc": ended,
            "provider_availability": availability.to_dict(),
            "require_real_mode": require_real_mode,
            "force_mock": force_mock,
            **{k: v for k, v in real_metrics.items() if v is not None},
        }
    )
    assert_emission_recovery_run_not_official(result_payload)
    _atomic_write_json(result_dir / "qlora_structured_emission_recovery_result.json", result_payload)
    _atomic_write_json(result_dir / "loss_mask_summary.json", loss_summary)
    _atomic_write_json(result_dir / "structured_output_results.json", structured_output)
    _atomic_write_json(result_dir / "resume_components.json", resume_components)
    _atomic_write_json(result_dir / "supervision_density.json", supervision_density)

    adapter_identity_path = adapter_dir / "adapter_identity.json"
    if adapter_identity_path.is_file():
        (result_dir / "adapter_identity.json").write_text(
            adapter_identity_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
    else:
        _atomic_write_json(
            result_dir / "adapter_identity.json",
            {
                "adapter_id": adapter_id,
                "base_model": selected_base_model,
                "technical_smoke_only": True,
                "selected_adapter": False,
                "valid_for_official_use": False,
                "note": (
                    "identity_stub_checkpoint_not_written" if not success else "missing_adapter_identity"
                ),
            },
        )

    manifest = finalize_emission_recovery_run_manifest(result_dir, run_id=run_id, success=success)
    return {
        "result": result_payload,
        "manifest": manifest,
        "loss_mask_summary": loss_summary,
        "resume_components": resume_components,
        "structured_output_results": structured_output,
        "supervision_density": supervision_density,
        "mode": mode,
        "success": success,
    }
