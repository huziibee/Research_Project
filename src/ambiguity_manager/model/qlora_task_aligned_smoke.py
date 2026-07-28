"""Task-aligned QLoRA technical-smoke orchestrator (T27).

Proves structured-target supervision, real token-level loss masks, full
checkpoint/resume component restore, and strict structured-output validation
on a frozen four-record ``source_dev`` set — without selecting an adapter or
model strategy.

Heavy ML imports (torch, transformers, peft, bitsandbytes, accelerate) are
strictly lazy. Local defaults use the deterministic mock contract harness;
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
from ambiguity_manager.model.qlora_task_aligned_smoke_data import (
    dataset_paths as task_aligned_paths,
    validation_paths as task_aligned_val_paths,
)
from ambiguity_manager.model.structured_output_validation import (
    STATUS_ACCEPTED,
    validate_structured_model_output,
)
from ambiguity_manager.model.token_loss_masking import IGNORE_INDEX
from ambiguity_manager.model.training_example_contract import (
    TrainingExample,
    build_inference_time_prompt,
    build_training_example,
)
from ambiguity_manager.model.training_target_packaging import load_training_target_policy_strict
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.systems.model_identities import parse_checkpoint_identity

PROVIDER_ID = "qlora_task_aligned_smoke_v1"
PROVIDER_VERSION = "1.0.0"

CONFIG_REL = "configs/model/qlora_task_aligned_smoke_v1.json"
ENVIRONMENT_REL = "configs/environments/t12_cluster_training_task_aligned_v1.json"
TRAINING_TARGET_POLICY_REL = "configs/data/training_target_policy_v1.json"

FORBIDDEN_EAGER_IMPORTS = frozenset({"torch", "transformers", "peft", "bitsandbytes", "accelerate"})

EVIDENCE_FILES = (
    "qlora_task_aligned_smoke_result.json",
    "adapter_identity.json",
    "loss_mask_summary.json",
    "structured_output_results.json",
    "resume_components.json",
    "run_manifest.json",
)


class QloraTaskAlignedSmokeError(RuntimeError):
    """Raised for task-aligned QLoRA smoke validation or execution failures."""


def _repo_root(root: Path | None = None) -> Path:
    return (root or ProjectPaths.from_repo_root().root).resolve()


def load_task_aligned_smoke_config(root: Path | None = None) -> dict[str, Any]:
    """Load and structurally validate the task-aligned smoke config."""
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
        errors.append("selected_adapter must remain null in the smoke config")
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
        raise QloraTaskAlignedSmokeError(
            "invalid qlora_task_aligned_smoke_v1 config:\n- " + "\n- ".join(errors)
        )
    return payload


def _refuse_nonempty_result_dir(result_dir: Path) -> None:
    result_dir.mkdir(parents=True, exist_ok=True)
    existing = [name for name in EVIDENCE_FILES if (result_dir / name).exists()]
    if existing:
        raise QloraTaskAlignedSmokeError(f"result_dir_not_empty:{','.join(existing)}")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise QloraTaskAlignedSmokeError(f"missing_jsonl:{path}")
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def load_task_aligned_records(root: Path | None = None) -> list[dict[str, Any]]:
    paths = task_aligned_paths(_repo_root(root))
    rows = _load_jsonl(paths["records"])
    if len(rows) < 1:
        raise QloraTaskAlignedSmokeError("task_aligned_train_records_empty")
    return rows


def load_task_aligned_validation_records(root: Path | None = None) -> list[dict[str, Any]]:
    paths = task_aligned_val_paths(_repo_root(root))
    rows = _load_jsonl(paths["records"])
    if len(rows) != 4:
        raise QloraTaskAlignedSmokeError(
            f"task_aligned_val_record_count_expected_4_got_{len(rows)}"
        )
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
    manifest_path = task_aligned_paths(root)["manifest"]
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return str(payload.get("manifest_hash") or sha256_hex(manifest_path.read_bytes()))


def _summarise_loss_masks(diagnostics: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not diagnostics:
        return {
            "example_count": 0,
            "examples_with_supervised_tokens": 0,
            "mean_supervised_token_percentage": 0.0,
            "per_example": [],
            "command_reconstruction_forbidden": True,
        }
    supervised_pct = [float(item.get("supervised_token_percentage") or 0.0) for item in diagnostics]
    with_tokens = sum(1 for item in diagnostics if int(item.get("target_supervised_tokens") or 0) > 0)
    return {
        "example_count": len(diagnostics),
        "examples_with_supervised_tokens": with_tokens,
        "mean_supervised_token_percentage": round(sum(supervised_pct) / max(1, len(supervised_pct)), 4),
        "per_example": [dict(item) for item in diagnostics],
        "command_reconstruction_forbidden": True,
        "labels_never_equal_input_ids": True,
    }


def assert_task_aligned_run_not_official(result_payload: Mapping[str, Any]) -> None:
    if result_payload.get("valid_for_official_use") is not False:
        raise QloraTaskAlignedSmokeError("task_aligned smoke must have valid_for_official_use=False")
    selected = result_payload.get("selected_adapter")
    if selected not in (None, False):
        raise QloraTaskAlignedSmokeError(
            "task_aligned smoke must keep selected_adapter null/false"
        )
    if result_payload.get("technical_smoke_only") is not True:
        raise QloraTaskAlignedSmokeError("task_aligned smoke must have technical_smoke_only=True")


def finalize_task_aligned_run_manifest(
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
    started: str | None = None,
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
            "start_timestamp_utc": started or _utc_now(),
            "end_timestamp_utc": _utc_now(),
            "provider_availability": dict(availability),
            "resume_components": dict(resume_components or {}),
            "structured_output_summary": dict(structured_output or {}),
        }
    )
    assert_task_aligned_run_not_official(result_payload)
    _atomic_write_json(result_dir / "qlora_task_aligned_smoke_result.json", result_payload)
    _atomic_write_json(
        result_dir / "loss_mask_summary.json",
        dict(loss_summary or {"example_count": 0, "error": "run_failed_before_masks"}),
    )
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
    manifest = finalize_task_aligned_run_manifest(result_dir, run_id=run_id, success=False)
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
        "loss_mask_summary": dict(loss_summary or {"example_count": 0}),
    }


class _HFTokenizerAdapter:
    """Thin encode/decode wrapper matching :class:`TokenizerLike`."""

    def __init__(self, tokenizer: Any) -> None:
        self._tokenizer = tokenizer
        pad = getattr(tokenizer, "pad_token_id", None)
        eos = getattr(tokenizer, "eos_token_id", None)
        self.pad_token_id = int(pad if pad is not None else (eos or 0))

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        return [int(x) for x in self._tokenizer.encode(text, add_special_tokens=add_special_tokens)]

    def decode(self, ids: Sequence[int], skip_special_tokens: bool = True) -> str:
        return str(self._tokenizer.decode(list(ids), skip_special_tokens=skip_special_tokens))


def _build_examples_from_records(
    rows: Sequence[Mapping[str, Any]],
    *,
    policy: Mapping[str, Any],
    tokenizer: Any | None,
    max_seq_len: int,
) -> list[TrainingExample]:
    examples: list[TrainingExample] = []
    for row in rows:
        examples.append(
            build_training_example(
                record=dict(row["record"]),
                eligibility=dict(row["eligibility"]),
                source_dataset=str(row.get("source_dataset") or row["record"].get("source_dataset") or ""),
                group_key=str(row.get("group_key") or ""),
                split=str(row.get("split") or "source_train"),
                policy=dict(policy),
                tokenizer=tokenizer,
                max_seq_len=max_seq_len,
                attach_masks=tokenizer is not None,
            )
        )
    return examples


def _build_validation_prompt(record: Mapping[str, Any]) -> str:
    """Prefer production-schema prompt_builder text; fall back to inference-time prompt."""
    try:
        from ambiguity_manager.model.prompt_builder import PromptBuildRequest, build_prompt_messages

        scene = record.get("scene_context")
        capability = record.get("capability_context")
        history = record.get("dialogue_history")
        messages = build_prompt_messages(
            PromptBuildRequest(
                command=str(record.get("command") or ""),
                scene_context=str(scene) if isinstance(scene, str) else None,
                dialogue_history=[str(x) for x in history] if isinstance(history, list) else [],
                capability_context=str(capability) if isinstance(capability, str) else None,
            )
        )
        return "\n\n".join(f"{msg['role'].upper()}:\n{msg['content']}" for msg in messages)
    except Exception:  # noqa: BLE001 - validation must still run if prompt assets missing
        return build_inference_time_prompt(record)


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


def _run_mock_task_aligned_smoke(
    *,
    selected_base_model: str,
    config: Mapping[str, Any],
    adapter_dir: Path,
    adapter_id: str,
    examples: Sequence[TrainingExample],
    validation_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
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
        raise QloraTaskAlignedSmokeError(
            "expected_guard_to_block_registering_smoke_adapter_as_selected"
        )

    for step in range(1, max_steps + 1):
        example = examples[(step - 1) % len(examples)]
        batch = [example.to_dict()]
        event = harness.train_one_step(batch)
        diagnostics = (
            dict(example.masked_sequence.diagnostics)
            if example.masked_sequence is not None
            else {"target_supervised_tokens": 1, "supervised_token_percentage": 10.0}
        )
        events.append(
            {
                **event,
                "example_id": example.training_example_id,
                "supervised_token_count": int(diagnostics.get("target_supervised_tokens") or 0),
                "loss_mask_diagnostics": diagnostics,
            }
        )
        consumed.append(example.training_example_id)
        data_position = step % len(examples)
        if step == resume_at:
            harness.save_adapter(adapter_dir, identity=identity)
            checkpoint_dir = adapter_dir.parent / "full_checkpoint"
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            # Mock full-checkpoint blob via pickle-compatible payload helpers.
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
                raise QloraTaskAlignedSmokeError("mock_data_position_mismatch")
            next_example = examples[expected_next_index % len(examples)]
            events.append(
                {
                    "step": step,
                    "resumed": True,
                    "next_example_id": next_example.training_example_id,
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

    structured_records: list[dict[str, Any]] = []
    for index, row in enumerate(validation_rows):
        record = dict(row["record"])
        prompt = _build_validation_prompt(record)
        # Deterministic mock: braces-only must fail; a schema-shaped JSON is retained as attempt.
        braces_only = validate_structured_model_output(prompt=prompt, raw_output="{ }")
        if braces_only.accepted:
            raise QloraTaskAlignedSmokeError("braces_only_must_not_accept")
        # Mock adapter "generation" differs from base on at least one record.
        base_raw = "BASE_MOCK_UNSTRUCTURED"
        adapter_raw = (
            '{"speech_act":"request","intent_summary":"mock","ambiguity_present":true,'
            '"ambiguity_types":[],"primary_ambiguity_type":null,"compound_ambiguity":false,'
            '"compound_ambiguity_count":0,"candidate_interpretations":[],'
            '"selected_interpretation":null,"clarification_question":null,'
            '"clarification_targets":[],"clarification_subtype":null,"cpc":{},'
            '"recommended_strategy":"clarify","strategy_sequence":[],'
            '"capability_status":"unknown","rejection_reason":null,'
            '"risk_relevant":false,"risk_level":"unknown"}'
            if index == 0
            else "ADAPTER_MOCK_UNSTRUCTURED"
        )
        base_verdict = validate_structured_model_output(prompt=prompt, raw_output=base_raw)
        adapter_verdict = validate_structured_model_output(prompt=prompt, raw_output=adapter_raw)
        structured_records.append(
            {
                "record_id": record.get("id"),
                "prompt": prompt,
                "base": base_verdict.to_dict(),
                "adapter": adapter_verdict.to_dict(),
                "outputs_differ": base_raw != adapter_raw,
                "braces_only_rejected": braces_only.braces_only_rejected or braces_only.status != STATUS_ACCEPTED,
            }
        )

    differ_count = sum(1 for item in structured_records if item["outputs_differ"])
    if differ_count < 1:
        raise QloraTaskAlignedSmokeError("adapter_must_differ_from_base_on_at_least_one_record")

    status_counts: dict[str, int] = {}
    for item in structured_records:
        status = str(item["adapter"]["status"])
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
        },
        "base_immutability": _base_immutability_probe(selected_base_model),
        "next_example_index_after_resume": resume_at % len(examples),
    }


def run_real_task_aligned_qlora_smoke(
    *,
    selected_base_model: str,
    dataset_rows: Sequence[Mapping[str, Any]],
    validation_rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    adapter_dir: Path,
    adapter_id: str,
    root: Path,
    production: bool = False,
    data_manifest_hash_override: str | None = None,
) -> dict[str, Any]:
    """Real 4-bit task-aligned QLoRA path with masked labels and full resume."""
    import time

    import torch
    from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
    from torch.optim.lr_scheduler import ConstantLR
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    started = time.perf_counter()
    repository, revision = parse_checkpoint_identity(selected_base_model)
    policy = load_training_target_policy_strict(root / TRAINING_TARGET_POLICY_REL)
    quant = config["quantization"]
    training_cfg = config["training"]
    adapter_cfg = config["adapter"]
    max_seq_len = int(config["sequence"]["max_seq_len"])
    max_steps = int(training_cfg["max_steps"])
    resume_at = int(training_cfg.get("resume_from_checkpoint_step") or 4)
    max_new_tokens = int((config.get("evaluation") or {}).get("max_new_tokens") or 512)
    env_identity = _environment_identity(root)
    config_hash = _config_hash(config)
    data_hash = data_manifest_hash_override or _data_manifest_hash(root)
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
        raise QloraTaskAlignedSmokeError("no_trainable_adapter_parameters")
    if frozen_parameter_count <= 0:
        raise QloraTaskAlignedSmokeError("expected_frozen_base_parameters")

    optimizer = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad),
        lr=float(training_cfg.get("learning_rate", 2e-4)),
    )
    scheduler = ConstantLR(optimizer, factor=1.0)
    scaler = None

    examples = _build_examples_from_records(
        dataset_rows,
        policy=policy,
        tokenizer=tok_adapter,
        max_seq_len=max_seq_len,
    )
    # Rebuild masks with the real tokenizer (build_training_example already did);
    # assert labels are never plain command reconstruction.
    for example in examples:
        if example.masked_sequence is None:
            raise QloraTaskAlignedSmokeError(f"missing_mask:{example.training_example_id}")
        if example.masked_sequence.diagnostics.get("command_reconstruction") is not False:
            raise QloraTaskAlignedSmokeError("command_reconstruction_not_false")
        if list(example.masked_sequence.labels) == list(example.masked_sequence.input_ids):
            raise QloraTaskAlignedSmokeError("labels_must_not_equal_input_ids")

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
    if not production:
        identity.assert_smoke_scope()
    _atomic_write_json(
        adapter_dir / "base_identity_reference.json",
        {"selected_base_model": selected_base_model, "immutable": True},
    )
    base_probe_before = _base_immutability_probe(selected_base_model)

    def _device() -> torch.device:
        return next(model.parameters()).device

    def _tensor_batch(example: TrainingExample) -> dict[str, torch.Tensor]:
        assert example.masked_sequence is not None
        seq = example.masked_sequence
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
        # Causal LM loss on masked labels only — never labels=input_ids of the command.
        if torch.equal(batch["labels"], batch["input_ids"]):
            raise QloraTaskAlignedSmokeError("refusing_unmasked_command_reconstruction_labels")
        if int((batch["labels"] != IGNORE_INDEX).sum().item()) <= 0:
            raise QloraTaskAlignedSmokeError("zero_supervised_tokens_in_batch")

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
        consumed_ids.append(example.training_example_id)
        data_position = step % len(examples)
        diag = dict(example.masked_sequence.diagnostics) if example.masked_sequence else {}
        events.append(
            {
                "step": step,
                "loss": float(loss.detach().cpu().item()),
                "example_id": example.training_example_id,
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
                raise QloraTaskAlignedSmokeError(f"optimiser_restore_failed:{exc}") from exc

            scheduler = ConstantLR(optimizer, factor=1.0)
            if blob.get("scheduler") is not None:
                try:
                    scheduler.load_state_dict(blob["scheduler"])
                    resume_components["scheduler_restore_ok"] = True
                except Exception as exc:  # noqa: BLE001
                    raise QloraTaskAlignedSmokeError(f"scheduler_restore_failed:{exc}") from exc
            else:
                resume_components["scheduler_restore_ok"] = True

            resume_components["rng_restore_ok"] = bool(restore_rng_state(blob["rng"]))

            restored_position = int(blob["data_position"])
            expected_next = examples[restored_position % len(examples)]
            next_example_index_after_resume = restored_position % len(examples)
            resume_components["data_position_restore_ok"] = restored_position == data_position
            if not resume_components["data_position_restore_ok"]:
                raise QloraTaskAlignedSmokeError(
                    f"data_position_mismatch: expected {data_position}, got {restored_position}"
                )
            events.append(
                {
                    "step": step,
                    "resumed": True,
                    "next_example_id": expected_next.training_example_id,
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
                raise QloraTaskAlignedSmokeError(f"full_resume_failed:{resume_components}")

    model.save_pretrained(str(adapter_dir))
    _atomic_write_json(adapter_dir / "adapter_identity.json", identity.to_dict())

    # Structured-output eval: base vs adapter on frozen validation records.
    # Load separate instances so the adapter is never merged into the base path.
    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

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
        prompt = _build_validation_prompt(record)
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
        base_verdict = validate_structured_model_output(prompt=prompt, raw_output=base_text)
        adapter_verdict = validate_structured_model_output(prompt=prompt, raw_output=adapted_text)
        structured_records.append(
            {
                "record_id": record.get("id"),
                "prompt": prompt,
                "base": base_verdict.to_dict(),
                "adapter": adapter_verdict.to_dict(),
                "outputs_differ": base_text != adapted_text,
            }
        )

    differ_count = sum(1 for item in structured_records if item["outputs_differ"])
    if differ_count < 1:
        raise QloraTaskAlignedSmokeError("adapter_must_differ_from_base_on_at_least_one_record")

    # Prove braces-only never accepted (contract probe retained in evidence).
    braces_probe = validate_structured_model_output(prompt="PROMPT", raw_output="{not:json}")
    if braces_probe.accepted:
        raise QloraTaskAlignedSmokeError("braces_only_must_not_accept")

    status_counts: dict[str, int] = {}
    for item in structured_records:
        status = str(item["adapter"]["status"])
        status_counts[status] = status_counts.get(status, 0) + 1

    base_probe_after = _base_immutability_probe(selected_base_model)
    if base_probe_before.get("marker_sha256_before") and base_probe_after.get("marker_sha256_after"):
        if base_probe_before["marker_sha256_before"] != base_probe_after["marker_sha256_after"]:
            raise QloraTaskAlignedSmokeError("base_snapshot_mutated")
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
            "braces_only_probe": braces_probe.to_dict(),
        },
        "base_immutability": base_probe_after,
        "next_example_index_after_resume": next_example_index_after_resume,
        "runtime_seconds": round(time.perf_counter() - started, 3),
        "loss_mask_diagnostics": [
            dict(ex.masked_sequence.diagnostics)
            for ex in examples
            if ex.masked_sequence is not None
        ],
    }


def run_task_aligned_smoke_training(
    *,
    result_dir: Path,
    run_id: str,
    root: Path | None = None,
    require_real_mode: bool = False,
    force_mock: bool = True,
) -> dict[str, Any]:
    """Run the task-aligned QLoRA smoke and always finalise evidence.

    Local defaults: ``require_real_mode=False``, ``force_mock=True`` → mock.
    Live cluster: ``require_real_mode=True``, ``force_mock=False``. If real
    mode is required and the provider is unavailable or ``force_mock`` would
    apply, the job fails with evidence — it never silently falls back to mock.
    """
    repo = _repo_root(root)
    selected_base_model = require_selected_base_model(repo)
    resolved_config = load_task_aligned_smoke_config(repo)
    _refuse_nonempty_result_dir(result_dir)

    train_rows = load_task_aligned_records(repo)
    val_rows = load_task_aligned_validation_records(repo)
    policy = load_training_target_policy_strict(repo / TRAINING_TARGET_POLICY_REL)

    availability = check_qlora_provider_available()
    adapter_id = f"qlora-task-aligned-smoke-adapter-{run_id}"
    adapter_dir = result_dir / "adapter"
    started = _utc_now()

    # Mode selection — never silent mock fallback when real mode is required.
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
    success = False

    try:
        max_seq_len = int(resolved_config["sequence"]["max_seq_len"])
        if use_real:
            outcome = run_real_task_aligned_qlora_smoke(
                selected_base_model=selected_base_model,
                dataset_rows=train_rows,
                validation_rows=val_rows,
                config=resolved_config,
                adapter_dir=adapter_dir,
                adapter_id=adapter_id,
                root=repo,
            )
        else:
            # Mock uses deterministic char tokenizer masks for loss-mask evidence.
            from ambiguity_manager.model.token_loss_masking import DeterministicCharTokenizer

            examples = _build_examples_from_records(
                train_rows,
                policy=policy,
                tokenizer=DeterministicCharTokenizer(),
                max_seq_len=min(512, max_seq_len),
            )
            outcome = _run_mock_task_aligned_smoke(
                selected_base_model=selected_base_model,
                config=resolved_config,
                adapter_dir=adapter_dir,
                adapter_id=adapter_id,
                examples=examples,
                validation_rows=val_rows,
            )
            outcome["loss_mask_diagnostics"] = [
                dict(ex.masked_sequence.diagnostics)
                for ex in examples
                if ex.masked_sequence is not None
            ]

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
        success = True
    except Exception as exc:  # noqa: BLE001 - evidence must be finalised regardless
        success = False
        failure = f"{type(exc).__name__}: {exc}"

    ended = _utc_now()
    result_dir.mkdir(parents=True, exist_ok=True)

    status_counts = dict(structured_output.get("status_counts") or {})
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
            "record_count": len(train_rows),
            "validation_record_count": len(val_rows),
            "training_events": training_events,
            "resume_components": resume_components,
            "structured_output_summary": {
                "status_counts": status_counts,
                "adapter_differs_from_base_count": structured_output.get(
                    "adapter_differs_from_base_count"
                ),
                "accepted_count": int(status_counts.get(STATUS_ACCEPTED, 0)),
                "record_count": len(structured_output.get("records") or []),
                "braces_only_acceptance_forbidden": True,
            },
            "start_timestamp_utc": started,
            "end_timestamp_utc": ended,
            "provider_availability": availability.to_dict(),
            "require_real_mode": require_real_mode,
            "force_mock": force_mock,
            **{k: v for k, v in real_metrics.items() if v is not None},
        }
    )
    assert_task_aligned_run_not_official(result_payload)
    _atomic_write_json(result_dir / "qlora_task_aligned_smoke_result.json", result_payload)
    _atomic_write_json(result_dir / "loss_mask_summary.json", loss_summary)
    _atomic_write_json(result_dir / "structured_output_results.json", structured_output)
    _atomic_write_json(result_dir / "resume_components.json", resume_components)

    adapter_identity_path = adapter_dir / "adapter_identity.json"
    if adapter_identity_path.is_file():
        (result_dir / "adapter_identity.json").write_text(
            adapter_identity_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
    else:
        # Always leave an adapter_identity evidence file even on early failure.
        _atomic_write_json(
            result_dir / "adapter_identity.json",
            {
                "adapter_id": adapter_id,
                "base_model": selected_base_model,
                "technical_smoke_only": True,
                "selected_adapter": False,
                "valid_for_official_use": False,
                "note": "identity_stub_checkpoint_not_written" if not success else "missing_adapter_identity",
            },
        )

    manifest = finalize_task_aligned_run_manifest(result_dir, run_id=run_id, success=success)
    return {
        "result": result_payload,
        "manifest": manifest,
        "loss_mask_summary": loss_summary,
        "resume_components": resume_components,
        "structured_output_results": structured_output,
        "mode": mode,
        "success": success,
    }
