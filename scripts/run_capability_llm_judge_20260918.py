#!/usr/bin/env python3
"""LLM capability judge over frozen GF-v2 predictions (no intent re-emit).

Reads existing predictions (intent_summary + parsed.analysis), asks Qwen3-8B
for a capability_status judgment, writes judgments JSONL. CPU re-route is a
separate script so this job stays GPU-bound and resumable.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ambiguity_manager.evaluation import pilot_120 as p120  # noqa: E402
from evaluate_pilot_120_direct_base import (  # noqa: E402
    BASE_MODEL,
    BASE_REVISION,
    sampling_generate_kwargs,
    set_run_seed,
)
from lib_capability_debate_20260918 import (  # noqa: E402
    append_jsonl,
    build_capability_judge_prompt,
    extract_json_object,
    intent_from_pred,
    load_jsonl_by_id,
    normalise_capability_obj,
    prior_capability_from_pred,
    write_json,
)


def _load_model() -> tuple[Any, Any]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available():
        raise SystemExit("cuda_required")
    tokenizer = AutoTokenizer.from_pretrained(
        BASE_MODEL, revision=BASE_REVISION, local_files_only=True
    )
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        revision=BASE_REVISION,
        local_files_only=True,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        ),
        device_map="auto",
    )
    if not any(parameter.device.type == "cuda" for parameter in model.parameters()):
        raise SystemExit("model_not_on_cuda")
    return model, tokenizer


def _generate(model: Any, tokenizer: Any, prompt: str, *, temperature: float, max_new_tokens: int) -> str:
    # Qwen3 defaults to thinking mode; that burns the token budget before JSON.
    try:
        rendered = tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
    except TypeError:
        rendered = tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True
        )
    inputs = tokenizer(rendered, return_tensors="pt").to(model.device)
    with __import__("torch").inference_mode():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            **sampling_generate_kwargs(temperature),
            repetition_penalty=1.08,
            no_repeat_ngram_size=5,
            pad_token_id=tokenizer.eos_token_id,
        )
    generated = output_ids[0][inputs["input_ids"].shape[-1] :]
    return tokenizer.decode(generated, skip_special_tokens=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="Frozen GF-v2 predictions JSONL (reuse intent).",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--retry-max", type=int, default=2)
    args = parser.parse_args()
    set_run_seed(args.seed)

    root = args.root.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    judgments_path = out / "capability_judgments.jsonl"
    progress_path = out / "capability_judge_progress.json"

    source_rows = p120.load_jsonl(root / "data/annotations/pilot_120_v1/source_canonical.jsonl")
    gold_rows = load_jsonl_by_id(root / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl")
    preds = load_jsonl_by_id(args.predictions.resolve())
    if args.limit and args.limit > 0:
        source_rows = source_rows[: args.limit]

    done = load_jsonl_by_id(judgments_path) if judgments_path.exists() else {}
    todo = [row for row in source_rows if str(row["record_id"]) not in done]
    write_json(
        progress_path,
        {
            "status": "STARTING",
            "n_done": len(done),
            "n_todo": len(todo),
            "predictions": str(args.predictions),
            "model": BASE_MODEL,
            "temperature": args.temperature,
        },
    )
    if not todo:
        write_json(progress_path, {"status": "COMPLETE", "n_done": len(done), "n_todo": 0})
        print(f"already_complete n={len(done)}")
        return 0

    model, tokenizer = _load_model()
    for source in todo:
        rid = str(source["record_id"])
        pred = preds.get(rid)
        if pred is None:
            raise SystemExit(f"missing_prediction:{rid}")
        intent = intent_from_pred(pred)
        if not intent:
            gold_cap = (gold_rows.get(rid) or {}).get("capability_status")
            row = {
                "record_id": rid,
                "capability_status": None,
                "confidence": None,
                "reason": None,
                "prior_capability": prior_capability_from_pred(pred),
                "gold_capability_status": gold_cap,
                "capability_match_gold": False,
                "intent_summary": None,
                "raw_output": "",
                "attempts": [],
                "latency_ms": 0.0,
                "model_id": BASE_MODEL,
                "temperature": args.temperature,
                "failed": True,
                "error": "missing_intent_summary_skip",
            }
            append_jsonl(judgments_path, row)
            done[rid] = row
            print(f"skip {rid} missing_intent")
            continue
        prior = prior_capability_from_pred(pred)
        prompt = build_capability_judge_prompt(
            source, intent_summary=intent, prior_capability=prior
        )
        started = time.perf_counter()
        raw = ""
        label = None
        normalised: dict[str, Any] = {}
        attempts: list[dict[str, Any]] = []
        for attempt in range(1, args.retry_max + 1):
            raw = _generate(
                model,
                tokenizer,
                prompt
                if attempt == 1
                else (
                    prompt
                    + "\nPrevious output was invalid. Return ONLY valid JSON with "
                    "capability_status, confidence, reason.\n"
                ),
                temperature=args.temperature,
                max_new_tokens=args.max_new_tokens,
            )
            obj = extract_json_object(raw)
            label, normalised = normalise_capability_obj(obj)
            attempts.append(
                {
                    "attempt": attempt,
                    "raw_chars": len(raw),
                    "ok": label is not None,
                    "error": None if label is not None else normalised.get("error"),
                }
            )
            if label is not None:
                break
        gold_cap = (gold_rows.get(rid) or {}).get("capability_status")
        row = {
            "record_id": rid,
            "capability_status": label,
            "confidence": normalised.get("confidence") if label else None,
            "reason": normalised.get("reason") if label else None,
            "prior_capability": prior,
            "gold_capability_status": gold_cap,
            "capability_match_gold": bool(label is not None and label == gold_cap),
            "intent_summary": intent,
            "raw_output": raw,
            "attempts": attempts,
            "latency_ms": (time.perf_counter() - started) * 1000.0,
            "model_id": BASE_MODEL,
            "temperature": args.temperature,
            "failed": label is None,
            "error": None if label is not None else normalised.get("error", "parse_failed"),
        }
        append_jsonl(judgments_path, row)
        done[rid] = row
        write_json(
            progress_path,
            {
                "status": "RUNNING",
                "last_record_id": rid,
                "n_done": len(done),
                "n_todo": len(source_rows) - len(done),
            },
        )
        print(f"judged {rid} cap={label} gold={gold_cap} failed={label is None}")

    n_ok = sum(1 for r in done.values() if not r.get("failed"))
    n_match = sum(1 for r in done.values() if r.get("capability_match_gold"))
    summary = {
        "status": "COMPLETE",
        "n": len(done),
        "n_ok": n_ok,
        "n_failed": len(done) - n_ok,
        "n_match_gold": n_match,
        "accuracy_vs_gold": (n_match / len(done)) if done else None,
        "judgments_path": str(judgments_path).replace("\\", "/"),
        "predictions": str(args.predictions).replace("\\", "/"),
        "temperature": args.temperature,
        "model": BASE_MODEL,
        "reused_intent": True,
    }
    write_json(out / "capability_judge_summary.json", summary)
    write_json(progress_path, {"status": "COMPLETE", **summary})
    print(json.dumps(summary, indent=2))
    return 0 if n_ok == len(done) else 2


if __name__ == "__main__":
    raise SystemExit(main())
