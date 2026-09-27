#!/usr/bin/env python3
"""GPU repair for a small set of ambiguity-debate record_ids (reuse intent)."""
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
from ambiguity_manager.systems.goal_first_analysis_v2 import CANONICAL_AMBIGUITY  # noqa: E402
from evaluate_pilot_120_direct_base import (  # noqa: E402
    BASE_MODEL,
    BASE_REVISION,
    sampling_generate_kwargs,
    set_run_seed,
)
from lib_capability_debate_20260918 import (  # noqa: E402
    CAPABILITY_SET,
    analysis_dict_from_pred,
    analysis_from_dict,
    build_debate_prompt,
    extract_json_object,
    intent_from_pred,
    load_jsonl_by_id,
    norm_route,
    normalise_debate_obj,
    prior_ambiguity_from_pred,
    prior_capability_from_pred,
    patch_capability_in_analysis,
    route_from_analysis,
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
    return model, tokenizer


def _generate(model: Any, tokenizer: Any, prompt: str, *, temperature: float, max_new_tokens: int) -> str:
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


def _role_once(
    model, tokenizer, *, role, source, intent, prior_amb, other_argument, temperature, max_new_tokens, retry_max
):
    prompt = build_debate_prompt(
        role, source, intent_summary=intent, prior_ambiguity=prior_amb, other_argument=other_argument
    )
    raw = ""
    parsed = None
    meta: dict[str, Any] = {}
    attempts = []
    for attempt in range(1, retry_max + 1):
        use = prompt if attempt == 1 else (
            prompt
            + "\nInvalid JSON last time. Reply with ONLY JSON. "
            "Keys: pilot_ambiguity_types, suggested_route "
            "(exactly execute|clarify|refuse|silently_resolve), confidence, reason.\n"
        )
        raw = _generate(model, tokenizer, use, temperature=temperature, max_new_tokens=max_new_tokens)
        obj = extract_json_object(raw)
        parsed, meta = normalise_debate_obj(obj)
        ok = parsed is not None and not parsed.get("route_missing")
        attempts.append({"attempt": attempt, "ok": ok, "error": None if ok else meta.get("error")})
        if ok:
            break
    failed = parsed is None or bool((parsed or {}).get("route_missing"))
    return {
        "role": role,
        "parsed": parsed,
        "raw_output": raw,
        "attempts": attempts,
        "failed": failed,
        "error": None if not failed else meta.get("error", "parse_failed"),
    }


def _patch_ambiguity(analysis: dict[str, Any], pilot_types: list[str]) -> dict[str, Any]:
    findings = [
        f for f in list(analysis.get("findings") or []) if not str(f).startswith("pilot_ambiguity_types:")
    ]
    findings.append("pilot_ambiguity_types:" + json.dumps(pilot_types, separators=(",", ":")))
    canonical = sorted({CANONICAL_AMBIGUITY[t] for t in pilot_types if t in CANONICAL_AMBIGUITY})
    out = dict(analysis)
    out["findings"] = findings
    out["ambiguity_types"] = canonical
    out["ambiguity_present"] = bool(pilot_types) or bool(out.get("ambiguity_present"))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--capability-judgments", type=Path, required=True)
    parser.add_argument("--debate-jsonl", type=Path, required=True)
    parser.add_argument("--ids-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--adjudicator-temperature", type=float, default=0.0)
    parser.add_argument("--max-new-tokens", type=int, default=768)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--retry-max", type=int, default=3)
    args = parser.parse_args()
    set_run_seed(args.seed)

    root = args.root.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    ids = json.loads(args.ids_json.read_text(encoding="utf-8"))["record_ids"]
    id_set = set(ids)

    source_by = {str(r["record_id"]): r for r in p120.load_jsonl(root / "data/annotations/pilot_120_v1/source_canonical.jsonl")}
    gold = load_jsonl_by_id(root / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl")
    preds = load_jsonl_by_id(args.predictions.resolve())
    caps = load_jsonl_by_id(args.capability_judgments.resolve())
    existing = load_jsonl_by_id(args.debate_jsonl.resolve())

    model, tokenizer = _load_model()
    repaired = 0
    still_bad = []

    for rid in ids:
        source = source_by[rid]
        pred = preds[rid]
        intent = intent_from_pred(pred)
        prior_amb = prior_ambiguity_from_pred(pred)
        started = time.perf_counter()
        a = _role_once(
            model, tokenizer, role="debater_a", source=source, intent=intent, prior_amb=prior_amb,
            other_argument=None, temperature=args.temperature, max_new_tokens=args.max_new_tokens,
            retry_max=args.retry_max,
        )
        b = _role_once(
            model, tokenizer, role="debater_b", source=source, intent=intent, prior_amb=prior_amb,
            other_argument=None, temperature=args.temperature, max_new_tokens=args.max_new_tokens,
            retry_max=args.retry_max,
        )
        other = json.dumps(
            {"debater_a": a.get("parsed"), "debater_b": b.get("parsed")},
            ensure_ascii=False,
            indent=2,
        )
        adj = _role_once(
            model, tokenizer, role="adjudicator", source=source, intent=intent, prior_amb=prior_amb,
            other_argument=other, temperature=args.adjudicator_temperature,
            max_new_tokens=args.max_new_tokens, retry_max=args.retry_max,
        )
        final = adj.get("parsed") or {}
        final_types = list(final.get("pilot_ambiguity_types") or [])
        suggested = final.get("suggested_route")
        gold_route = norm_route(str((gold.get(rid) or {}).get("terminal_strategy")))

        analysis = analysis_dict_from_pred(pred)
        routes = {
            "goal_first_manager_v2": "missing",
            "rich_conservative_manager_v2": "missing",
            "degree_based_router_v2": "missing",
        }
        if analysis is not None:
            cap_j = caps.get(rid)
            if cap_j and not cap_j.get("failed") and cap_j.get("capability_status") in CAPABILITY_SET:
                analysis = patch_capability_in_analysis(analysis, str(cap_j["capability_status"]))
            elif prior_capability_from_pred(pred) in CAPABILITY_SET:
                analysis = patch_capability_in_analysis(analysis, str(prior_capability_from_pred(pred)))
            analysis = _patch_ambiguity(analysis, final_types)
            routes = route_from_analysis(analysis_from_dict(analysis))

        row = {
            "record_id": rid,
            "intent_summary": intent,
            "prior_pilot_ambiguity_types": prior_amb,
            "debater_a": a,
            "debater_b": b,
            "adjudicator": adj,
            "final_pilot_ambiguity_types": final_types,
            "final_suggested_route": suggested,
            "final_reason": final.get("reason"),
            "accept_debater": final.get("accept_debater"),
            "dissent_notes": final.get("dissent_notes"),
            "gold_route": gold_route,
            "suggested_match_gold": suggested == gold_route if suggested else False,
            "manager_watch_routes": routes,
            "manager_gf_match_gold": routes["goal_first_manager_v2"] == gold_route,
            "latency_ms": (time.perf_counter() - started) * 1000.0,
            "model_id": BASE_MODEL,
            "failed": bool(adj.get("failed")),
            "reused_intent": True,
            "gpu_repaired": True,
        }
        existing[rid] = row
        if adj.get("failed"):
            still_bad.append(rid)
        else:
            repaired += 1
        print(f"repaired {rid} route={suggested} failed={adj.get('failed')}")

    # Rewrite full ordered debate file
    out_jsonl = out / "ambiguity_debate_adjudication.jsonl"
    order = [str(r["record_id"]) for r in p120.load_jsonl(root / "data/annotations/pilot_120_v1/source_canonical.jsonl")]
    with out_jsonl.open("w", encoding="utf-8") as handle:
        for rid in order:
            if rid not in existing:
                raise SystemExit(f"missing_row_after_repair:{rid}")
            handle.write(json.dumps(existing[rid], ensure_ascii=False, sort_keys=True) + "\n")

    n_ok = sum(1 for r in existing.values() if not r.get("failed"))
    summary = {
        "status": "COMPLETE_GPU_REPAIR",
        "n": len(existing),
        "n_ok": n_ok,
        "n_failed": len(existing) - n_ok,
        "repaired_attempted": len(ids),
        "repaired_ok": repaired,
        "still_bad": still_bad,
        "debate_path": str(out_jsonl).replace("\\", "/"),
    }
    write_json(out / "ambiguity_debate_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if not still_bad else 2


if __name__ == "__main__":
    raise SystemExit(main())
