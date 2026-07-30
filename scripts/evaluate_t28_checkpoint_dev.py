#!/usr/bin/env python3
"""Resumable, source-dev-only evaluation of a completed T28 adapter.

This is an execution-path recovery utility.  It does not change the frozen
data, prompts, base revision, decoding limit, or selection policy.  It batches
the same greedy HF generation calls and appends each completed batch to a
JSONL file so a Slurm time limit can be resumed without losing evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.model.t28 import T28Error, assert_dev_only  # noqa: E402
from ambiguity_manager.model.t28_trainer import iter_jsonl, sha256_file  # noqa: E402
from ambiguity_manager.model.qlora_task_aligned_smoke import (  # noqa: E402
    _HFTokenizerAdapter,
    _build_validation_prompt,
)
from ambiguity_manager.model.structured_output_validation import (  # noqa: E402
    validate_structured_model_output,
)


EXPECTED_DEV_SHA256 = "6b2b3b3ac1f3682636e1a5bd4ac0bd635660827febfc4c4230cdd5a537a4e2a4"
EXPECTED_BASE_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _append_log(path: Path, event: str, **fields: Any) -> None:
    payload = {"timestamp_epoch": time.time(), "event": event, **fields}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _load_completed(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    completed: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise T28Error(f"partial_or_invalid_eval_jsonl:{path}:{line_number}") from exc
            record_id = str(row.get("record_id") or "")
            if not record_id or record_id in completed:
                raise T28Error(f"duplicate_or_missing_eval_record_id:{path}:{line_number}")
            completed[record_id] = row
    return completed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--dev-manifest", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--base-model", default="Qwen/Qwen3-8B")
    parser.add_argument("--base-revision", default=EXPECTED_BASE_REVISION)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-new-tokens", type=int, default=384)
    args = parser.parse_args()

    if args.base_revision != EXPECTED_BASE_REVISION:
        raise T28Error("base_revision_not_frozen")
    if sha256_file(args.dev_manifest) != EXPECTED_DEV_SHA256:
        raise T28Error("dev_manifest_hash_mismatch")
    rows = list(iter_jsonl(args.dev_manifest))
    assert_dev_only(rows)
    if not rows or any(str(row.get("split")) != "source_dev" for row in rows):
        raise T28Error("dev_manifest_not_source_dev_only")
    if any(row.get("source_holdout") or row.get("protected_data") for row in rows):
        raise T28Error("protected_or_holdout_record_detected")
    if not args.adapter.is_dir() or not (args.adapter / "adapter_config.json").is_file():
        raise T28Error("adapter_missing_or_incomplete")
    if args.batch_size < 1 or args.max_new_tokens != 384:
        raise T28Error("decoding_or_batch_configuration_not_frozen")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results_path = args.output_dir / "dev_raw_and_parsed.jsonl"
    summary_path = args.output_dir / "dev_evaluation.json"
    log_path = args.output_dir / "evaluation_progress.log.jsonl"
    completed = _load_completed(results_path)
    pending = [row for row in rows if str(row["record_id"]) not in completed]
    started_epoch = time.time()
    run_meta = {
        "status": "RUNNING",
        "dev_manifest_sha256": sha256_file(args.dev_manifest),
        "dev_manifest_count": len(rows),
        "completed_before_start": len(completed),
        "base_model": args.base_model,
        "base_revision": args.base_revision,
        "adapter_path": str(args.adapter),
        "bundle_root": str(args.bundle_root),
        "batch_size": args.batch_size,
        "max_new_tokens": args.max_new_tokens,
        "log_path": str(log_path),
        "source_holdout_loaded": 0,
        "protected_records_loaded": 0,
        "started_at_epoch": started_epoch,
    }
    _write_json(args.output_dir / "evaluation_manifest.json", run_meta)
    _append_log(
        log_path,
        "evaluation_started",
        total=len(rows),
        completed=len(completed),
        remaining=len(pending),
        batch_size=args.batch_size,
    )
    if not pending:
        return _finalize(args.output_dir, rows, completed, run_meta)

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    _append_log(log_path, "model_loading_started", completed=len(completed))
    tokenizer = AutoTokenizer.from_pretrained(
        args.base_model, revision=args.base_revision, local_files_only=True
    )
    tokenizer.padding_side = "left"
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    base = AutoModelForCausalLM.from_pretrained(
        args.base_model, revision=args.base_revision, local_files_only=True,
        quantization_config=bnb, device_map="auto",
    )
    adapter_base = AutoModelForCausalLM.from_pretrained(
        args.base_model, revision=args.base_revision, local_files_only=True,
        quantization_config=bnb, device_map="auto",
    )
    adapted = PeftModel.from_pretrained(adapter_base, str(args.adapter))
    base.eval()
    adapted.eval()
    _append_log(log_path, "model_loading_finished", completed=len(completed))

    for start in range(0, len(pending), args.batch_size):
        batch = pending[start : start + args.batch_size]
        prompts = [_build_validation_prompt(dict(row["record"])) for row in batch]
        encoded = tokenizer(prompts, return_tensors="pt", padding=True, truncation=False)
        base_inputs = {key: value.to(next(base.parameters()).device) for key, value in encoded.items()}
        adapted_inputs = {key: value.to(next(adapted.parameters()).device) for key, value in encoded.items()}
        batch_number = (start // args.batch_size) + 1
        total_batches = (len(pending) + args.batch_size - 1) // args.batch_size
        elapsed = max(time.time() - started_epoch, 1e-6)
        rate = len(completed) / elapsed
        _append_log(
            log_path,
            "batch_started",
            batch=batch_number,
            total_batches=total_batches,
            completed=len(completed),
            remaining=len(rows) - len(completed),
            eta_seconds=((len(rows) - len(completed)) / rate if rate > 0 else None),
        )
        batch_started = time.time()
        with torch.no_grad():
            base_started = time.time()
            base_ids = base.generate(**base_inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
            _append_log(log_path, "base_batch_finished", batch=batch_number, seconds=time.time() - base_started)
            adapted_started = time.time()
            adapted_ids = adapted.generate(**adapted_inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
            _append_log(log_path, "adapter_batch_finished", batch=batch_number, seconds=time.time() - adapted_started)
        base_texts = tokenizer.batch_decode(base_ids, skip_special_tokens=True)
        adapted_texts = tokenizer.batch_decode(adapted_ids, skip_special_tokens=True)
        emitted: list[dict[str, Any]] = []
        for row, prompt, base_text, adapted_text in zip(batch, prompts, base_texts, adapted_texts):
            base_verdict = validate_structured_model_output(prompt=prompt, raw_output=base_text)
            adapter_verdict = validate_structured_model_output(prompt=prompt, raw_output=adapted_text)
            emitted.append({
                "record_id": row["record_id"],
                "split": row["split"],
                "prompt": prompt,
                "base_raw_output": base_text,
                "adapter_raw_output": adapted_text,
                "base_parsed": base_verdict.to_dict(),
                "adapter_parsed": adapter_verdict.to_dict(),
                "outputs_differ": base_text != adapted_text,
            })
        _append_jsonl(results_path, emitted)
        completed.update({str(row["record_id"]): row for row in emitted})
        elapsed = max(time.time() - started_epoch, 1e-6)
        rate = len(completed) / elapsed
        progress = {
            "status": "RUNNING",
            "completed": len(completed),
            "total": len(rows),
            "remaining": len(rows) - len(completed),
            "last_batch_start": start,
            "last_batch_seconds": time.time() - batch_started,
            "records_per_second": rate,
            "eta_seconds": ((len(rows) - len(completed)) / rate if rate > 0 else None),
            "last_event_epoch": time.time(),
        }
        _write_json(args.output_dir / "evaluation_progress.json", progress)
        _append_log(log_path, "batch_finished", batch=batch_number, **progress)
        print(json.dumps({"event": "batch_finished", **progress}, sort_keys=True), flush=True)
    return _finalize(args.output_dir, rows, completed, run_meta)


def _finalize(output_dir: Path, rows: list[dict[str, Any]], completed: dict[str, dict[str, Any]], meta: dict[str, Any]) -> int:
    if len(completed) != len(rows):
        raise T28Error("dev_evaluation_incomplete")
    adapter_status: dict[str, int] = {}
    base_status: dict[str, int] = {}
    for row in completed.values():
        adapter_status[str(row["adapter_parsed"].get("status"))] = adapter_status.get(str(row["adapter_parsed"].get("status")), 0) + 1
        base_status[str(row["base_parsed"].get("status"))] = base_status.get(str(row["base_parsed"].get("status")), 0) + 1
    summary = {
        **meta,
        "status": "VERIFY_PASSED",
        "completed": len(completed),
        "remaining": 0,
        "silent_skips": 0,
        "adapter_status_counts": adapter_status,
        "base_status_counts": base_status,
        "adapter_differs_from_base_count": sum(bool(row["outputs_differ"]) for row in completed.values()),
        "results_sha256": _sha256(output_dir / "dev_raw_and_parsed.jsonl"),
        "finished_at_epoch": time.time(),
    }
    _write_json(output_dir / "dev_evaluation.json", summary)
    _write_json(output_dir / "evaluation_progress.json", summary)
    _append_log(output_dir / "evaluation_progress.log.jsonl", "evaluation_finished", **summary)
    print(json.dumps({"event": "evaluation_finished", **summary}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except T28Error as exc:
        print(f"T28_DEV_EVAL_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
