#!/usr/bin/env python3
"""Inference-only T27C recovery over a verified technical adapter.

The adapter is an input artefact, never an official selection.  This entry point
does not contain a training path and refuses to start when identity verification
is incomplete.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ambiguity_manager.model.qlora_smoke import require_selected_base_model  # noqa: E402
from ambiguity_manager.model.qlora_task_conditioned_smoke import (  # noqa: E402
    _evaluate_task_matrix,
    _tasks_for_record,
    load_diagnostic_records,
    load_required_task_matrix,
    load_sealed_records,
    load_task_conditioned_smoke_config,
)
from ambiguity_manager.model.task_constrained_decoding import generate_with_task_constraint  # noqa: E402
from ambiguity_manager.model.task_prediction_contract import (  # noqa: E402
    get_task_spec,
    load_field_responsibility_registry,
    load_task_registry,
)
from ambiguity_manager.model.t27c_runtime_recovery import verify_adapter_reuse  # noqa: E402
from ambiguity_manager.model.qlora_task_conditioned_smoke import (  # noqa: E402
    _config_hash,
    _data_manifest_hash,
    _field_registry_hash,
    _task_registry_hash,
    _utc_now,
)
from ambiguity_manager.systems.structured_analysis_assembler import StructuredAnalysisAssembler  # noqa: E402
from ambiguity_manager.paths import repo_root  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter-dir", required=True, type=Path)
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-archive-sha256", default=None)
    parser.add_argument("--source-identity-manifest", type=Path, default=None)
    parser.add_argument("--diagnostic", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = repo_root()
    config = load_task_conditioned_smoke_config(root)
    task_registry = load_task_registry(root)
    field_registry = load_field_responsibility_registry(root)
    selected_base = require_selected_base_model(root)
    reuse = verify_adapter_reuse(
        args.adapter_dir,
        selected_base_model=selected_base,
        config=config,
        train_manifest_hash=_data_manifest_hash(root),
        task_registry_hash=_task_registry_hash(root),
        field_registry_hash=_field_registry_hash(root),
        source_commit=args.source_commit,
    )
    if reuse.get("status") != "reusable":
        args.result_dir.mkdir(parents=True, exist_ok=True)
        (args.result_dir / "recovery_blocked.json").write_text(json.dumps({"status": "BLOCKED", "adapter_reuse": reuse}, indent=2) + "\n", encoding="utf-8")
        print(f"T27C_INFERENCE_RECOVERY_BLOCKED adapter_status={reuse.get('status')}", file=sys.stderr)
        return 2

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    repository, revision = selected_base.split("@", 1)
    tokenizer = AutoTokenizer.from_pretrained(repository, revision=revision, local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    quant = config["quantization"]
    model = AutoModelForCausalLM.from_pretrained(
        repository,
        revision=revision,
        local_files_only=True,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type=quant["quant_type"],
            bnb_4bit_compute_dtype=getattr(torch, quant["compute_dtype"]),
            bnb_4bit_use_double_quant=bool(quant["double_quant"]),
        ),
        device_map="auto",
    )
    adapter = PeftModel.from_pretrained(model, str(args.adapter_dir), is_trainable=False)
    records = load_diagnostic_records(root) if args.diagnostic else load_sealed_records(root)
    matrix = load_required_task_matrix(root)
    result_dir = args.result_dir.resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    from ambiguity_manager.model.t27c_runtime_recovery import Heartbeat, PredictionJournal

    runtime = {
        "heartbeat": Heartbeat(result_dir / "heartbeat.json", args.run_id, sum(len(_tasks_for_record(matrix, str(r["id"]))) for r in records) * 2),
        "journal": PredictionJournal(result_dir / "prediction_journal.jsonl"),
        "raw_output_dir": result_dir / "raw_outputs",
        "timeouts": {str(t["task_id"]): int(config["runtime_recovery"]["declared_minimum_seconds"]) for t in task_registry["tasks"]},
    }

    def generate(request, task_spec, *, enabled):
        target = adapter if enabled else adapter
        context = target if enabled else target.disable_adapter()
        if enabled:
            return generate_with_task_constraint(model=target, tokenizer=tokenizer, prompt=request.model_input, json_schema=task_spec["json_schema"], max_new_tokens=int(task_spec.get("maximum_output_tokens") or 128), generation_config={"do_sample": False})
        with context:
            return generate_with_task_constraint(model=target, tokenizer=tokenizer, prompt=request.model_input, json_schema=task_spec["json_schema"], max_new_tokens=int(task_spec.get("maximum_output_tokens") or 128), generation_config={"do_sample": False})

    base = _evaluate_task_matrix(records=records, matrix=matrix, task_registry=task_registry, field_registry=field_registry, selected_base_model=selected_base, adapter_identity=None, role="base", generate_fn=lambda **kw: generate(enabled=False, **kw), constraint_initialised=True, runtime=runtime)
    adapted = _evaluate_task_matrix(records=records, matrix=matrix, task_registry=task_registry, field_registry=field_registry, selected_base_model=selected_base, adapter_identity="verified-technical-adapter", role="adapter", generate_fn=lambda **kw: generate(enabled=True, **kw), constraint_initialised=True, runtime=runtime)
    payload = {"run_id": args.run_id, "mode": "real_cluster_inference_only", "diagnostic": args.diagnostic, "success": True, "selected_base_model": selected_base, "selected_adapter": None, "selected_model_strategy": None, "valid_for_official_use": False, "adapter_reuse": reuse, "base_eval_summary": {k: base.get(k) for k in ("task_calls_attempted", "parse_valid", "schema_valid", "semantic_valid", "parse_valid_rate", "schema_valid_rate", "semantic_valid_rate", "assembly_attempts", "production_schema_valid", "semantic_safety_accepted")}, "adapter_eval_summary": {k: adapted.get(k) for k in ("task_calls_attempted", "parse_valid", "schema_valid", "semantic_valid", "parse_valid_rate", "schema_valid_rate", "semantic_valid_rate", "assembly_attempts", "production_schema_valid", "semantic_safety_accepted")}, "finished_at_utc": _utc_now()}
    (result_dir / "qlora_task_conditioned_smoke_result.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (result_dir / "task_prediction_results.json").write_text(json.dumps({"base": base["task_results"], "adapter": adapted["task_results"]}, indent=2) + "\n", encoding="utf-8")
    (result_dir / "assembly_results.json").write_text(json.dumps({"base": base["assembly_results"], "adapter": adapted["assembly_results"]}, indent=2) + "\n", encoding="utf-8")
    (result_dir / "run_manifest.json").write_text(json.dumps({"run_id": args.run_id, "mode": payload["mode"], "success": True, "diagnostic": args.diagnostic}, indent=2) + "\n", encoding="utf-8")
    print(f"T27C_INFERENCE_RECOVERY_COMPLETE run_id={args.run_id} diagnostic={args.diagnostic}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
