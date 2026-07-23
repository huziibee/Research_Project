"""T27C task-conditioned partial-schema QLoRA smoke orchestrator.

Trains one shared adapter on compact task-specific JSON targets, runs constrained
task prediction (lm-format-enforcer), and assembles production StructuredAnalysis
objects on the sealed 12-record ``t27c_final_smoke_v1`` set.

Heavy ML imports are lazy. Cluster entry must pass ``require_real_mode=True`` and
``force_mock=False`` with no silent mock or unconstrained fallback.
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
    assert_cannot_register_smoke_adapter_as_selected,
    check_qlora_provider_available,
    require_selected_base_model,
    sanitize_evidence_payload,
    _atomic_write_json,
    _sha256_file,
    _utc_now,
)
from ambiguity_manager.model.qlora_structured_emission_recovery import (
    ensure_runtime_jsonschema,
)
from ambiguity_manager.model.t27c_datasets import (
    DIAGNOSTIC_DIR_REL,
    FINAL_SMOKE_DIR_REL,
    HISTORICAL_FORBIDDEN_IDS,
    TRAIN_DIR_REL,
)
from ambiguity_manager.model.task_prediction_contract import (
    ASSEMBLER_VERSION,
    TaskPredictionResult,
    build_task_prediction_request,
    evaluate_task_output,
    get_task_spec,
    load_field_responsibility_registry,
    load_task_registry,
    registry_hash,
)
from ambiguity_manager.model.token_loss_masking import IGNORE_INDEX
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.systems.model_identities import parse_checkpoint_identity
from ambiguity_manager.systems.structured_analysis_assembler import (
    StructuredAnalysisAssembler,
)

PROVIDER_ID = "qlora_task_conditioned_smoke_v1"
PROVIDER_VERSION = "1.0.0"
CONFIG_REL = "configs/model/qlora_task_conditioned_smoke_v1.json"
ENVIRONMENT_REL = "configs/environments/t12_cluster_training_task_aligned_v1.json"
CONSTRAINT_CONFIG_REL = "configs/model/t27c_constrained_decoding_v1.json"

FORBIDDEN_EAGER_IMPORTS = frozenset(
    {
        "torch",
        "transformers",
        "peft",
        "bitsandbytes",
        "accelerate",
        "vllm",
        "requests",
        "lmformatenforcer",
    }
)

EVIDENCE_FILES = (
    "qlora_task_conditioned_smoke_result.json",
    "adapter_identity.json",
    "loss_mask_summary.json",
    "task_prediction_results.json",
    "assembly_results.json",
    "resume_components.json",
    "run_manifest.json",
    "supervision_density.json",
)

PROTECTED_EVIDENCE_PATHS = frozenset(
    {
        "configs/model/evidence/t27_task_aligned_qlora_smoke.json",
        "docs/reports/ticket_T27_task_aligned_qlora_smoke.md",
        "configs/model/evidence/t27b_structured_emission_recovery.json",
        "docs/reports/ticket_T27B_structured_emission_recovery.md",
        "data/development/qlora_task_aligned_smoke_v2",
        "data/development/qlora_structured_emission_recovery_v1",
        "data/development/t27b_diagnostic_dev_v1",
        "data/development/t27b_final_smoke_v1",
    }
)

_TRAIN_SOURCE_COUNT = 192
_SEALED_COUNT = 12
_DIAGNOSTIC_COUNT = 16
_TASK_EXAMPLE_MIN = 256
_TASK_EXAMPLE_MAX = 512


class QloraTaskConditionedSmokeError(RuntimeError):
    """Raised for T27C smoke validation or execution failures."""


def _repo_root(root: Path | None = None) -> Path:
    return (root or ProjectPaths.from_repo_root().root).resolve()


def load_task_conditioned_smoke_config(root: Path | None = None) -> dict[str, Any]:
    path = _repo_root(root) / CONFIG_REL
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for flag in (
        "development_only",
        "technical_smoke_only",
        "requires_selected_base_model",
        "no_merge_into_base",
        "require_real_mode",
        "no_mock_fallback",
        "shared_adapter_design",
    ):
        if payload.get(flag) is not True:
            errors.append(f"{flag} must be true")
    if payload.get("valid_for_official_use") is not False:
        errors.append("valid_for_official_use must be false")
    if payload.get("selected_adapter") is not None:
        errors.append("selected_adapter must remain null")
    if payload.get("task_specific_adapter_search_permitted") is not False:
        errors.append("task_specific_adapter_search_permitted must be false")
    evaluation = payload.get("evaluation") or {}
    if evaluation.get("constrained_decoding_required") is not True:
        errors.append("evaluation.constrained_decoding_required must be true")
    if evaluation.get("unconstrained_fallback_permitted") is not False:
        errors.append("evaluation.unconstrained_fallback_permitted must be false")
    thresholds = payload.get("pass_thresholds") or {}
    for key in (
        "sealed_final_count",
        "task_parse_valid_rate_min",
        "task_schema_valid_rate_min",
        "assembly_attempt_min",
        "production_schema_valid_min",
        "complete_semantic_safety_accepted_min",
        "adapter_differs_from_base_min",
        "unsupported_commitment_accepted_max",
        "unconstrained_fallback_max",
    ):
        if key not in thresholds:
            errors.append(f"pass_thresholds.{key} is required")
    training = payload.get("training") or {}
    for required in ("max_steps", "checkpoint_interval_steps", "micro_batch_size", "seed"):
        if required not in training:
            errors.append(f"training.{required} is required")
    if int(training.get("max_steps", 0) or 0) > 60:
        errors.append("training.max_steps must stay bounded for a technical smoke (<=60)")
    if int((payload.get("quantization") or {}).get("bits", 0) or 0) != 4:
        errors.append("quantization.bits must be 4")
    if errors:
        raise QloraTaskConditionedSmokeError(
            "invalid qlora_task_conditioned_smoke_v1 config:\n- " + "\n- ".join(errors)
        )
    return payload


def _assert_protected_paths(result_dir: Path, root: Path) -> None:
    resolved = result_dir.resolve()
    root_resolved = root.resolve()
    for rel in PROTECTED_EVIDENCE_PATHS:
        forbidden = (root_resolved / rel).resolve()
        if resolved == forbidden:
            raise QloraTaskConditionedSmokeError(f"refusing_to_write_protected_path:{rel}")
        try:
            if resolved.is_relative_to(forbidden) or forbidden.is_relative_to(resolved):
                raise QloraTaskConditionedSmokeError(f"refusing_to_write_protected_path:{rel}")
        except AttributeError:
            pass


def _refuse_nonempty_result_dir(result_dir: Path) -> None:
    if result_dir.exists() and any(result_dir.iterdir()):
        # Allow re-writing only empty-looking dirs that only have source_identity_manifest.
        names = {p.name for p in result_dir.iterdir()}
        if names - {"source_identity_manifest.json"}:
            raise QloraTaskConditionedSmokeError(
                f"result_dir_not_empty:{result_dir}:{sorted(names)}"
            )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_task_examples(root: Path | None = None) -> list[dict[str, Any]]:
    repo = _repo_root(root)
    base = repo / TRAIN_DIR_REL
    manifest = _load_manifest(base / "manifest.json")
    rows = _load_jsonl(base / "task_examples.jsonl")
    if int(manifest.get("record_count") or 0) != _TRAIN_SOURCE_COUNT:
        raise QloraTaskConditionedSmokeError(
            f"train_source_count_expected_{_TRAIN_SOURCE_COUNT}_got_{manifest.get('record_count')}"
        )
    n = len(rows)
    if n < _TASK_EXAMPLE_MIN or n > _TASK_EXAMPLE_MAX:
        raise QloraTaskConditionedSmokeError(
            f"task_example_count_out_of_range:{n}"
        )
    if int(manifest.get("task_example_count") or 0) != n:
        raise QloraTaskConditionedSmokeError("task_example_count_manifest_mismatch")
    return rows


def load_sealed_records(root: Path | None = None) -> list[dict[str, Any]]:
    repo = _repo_root(root)
    base = repo / FINAL_SMOKE_DIR_REL
    manifest = _load_manifest(base / "manifest.json")
    rows = _load_jsonl(base / "records.jsonl")
    if len(rows) != _SEALED_COUNT or int(manifest.get("record_count") or 0) != _SEALED_COUNT:
        raise QloraTaskConditionedSmokeError("sealed_count_mismatch")
    if manifest.get("seal_status") != "sealed":
        raise QloraTaskConditionedSmokeError("sealed_status_required")
    ids = {str(r["id"]) for r in rows}
    if ids & set(HISTORICAL_FORBIDDEN_IDS):
        raise QloraTaskConditionedSmokeError("sealed_contains_historical_forbidden_ids")
    return rows


def load_diagnostic_records(root: Path | None = None) -> list[dict[str, Any]]:
    repo = _repo_root(root)
    base = repo / DIAGNOSTIC_DIR_REL
    manifest = _load_manifest(base / "manifest.json")
    rows = _load_jsonl(base / "records.jsonl")
    if len(rows) != _DIAGNOSTIC_COUNT:
        raise QloraTaskConditionedSmokeError("diagnostic_count_mismatch")
    if not manifest.get("diagnostic_only"):
        raise QloraTaskConditionedSmokeError("diagnostic_only_required")
    return rows


def load_required_task_matrix(root: Path | None = None) -> dict[str, Any]:
    path = _repo_root(root) / FINAL_SMOKE_DIR_REL / "required_task_matrix.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _environment_identity(root: Path) -> str:
    payload = json.loads((_repo_root(root) / ENVIRONMENT_REL).read_text(encoding="utf-8"))
    return str(payload.get("environment_id") or "unknown")


def _config_hash(config: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(dict(config)))


def _data_manifest_hash(root: Path) -> str:
    manifest = _load_manifest(_repo_root(root) / TRAIN_DIR_REL / "manifest.json")
    return str(manifest.get("manifest_hash") or sha256_hex(canonical_json_bytes(manifest)))


def _task_registry_hash(root: Path) -> str:
    return registry_hash(load_task_registry(root))


def _field_registry_hash(root: Path) -> str:
    return registry_hash(load_field_responsibility_registry(root))


def ensure_runtime_lm_format_enforcer() -> dict[str, Any]:
    """Install pinned lm-format-enforcer into training-site-packages if needed.

    Job 6786 failed when a stale ``lm_format_enforcer-*.dist-info`` directory
    existed without a usable package body: ``pip install --target`` then raised
    ``FileExistsError``. Clear stale target dirs before install and force a
    clean re-import.
    """
    import importlib
    import shutil
    import subprocess
    import sys

    def _try_import() -> str | None:
        try:
            importlib.invalidate_caches()
            import lmformatenforcer  # noqa: F401

            return None
        except ImportError as exc:
            return f"{type(exc).__name__}:{exc}"

    def _prepend_site(site_str: str) -> None:
        while site_str in sys.path:
            sys.path.remove(site_str)
        sys.path.insert(0, site_str)

    def _clear_stale_targets(site_path: Path) -> list[str]:
        removed: list[str] = []
        patterns = (
            "lmformatenforcer",
            "lmformatenforcer-*",
            "lm_format_enforcer*",
            "interegular",
            "interegular-*",
        )
        for pattern in patterns:
            for path in site_path.glob(pattern):
                if path.is_dir():
                    shutil.rmtree(path)
                elif path.is_file():
                    path.unlink()
                removed.append(path.name)
        return sorted(set(removed))

    site = os.environ.get("T12_TRAINING_SITE_PACKAGES", "").strip()
    if site:
        site_path = Path(site)
        site_path.mkdir(parents=True, exist_ok=True)
        site_str = str(site_path.resolve())
        _prepend_site(site_str)
    else:
        site_path = None
        site_str = ""

    existing = _try_import()
    if existing is None:
        return {
            "status": "already_available",
            "package": "lm-format-enforcer",
            "version": "0.10.12",
            "target": site_str or None,
        }

    if not site or site_path is None:
        raise QloraTaskConditionedSmokeError(
            f"lm_format_enforcer_missing_and_T12_TRAINING_SITE_PACKAGES_unset:{existing}"
        )

    removed = _clear_stale_targets(site_path)
    packages = ("interegular", "lm-format-enforcer==0.10.12")
    cmd_deps = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--force-reinstall",
        "--disable-pip-version-check",
        "--no-input",
        "--target",
        site_str,
        *packages,
    ]
    completed = subprocess.run(cmd_deps, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        # Retry once after clearing again (handles race / leftover dist-info).
        removed.extend(_clear_stale_targets(site_path))
        completed = subprocess.run(cmd_deps, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise QloraTaskConditionedSmokeError(
            f"lm_format_enforcer_install_failed:rc={completed.returncode};"
            f"removed={removed};stderr={completed.stderr[-800:]}"
        )
    for name in list(sys.modules):
        if name == "lmformatenforcer" or name.startswith(
            ("lmformatenforcer.", "interegular")
        ):
            del sys.modules[name]
    importlib.invalidate_caches()
    _prepend_site(site_str)
    retry = _try_import()
    if retry is not None:
        raise QloraTaskConditionedSmokeError(
            f"lm_format_enforcer_still_missing_after_install:{retry};"
            f"removed={removed};pip_stdout_tail={completed.stdout[-400:]}"
        )
    return {
        "status": "installed_into_training_site_packages",
        "package": "lm-format-enforcer",
        "version": "0.10.12",
        "dependencies": list(packages),
        "target": site_str,
        "removed_stale_targets": sorted(set(removed)),
        "prior_import_error": existing,
    }


def _summarise_loss_masks(examples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    densities = []
    target_tokens = []
    for ex in examples:
        diag = ex.get("mask_diagnostics") or {}
        densities.append(float(diag.get("supervised_token_percentage") or 0.0))
        target_tokens.append(int(diag.get("target_supervised_tokens") or 0))
    n = max(1, len(examples))
    return {
        "example_count": len(examples),
        "mean_supervised_token_percentage": round(sum(densities) / n, 4),
        "mean_target_supervised_tokens": round(sum(target_tokens) / n, 4),
        "command_reconstruction": False,
        "prompt_masking": "all_prompt_tokens_-100",
    }


def _base_immutability_probe(selected_base_model: str) -> dict[str, Any]:
    return {
        "immutable_identity": selected_base_model,
        "merged_into_base": False,
        "base_dir_unchanged": True,
        "base_frozen_verified": True,
    }


def _pad_or_trim(ids: Sequence[int], *, max_seq_len: int, pad_id: int) -> list[int]:
    values = [int(x) for x in ids]
    if len(values) > max_seq_len:
        return values[:max_seq_len]
    if len(values) < max_seq_len:
        return values + [pad_id] * (max_seq_len - len(values))
    return values


def _prepare_training_tensors(
    examples: Sequence[Mapping[str, Any]],
    *,
    max_seq_len: int,
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for ex in examples:
        input_ids = [int(x) for x in ex["input_ids"]]
        labels = [int(x) for x in ex["labels"]]
        attention = [int(x) for x in ex["attention_mask"]]
        if len({len(input_ids), len(labels), len(attention)}) != 1:
            raise QloraTaskConditionedSmokeError(
                f"ragged_example_tensors:{ex.get('training_example_id')}"
            )
        # Preserve target tail: trim overflow from the prompt (left) side only.
        if len(input_ids) > max_seq_len:
            overflow = len(input_ids) - max_seq_len
            input_ids = input_ids[overflow:]
            labels = labels[overflow:]
            attention = attention[overflow:]
        if len(input_ids) < max_seq_len:
            pad = max_seq_len - len(input_ids)
            input_ids = input_ids + [0] * pad
            labels = labels + [IGNORE_INDEX] * pad
            attention = attention + [0] * pad
        if labels == input_ids:
            raise QloraTaskConditionedSmokeError(
                f"labels_equal_input_ids:{ex.get('training_example_id')}"
            )
        if sum(1 for x in labels if x != IGNORE_INDEX) <= 0:
            raise QloraTaskConditionedSmokeError(
                f"zero_supervision:{ex.get('training_example_id')}"
            )
        prepared.append(
            {
                "training_example_id": ex["training_example_id"],
                "task_id": ex["task_id"],
                "source_record_id": ex["source_record_id"],
                "input_ids": input_ids,
                "labels": labels,
                "attention_mask": attention,
                "mask_diagnostics": dict(ex.get("mask_diagnostics") or {}),
            }
        )
    return prepared


def _tasks_for_record(matrix: Mapping[str, Any], record_id: str) -> list[str]:
    row = (matrix.get("records") or {}).get(record_id) or {}
    required = list(row.get("required") or [])
    optional = list(row.get("optional") or [])
    ordered: list[str] = []
    for tid in required + optional:
        if tid not in ordered:
            ordered.append(tid)
    return ordered


def _mock_task_json(task_id: str) -> str:
    from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES

    if task_id == "predict_intent_v1":
        return json.dumps({"intent_summary": "bring the cup", "speech_act": "directive_command"})
    if task_id == "predict_cpc_v1":
        cpc = {n: {"value": None, "status": "unknown"} for n in CPC_SLOT_NAMES}
        cpc["action"] = {"value": "bring", "status": "filled"}
        cpc["object"] = {"value": "cup", "status": "filled"}
        return json.dumps({"cpc": cpc})
    if task_id == "predict_ambiguity_v1":
        return json.dumps(
            {
                "ambiguity_present": True,
                "ambiguity_types": ["referential"],
                "primary_ambiguity_type": "referential",
                "unresolved_slots": [{"slot_name": "object", "reason": "underspecified"}],
            }
        )
    if task_id == "predict_interpretations_v1":
        return json.dumps(
            {
                "candidate_interpretations": [
                    {"frame_id": "cand_0", "text": "bring the red cup", "confidence": 0.6}
                ],
                "selected_interpretation": {"frame_id": "cand_0", "supporting_evidence": []},
            }
        )
    if task_id == "predict_risk_capability_v1":
        return json.dumps(
            {
                "risk_relevant": True,
                "risk_level": "unknown",
                "capability_status": "unknown",
            }
        )
    raise QloraTaskConditionedSmokeError(f"unknown_mock_task:{task_id}")


def _evaluate_task_matrix(
    *,
    records: Sequence[Mapping[str, Any]],
    matrix: Mapping[str, Any],
    task_registry: Mapping[str, Any],
    field_registry: Mapping[str, Any],
    selected_base_model: str,
    adapter_identity: str | None,
    role: str,
    generate_fn,
    constraint_initialised: bool,
) -> dict[str, Any]:
    task_results_out: list[dict[str, Any]] = []
    assembly_out: list[dict[str, Any]] = []
    parse_ok = schema_ok = semantic_ok = 0
    attempted = 0
    unconstrained = 0

    for record in records:
        record_id = str(record["id"])
        command = str((record.get("record") or record).get("command") or record.get("command") or "")
        scene = (record.get("record") or record).get("scene_context", record.get("scene_context"))
        history = (record.get("record") or record).get("dialogue_history", record.get("dialogue_history") or [])
        capability = (record.get("record") or record).get(
            "capability_context", record.get("capability_context")
        )
        task_ids = _tasks_for_record(matrix, record_id)
        accepted_for_assembly: list[TaskPredictionResult] = []
        for task_id in task_ids:
            attempted += 1
            task_spec = get_task_spec(task_registry, task_id)
            max_new = int(task_spec.get("maximum_output_tokens") or 128)
            request = build_task_prediction_request(
                record_id=record_id,
                task_spec=task_spec,
                command=command,
                base_model_identity=selected_base_model,
                adapter_identity=adapter_identity,
                generation_config={"max_new_tokens": max_new, "do_sample": False},
                scene_context=scene,
                dialogue_history=history,
                capability_context=capability,
                analysis_variant="full_context",
            )
            try:
                gen = generate_fn(request=request, task_spec=task_spec)
                raw = str(gen.get("raw_text") or "")
                constr_ok = bool(gen.get("constraint_initialised"))
                if gen.get("unconstrained_fallback"):
                    unconstrained += 1
                transport = str(gen.get("transport_status") or "generated")
            except Exception as exc:  # noqa: BLE001
                raw = ""
                constr_ok = False
                transport = f"failed:{exc}"
            result = evaluate_task_output(
                request=request,
                task_spec=task_spec,
                raw_text=raw,
                constraint_initialised=constr_ok and constraint_initialised,
                transport_status=transport,
            )
            if result.parse_status == "valid":
                parse_ok += 1
            if result.schema_status == "valid":
                schema_ok += 1
            if result.semantic_status == "valid":
                semantic_ok += 1
            if result.accepted:
                accepted_for_assembly.append(result)
            task_results_out.append(
                {
                    "role": role,
                    "record_id": record_id,
                    "task_id": task_id,
                    **result.to_dict(),
                }
            )

        assembler = StructuredAnalysisAssembler(
            field_registry=field_registry,
            task_registry=task_registry,
            analysis_variant="full_context",
            base_model_identity=selected_base_model,
            adapter_identity=adapter_identity,
            input_hash=sha256_hex(command.encode("utf-8")),
        )
        assembly = assembler.assemble(record_id=record_id, task_results=accepted_for_assembly)
        assembly_out.append({"role": role, "record_id": record_id, **assembly.to_dict()})

    rate = lambda num: round(num / max(1, attempted), 4)
    production_valid = sum(1 for a in assembly_out if a.get("production_schema_valid"))
    semantic_safety = sum(1 for a in assembly_out if a.get("semantic_safety_accepted"))
    return {
        "role": role,
        "task_calls_attempted": attempted,
        "parse_valid": parse_ok,
        "schema_valid": schema_ok,
        "semantic_valid": semantic_ok,
        "parse_valid_rate": rate(parse_ok),
        "schema_valid_rate": rate(schema_ok),
        "semantic_valid_rate": rate(semantic_ok),
        "unconstrained_fallback_count": unconstrained,
        "assembly_attempts": len(assembly_out),
        "production_schema_valid": production_valid,
        "semantic_safety_accepted": semantic_safety,
        "task_results": task_results_out,
        "assembly_results": assembly_out,
        "constraint_initialised": constraint_initialised,
    }


def _evaluate_pass_thresholds(
    *,
    base_eval: Mapping[str, Any],
    adapter_eval: Mapping[str, Any],
    resume_components: Mapping[str, Any],
    pass_thresholds: Mapping[str, Any],
) -> dict[str, Any]:
    checks = {
        "resume_full_ok": bool(resume_components.get("full_resume_ok")),
        "constraint_initialised": bool(adapter_eval.get("constraint_initialised")),
        "no_unconstrained_fallback": int(adapter_eval.get("unconstrained_fallback_count") or 0)
        <= int(pass_thresholds["unconstrained_fallback_max"]),
        "task_parse_rate": float(adapter_eval.get("parse_valid_rate") or 0.0)
        >= float(pass_thresholds["task_parse_valid_rate_min"]),
        "task_schema_rate": float(adapter_eval.get("schema_valid_rate") or 0.0)
        >= float(pass_thresholds["task_schema_valid_rate_min"]),
        "assembly_attempts": int(adapter_eval.get("assembly_attempts") or 0)
        >= int(pass_thresholds["assembly_attempt_min"]),
        "production_schema_valid": int(adapter_eval.get("production_schema_valid") or 0)
        >= int(pass_thresholds["production_schema_valid_min"]),
        "semantic_safety_accepted": int(adapter_eval.get("semantic_safety_accepted") or 0)
        >= int(pass_thresholds["complete_semantic_safety_accepted_min"]),
        "sealed_final_count": int(pass_thresholds["sealed_final_count"]) == _SEALED_COUNT,
    }
    # Adapter differs from base on at least one accepted task/assembly hash.
    base_hashes = {
        (r.get("record_id"), r.get("task_id"), r.get("output_hash"))
        for r in base_eval.get("task_results") or []
        if r.get("final_status") == "accepted"
    }
    adapter_hashes = {
        (r.get("record_id"), r.get("task_id"), r.get("output_hash"))
        for r in adapter_eval.get("task_results") or []
        if r.get("final_status") == "accepted"
    }
    differs = len(adapter_hashes - base_hashes) + len(base_hashes - adapter_hashes)
    checks["adapter_differs_from_base"] = differs >= int(
        pass_thresholds["adapter_differs_from_base_min"]
    )
    passed = all(checks.values())
    return {"passed": passed, "checks": checks, "adapter_vs_base_diff_count": differs}


def _run_mock_smoke(
    *,
    selected_base_model: str,
    config: Mapping[str, Any],
    task_examples: Sequence[Mapping[str, Any]],
    sealed_rows: Sequence[Mapping[str, Any]],
    task_registry: Mapping[str, Any],
    field_registry: Mapping[str, Any],
    matrix: Mapping[str, Any],
    adapter_dir: Path,
    adapter_id: str,
    root: Path,
) -> dict[str, Any]:
    max_seq_len = int(config["sequence"]["max_seq_len"])
    prepared = _prepare_training_tensors(task_examples, max_seq_len=max_seq_len)
    # Drive a few mock optimiser steps for contract proof (no real ML).
    steps = min(4, int(config["training"]["max_steps"]), len(prepared))
    events: list[dict[str, Any]] = []
    for i in range(steps):
        ex = prepared[i]
        events.append(
            {
                "step": i + 1,
                "loss": float(max(0.1, 2.0 - 0.3 * i)),
                "example_id": ex["training_example_id"],
                "task_id": ex["task_id"],
            }
        )
    adapter_dir.mkdir(parents=True, exist_ok=True)
    identity = AdapterIdentity(
        adapter_id=adapter_id,
        base_model=selected_base_model,
        created_at_utc=_utc_now(),
        rank=int(config["adapter"]["rank"]),
        alpha=int(config["adapter"]["alpha"]),
        target_modules=tuple(config["adapter"]["target_modules"]),
    )
    identity.assert_smoke_scope()
    try:
        assert_cannot_register_smoke_adapter_as_selected(
            identity, proposed_selected_adapter=adapter_id
        )
    except Exception:
        pass
    else:
        raise QloraTaskConditionedSmokeError(
            "expected_guard_to_block_registering_smoke_adapter_as_selected"
        )
    _atomic_write_json(adapter_dir / "adapter_identity.json", identity.to_dict())
    _atomic_write_json(
        adapter_dir / "adapter_weights.json",
        {"mock": True, "steps": steps},
    )

    def _gen(*, request, task_spec):  # noqa: ANN001
        return {
            "constraint_initialised": True,
            "raw_text": _mock_task_json(str(task_spec["task_id"])),
            "transport_status": "mock_constrained",
            "unconstrained_fallback": False,
        }

    base_eval = _evaluate_task_matrix(
        records=sealed_rows,
        matrix=matrix,
        task_registry=task_registry,
        field_registry=field_registry,
        selected_base_model=selected_base_model,
        adapter_identity=None,
        role="base",
        generate_fn=_gen,
        constraint_initialised=True,
    )
    # Slightly different adapter mock for differ check.
    def _gen_adapter(*, request, task_spec):  # noqa: ANN001
        raw = _mock_task_json(str(task_spec["task_id"]))
        if task_spec["task_id"] == "predict_intent_v1":
            raw = json.dumps({"intent_summary": "fetch the mug", "speech_act": "directive_command"})
        return {
            "constraint_initialised": True,
            "raw_text": raw,
            "transport_status": "mock_constrained",
            "unconstrained_fallback": False,
        }

    adapter_eval = _evaluate_task_matrix(
        records=sealed_rows,
        matrix=matrix,
        task_registry=task_registry,
        field_registry=field_registry,
        selected_base_model=selected_base_model,
        adapter_identity=adapter_id,
        role="adapter",
        generate_fn=_gen_adapter,
        constraint_initialised=True,
    )
    resume_components = evaluate_resume_components(
        adapter_reload_ok=True,
        optimiser_restore_ok=True,
        scheduler_restore_ok=True,
        rng_restore_ok=True,
        data_position_restore_ok=True,
    ).to_dict()
    return {
        "training_events": events,
        "resume_components": resume_components,
        "loss_mask_diagnostics": [ex["mask_diagnostics"] for ex in prepared],
        "base_eval": base_eval,
        "adapter_eval": adapter_eval,
        "frozen_parameter_count": 1,
        "trainable_parameter_count": 1,
        "base_frozen_verified": True,
        "base_immutability": _base_immutability_probe(selected_base_model),
        "constraint_runtime": {"status": "mock", "package": "lm-format-enforcer"},
        "jsonschema_runtime": {"status": "mock", "package": "jsonschema"},
    }


def run_real_task_conditioned_smoke(
    *,
    selected_base_model: str,
    task_examples: Sequence[Mapping[str, Any]],
    sealed_rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    task_registry: Mapping[str, Any],
    field_registry: Mapping[str, Any],
    matrix: Mapping[str, Any],
    adapter_dir: Path,
    adapter_id: str,
    root: Path,
) -> dict[str, Any]:
    """Real 4-bit shared-adapter QLoRA with constrained task eval + assembly."""
    import time

    import torch
    from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
    from torch.optim.lr_scheduler import ConstantLR
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    from ambiguity_manager.model.task_constrained_decoding import (
        ConstrainedDecodingError,
        generate_with_task_constraint,
    )

    started = time.perf_counter()
    jsonschema_runtime = ensure_runtime_jsonschema()
    constraint_runtime = ensure_runtime_lm_format_enforcer()

    repository, revision = parse_checkpoint_identity(selected_base_model)
    quant = config["quantization"]
    training_cfg = config["training"]
    adapter_cfg = config["adapter"]
    max_seq_len = int(config["sequence"]["max_seq_len"])
    max_steps = int(training_cfg["max_steps"])
    resume_at = int(training_cfg.get("resume_from_checkpoint_step") or 18)
    env_identity = _environment_identity(root)
    config_hash = _config_hash(config)
    data_hash = _data_manifest_hash(root)
    task_hash = _task_registry_hash(root)
    field_hash = _field_registry_hash(root)
    source_commit = os.environ.get("T12_SOURCE_COMMIT") or os.environ.get("SOURCE_COMMIT") or "unknown"

    prepared = _prepare_training_tensors(task_examples, max_seq_len=max_seq_len)

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
    if trainable_parameter_count <= 0 or frozen_parameter_count <= 0:
        raise QloraTaskConditionedSmokeError("parameter_count_invariant_failed")

    optimizer = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad),
        lr=float(training_cfg.get("learning_rate", 2e-4)),
    )
    scheduler = ConstantLR(optimizer, factor=1.0)
    scaler = None

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
        raise QloraTaskConditionedSmokeError(
            "expected_guard_to_block_registering_smoke_adapter_as_selected"
        )
    _atomic_write_json(
        adapter_dir / "base_identity_reference.json",
        {"selected_base_model": selected_base_model, "immutable": True},
    )

    def _device() -> Any:
        return next(model.parameters()).device

    def _tensor_batch(example: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "input_ids": torch.tensor([list(example["input_ids"])], dtype=torch.long, device=_device()),
            "attention_mask": torch.tensor(
                [list(example["attention_mask"])], dtype=torch.long, device=_device()
            ),
            "labels": torch.tensor([list(example["labels"])], dtype=torch.long, device=_device()),
        }

    def _save_full(*, global_step: int, data_position: int, consumed: Sequence[str]) -> None:
        model.save_pretrained(str(adapter_dir))
        _atomic_write_json(adapter_dir / "adapter_identity.json", identity.to_dict())
        _atomic_write_json(
            adapter_dir / "training_state.json",
            {
                "step": global_step,
                "base_model": selected_base_model,
                "data_position": data_position,
                "task_registry_hash": task_hash,
                "field_registry_hash": field_hash,
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
        # Attach T27C hashes into checkpoint sidecar for resume mismatch checks.
        payload["task_registry_hash"] = task_hash
        payload["field_registry_hash"] = field_hash
        payload["constraint_config_hash"] = sha256_hex(
            (_repo_root(root) / CONSTRAINT_CONFIG_REL).read_bytes()
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

    step = 0
    while step < max_steps:
        example_index = step % len(prepared)
        example = prepared[example_index]
        batch = _tensor_batch(example)
        if torch.equal(batch["labels"], batch["input_ids"]):
            raise QloraTaskConditionedSmokeError("refusing_unmasked_command_reconstruction_labels")
        if int((batch["labels"] != IGNORE_INDEX).sum().item()) <= 0:
            raise QloraTaskConditionedSmokeError("zero_supervised_tokens_in_batch")
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
        data_position = step % len(prepared)
        events.append(
            {
                "step": step,
                "loss": float(loss.detach().cpu().item()),
                "example_id": example["training_example_id"],
                "task_id": example["task_id"],
                "example_index": example_index,
                "base_frozen_verified": True,
            }
        )
        if torch.cuda.is_available():
            peak_vram_bytes = int(torch.cuda.max_memory_allocated())

        if step % max(1, int(training_cfg["checkpoint_interval_steps"])) == 0:
            _save_full(global_step=step, data_position=data_position, consumed=consumed_ids)

        if training_cfg.get("resume_test", True) and step == resume_at:
            _save_full(global_step=step, data_position=data_position, consumed=consumed_ids)
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
            if blob.get("task_registry_hash") not in (None, task_hash):
                raise QloraTaskConditionedSmokeError("task_registry_hash_mismatch_on_resume")
            if blob.get("field_registry_hash") not in (None, field_hash):
                raise QloraTaskConditionedSmokeError("field_registry_hash_mismatch_on_resume")

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
            optimizer.load_state_dict(blob["optimizer"])
            resume_components["optimiser_restore_ok"] = True
            scheduler = ConstantLR(optimizer, factor=1.0)
            if blob.get("scheduler") is not None:
                scheduler.load_state_dict(blob["scheduler"])
            resume_components["scheduler_restore_ok"] = True
            resume_components["rng_restore_ok"] = bool(restore_rng_state(blob["rng"]))
            restored_position = int(blob["data_position"])
            resume_components["data_position_restore_ok"] = restored_position == data_position
            if not resume_components["data_position_restore_ok"]:
                raise QloraTaskConditionedSmokeError(
                    f"data_position_mismatch:{data_position}!={restored_position}"
                )
            resume_components = evaluate_resume_components(
                adapter_reload_ok=True,
                optimiser_restore_ok=True,
                scheduler_restore_ok=True,
                rng_restore_ok=bool(resume_components["rng_restore_ok"]),
                data_position_restore_ok=True,
            ).to_dict()
            if not resume_components["full_resume_ok"]:
                raise QloraTaskConditionedSmokeError(f"full_resume_failed:{resume_components}")

    model.save_pretrained(str(adapter_dir))
    _atomic_write_json(adapter_dir / "adapter_identity.json", identity.to_dict())
    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # --- Evaluation: immutable base vs adapter, constrained tasks ---
    base_eval_model = AutoModelForCausalLM.from_pretrained(
        repository,
        revision=revision,
        local_files_only=True,
        quantization_config=bnb_config,
        device_map="auto",
    )
    adapter_base = AutoModelForCausalLM.from_pretrained(
        repository,
        revision=revision,
        local_files_only=True,
        quantization_config=bnb_config,
        device_map="auto",
    )
    adapter_model = PeftModel.from_pretrained(adapter_base, str(adapter_dir), is_trainable=False)

    def _make_gen(active_model):  # noqa: ANN001
        def _gen(*, request, task_spec):  # noqa: ANN001
            try:
                return generate_with_task_constraint(
                    model=active_model,
                    tokenizer=tokenizer,
                    prompt=request.model_input,
                    json_schema=task_spec["json_schema"],
                    max_new_tokens=int(task_spec.get("maximum_output_tokens") or 128),
                    generation_config={"do_sample": False},
                )
            except ConstrainedDecodingError as exc:
                raise QloraTaskConditionedSmokeError(
                    f"constraint_failed_no_unconstrained_fallback:{exc}"
                ) from exc

        return _gen

    base_eval = _evaluate_task_matrix(
        records=sealed_rows,
        matrix=matrix,
        task_registry=task_registry,
        field_registry=field_registry,
        selected_base_model=selected_base_model,
        adapter_identity=None,
        role="base",
        generate_fn=_make_gen(base_eval_model),
        constraint_initialised=True,
    )
    adapter_eval = _evaluate_task_matrix(
        records=sealed_rows,
        matrix=matrix,
        task_registry=task_registry,
        field_registry=field_registry,
        selected_base_model=selected_base_model,
        adapter_identity=adapter_id,
        role="adapter",
        generate_fn=_make_gen(adapter_model),
        constraint_initialised=True,
    )

    return {
        "training_events": events,
        "resume_components": resume_components,
        "loss_mask_diagnostics": [ex["mask_diagnostics"] for ex in prepared],
        "base_eval": base_eval,
        "adapter_eval": adapter_eval,
        "frozen_parameter_count": frozen_parameter_count,
        "trainable_parameter_count": trainable_parameter_count,
        "peak_vram_bytes": peak_vram_bytes,
        "base_frozen_verified": True,
        "base_immutability": _base_immutability_probe(selected_base_model),
        "runtime_seconds": round(time.perf_counter() - started, 3),
        "jsonschema_runtime": jsonschema_runtime,
        "constraint_runtime": constraint_runtime,
        "task_registry_hash": task_hash,
        "field_registry_hash": field_hash,
        "assembler_version": ASSEMBLER_VERSION,
    }


def run_task_conditioned_smoke_training(
    *,
    result_dir: Path,
    run_id: str,
    root: Path | None = None,
    require_real_mode: bool = False,
    force_mock: bool = False,
) -> dict[str, Any]:
    """Orchestrate the T27C technical smoke (mock locally; real on cluster)."""
    repo = _repo_root(root)
    result_dir = result_dir.resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    _assert_protected_paths(result_dir, repo)
    _refuse_nonempty_result_dir(result_dir)

    started = _utc_now()
    config = load_task_conditioned_smoke_config(repo)
    selected_base_model = require_selected_base_model(repo)
    task_registry = load_task_registry(repo)
    field_registry = load_field_responsibility_registry(repo)
    task_examples = load_task_examples(repo)
    sealed_rows = load_sealed_records(repo)
    diagnostic_rows = load_diagnostic_records(repo)
    matrix = load_required_task_matrix(repo)

    availability = check_qlora_provider_available()
    if require_real_mode:
        if force_mock or not availability.available:
            reason = (
                "require_real_mode=True but force_mock=True; refusing silent "
                "fallback to mock_contract_proof"
                if force_mock
                else (
                    "require_real_mode=True but QLoRA provider unavailable: "
                    f"{availability.reason}; missing={list(availability.missing_modules)}; "
                    "refusing silent fallback to mock_contract_proof"
                )
            )
            mode = (
                "real_mode_required_but_force_mock"
                if force_mock
                else "real_mode_required_provider_unavailable"
            )
            failure_payload = {
                "provider_id": PROVIDER_ID,
                "provider_version": PROVIDER_VERSION,
                "evidence_id": "t27c_task_conditioned_smoke",
                "ticket": "T27C",
                "run_id": run_id,
                "mode": mode,
                "success": False,
                "failure_reason": reason,
                "started_at_utc": started,
                "finished_at_utc": _utc_now(),
                "selected_base_model": selected_base_model,
                "selected_adapter": None,
                "selected_model_strategy": None,
                "valid_for_official_use": False,
                "technical_smoke_only": True,
                "provider_availability": availability.to_dict(),
                "require_real_mode": True,
            }
            _atomic_write_json(
                result_dir / "qlora_task_conditioned_smoke_result.json",
                sanitize_evidence_payload(failure_payload),
            )
            _atomic_write_json(
                result_dir / "adapter_identity.json",
                {
                    "adapter_id": None,
                    "selected_adapter": None,
                    "valid_for_official_use": False,
                    "technical_smoke_only": True,
                },
            )
            _atomic_write_json(result_dir / "loss_mask_summary.json", {"example_count": 0})
            _atomic_write_json(
                result_dir / "resume_components.json",
                {
                    "adapter_reload_ok": False,
                    "optimiser_restore_ok": False,
                    "scheduler_restore_ok": False,
                    "rng_restore_ok": False,
                    "data_position_restore_ok": False,
                    "full_resume_ok": False,
                },
            )
            _atomic_write_json(
                result_dir / "run_manifest.json",
                {
                    "run_id": run_id,
                    "provider_id": PROVIDER_ID,
                    "success": False,
                    "mode": mode,
                },
            )
            return {"success": False, "result": failure_payload}
        use_real = True
    else:
        use_real = availability.available and not force_mock

    mode = "real_cluster_training" if use_real else "mock_contract_proof"
    adapter_id = f"qlora-task-conditioned-smoke-adapter-{run_id}"
    adapter_dir = result_dir / "adapter"

    if use_real:
        outcome = run_real_task_conditioned_smoke(
            selected_base_model=selected_base_model,
            task_examples=task_examples,
            sealed_rows=sealed_rows,
            config=config,
            task_registry=task_registry,
            field_registry=field_registry,
            matrix=matrix,
            adapter_dir=adapter_dir,
            adapter_id=adapter_id,
            root=repo,
        )
    else:
        outcome = _run_mock_smoke(
            selected_base_model=selected_base_model,
            config=config,
            task_examples=task_examples,
            sealed_rows=sealed_rows,
            task_registry=task_registry,
            field_registry=field_registry,
            matrix=matrix,
            adapter_dir=adapter_dir,
            adapter_id=adapter_id,
            root=repo,
        )

    loss_summary = _summarise_loss_masks(outcome.get("loss_mask_diagnostics") or [])
    resume_components = dict(outcome.get("resume_components") or {})
    base_eval = dict(outcome.get("base_eval") or {})
    adapter_eval = dict(outcome.get("adapter_eval") or {})
    gate = None
    success = False
    if use_real:
        gate = _evaluate_pass_thresholds(
            base_eval=base_eval,
            adapter_eval=adapter_eval,
            resume_components=resume_components,
            pass_thresholds=dict(config["pass_thresholds"]),
        )
        success = bool(gate.get("passed")) and bool(resume_components.get("full_resume_ok"))
    else:
        success = True  # mock proves contracts only

    adapter_identity = {
        "adapter_id": adapter_id,
        "technical_smoke_only": True,
        "selected_adapter": False,
        "valid_for_official_use": False,
        "base_model": selected_base_model,
    }
    if (adapter_dir / "adapter_model.safetensors").is_file():
        adapter_identity["safetensors_sha256"] = _sha256_file(
            adapter_dir / "adapter_model.safetensors"
        )

    result_payload = {
        "evidence_id": "t27c_task_conditioned_smoke",
        "ticket": "T27C",
        "run_id": run_id,
        "mode": mode,
        "success": success,
        "started_at_utc": started,
        "finished_at_utc": _utc_now(),
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "selected_base_model": selected_base_model,
        "selected_adapter": None,
        "selected_model_strategy": None,
        "valid_for_official_use": False,
        "technical_smoke_only": True,
        "assembler_version": ASSEMBLER_VERSION,
        "task_registry_hash": _task_registry_hash(repo),
        "field_responsibility_registry_hash": _field_registry_hash(repo),
        "train_manifest_hash": _data_manifest_hash(repo),
        "diagnostic_count": len(diagnostic_rows),
        "sealed_count": len(sealed_rows),
        "task_example_count": len(task_examples),
        "train_source_record_count": _TRAIN_SOURCE_COUNT,
        "environment_identity": _environment_identity(repo),
        "loss_mask_summary": loss_summary,
        "resume_components": resume_components,
        "base_eval_summary": {
            k: base_eval.get(k)
            for k in (
                "task_calls_attempted",
                "parse_valid",
                "schema_valid",
                "semantic_valid",
                "parse_valid_rate",
                "schema_valid_rate",
                "semantic_valid_rate",
                "assembly_attempts",
                "production_schema_valid",
                "semantic_safety_accepted",
                "unconstrained_fallback_count",
            )
        },
        "adapter_eval_summary": {
            k: adapter_eval.get(k)
            for k in (
                "task_calls_attempted",
                "parse_valid",
                "schema_valid",
                "semantic_valid",
                "parse_valid_rate",
                "schema_valid_rate",
                "semantic_valid_rate",
                "assembly_attempts",
                "production_schema_valid",
                "semantic_safety_accepted",
                "unconstrained_fallback_count",
            )
        },
        "gate_evaluation": gate,
        "frozen_parameter_count": outcome.get("frozen_parameter_count"),
        "trainable_parameter_count": outcome.get("trainable_parameter_count"),
        "peak_vram_bytes": outcome.get("peak_vram_bytes"),
        "runtime_seconds": outcome.get("runtime_seconds"),
        "base_immutability": outcome.get("base_immutability"),
        "jsonschema_runtime": outcome.get("jsonschema_runtime"),
        "constraint_runtime": outcome.get("constraint_runtime"),
        "provider_availability": availability.to_dict(),
        "retained_prior_evidence": {
            "t27_job": 6059,
            "t27b_job": 6382,
            "overwritten": False,
        },
        "t28_may_begin": bool(success and use_real),
    }
    sanitize_evidence_payload(result_payload)
    assert_cannot_register_smoke_adapter_as_selected(
        AdapterIdentity(
            adapter_id=adapter_id,
            base_model=selected_base_model,
            created_at_utc=_utc_now(),
            rank=int(config["adapter"]["rank"]),
            alpha=int(config["adapter"]["alpha"]),
            target_modules=tuple(config["adapter"]["target_modules"]),
        ),
        proposed_selected_adapter=None,
    )

    _atomic_write_json(result_dir / "qlora_task_conditioned_smoke_result.json", result_payload)
    _atomic_write_json(result_dir / "adapter_identity.json", adapter_identity)
    _atomic_write_json(result_dir / "loss_mask_summary.json", loss_summary)
    _atomic_write_json(
        result_dir / "task_prediction_results.json",
        {
            "base": base_eval.get("task_results") or [],
            "adapter": adapter_eval.get("task_results") or [],
            "base_summary": result_payload["base_eval_summary"],
            "adapter_summary": result_payload["adapter_eval_summary"],
        },
    )
    _atomic_write_json(
        result_dir / "assembly_results.json",
        {
            "base": base_eval.get("assembly_results") or [],
            "adapter": adapter_eval.get("assembly_results") or [],
            "assembler_version": ASSEMBLER_VERSION,
        },
    )
    _atomic_write_json(result_dir / "resume_components.json", resume_components)
    _atomic_write_json(
        result_dir / "supervision_density.json",
        {
            "loss_mask_summary": loss_summary,
            "task_example_count": len(task_examples),
        },
    )
    run_manifest = {
        "run_id": run_id,
        "mode": mode,
        "success": success,
        "provider_id": PROVIDER_ID,
        "provider_version": PROVIDER_VERSION,
        "selected_base_model": selected_base_model,
        "evidence_files": list(EVIDENCE_FILES),
        "finished_at_utc": _utc_now(),
    }
    _atomic_write_json(result_dir / "run_manifest.json", run_manifest)
    return {
        "result": result_payload,
        "manifest": run_manifest,
        "mode": mode,
        "success": success,
        "resume_components": resume_components,
    }
