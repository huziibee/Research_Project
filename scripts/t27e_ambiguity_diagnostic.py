#!/usr/bin/env python3
"""Run the fresh T27E current-vs-minimal ambiguity diagnostic only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex  # noqa: E402
from ambiguity_manager.model.qlora_smoke import require_selected_base_model  # noqa: E402
from ambiguity_manager.model.qlora_task_conditioned_smoke import (  # noqa: E402
    _evaluate_task_matrix,
    _utc_now,
)
from ambiguity_manager.model.task_constrained_decoding import generate_with_task_constraint  # noqa: E402
from ambiguity_manager.model.task_prediction_contract import (  # noqa: E402
    load_field_responsibility_registry,
    load_task_registry,
)
from ambiguity_manager.model.t27e_ambiguity_recovery import (  # noqa: E402
    ambiguity_forensic_summary,
    effective_ambiguity_task_spec,
    policy_hash,
)
from ambiguity_manager.paths import repo_root  # noqa: E402


def _records(root: Path) -> list[dict]:
    directory = root / "data/development/t27e_diagnostic_dev_v1"
    return [json.loads(line) for line in (directory / "records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def _matrix(records: list[dict]) -> dict:
    return {"records": {str(row["id"]): {"required": ["predict_ambiguity_v1"], "optional": []} for row in records}}


def _run_variant(*, records, registry, field_registry, model, tokenizer, selected_base, adapter, variant, result_root):
    matrix = _matrix(records)
    variant_dir = result_root / variant
    variant_dir.mkdir(parents=True, exist_ok=True)

    def generate(request, task_spec):
        if adapter:
            return generate_with_task_constraint(
                model=model, tokenizer=tokenizer, prompt=request.model_input,
                json_schema=task_spec["json_schema"],
                max_new_tokens=int(task_spec.get("maximum_output_tokens") or 128),
                generation_config={"do_sample": False},
            )
        with model.disable_adapter():
            return generate_with_task_constraint(
                model=model, tokenizer=tokenizer, prompt=request.model_input,
                json_schema=task_spec["json_schema"],
                max_new_tokens=int(task_spec.get("maximum_output_tokens") or 128),
                generation_config={"do_sample": False},
            )

    outcome = _evaluate_task_matrix(
        records=records, matrix=matrix, task_registry=registry,
        field_registry=field_registry, selected_base_model=selected_base,
        adapter_identity="technical_t27e_diagnostic_adapter" if adapter else None,
        role="adapter" if adapter else "base", generate_fn=generate,
        constraint_initialised=True,
    )
    forensic = []
    for item in outcome.get("task_results", []):
        telemetry = item.get("generation_telemetry") or {}
        forensic.append({
            "record_id": item["record_id"], "task_id": item["task_id"],
            "variant": variant, "mode": "adapter" if adapter else "base",
            "prompt_hash": item["task_provenance"].get("prompt_hash"),
            "schema_hash": item["task_provenance"].get("schema_hash"),
            "constraint_initialised": item["constraint_initialised"],
            "telemetry": telemetry,
            "forensic": ambiguity_forensic_summary(
                raw_text=(item.get("raw_attempts") or [""])[0],
                maximum_output_tokens=int(telemetry.get("maximum_output_tokens") or 0),
                generated_token_count=int(telemetry.get("generated_token_count") or 0),
                termination_reason=str(telemetry.get("termination_reason") or "unknown"),
            ),
            "final_status": item["final_status"],
            "failure_details": item["failure_details"],
        })
    payload = {
        "ticket": "T27E", "variant": variant, "mode": "adapter" if adapter else "base",
        "record_count": len(records), "task_calls": len(forensic),
        "task_registry_hash": sha256_hex(canonical_json_bytes(registry)),
        "policy_hash": policy_hash(ROOT), "forensic": forensic,
        "summary": {k: outcome.get(k) for k in ("task_calls_attempted", "parse_valid", "schema_valid", "semantic_valid", "unconstrained_fallback_count")},
        "finished_at_utc": _utc_now(),
    }
    (variant_dir / f"{('adapter' if adapter else 'base')}_evidence.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter-dir", required=True, type=Path)
    parser.add_argument("--result-dir", required=True, type=Path)
    # Standard cluster operator provenance arguments are accepted and recorded
    # by the wrapper; this diagnostic does not use them to alter generation.
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--source-commit", default=None)
    parser.add_argument("--source-archive-sha256", default=None)
    parser.add_argument("--source-identity-manifest", type=Path, default=None)
    args = parser.parse_args()
    root = repo_root()
    selected_base = require_selected_base_model(root)
    records = _records(root)
    base_registry = load_task_registry(root)
    minimal_registry = json.loads(json.dumps(base_registry))
    for index, task in enumerate(minimal_registry["tasks"]):
        if task.get("task_id") == "predict_ambiguity_v1":
            minimal_registry["tasks"][index] = effective_ambiguity_task_spec(base_registry)
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
    adapter_model = PeftModel.from_pretrained(model, str(args.adapter_dir), is_trainable=False)
    out = args.result_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    all_payloads = []
    for variant, registry in (("current_schema", base_registry), ("minimal_required_schema", minimal_registry)):
        for adapter in (False, True):
            all_payloads.append(_run_variant(records=records, registry=registry, field_registry=field_registry, model=adapter_model, tokenizer=tokenizer, selected_base=selected_base, adapter=adapter, variant=variant, result_root=out))
    evidence = {
        "ticket": "T27E", "run_id": args.run_id, "source_commit": args.source_commit,
        "policy_hash": policy_hash(root), "variants": all_payloads,
    }
    evidence_path = out / "t27e_ambiguity_forensic_evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    (out / "run_manifest.json").write_text(json.dumps({
        "ticket": "T27E", "run_id": args.run_id, "source_commit": args.source_commit,
        "source_archive_sha256": args.source_archive_sha256,
        "policy_hash": policy_hash(root), "diagnostic": True,
        "sealed_output_accessed": False,
        "evidence_sha256": sha256_hex(evidence_path.read_bytes()),
        "expected_record_count": 16, "expected_task_calls": 64,
        "unconstrained_fallbacks": 0,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"T27E_DIAGNOSTIC_COMPLETE result_dir={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
