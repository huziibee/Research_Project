#!/usr/bin/env python3
"""Generate a dedicated intent_summary box for raw Qwen or the unofficial fine-tune.

Versioned separately from T39. Lists the 17 ambiguity names and 8 speech-acts
in the prompt so the vocab crash cannot happen again. Does not score CPC
(Pilot-120 gold has no CPC frames).
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

from evaluate_pilot_120_direct_base import (  # noqa: E402
    AMBIGUITY_TYPES,
    BASE_MODEL,
    BASE_REVISION,
    CAPABILITIES,
    SELECTED_ADAPTER_SYSTEM_ID,
    SYSTEM_ID,
    TERMINALS,
    _append_jsonl,
    _load_done,
    _write_json,
    apply_adapter_scale,
    extract_json,
    sampling_generate_kwargs,
    set_run_seed,
    verify_freeze,
)
from ambiguity_manager.evaluation import pilot_120 as p120  # noqa: E402

SPEECH_ACTS = [
    "directive_command",
    "indirect_request",
    "information_question",
    "permission_request",
    "prohibition",
    "conditional_directive",
    "multi_intent",
    "other_non_actionable",
]


def build_prompt(rec: dict[str, Any]) -> str:
    return (
        "You are evaluating a robot command.\n"
        "Return ONLY one JSON object with exactly these keys:\n"
        "  intent_summary: one or two sentences naming the job the person wants done\n"
        "  speech_act: one of " + " | ".join(SPEECH_ACTS) + "\n"
        "  ambiguity_types: array using ONLY these names (may be empty): "
        + ", ".join(AMBIGUITY_TYPES)
        + "\n"
        "  capability_status: one of " + " | ".join(CAPABILITIES) + "\n"
        "  terminal_strategy: one of " + " | ".join(TERMINALS) + "\n"
        "You may reason first. After any reasoning you MUST finish with that JSON object.\n\n"
        f"record_id: {rec['record_id']}\n"
        f"command: {rec['command']}\n"
        f"dialogue_history: {json.dumps(rec.get('dialogue_history') or [], ensure_ascii=False)}\n"
        f"scene_context: {rec['scene_context']}\n"
        f"capability_context: {rec['capability_context']}\n"
    )


def normalise(obj: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
    if not obj:
        return None, "no_json"
    summary = str(obj.get("intent_summary") or "").strip()
    if not summary:
        return None, "empty_intent_summary"
    speech = str(obj.get("speech_act") or "").strip()
    if speech not in SPEECH_ACTS:
        return None, f"bad_speech_act:{speech}"
    term = str(obj.get("terminal_strategy") or "").strip()
    if term == "silently_resolve":
        term = "execute"
    if term not in TERMINALS:
        return None, f"bad_terminal:{term}"
    caps = str(obj.get("capability_status") or "").strip()
    if caps not in CAPABILITIES:
        return None, f"bad_capability:{caps}"
    raw_types = obj.get("ambiguity_types") or []
    if not isinstance(raw_types, list):
        return None, "bad_ambiguity_types"
    types = sorted({str(t) for t in raw_types if str(t) in AMBIGUITY_TYPES})
    return {
        "intent_summary": summary,
        "speech_act": speech,
        "ambiguity_types": types,
        "capability_status": caps,
        "terminal_strategy": term,
    }, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--system-id", default=SYSTEM_ID)
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--adapter-identity", type=Path)
    parser.add_argument("--adapter-scale", type=float, default=0.18)
    parser.add_argument("--allow-unofficial-adapter", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=20260913)
    parser.add_argument("--max-new-tokens", type=int, default=4096)
    args = parser.parse_args()
    set_run_seed(args.seed)

    adapter_identity = None
    adapter_id = None
    if args.adapter is None:
        if args.system_id != SYSTEM_ID:
            raise SystemExit("raw_intent_box_requires_direct_base_system_id")
    else:
        if args.system_id != SELECTED_ADAPTER_SYSTEM_ID or args.adapter_identity is None:
            raise SystemExit("fine_tune_intent_box_requires_identity")
        adapter_identity = json.loads(args.adapter_identity.read_text(encoding="utf-8"))
        official = adapter_identity.get("valid_for_official_use") is True
        selected = adapter_identity.get("selected_adapter") is True
        if official:
            if not selected:
                raise SystemExit("official_adapter_requires_selected")
            if args.allow_unofficial_adapter:
                raise SystemExit("refusing_unofficial_flag_on_official_adapter")
        elif not selected and not args.allow_unofficial_adapter:
            raise SystemExit("unofficial_adapter_needs_allow_flag")
        adapter_id = str(
            adapter_identity.get("adapter_id")
            or ("official-fine-tune" if official else "unofficial-fine-tune")
        )

    root = args.root.resolve()
    freeze_check = verify_freeze(root)
    source_rows = p120.load_jsonl(root / "data/annotations/pilot_120_v1/source_canonical.jsonl")
    ids = [row["record_id"] for row in source_rows]
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    pred_path = out / f"{args.system_id}.predictions.jsonl"
    done = _load_done(pred_path)
    _write_json(
        out / "run_manifest.json",
        {
            "study": "final_close_intent_box_20260913",
            "system_id": args.system_id,
            "unofficial_fine_tune": bool(args.adapter) and not (
                (adapter_identity or {}).get("valid_for_official_use") is True
            ),
            "adapter_id": adapter_id,
            "adapter_scale": float(args.adapter_scale) if args.adapter else None,
            "adapter_identity": adapter_identity,
            "freeze": freeze_check,
            "temperature": float(args.temperature),
            "seed": args.seed,
            "lists_ambiguity_vocab_in_prompt": True,
            "lists_speech_act_vocab_in_prompt": True,
            "does_not_claim_cpc_f1": True,
            "n_expected": len(ids),
            "n_done_at_start": len(done),
        },
    )

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available():
        raise SystemExit("cuda_required")
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, revision=BASE_REVISION, local_files_only=True)
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
    if args.adapter is not None:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(args.adapter), local_files_only=True)
        apply_adapter_scale(model, float(args.adapter_scale))
    model.eval()

    by_id = {row["record_id"]: row for row in source_rows}
    for index, rid in enumerate(ids):
        if rid in done:
            continue
        rec = by_id[rid]
        messages = [{"role": "user", "content": build_prompt(rec)}]
        rendered = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tok(rendered, return_tensors="pt").to(model.device)
        started = time.perf_counter()
        failed = False
        error = None
        raw_text = ""
        parsed = None
        try:
            with torch.inference_mode():
                out_ids = model.generate(
                    **inputs,
                    max_new_tokens=args.max_new_tokens,
                    **sampling_generate_kwargs(args.temperature),
                    pad_token_id=tok.eos_token_id,
                )
            raw_text = tok.decode(out_ids[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True)
            parsed, error = normalise(extract_json(raw_text))
            if error:
                failed = True
        except Exception as exc:  # noqa: BLE001
            failed = True
            error = f"exception:{type(exc).__name__}:{exc}"
        row = {
            "record_id": rid,
            "system_id": args.system_id,
            "intent_summary": None if failed else parsed["intent_summary"],
            "speech_act": None if failed else parsed["speech_act"],
            "ambiguity_types": None if failed else parsed["ambiguity_types"],
            "capability_status": None if failed else parsed["capability_status"],
            "terminal_strategy": None if failed else parsed["terminal_strategy"],
            "raw_output": raw_text,
            "parsed": parsed,
            "schema_valid": not failed,
            "failed": failed,
            "error": error,
            "latency_ms": (time.perf_counter() - started) * 1000.0,
            "execution_mode": "final_close_intent_box",
        }
        _append_jsonl(pred_path, [row])
        print(json.dumps({"index": index, "record_id": rid, "failed": failed, "error": error}), flush=True)

    report = p120.evaluate_predictions(
        pred_path,
        config_path=root / "configs/evaluation/pilot_120_v1.json",
        paths=p120.default_paths(root),
    )
    _write_json(out / f"{args.system_id}.eval.json", report)
    print(json.dumps({"ok": True, "predictions": str(pred_path), "eval": report.get("terminal_strategy")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
