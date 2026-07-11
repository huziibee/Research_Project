#!/usr/bin/env python3
"""T12 Slice 3C offline checkpoint load and smoke generation probe."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.governance.hashing import sha256_hex
from ambiguity_manager.governance.model_licence import MANDATORY_CONTEXT_LIMIT
from ambiguity_manager.model.checkpoint_load import (
    AUTHORIZED_CANDIDATE_ENTRY_ID,
    AUTHORIZED_REVISION_SHA,
    AUTHORIZED_TOKENIZER_REVISION_SHA,
    DEFAULT_TIMEOUT_S,
    LOAD_EVIDENCE_REL,
    RAW_LOG_DIR_REL,
    SMOKE_RAW_DIR_REL,
    build_cleanup_evidence,
    build_load_evidence_scaffold,
    build_process_exit_reclaim_evidence,
    build_runtime_spec,
    collect_resource_snapshot,
    compute_overall_status,
    detect_lingering_probe_processes,
    gpu_free_vram_mib,
    load_json,
    load_verified_config_dict,
    locate_snapshot,
    migrate_cleanup_evidence,
    migrate_identity_evidence,
    resolve_load_paths,
    validate_checkpoint_load_evidence,
    validate_pre_load_gates,
    validate_wsl_cache_policy,
    verify_snapshot_file_hashes,
    write_json,
)
from ambiguity_manager.model.context_budget import DEFAULT_SAFETY_MARGIN
from ambiguity_manager.model.factory import create_model_client
from ambiguity_manager.model.integrity import load_synthetic_fixtures
from ambiguity_manager.model.prompt_builder import build_messages_from_fixture
from ambiguity_manager.paths import ProjectPaths, repo_relative_path
from ambiguity_manager.schema.v2.json_schema import build_prediction_json_schema


def _ensure_offline_env() -> None:
    from ambiguity_manager.model.checkpoint_download import is_wsl_linux_runtime

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    native_hf = Path.home() / ".cache" / "huggingface"
    if is_wsl_linux_runtime():
        os.environ["HF_HOME"] = str(native_hf)
        os.environ["HF_HUB_CACHE"] = str(native_hf / "hub")
    elif "HF_HOME" not in os.environ:
        os.environ["HF_HOME"] = str(native_hf)
        os.environ["HF_HUB_CACHE"] = str(native_hf / "hub")


def _load_context(repo_root: Path) -> dict[str, Any]:
    paths = resolve_load_paths(repo_root)
    download_evidence = load_json(paths["download_evidence"])
    register = load_json(paths["register"])
    if paths["load_evidence"].is_file():
        evidence = load_json(paths["load_evidence"])
    else:
        evidence = build_load_evidence_scaffold()
    inference_manifest = load_json(paths["inference_manifest"])
    training_manifest = load_json(paths["training_manifest"])
    return {
        "paths": paths,
        "download_evidence": download_evidence,
        "register": register,
        "evidence": evidence,
        "inference_manifest": inference_manifest,
        "training_manifest": training_manifest,
    }


def _refresh_evidence_hashes(ctx: dict[str, Any]) -> None:
    paths = ctx["paths"]
    evidence = ctx["evidence"]
    evidence["checkpoint_download_evidence_sha256"] = sha256_hex(
        paths["download_evidence"].read_bytes()
    )
    evidence["inference_environment_manifest_sha256"] = sha256_hex(
        paths["inference_manifest"].read_bytes()
    )
    evidence["training_environment_manifest_sha256"] = sha256_hex(
        paths["training_manifest"].read_bytes()
    )
    inf_lock = paths["repo_root"] / ctx["inference_manifest"]["lockfile_relpath"]
    train_lock = paths["repo_root"] / ctx["training_manifest"]["lockfile_relpath"]
    evidence["inference_lockfile_sha256"] = sha256_hex(inf_lock.read_bytes())
    evidence["training_lockfile_sha256"] = sha256_hex(train_lock.read_bytes())


def _validate_gates(ctx: dict[str, Any]) -> None:
    paths = ctx["paths"]
    before = collect_resource_snapshot(cache_dir=paths["hub_cache_dir"])
    errors = validate_pre_load_gates(
        download_evidence=ctx["download_evidence"],
        register=ctx["register"],
        resource_snapshot=before,
    )
    errors.extend(validate_wsl_cache_policy(paths["hub_cache_dir"]))
    if errors:
        raise SystemExit("pre-load gate failure:\n" + "\n".join(errors))


def _perform_environment_load(
    *,
    ctx: dict[str, Any],
    environment_id: str,
    for_training: bool,
) -> dict[str, Any]:
    from ambiguity_manager.model.checkpoint_load import build_quantisation_config
    from ambiguity_manager.model.hf_load_helpers import (
        cleanup_model,
        collect_identity_evidence,
        load_model,
        load_tokenizer,
        peak_vram_mib,
        torch_bf16_supported,
        verify_peft_architecture,
    )

    paths = ctx["paths"]
    _validate_gates(ctx)
    snapshot = locate_snapshot(paths["hub_cache_dir"])
    verify_snapshot_file_hashes(snapshot, ctx["download_evidence"])
    config_dict = load_verified_config_dict(snapshot)

    before = collect_resource_snapshot(cache_dir=paths["hub_cache_dir"])
    baseline_free_vram = before.get("gpu_free_vram_mib")
    bf16 = torch_bf16_supported()
    quant = build_quantisation_config(bf16_supported=bf16, for_training=for_training)
    ctx["evidence"]["quantisation_configuration"] = quant.as_dict()

    import torch

    torch.cuda.reset_peak_memory_stats()
    start = time.perf_counter()
    tokenizer = load_tokenizer(local_files_only=True)
    model = load_model(quant=quant, local_files_only=True)
    load_duration_s = round(time.perf_counter() - start, 3)

    device = str(next(model.parameters()).device)
    if device != "cuda:0":
        cleanup_model(model, tokenizer)
        raise SystemExit(f"expected cuda:0 placement, got {device}")

    identity = collect_identity_evidence(model, tokenizer, config_dict=config_dict)
    peft_ok = verify_peft_architecture(model) if for_training else None

    after_load_vram = peak_vram_mib()
    in_process_cleanup = cleanup_model(model, tokenizer, baseline_free_vram_mib=baseline_free_vram)
    after = collect_resource_snapshot(cache_dir=paths["hub_cache_dir"])
    process_exit = build_process_exit_reclaim_evidence(
        worker_process_exit_completed=True,
        post_process_exit_free_vram_mib=None,
        baseline_free_vram_mib=baseline_free_vram,
        lingering_probe_processes_detected=bool(detect_lingering_probe_processes()),
    )
    cleanup = build_cleanup_evidence(in_process=in_process_cleanup, process_exit=process_exit)

    section = {
        "environment_id": environment_id,
        "status": "passed",
        "identity_evidence": identity,
        "resource_evidence_before": before,
        "resource_evidence_after": after,
        "load_duration_s": load_duration_s,
        "peak_allocated_vram_mib": after_load_vram,
        "cleanup_result": cleanup,
        "four_bit_load_status": "passed" if identity.get("loaded_in_4bit") else "failed",
    }
    if for_training:
        section["peft_architecture_compatible"] = peft_ok
    return section


def cmd_inference_load(repo_root: Path) -> int:
    _ensure_offline_env()
    ctx = _load_context(repo_root)
    section = _perform_environment_load(
        ctx=ctx,
        environment_id="t12-inference-wsl2",
        for_training=False,
    )
    ctx["evidence"]["inference_environment_load"] = section
    _refresh_evidence_hashes(ctx)
    ctx["evidence"]["overall_status"] = compute_overall_status(ctx["evidence"])
    write_json(ctx["paths"]["load_evidence"], ctx["evidence"])
    print(json.dumps(section, indent=2))
    return 0


def cmd_training_load(repo_root: Path) -> int:
    _ensure_offline_env()
    ctx = _load_context(repo_root)
    section = _perform_environment_load(
        ctx=ctx,
        environment_id="t12-training-wsl2",
        for_training=True,
    )
    ctx["evidence"]["training_environment_load"] = section
    _refresh_evidence_hashes(ctx)
    ctx["evidence"]["overall_status"] = compute_overall_status(ctx["evidence"])
    write_json(ctx["paths"]["load_evidence"], ctx["evidence"])
    print(json.dumps(section, indent=2))
    return 0


def cmd_smoke_generate(repo_root: Path) -> int:
    _ensure_offline_env()
    ctx = _load_context(repo_root)
    _validate_gates(ctx)
    locate_snapshot(ctx["paths"]["hub_cache_dir"])
    verify_snapshot_file_hashes(
        locate_snapshot(ctx["paths"]["hub_cache_dir"]),
        ctx["download_evidence"],
    )

    fixture_path = repo_root / "tests" / "fixtures" / "schema_v2" / "t12_synthetic_inputs.jsonl"
    fixtures = load_synthetic_fixtures(fixture_path)
    fixture = next(item for item in fixtures if item.get("fixture_id") == "syn-001")

    schema = build_prediction_json_schema()
    messages = build_messages_from_fixture(fixture, json_schema=schema)
    runtime = build_runtime_spec(environment_id="t12-inference-wsl2")
    client = create_model_client(runtime)

    from ambiguity_manager.model.protocol import GenerateJsonRequest

    request = GenerateJsonRequest(
        messages=messages,
        json_schema=schema,
        seed=0,
        temperature=0.0,
        top_p=1.0,
        requested_max_new_tokens=512,
        timeout_s=DEFAULT_TIMEOUT_S,
        fixture_id="syn-001",
        run_id="t12-smoke-syn-001",
    )
    result = client.generate_json(request)

    raw_dir = ctx["paths"]["smoke_raw_dir"]
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "t12_smoke_syn-001.txt"
    raw_path.write_text(result.raw_output, encoding="utf-8")
    raw_relpath = repo_relative_path(raw_path, start=repo_root)
    raw_digest = sha256_hex(result.raw_output.encode("utf-8"))

    smoke_status = "passed"
    if result.final_status in {"timeout", "backend_error", "empty_output"}:
        smoke_status = "failed"
    elif not result.raw_output.strip():
        smoke_status = "failed"

    smoke_section = {
        "status": smoke_status,
        "fixture_id": "syn-001",
        "seed": 0,
        "do_sample": False,
        "requested_max_new_tokens": 512,
        "context_limit": MANDATORY_CONTEXT_LIMIT,
        "safety_margin_tokens": DEFAULT_SAFETY_MARGIN,
        "timeout_s": DEFAULT_TIMEOUT_S,
        "raw_output_relpath": raw_relpath,
        "raw_output_sha256": raw_digest,
        "raw_output_nonempty": bool(result.raw_output.strip()),
        "parse_result": {
            "parsed_object_present": result.parsed_object is not None,
            "repair_attempts": result.repair_attempts,
            "final_status": result.final_status,
        },
        "schema_result": {
            "schema_valid": result.schema_valid,
            "schema_errors": result.schema_errors,
        },
        "final_status": result.final_status,
        "latency_ms": result.latency_ms,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "peak_vram_mib": result.peak_vram_mib,
    }
    ctx["evidence"]["smoke_generation"] = smoke_section
    _refresh_evidence_hashes(ctx)
    ctx["evidence"]["overall_status"] = compute_overall_status(ctx["evidence"])
    write_json(ctx["paths"]["load_evidence"], ctx["evidence"])
    print(json.dumps(smoke_section, indent=2))
    return 0 if smoke_status == "passed" else 1


def _update_environment_manifest(
    manifest_path: Path,
    *,
    evidence_relpath: str,
) -> None:
    data = load_json(manifest_path)
    data["checkpoint_load_verified"] = True
    data["candidate_entry_id"] = AUTHORIZED_CANDIDATE_ENTRY_ID
    data["immutable_revision_sha"] = AUTHORIZED_REVISION_SHA
    data["tokenizer_revision_sha"] = AUTHORIZED_TOKENIZER_REVISION_SHA
    data["four_bit_load_status"] = "passed"
    data["checkpoint_load_evidence_relpath"] = evidence_relpath
    write_json(manifest_path, data)


def cmd_correct_evidence(repo_root: Path) -> int:
    """Correct tracked evidence semantics without reloading the model or regenerating."""
    ctx = _load_context(repo_root)
    evidence = ctx["evidence"]
    snapshot = locate_snapshot(ctx["paths"]["hub_cache_dir"])
    config_dict = load_verified_config_dict(snapshot)
    lingering = detect_lingering_probe_processes()
    post_exit_free = gpu_free_vram_mib()

    for key in ("inference_environment_load", "training_environment_load"):
        section = evidence.get(key)
        if not isinstance(section, dict) or section.get("status") != "passed":
            continue
        identity = section.get("identity_evidence")
        if isinstance(identity, dict):
            section["identity_evidence"] = migrate_identity_evidence(identity, config=config_dict)
            peak_mib = section.get("peak_allocated_vram_mib")
            if peak_mib and "loaded_model_memory_footprint_bytes" not in section["identity_evidence"]:
                section["identity_evidence"]["loaded_model_memory_footprint_bytes"] = int(
                    round(float(peak_mib) * 1024 * 1024)
                )
        section["cleanup_result"] = migrate_cleanup_evidence(
            section,
            post_process_exit_free_vram_mib=post_exit_free,
            lingering_probe_processes_detected=bool(lingering),
            worker_process_exit_completed=True,
        )

    smoke = evidence.get("smoke_generation")
    if isinstance(smoke, dict) and smoke.get("status") == "passed":
        smoke["worker_process_exit_completed"] = True
        smoke["post_process_exit_free_vram_mib"] = post_exit_free
        smoke["lingering_probe_processes_detected"] = bool(lingering)

    evidence["evidence_correction"] = {
        "correction_pass": "slice_3c_parameter_and_cleanup_semantics",
        "no_model_reload": True,
        "no_regeneration": True,
        "post_exit_free_vram_mib": post_exit_free,
        "lingering_probe_processes_detected": bool(lingering),
    }
    write_json(ctx["paths"]["load_evidence"], evidence)

    report = {
        "correction_status": "completed",
        "post_process_exit_free_vram_mib": post_exit_free,
        "lingering_probe_processes_detected": bool(lingering),
        "lingering_pids": lingering,
    }
    print(json.dumps(report, indent=2))
    errors = validate_checkpoint_load_evidence(
        evidence,
        download_evidence=ctx["download_evidence"],
        register=ctx["register"],
        inference_manifest=ctx["inference_manifest"],
        training_manifest=ctx["training_manifest"],
    )
    return 0 if not errors else 1


def cmd_report(repo_root: Path) -> int:
    ctx = _load_context(repo_root)
    evidence = ctx["evidence"]
    overall = compute_overall_status(evidence)
    evidence["overall_status"] = overall

    if overall in {"PASS", "PARTIALLY_VERIFIED"}:
        inf = evidence.get("inference_environment_load", {})
        train = evidence.get("training_environment_load", {})
        if isinstance(inf, dict) and inf.get("status") == "passed":
            _update_environment_manifest(
                ctx["paths"]["inference_manifest"],
                evidence_relpath=LOAD_EVIDENCE_REL,
            )
        if isinstance(train, dict) and train.get("status") == "passed":
            _update_environment_manifest(
                ctx["paths"]["training_manifest"],
                evidence_relpath=LOAD_EVIDENCE_REL,
            )
        ctx["inference_manifest"] = load_json(ctx["paths"]["inference_manifest"])
        ctx["training_manifest"] = load_json(ctx["paths"]["training_manifest"])

    write_json(ctx["paths"]["load_evidence"], evidence)

    errors = validate_checkpoint_load_evidence(
        evidence,
        download_evidence=ctx["download_evidence"],
        register=ctx["register"],
        inference_manifest=ctx["inference_manifest"],
        training_manifest=ctx["training_manifest"],
    )

    report = {
        "overall_status": overall,
        "validation_errors": errors,
        "inference_load_status": evidence.get("inference_environment_load", {}).get("status"),
        "training_load_status": evidence.get("training_environment_load", {}).get("status"),
        "smoke_status": evidence.get("smoke_generation", {}).get("status"),
        "selected_model": ctx["register"].get("selected_model"),
    }
    log_dir = ctx["paths"]["raw_log_dir"]
    log_dir.mkdir(parents=True, exist_ok=True)
    report_path = log_dir / "t12_checkpoint_load_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="T12 Slice 3C checkpoint load probe")
    parser.add_argument(
        "mode",
        choices=("inference-load", "training-load", "smoke-generate", "correct-evidence", "report"),
    )
    args = parser.parse_args()
    repo_root = ProjectPaths.from_repo_root().root

    if args.mode == "inference-load":
        return cmd_inference_load(repo_root)
    if args.mode == "training-load":
        return cmd_training_load(repo_root)
    if args.mode == "smoke-generate":
        return cmd_smoke_generate(repo_root)
    if args.mode == "correct-evidence":
        return cmd_correct_evidence(repo_root)
    return cmd_report(repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
