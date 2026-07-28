#!/usr/bin/env python3
"""Non-sealed T27F all-task runtime canary using T27E diagnostic records only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex  # noqa: E402
from ambiguity_manager.model.qlora_smoke import require_selected_base_model  # noqa: E402
from ambiguity_manager.model.qlora_task_conditioned_smoke import _evaluate_task_matrix, _utc_now  # noqa: E402
from ambiguity_manager.model.schema_preflight import run_schema_preflight  # noqa: E402
from ambiguity_manager.model.task_constrained_decoding import generate_with_task_constraint  # noqa: E402
from ambiguity_manager.model.task_prediction_contract import load_field_responsibility_registry, load_task_registry  # noqa: E402
from ambiguity_manager.model.t27c_runtime_recovery import Heartbeat, PredictionJournal  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter-dir", required=True, type=Path)
    parser.add_argument("--records-dir", type=Path, default=ROOT / "data/development/t27e_diagnostic_dev_v1")
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-commit", default=None)
    parser.add_argument("--source-archive-sha256", default=None)
    parser.add_argument("--source-identity-manifest", type=Path, default=None)
    args = parser.parse_args()
    preflight = run_schema_preflight(ROOT)
    if not preflight["passed"]:
        raise RuntimeError("t27f_canary_schema_preflight_failed")
    records_dir = args.records_dir if args.records_dir.is_absolute() else ROOT / args.records_dir
    records = [json.loads(line) for line in (records_dir / "records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    matrix = json.loads((records_dir / "required_task_matrix.json").read_text(encoding="utf-8"))
    registry = load_task_registry(ROOT)
    fields = load_field_responsibility_registry(ROOT)
    selected_base = require_selected_base_model(ROOT)
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    repository, revision = selected_base.split("@", 1)
    tokenizer = AutoTokenizer.from_pretrained(repository, revision=revision, local_files_only=True)
    if tokenizer.pad_token is None: tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(repository, revision=revision, local_files_only=True, quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True), device_map="auto")
    adapter = PeftModel.from_pretrained(model, str(args.adapter_dir), is_trainable=False)
    result_dir = args.result_dir.resolve(); result_dir.mkdir(parents=True, exist_ok=True)
    expected = sum(len((matrix.get("records") or {}).get(str(row["id"]), {}).get("required", [])) + len((matrix.get("records") or {}).get(str(row["id"]), {}).get("optional", [])) for row in records) * 2
    runtime = {"heartbeat": Heartbeat(result_dir / "heartbeat.json", args.run_id, expected), "journal": PredictionJournal(result_dir / "prediction_journal.jsonl"), "raw_output_dir": result_dir / "raw_outputs", "timeouts": {str(t["task_id"]): 300 for t in registry["tasks"]}}

    def generate(request, task_spec, enabled):
        target = adapter
        if not enabled:
            with adapter.disable_adapter():
                return generate_with_task_constraint(model=target, tokenizer=tokenizer, prompt=request.model_input, json_schema=task_spec["json_schema"], max_new_tokens=int(task_spec["maximum_output_tokens"]), generation_config={"do_sample": False})
        return generate_with_task_constraint(model=target, tokenizer=tokenizer, prompt=request.model_input, json_schema=task_spec["json_schema"], max_new_tokens=int(task_spec["maximum_output_tokens"]), generation_config={"do_sample": False})

    base = _evaluate_task_matrix(records=records, matrix=matrix, task_registry=registry, field_registry=fields, selected_base_model=selected_base, adapter_identity=None, role="base", generate_fn=lambda **kw: generate(enabled=False, **kw), constraint_initialised=True, runtime=runtime)
    adapted = _evaluate_task_matrix(records=records, matrix=matrix, task_registry=registry, field_registry=fields, selected_base_model=selected_base, adapter_identity="technical_t27e_canary_adapter", role="adapter", generate_fn=lambda **kw: generate(enabled=True, **kw), constraint_initialised=True, runtime=runtime)
    payload = {"ticket": "T27F", "canary": True, "sealed_output_accessed": False, "run_id": args.run_id, "source_commit": args.source_commit, "source_archive_sha256": args.source_archive_sha256, "preflight": preflight, "records": len(records), "expected_task_calls": expected, "base": {k: base.get(k) for k in ("task_calls_attempted", "parse_valid", "schema_valid", "semantic_valid", "assembly_results", "unconstrained_fallback_count")}, "adapter": {k: adapted.get(k) for k in ("task_calls_attempted", "parse_valid", "schema_valid", "semantic_valid", "assembly_results", "unconstrained_fallback_count")}, "finished_at_utc": _utc_now()}
    (result_dir / "t27f_canary_evidence.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (result_dir / "run_manifest.json").write_text(json.dumps({"ticket": "T27F", "run_id": args.run_id, "sealed": False, "record_count": len(records), "expected_task_calls": expected, "preflight_passed": preflight["passed"], "evidence_sha256": sha256_hex(canonical_json_bytes(payload))}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
