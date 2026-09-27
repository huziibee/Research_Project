#!/usr/bin/env python3
"""Run raw Qwen or the official T28 adapter on a native packet.

Same packets/prompts/official fields as Gemma/GLM natives. This is generation
for VAGUE / AmbiK / Indirect / CLARA — not Pilot-120 manager routing.
Degree / timid policies do not apply here; they are Pilot-120 route rules.
CLARA already has a context-blind condition in the packet.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_pilot_120_direct_base import (  # noqa: E402
    BASE_MODEL,
    BASE_REVISION,
    SELECTED_ADAPTER_SYSTEM_ID,
    SYSTEM_ID,
    apply_adapter_scale,
    extract_json,
    sampling_generate_kwargs,
    selected_adapter_identity,
    set_run_seed,
)
from run_ambik_ambiguity_type import parse as parse_ambik  # noqa: E402
from run_native_context_structured import valid as valid_context  # noqa: E402
from run_vague_goal_triplet import parse as parse_vague  # noqa: E402

TASKS = ("vague", "ambik", "indirect", "clara")


def user_text(task: str, row: dict[str, Any]) -> str:
    if task == "vague":
        text = "USER COMMAND:\n" + row["command"]
        if row.get("textual_caption") is not None:
            text += "\n\nTEXTUAL SCENE DESCRIPTION:\n" + row["textual_caption"]
        return text
    if task == "ambik":
        return "USER COMMAND:\n" + row["command"] + "\n\nSCENE CONTEXT:\n" + row["scene_context"]
    text = "USER COMMAND:\n" + row["command"]
    if row.get("scene_context"):
        text += "\n\nSCENE CONTEXT:\n" + row["scene_context"]
    if row.get("capability_context"):
        text += "\n\nCAPABILITY CONTEXT:\n" + row["capability_context"]
    return text


def row_key(row: dict[str, Any]) -> tuple[str, str | None]:
    return str(row["record_id"]), row.get("condition")


def failed_payload(task: str) -> dict[str, Any]:
    if task == "vague":
        return {"goal_triplet": {"subject": "unknown", "action": "unknown", "object": "unknown"}}
    if task == "ambik":
        return {"ambiguity_types": []}
    if task == "indirect":
        return {"ambiguity_present": True, "ambiguity_types": ["pragmatic"], "missing_slots": []}
    return {"ambiguity_present": False, "capability_status": None, "recommended_strategy": None}


def parse_task(task: str, raw: str) -> dict[str, Any]:
    if task == "ambik":
        return {"ambiguity_types": parse_ambik(raw)}
    obj = extract_json(raw)
    if obj is None:
        raise ValueError("no_json")
    if task == "vague":
        return {"goal_triplet": parse_vague(json.dumps(obj))}
    return valid_context(obj, task)


def load_done(path: Path) -> set[tuple[str, str | None]]:
    done: set[tuple[str, str | None]] = set()
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        done.add((str(row.get("record_id") or ""), row.get("condition")))
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=TASKS, required=True)
    ap.add_argument("--packet", type=Path, required=True)
    ap.add_argument("--prompt", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--system-id", default=SYSTEM_ID)
    ap.add_argument("--adapter", type=Path)
    ap.add_argument("--adapter-identity", type=Path)
    ap.add_argument("--adapter-scale", type=float, default=0.18)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=20260914)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-new-tokens", type=int, default=256)
    args = ap.parse_args()
    if float(args.temperature) < 0:
        raise SystemExit("temperature_must_be_nonnegative")
    set_run_seed(args.seed)

    adapter_id = None
    if args.adapter is None:
        if args.system_id != SYSTEM_ID:
            raise SystemExit("direct_base_requires_no_adapter")
    else:
        if args.system_id != SELECTED_ADAPTER_SYSTEM_ID or args.adapter_identity is None:
            raise SystemExit("adapter_run_requires_identity")
        ident = json.loads(args.adapter_identity.read_text(encoding="utf-8"))
        adapter_id = selected_adapter_identity(
            ident, adapter_scale=float(args.adapter_scale), allow_unofficial=False
        )

    rows = [json.loads(line) for line in args.packet.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit and args.limit > 0:
        rows = rows[: int(args.limit)]
    prompt = args.prompt.read_text(encoding="utf-8")
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_path = out_dir / "predictions.jsonl"
    done = load_done(pred_path)

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available():
        raise SystemExit("cuda_required")
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, revision=BASE_REVISION, local_files_only=True)
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        revision=BASE_REVISION,
        local_files_only=True,
        quantization_config=bnb,
        device_map="auto",
    )
    if args.adapter is not None:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(args.adapter), local_files_only=True)
        apply_adapter_scale(model, float(args.adapter_scale))
    model.eval()

    started = time.time()
    n_new = 0
    with pred_path.open("a", encoding="utf-8", newline="\n") as handle:
        for index, row in enumerate(rows):
            key = row_key(row)
            if key in done:
                continue
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_text(args.task, row)},
            ]
            rendered = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = tok(rendered, return_tensors="pt").to(model.device)
            raw = ""
            parsed = None
            error = None
            try:
                with torch.inference_mode():
                    out_ids = model.generate(
                        **inputs,
                        max_new_tokens=args.max_new_tokens,
                        **sampling_generate_kwargs(args.temperature),
                        pad_token_id=tok.eos_token_id,
                    )
                gen = out_ids[0][inputs["input_ids"].shape[-1] :]
                raw = tok.decode(gen, skip_special_tokens=True)
                parsed = parse_task(args.task, raw)
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}:{exc}"
                parsed = failed_payload(args.task)
            rec = {
                "record_id": row["record_id"],
                "source_fingerprint_sha256": row.get("source_fingerprint_sha256"),
                "system_id": args.system_id,
                "failed": error is not None,
                "error": error,
                "raw_output": raw,
                **parsed,
            }
            if "condition" in row or args.task in {"vague", "clara", "indirect"}:
                rec["condition"] = row.get("condition")
            handle.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
            handle.flush()
            n_new += 1
            if n_new % 25 == 0:
                print(json.dumps({"task": args.task, "written": n_new, "index": index}), flush=True)

    n_done = sum(1 for line in pred_path.read_text(encoding="utf-8").splitlines() if line.strip())
    manifest = {
        "task": args.task,
        "system_id": args.system_id,
        "adapter_id": adapter_id,
        "packet": str(args.packet),
        "prompt": str(args.prompt),
        "n_packet": len(rows),
        "n_predictions": n_done,
        "n_new": n_new,
        "temperature": float(args.temperature),
        "seed": int(args.seed),
        "elapsed_seconds": round(time.time() - started, 3),
        "qwen_native_not_pilot120_manager": True,
        "complete": n_done >= len(rows),
    }
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if n_done >= len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
