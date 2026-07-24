#!/usr/bin/env python3
"""Run the single frozen T27E sealed all-task smoke with minimal ambiguity schema."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.model.qlora_smoke import require_selected_base_model  # noqa: E402
from ambiguity_manager.model.qlora_task_conditioned_smoke import (  # noqa: E402
    _evaluate_task_matrix,
    _tasks_for_record,
    _utc_now,
)
from ambiguity_manager.model.task_constrained_decoding import generate_with_task_constraint  # noqa: E402
from ambiguity_manager.model.task_prediction_contract import (  # noqa: E402
    load_field_responsibility_registry,
    load_task_registry,
)
from ambiguity_manager.model.t27c_runtime_recovery import Heartbeat, PredictionJournal  # noqa: E402
from ambiguity_manager.model.t27e_ambiguity_recovery import effective_ambiguity_task_spec, policy_hash  # noqa: E402
from ambiguity_manager.paths import repo_root  # noqa: E402


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter-dir", required=True, type=Path)
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-archive-sha256", required=True)
    parser.add_argument("--source-identity-manifest", type=Path, default=None)
    parser.add_argument("--records-manifest", required=True, type=Path)
    parser.add_argument("--task-matrix", required=True, type=Path)
    parser.add_argument("--adapter-source-commit", required=True)
    parser.add_argument("--adapter-sha256", required=True)
    args = parser.parse_args()
    root = repo_root()
    selected_base = require_selected_base_model(root)
    manifest_path = args.records_manifest if args.records_manifest.is_absolute() else root / args.records_manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = [json.loads(line) for line in (manifest_path.parent / "records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(records) != int(manifest["record_count"]):
        raise RuntimeError("t27e_sealed_manifest_count_mismatch")
    matrix_path = args.task_matrix if args.task_matrix.is_absolute() else root / args.task_matrix
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    registry = load_task_registry(root)
    for index, task in enumerate(registry["tasks"]):
        if task.get("task_id") == "predict_ambiguity_v1":
            registry["tasks"][index] = effective_ambiguity_task_spec(registry)
    field_registry = load_field_responsibility_registry(root)

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    repository, revision = selected_base.split("@", 1)
    tokenizer = AutoTokenizer.from_pretrained(repository, revision=revision, local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        repository, revision=revision, local_files_only=True,
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True),
        device_map="auto",
    )
    adapter = PeftModel.from_pretrained(model, str(args.adapter_dir), is_trainable=False)
    result_dir = args.result_dir.resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    task_count = sum(len(_tasks_for_record(matrix, str(row["id"]))) for row in records) * 2
    runtime = {
        "heartbeat": Heartbeat(result_dir / "heartbeat.json", args.run_id, task_count),
        "journal": PredictionJournal(result_dir / "prediction_journal.jsonl"),
        "raw_output_dir": result_dir / "raw_outputs",
        "timeouts": {str(task["task_id"]): 300 for task in registry["tasks"]},
    }

    def generate(request, task_spec, *, enabled):
        if enabled:
            return generate_with_task_constraint(model=adapter, tokenizer=tokenizer, prompt=request.model_input, json_schema=task_spec["json_schema"], max_new_tokens=int(task_spec.get("maximum_output_tokens") or 128), generation_config={"do_sample": False})
        with adapter.disable_adapter():
            return generate_with_task_constraint(model=adapter, tokenizer=tokenizer, prompt=request.model_input, json_schema=task_spec["json_schema"], max_new_tokens=int(task_spec.get("maximum_output_tokens") or 128), generation_config={"do_sample": False})

    base = _evaluate_task_matrix(records=records, matrix=matrix, task_registry=registry, field_registry=field_registry, selected_base_model=selected_base, adapter_identity=None, role="base", generate_fn=lambda **kw: generate(enabled=False, **kw), constraint_initialised=True, runtime=runtime)
    adapted = _evaluate_task_matrix(records=records, matrix=matrix, task_registry=registry, field_registry=field_registry, selected_base_model=selected_base, adapter_identity=args.adapter_sha256, role="adapter", generate_fn=lambda **kw: generate(enabled=True, **kw), constraint_initialised=True, runtime=runtime)
    payload = {
        "ticket": "T27E", "run_id": args.run_id, "source_commit": args.source_commit,
        "source_archive_sha256": args.source_archive_sha256, "policy_hash": policy_hash(root),
        "records_manifest_sha256": sha256_file(manifest_path), "task_matrix_sha256": sha256_file(matrix_path),
        "base_model": selected_base, "adapter_source_commit": args.adapter_source_commit,
        "adapter_sha256": args.adapter_sha256, "selected_adapter": None,
        "selected_model_strategy": None, "valid_for_official_use": False,
        "base": {k: base.get(k) for k in ("task_calls_attempted", "parse_valid", "schema_valid", "semantic_valid", "assembly_attempts", "production_schema_valid", "semantic_safety_accepted", "unconstrained_fallback_count", "assembly_results")},
        "adapter": {k: adapted.get(k) for k in ("task_calls_attempted", "parse_valid", "schema_valid", "semantic_valid", "assembly_attempts", "production_schema_valid", "semantic_safety_accepted", "unconstrained_fallback_count", "assembly_results")},
        "finished_at_utc": _utc_now(),
    }
    (result_dir / "t27e_sealed_evidence.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (result_dir / "task_prediction_results.json").write_text(json.dumps({"base": base["task_results"], "adapter": adapted["task_results"]}, indent=2) + "\n", encoding="utf-8")
    (result_dir / "assembly_results.json").write_text(json.dumps({"base": base["assembly_results"], "adapter": adapted["assembly_results"]}, indent=2) + "\n", encoding="utf-8")
    (result_dir / "run_manifest.json").write_text(json.dumps({"ticket": "T27E", "run_id": args.run_id, "source_commit": args.source_commit, "policy_hash": policy_hash(root), "sealed": True, "record_count": len(records), "terminal_expected": task_count}, indent=2) + "\n", encoding="utf-8")
    print(f"T27E_SEALED_COMPLETE run_id={args.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
