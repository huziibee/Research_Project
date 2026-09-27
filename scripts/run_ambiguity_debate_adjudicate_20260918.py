#!/usr/bin/env python3
"""Two LLM debaters + one adjudicator for ambiguity types and suggested route.

Reuses frozen intent_summary from GF-v2 predictions. Does not re-emit intent.
Writes per-role outputs and a final adjudication JSONL with written reasons.
Optionally patches ambiguity into analysis and CPU-re-routes managers so we can
watch how the manager handles compound ambiguities after capability work.
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
from ambiguity_manager.systems.goal_first_analysis_v2 import CANONICAL_AMBIGUITY  # noqa: E402
from evaluate_pilot_120_direct_base import (  # noqa: E402
    BASE_MODEL,
    BASE_REVISION,
    sampling_generate_kwargs,
    set_run_seed,
)
from lib_capability_debate_20260918 import (  # noqa: E402
    analysis_dict_from_pred,
    analysis_from_dict,
    append_jsonl,
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
    slice_stats,
    write_json,
    CAPABILITY_SET,
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
    model: Any,
    tokenizer: Any,
    *,
    role: str,
    source: dict[str, Any],
    intent: str,
    prior_amb: list[str],
    other_argument: str | None,
    temperature: float,
    max_new_tokens: int,
    retry_max: int,
) -> dict[str, Any]:
    prompt = build_debate_prompt(
        role,
        source,
        intent_summary=intent,
        prior_ambiguity=prior_amb,
        other_argument=other_argument,
    )
    raw = ""
    parsed = None
    meta: dict[str, Any] = {}
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, retry_max + 1):
        use_prompt = prompt
        if attempt > 1:
            use_prompt = (
                prompt
                + "\nPrevious output was invalid. Return ONLY valid JSON with "
                "pilot_ambiguity_types, suggested_route, confidence, reason.\n"
            )
        raw = _generate(
            model, tokenizer, use_prompt, temperature=temperature, max_new_tokens=max_new_tokens
        )
        obj = extract_json_object(raw)
        parsed, meta = normalise_debate_obj(obj)
        ok = parsed is not None and not parsed.get("route_missing")
        attempts.append(
            {
                "attempt": attempt,
                "raw_chars": len(raw),
                "ok": ok,
                "error": None if ok else meta.get("error"),
            }
        )
        if ok:
            break
    return {
        "role": role,
        "parsed": parsed,
        "raw_output": raw,
        "attempts": attempts,
        "failed": parsed is None or bool((parsed or {}).get("route_missing")),
        "error": None
        if parsed is not None and not (parsed or {}).get("route_missing")
        else meta.get("error", "parse_failed"),
    }


def _patch_ambiguity(analysis: dict[str, Any], pilot_types: list[str]) -> dict[str, Any]:
    findings = [
        f
        for f in list(analysis.get("findings") or [])
        if not str(f).startswith("pilot_ambiguity_types:")
    ]
    findings.append(
        "pilot_ambiguity_types:" + json.dumps(pilot_types, separators=(",", ":"))
    )
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
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--capability-judgments",
        type=Path,
        default=None,
        help="Optional capability judgments to apply before manager watch re-route.",
    )
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--adjudicator-temperature", type=float, default=0.0)
    parser.add_argument("--max-new-tokens", type=int, default=384)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--retry-max", type=int, default=2)
    args = parser.parse_args()
    set_run_seed(args.seed)

    root = args.root.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    debate_path = out / "ambiguity_debate_adjudication.jsonl"
    progress_path = out / "debate_progress.json"

    source_rows = p120.load_jsonl(root / "data/annotations/pilot_120_v1/source_canonical.jsonl")
    gold = load_jsonl_by_id(root / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl")
    preds = load_jsonl_by_id(args.predictions.resolve())
    cap_judgments = (
        load_jsonl_by_id(args.capability_judgments.resolve())
        if args.capability_judgments
        else {}
    )
    if args.limit and args.limit > 0:
        source_rows = source_rows[: args.limit]

    done = load_jsonl_by_id(debate_path) if debate_path.exists() else {}
    todo = [row for row in source_rows if str(row["record_id"]) not in done]
    write_json(
        progress_path,
        {
            "status": "STARTING",
            "n_done": len(done),
            "n_todo": len(todo),
            "reused_intent": True,
            "temperature_debaters": args.temperature,
            "temperature_adjudicator": args.adjudicator_temperature,
        },
    )
    if not todo:
        print(f"already_complete n={len(done)}")
        return 0

    model, tokenizer = _load_model()
    watch_rows: list[dict[str, Any]] = []

    for source in todo:
        rid = str(source["record_id"])
        pred = preds[rid]
        intent = intent_from_pred(pred)
        if not intent or analysis_dict_from_pred(pred) is None:
            gold_route = norm_route(str((gold.get(rid) or {}).get("terminal_strategy")))
            row = {
                "record_id": rid,
                "intent_summary": intent or None,
                "failed": True,
                "error": "missing_intent_or_analysis_skip",
                "gold_route": gold_route,
                "reused_intent": True,
                "manager_watch_routes": {
                    "goal_first_manager_v2": "missing",
                    "rich_conservative_manager_v2": "missing",
                    "degree_based_router_v2": "missing",
                },
            }
            append_jsonl(debate_path, row)
            done[rid] = row
            print(f"skip {rid} missing_intent_or_analysis")
            continue
        prior_amb = prior_ambiguity_from_pred(pred)
        started = time.perf_counter()

        a = _role_once(
            model,
            tokenizer,
            role="debater_a",
            source=source,
            intent=intent,
            prior_amb=prior_amb,
            other_argument=None,
            temperature=args.temperature,
            max_new_tokens=args.max_new_tokens,
            retry_max=args.retry_max,
        )
        b = _role_once(
            model,
            tokenizer,
            role="debater_b",
            source=source,
            intent=intent,
            prior_amb=prior_amb,
            other_argument=None,
            temperature=args.temperature,
            max_new_tokens=args.max_new_tokens,
            retry_max=args.retry_max,
        )
        other = json.dumps(
            {
                "debater_a": a.get("parsed"),
                "debater_b": b.get("parsed"),
                "debater_a_reason": (a.get("parsed") or {}).get("reason") if a.get("parsed") else a.get("error"),
                "debater_b_reason": (b.get("parsed") or {}).get("reason") if b.get("parsed") else b.get("error"),
            },
            ensure_ascii=False,
            indent=2,
        )
        adj = _role_once(
            model,
            tokenizer,
            role="adjudicator",
            source=source,
            intent=intent,
            prior_amb=prior_amb,
            other_argument=other,
            temperature=args.adjudicator_temperature,
            max_new_tokens=args.max_new_tokens,
            retry_max=args.retry_max,
        )

        gold_route = norm_route(str((gold.get(rid) or {}).get("terminal_strategy")))
        final = adj.get("parsed") or {}
        final_types = list(final.get("pilot_ambiguity_types") or [])
        suggested = final.get("suggested_route")

        # Manager watch: patch capability (if available) + adjudicated ambiguity, re-route.
        analysis = analysis_dict_from_pred(pred)
        cap_j = cap_judgments.get(rid)
        if cap_j and not cap_j.get("failed") and cap_j.get("capability_status") in CAPABILITY_SET:
            analysis = patch_capability_in_analysis(analysis, str(cap_j["capability_status"]))
        elif prior_capability_from_pred(pred) in CAPABILITY_SET:
            # keep prior via no-op patch of prior
            analysis = patch_capability_in_analysis(
                analysis, str(prior_capability_from_pred(pred))
            )
        if final_types or adj.get("parsed"):
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
        }
        append_jsonl(debate_path, row)
        done[rid] = row
        watch_rows.append(
            {
                "record_id": rid,
                "gold_route": gold_route,
                "goal_first_manager_v2": routes["goal_first_manager_v2"],
                "rich_conservative_manager_v2": routes["rich_conservative_manager_v2"],
                "degree_based_router_v2": routes["degree_based_router_v2"],
                "adjudicator_suggested": suggested or "missing",
            }
        )
        write_json(
            progress_path,
            {
                "status": "RUNNING",
                "last_record_id": rid,
                "n_done": len(done),
                "n_todo": len(source_rows) - len(done),
            },
        )
        print(
            f"debate {rid} types={final_types} route={suggested} "
            f"gf={routes['goal_first_manager_v2']} gold={gold_route}"
        )

    # Rebuild watch_rows from all done for summary (resume-safe).
    watch_rows = []
    suggested_rows = []
    for rid, row in done.items():
        gold_route = row.get("gold_route") or norm_route(
            str((gold.get(rid) or {}).get("terminal_strategy"))
        )
        routes = row.get("manager_watch_routes") or {}
        watch_rows.append(
            {
                "record_id": rid,
                "gold_route": gold_route,
                "goal_first_manager_v2": routes.get("goal_first_manager_v2", "missing"),
                "rich_conservative_manager_v2": routes.get(
                    "rich_conservative_manager_v2", "missing"
                ),
                "degree_based_router_v2": routes.get("degree_based_router_v2", "missing"),
            }
        )
        suggested_rows.append(
            {
                "record_id": rid,
                "gold_route": gold_route,
                "adjudicator_suggested": row.get("final_suggested_route") or "missing",
            }
        )

    systems = [
        "goal_first_manager_v2",
        "rich_conservative_manager_v2",
        "degree_based_router_v2",
    ]
    n_ok = sum(1 for r in done.values() if not r.get("failed"))
    summary = {
        "status": "COMPLETE",
        "n": len(done),
        "n_ok": n_ok,
        "n_failed": len(done) - n_ok,
        "suggested_route_accuracy": slice_stats(
            [
                {
                    "record_id": r["record_id"],
                    "gold_route": r["gold_route"],
                    "adjudicator_suggested": r["adjudicator_suggested"],
                }
                for r in suggested_rows
            ],
            "adjudicator_suggested",
        ),
        "manager_watch_after_patch": {sid: slice_stats(watch_rows, sid) for sid in systems},
        "reused_intent": True,
        "capability_judgments_applied": bool(cap_judgments),
        "debate_path": str(debate_path).replace("\\", "/"),
        "model": BASE_MODEL,
        "temperature_debaters": args.temperature,
        "temperature_adjudicator": args.adjudicator_temperature,
    }
    write_json(out / "ambiguity_debate_summary.json", summary)
    write_json(progress_path, {"status": "COMPLETE", **summary})
    print(json.dumps(summary, indent=2))
    return 0 if n_ok == len(done) else 2


if __name__ == "__main__":
    raise SystemExit(main())
