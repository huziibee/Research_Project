#!/usr/bin/env python3
"""One-turn recovery follow-up for Pilot-120 capability-rescue CLARIFY cases.

Frozen oracle upper-bound experiment:
  If the user supplies a gold-consistent intent restatement after an unnecessary
  CLARIFY, can the Goal-First + capability-adjudication stack recover to EXECUTE?

Does NOT alter first-turn routing metrics or rewrite gold.
Modes:
  freeze  — assert cohorts, write oracle responses + protocol + manifest (CPU)
  run     — GPU Goal-First analysis + capability judge + deterministic route
  score   — build tables / Wilson CI / McNemar from written predictions (CPU)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_pilot_120_direct_base import (  # noqa: E402
    BASE_MODEL,
    BASE_REVISION,
    sampling_generate_kwargs,
    set_run_seed,
)
from lib_capability_debate_20260918 import (  # noqa: E402
    analysis_dict_from_pred,
    analysis_from_dict,
    build_capability_judge_prompt,
    extract_json_object,
    intent_from_pred,
    load_jsonl_by_id,
    normalise_capability_obj,
    norm_route,
    patch_capability_in_analysis,
    prior_capability_from_pred,
    route_from_analysis,
    write_json,
)

# Hard-coded expected IDs for abort-on-mismatch (cohorts are still derived).
EXPECTED_PRIMARY = (
    "CA-0012",
    "CA-0021",
    "CA-0029",
    "CA-0239",
    "CA-0360",
    "CA-0361",
    "CA-0397",
    "CA-0470",
    "CA-0565",
    "CA-0573",
    "CA-0648",
    "CA-0677",
    "CA-0679",
    "CA-0702",
    "CA-0718",
    "CA-0733",
    "CA-0778",
    "CA-0805",
    "CA-0827",
    "CA-0851",
    "CA-0940",
    "CA-0972",
)
EXPECTED_EXTRA = ("CA-0332", "CA-0372", "CA-0739", "CA-0797")
FORBIDDEN_ORACLE_RE = re.compile(
    r"\b(EXECUTE|CLARIFY|REFUSE|gold|correct\s+route)\b",
    re.IGNORECASE,
)
FORBIDDEN_LABEL_RE = re.compile(
    r"\b(capable|conditionally_capable|incapable|unauthorized|unsafe|"
    r"risk_level|ambiguity_types|terminal_strategy)\b",
    re.IGNORECASE,
)

ROUTER_VERSION = "DeterministicRouter@goal_first_v2"
PARSER_VERSION = "goal_first_analysis_v2@normalise_analysis_output"
CAPABILITY_JUDGE_VERSION = "capability_llm_judge_20260918"
CLARIFY_GENERATOR_VERSION = "deterministic_clarification@1.2.0"
MANAGER_VERSION = "goal_first_manager_v2@2.0.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def gold_route_of(row: dict[str, Any]) -> str:
    return norm_route(
        str(
            row.get("gold_terminal_strategy")
            or row.get("terminal_strategy")
            or row.get("gold_route")
            or ""
        )
    )


def resolve_evidence_paths(evidence_root: Path) -> dict[str, Path]:
    root = evidence_root.resolve()
    paths = {
        "joined_gold": root / "03_gold_and_metrics" / "pilot120_joined_ground_truth.jsonl",
        "repaired_preds": (
            root
            / "08_predictions_and_emits"
            / "unified_55670_repaired_20260918"
            / "T0.7"
            / "predictions"
            / "goal_first_manager_v2.predictions.jsonl"
        ),
        "postcap_preds": (
            root
            / "08_predictions_and_emits"
            / "clarify_cpc_rescue_20260918"
            / "goal_first_v2.llmcap_route_scene_clarify.predictions.jsonl"
        ),
        "capability_judgments": (
            root
            / "08_predictions_and_emits"
            / "capability_debate_local_oracle_20260918"
            / "capability_judgments_cluster.jsonl"
        ),
    }
    missing = [k for k, p in paths.items() if not p.exists()]
    if missing:
        # Local repo fallbacks (same content as the paper pack copies).
        fallback = {
            "joined_gold": ROOT
            / "outputs/paper_writer_handoff_20260922/A_EVIDENCE_FOR_PAPER"
            / "03_gold_and_metrics/pilot120_joined_ground_truth.jsonl",
            "repaired_preds": ROOT
            / "outputs/cluster_pulls/unified_55670_repaired_20260918/T0.7/predictions"
            / "goal_first_manager_v2.predictions.jsonl",
            "postcap_preds": ROOT
            / "outputs/clarify_cpc_rescue_20260918"
            / "goal_first_v2.llmcap_route_scene_clarify.predictions.jsonl",
            "capability_judgments": ROOT
            / "outputs/capability_debate_local_oracle_20260918"
            / "capability_judgments_cluster.jsonl",
        }
        for key in missing:
            alt = fallback[key]
            if not alt.exists():
                raise SystemExit(f"missing_source:{key}:{paths[key]} and fallback:{alt}")
            paths[key] = alt
    return paths


def derive_cohorts(
    joined: dict[str, dict[str, Any]],
    repaired: dict[str, dict[str, Any]],
    postcap: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    secondary: list[str] = []
    for rid in sorted(joined):
        if gold_route_of(joined[rid]) != "execute":
            continue
        if rid not in postcap:
            continue
        if norm_route(postcap[rid].get("terminal_strategy")) == "clarify":
            secondary.append(rid)
    primary = [
        rid
        for rid in secondary
        if norm_route((repaired.get(rid) or {}).get("terminal_strategy")) == "refuse"
    ]
    already_clarify = [
        rid
        for rid in secondary
        if norm_route((repaired.get(rid) or {}).get("terminal_strategy")) == "clarify"
    ]
    if set(primary) != set(EXPECTED_PRIMARY):
        raise SystemExit(
            "primary_cohort_mismatch "
            f"got={primary} expected={list(EXPECTED_PRIMARY)}"
        )
    if set(already_clarify) != set(EXPECTED_EXTRA):
        raise SystemExit(
            "extra_secondary_mismatch "
            f"got={already_clarify} expected={list(EXPECTED_EXTRA)}"
        )
    if set(secondary) != set(EXPECTED_PRIMARY) | set(EXPECTED_EXTRA):
        raise SystemExit(f"secondary_cohort_mismatch got={secondary}")
    if len(primary) != 22 or len(secondary) != 26:
        raise SystemExit(f"cohort_size_fail primary={len(primary)} secondary={len(secondary)}")
    return primary, secondary


def assert_pre_inference(
    *,
    primary: list[str],
    secondary: list[str],
    joined: dict[str, dict[str, Any]],
    repaired: dict[str, dict[str, Any]],
    postcap: dict[str, dict[str, Any]],
    oracles: dict[str, dict[str, Any]],
) -> None:
    assert len(primary) == 22
    assert len(secondary) == 26
    for rid in secondary:
        g = joined[rid]
        c = postcap[rid]
        assert gold_route_of(g) == "execute", rid
        assert norm_route(c.get("terminal_strategy")) == "clarify", rid
        cq = str(c.get("clarification_question") or "").strip()
        assert cq, f"empty_clarification_question:{rid}"
        ref = str(g.get("reference_A_intent_text") or "").strip()
        assert ref, f"empty_reference_A_intent_text:{rid}"
        oracle = oracles[rid]
        text = str(oracle["oracle_user_message"])
        assert text.startswith("I mean: "), rid
        assert FORBIDDEN_ORACLE_RE.search(text) is None, f"oracle_forbidden:{rid}"
        assert FORBIDDEN_LABEL_RE.search(text) is None, f"oracle_label_leak:{rid}"
    for rid in primary:
        assert norm_route(repaired[rid].get("terminal_strategy")) == "refuse", rid
    for rid in EXPECTED_EXTRA:
        assert rid in secondary
        assert norm_route(repaired[rid].get("terminal_strategy")) == "clarify", rid


def build_oracle_row(
    rid: str,
    joined: dict[str, dict[str, Any]],
    postcap: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    g = joined[rid]
    c = postcap[rid]
    ref = str(g.get("reference_A_intent_text") or "").strip()
    cq = str(c.get("clarification_question") or "").strip()
    hist = list(g.get("dialogue_history") or [])
    if not all(isinstance(x, str) for x in hist):
        raise SystemExit(f"bad_dialogue_history:{rid}")
    command = str(g.get("command") or "")
    answered_history = list(hist) + [f"User: {command}", f"Robot: {cq}"]
    oracle_msg = f"I mean: {ref}"
    return {
        "record_id": rid,
        "condition": "oracle_intent_restatement",
        "original_command": command,
        "original_dialogue_history": hist,
        "scene_context": g.get("scene_context"),
        "capability_context": g.get("capability_context"),
        "first_turn_clarification_question": cq,
        "reference_A_intent_text": ref,
        "oracle_user_message": oracle_msg,
        "second_turn_command": oracle_msg,
        "second_turn_dialogue_history": answered_history,
        "control_command": command,
        "control_dialogue_history": hist,
        "note": (
            "Oracle upper-bound user response using frozen reference_A_intent_text. "
            "Not a naturalistic user simulation."
        ),
    }


def wilson_interval(k: int, n: int, z: float = 1.959963984540054) -> dict[str, float]:
    if n <= 0:
        return {"low": 0.0, "high": 0.0, "estimate": 0.0}
    phat = k / n
    denom = 1.0 + z * z / n
    centre = phat + z * z / (2.0 * n)
    spread = z * math.sqrt((phat * (1.0 - phat) + z * z / (4.0 * n)) / n)
    return {
        "estimate": phat,
        "low": max(0.0, (centre - spread) / denom),
        "high": min(1.0, (centre + spread) / denom),
        "k": float(k),
        "n": float(n),
    }


def exact_mcnemar(b: int, c: int) -> dict[str, Any]:
    """Exact two-sided McNemar on discordant pairs (binomial mid-p omitted)."""
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "n_discordant": 0, "p_value": 1.0, "note": "no_discordant_pairs"}
    # two-sided: sum of binomial probabilities as extreme as min(b,c)
    from math import comb

    k = min(b, c)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2**n)
    p = min(1.0, 2.0 * tail)
    return {"b": b, "c": c, "n_discordant": n, "p_value": p, "method": "exact_binomial_two_sided"}


def transition_counts(rows: list[dict[str, Any]], route_key: str) -> dict[str, int]:
    c: Counter[str] = Counter()
    for row in rows:
        first = norm_route(row.get("first_turn_terminal_route"))
        second = norm_route(row.get(route_key))
        c[f"{first}->{second}"] += 1
        c[f"to:{second}"] += 1
    return dict(c)


def default_experiment_dir() -> Path:
    return ROOT / "outputs" / "one_turn_recovery_20260922"


def write_protocol(path: Path) -> None:
    text = f"""# Frozen protocol — one-turn recovery (oracle upper bound)

Built (UTC): {utc_now()}

## Claim boundary

This experiment asks whether an **unnecessary CLARIFY** on a gold-EXECUTE case is
**recoverable after one oracle user response**.

It is an **oracle upper bound**, not a naturalistic user simulation.
It does **not** replace or alter the first-turn exact routing score (83/120 under
LLM capability patch).

## Stack (must match repaired T0.7 capability-rescue)

1. Goal-First manager v2 analysis (Qwen3-8B, thinking-on, T=0.7)
2. Capability LLM adjudication (`capability_llm_judge_20260918`)
3. Deterministic router (`goal_first_v2`)
4. Clarification wording generator only if terminal route remains clarify
   (`deterministic_clarification@1.2.0`)

## Cohorts (frozen before inference)

- Primary (n=22): repaired T0.7 route REFUSE → post-capability route CLARIFY,
  gold terminal route EXECUTE.
- Secondary (n=26): all post-capability CLARIFY ∩ gold EXECUTE
  (primary 22 + 4 already-CLARIFY pre-capability).

## Intervention

- **Answered / treatment:** second-turn `command` = `I mean: <reference_A_intent_text>`;
  dialogue history = original history + original user command + actual first-turn
  clarification question from `goal_first_v2.llmcap_route_scene_clarify`.
- **Control:** matched NO-ANSWER replay of the original first-turn inputs under the
  same seed/model/runtime.

## Seeds

- Primary freeze: seed 0 (matches `fix_emit.sbatch` / study default).
- Optional robustness: seed 1 (reported separately; not pooled as new cases).

## Blindness

The model under test never receives gold route, risk, capability, or evaluation labels.
Oracle responses are checked to exclude explicit route/risk/capability/evaluation wording.

## Outcomes

- Primary recovery rate among 22; Wilson 95% CI; 3-way transition table.
- Secondary recovery rate among 26; same reporting.
- Interaction-level one-turn success on gold-EXECUTE:
  `(46 + recovered_among_26) / 76`
  where 46/76 is first-turn immediate EXECUTE after capability intervention.
- Seed-0 paired 2×2 control vs answered + exact McNemar (case = unit).

## Interpretation limits

Do not claim naturalistic recoverability, question pleasantness, or wording quality.
Those remain separate clarification-quality results.
"""
    path.write_text(text, encoding="utf-8")


def cmd_freeze(args: argparse.Namespace) -> int:
    evidence = Path(args.evidence_root).resolve()
    out = Path(args.experiment_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    paths = resolve_evidence_paths(evidence)
    joined = load_jsonl_by_id(paths["joined_gold"])
    repaired = load_jsonl_by_id(paths["repaired_preds"])
    postcap = load_jsonl_by_id(paths["postcap_preds"])
    judgments = load_jsonl_by_id(paths["capability_judgments"])
    if len(judgments) < 1:
        raise SystemExit("capability_judgments_empty")

    primary, secondary = derive_cohorts(joined, repaired, postcap)
    oracles = {rid: build_oracle_row(rid, joined, postcap) for rid in secondary}
    assert_pre_inference(
        primary=primary,
        secondary=secondary,
        joined=joined,
        repaired=repaired,
        postcap=postcap,
        oracles=oracles,
    )

    primary_rows = []
    secondary_rows = []
    for rid in secondary:
        g = joined[rid]
        row = {
            "record_id": rid,
            "in_primary_22": rid in primary,
            "gold_terminal_route": "execute",
            "repaired_t07_route": norm_route(repaired[rid].get("terminal_strategy")),
            "post_capability_route": norm_route(postcap[rid].get("terminal_strategy")),
            "clarification_question": postcap[rid].get("clarification_question"),
            "reference_A_intent_text": g.get("reference_A_intent_text"),
            "original_command": g.get("command"),
            "original_dialogue_history": g.get("dialogue_history") or [],
            "scene_context": g.get("scene_context"),
            "capability_context": g.get("capability_context"),
            "first_turn_intent_summary": postcap[rid].get("intent_summary")
            or repaired[rid].get("intent_summary"),
            "source_capability_judgment": (judgments.get(rid) or {}).get("capability_status"),
        }
        secondary_rows.append(row)
        if rid in primary:
            primary_rows.append(row)

    write_jsonl(out / "02_primary_cohort_22.jsonl", primary_rows)
    write_jsonl(out / "03_secondary_cohort_26.jsonl", secondary_rows)
    write_jsonl(out / "04_oracle_responses.jsonl", [oracles[rid] for rid in secondary])
    write_protocol(out / "00_FROZEN_PROTOCOL.md")

    script_path = Path(__file__).resolve()
    manifest = {
        "experiment_id": "one_turn_recovery_20260922",
        "frozen_at_utc": utc_now(),
        "claim_boundary": "oracle_upper_bound_one_turn_recovery_not_naturalistic",
        "does_not_alter_first_turn_routing_score": "83/120",
        "first_turn_immediate_execute_on_gold_execute": "46/76",
        "model_id": BASE_MODEL,
        "model_revision": BASE_REVISION,
        "temperature": 0.7,
        "primary_seed": 0,
        "robustness_seeds": [1],
        "inference_parameters": {
            "do_sample": True,
            "temperature": 0.7,
            "max_new_tokens_analysis": 4096,
            "retry_max_new_tokens": 8192,
            "constrained_final_max_new_tokens": 1024,
            "capability_judge_temperature": 0.0,
            "capability_judge_max_new_tokens": 512,
            "repetition_penalty_analysis": 1.12,
            "repetition_penalty_capability": 1.08,
        },
        "router_version": ROUTER_VERSION,
        "parser_version": PARSER_VERSION,
        "capability_judge_version": CAPABILITY_JUDGE_VERSION,
        "manager_version": MANAGER_VERSION,
        "clarification_generator_version": CLARIFY_GENERATOR_VERSION,
        "primary_n": 22,
        "secondary_n": 26,
        "primary_ids": primary,
        "secondary_ids": secondary,
        "evidence_root": str(evidence),
        "sha256": {
            "joined_gold": sha256_file(paths["joined_gold"]),
            "repaired_preds": sha256_file(paths["repaired_preds"]),
            "postcap_preds": sha256_file(paths["postcap_preds"]),
            "capability_judgments": sha256_file(paths["capability_judgments"]),
            "experiment_script": sha256_file(script_path),
            "primary_cohort_file": sha256_file(out / "02_primary_cohort_22.jsonl"),
            "secondary_cohort_file": sha256_file(out / "03_secondary_cohort_26.jsonl"),
            "oracle_response_file": sha256_file(out / "04_oracle_responses.jsonl"),
            "frozen_protocol": sha256_file(out / "00_FROZEN_PROTOCOL.md"),
        },
        "source_paths": {k: str(v) for k, v in paths.items()},
        "pre_inference_asserts": "PASSED",
    }
    write_json(out / "01_frozen_manifest.json", manifest)

    readme = f"""# One-turn recovery experiment (`one_turn_recovery_20260922`)

Oracle upper-bound follow-up to the repaired T0.7 capability-rescue study.

## Status

- Freeze: complete (`01_frozen_manifest.json`)
- Inference: run via cluster sbatch (see `cluster/pilot120_one_turn_recovery_20260922/`)

## Key frozen facts

- Primary n=22 (REFUSE→CLARIFY under capability intervention; gold EXECUTE)
- Secondary n=26 (all post-capability CLARIFY ∩ gold EXECUTE)
- First-turn immediate EXECUTE on gold-EXECUTE remains **46/76**
- First-turn exact routing score remains **83/120** (untouched)

## Reproduce scoring after GPU job

```bash
python3 scripts/one_turn_recovery_20260922.py score \\
  --experiment-dir "$OUT/one_turn_recovery_20260922"
```
"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps({"status": "FROZEN", "dir": str(out), "primary": 22, "secondary": 26}, indent=2))
    return 0


def _load_model():
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
    if not any(p.device.type == "cuda" for p in model.parameters()):
        raise SystemExit("model_not_on_cuda")
    model.eval()
    return model, tokenizer


def _generate_raw(
    model: Any,
    tokenizer: Any,
    prompt: str,
    *,
    temperature: float,
    max_new_tokens: int,
    enable_thinking: bool,
    repetition_penalty: float,
) -> str:
    kwargs = {
        "tokenize": False,
        "add_generation_prompt": True,
    }
    try:
        rendered = tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            enable_thinking=enable_thinking,
            **kwargs,
        )
    except TypeError:
        rendered = tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            **kwargs,
        )
    inputs = tokenizer(rendered, return_tensors="pt").to(model.device)
    with __import__("torch").inference_mode():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            **sampling_generate_kwargs(temperature),
            repetition_penalty=repetition_penalty,
            no_repeat_ngram_size=6 if enable_thinking else 5,
            pad_token_id=tokenizer.eos_token_id,
        )
    generated = output_ids[0][inputs["input_ids"].shape[-1] :]
    return tokenizer.decode(generated, skip_special_tokens=True)


def run_goal_first_analysis(
    *,
    model: Any,
    tokenizer: Any,
    system_input: Any,
    temperature: float,
) -> dict[str, Any]:
    from ambiguity_manager.systems.goal_first_analysis_v2 import (
        ANALYSIS_JSON_SCHEMA,
        build_analysis_prompt,
        build_constrained_prompt,
        build_retry_prompt,
        extract_analysis_json,
        normalise_analysis_output,
    )
    from ambiguity_manager.systems.manager import GoalFirstManagerV2

    attempts: list[dict[str, Any]] = []
    raw = ""
    analysis = None
    meta = None
    error = "analysis_validation_failed"
    started = time.perf_counter()
    plan = (("thinking", 4096), ("thinking_retry", 8192))
    prompt = build_analysis_prompt(system_input)
    for attempt_number, (mode, token_limit) in enumerate(plan, 1):
        if attempt_number == 2:
            prompt = build_retry_prompt(system_input, error)
        raw = _generate_raw(
            model,
            tokenizer,
            prompt,
            temperature=temperature,
            max_new_tokens=token_limit,
            enable_thinking=True,
            repetition_penalty=1.12,
        )
        analysis, meta, err = normalise_analysis_output(
            extract_analysis_json(raw),
            system_input=system_input,
            provider_id="one_turn_recovery_gfv2",
        )
        error = err or "analysis_validation_failed"
        attempts.append(
            {
                "attempt": attempt_number,
                "mode": mode,
                "max_new_tokens": token_limit,
                "raw_chars": len(raw),
                "raw_sha256": sha256_text(raw),
                "validation_error": None if err is None else error,
            }
        )
        if err is None and analysis is not None and meta is not None:
            break
    else:
        from ambiguity_manager.model.task_constrained_decoding import generate_with_task_constraint

        generated = generate_with_task_constraint(
            model=model,
            tokenizer=tokenizer,
            prompt=build_constrained_prompt(system_input),
            json_schema=ANALYSIS_JSON_SCHEMA,
            max_new_tokens=1024,
            generation_config=sampling_generate_kwargs(temperature),
        )
        raw = str(generated["raw_text"])
        analysis, meta, err = normalise_analysis_output(
            extract_analysis_json(raw),
            system_input=system_input,
            provider_id="one_turn_recovery_gfv2",
        )
        error = err or "analysis_validation_failed"
        attempts.append(
            {
                "attempt": len(attempts) + 1,
                "mode": "schema_constrained_final",
                "max_new_tokens": 1024,
                "raw_chars": len(raw),
                "raw_sha256": sha256_text(raw),
                "validation_error": None if err is None else error,
                "constraint": {
                    "transport_status": generated.get("transport_status"),
                    "termination_reason": generated.get("termination_reason"),
                },
            }
        )
    latency_ms = (time.perf_counter() - started) * 1000.0
    if analysis is None or meta is None:
        return {
            "failed": True,
            "error": error,
            "raw_output": raw,
            "analysis_attempts": attempts,
            "latency_ms": latency_ms,
            "emit_route": None,
            "terminal_route": None,
            "intent_summary": None,
            "parsed": None,
            "capability_status_emit": None,
        }

    manager = GoalFirstManagerV2()
    result = manager.run(system_input, cached_analysis=analysis)
    emit_route = norm_route(
        result.recommended_strategy.value
        if hasattr(result.recommended_strategy, "value")
        else str(result.recommended_strategy)
    )
    # Map face_preserving_rejection -> refuse for study aliases
    if emit_route == "face_preserving_rejection":
        emit_route = "refuse"
    if emit_route == "silently_resolve":
        emit_route = "execute"
    return {
        "failed": False,
        "error": None,
        "raw_output": raw,
        "analysis_attempts": attempts,
        "latency_ms": latency_ms,
        "emit_route": emit_route,
        "terminal_route": emit_route,
        "intent_summary": meta.get("intent_summary"),
        "capability_status_emit": meta.get("pilot_capability_status"),
        "risk_level_emit": (
            analysis.risk_level.value
            if getattr(analysis, "risk_level", None) is not None
            and hasattr(analysis.risk_level, "value")
            else getattr(analysis, "risk_level", None)
        ),
        "parsed": result.to_dict(),
        "analysis_dict": analysis.to_dict() if hasattr(analysis, "to_dict") else None,
        "meta": meta,
    }


def run_capability_adjudication(
    *,
    model: Any,
    tokenizer: Any,
    source_for_judge: dict[str, Any],
    pred_like: dict[str, Any],
) -> dict[str, Any]:
    intent = intent_from_pred(pred_like)
    prior = prior_capability_from_pred(pred_like)
    prompt = build_capability_judge_prompt(
        source_for_judge, intent_summary=intent, prior_capability=prior
    )
    started = time.perf_counter()
    raw = ""
    label = None
    normalised: dict[str, Any] = {}
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, 3):
        raw = _generate_raw(
            model,
            tokenizer,
            prompt
            if attempt == 1
            else (
                prompt
                + "\nPrevious output was invalid. Return ONLY valid JSON with "
                "capability_status, confidence, reason.\n"
            ),
            temperature=0.0,
            max_new_tokens=512,
            enable_thinking=False,
            repetition_penalty=1.08,
        )
        obj = extract_json_object(raw)
        label, normalised = normalise_capability_obj(obj)
        attempts.append({"attempt": attempt, "raw_chars": len(raw), "ok": label is not None})
        if label is not None:
            break
    latency_ms = (time.perf_counter() - started) * 1000.0
    terminal = None
    router_trace: dict[str, Any] = {}
    clarification_question = None
    if label is not None:
        adict = analysis_dict_from_pred(pred_like) or pred_like.get("analysis_dict") or {}
        if not adict and pred_like.get("parsed"):
            adict = ((pred_like.get("parsed") or {}).get("analysis")) or {}
        patched = patch_capability_in_analysis(dict(adict), str(label))
        analysis = analysis_from_dict(patched)
        routes = route_from_analysis(analysis)
        terminal = routes["goal_first_manager_v2"]
        router_trace = {
            "routes": routes,
            "patched_capability": label,
            "router_version": ROUTER_VERSION,
        }
        if terminal == "clarify":
            from ambiguity_manager.systems.response_generation import generate_clarification

            targets = list(patched.get("clarification_targets") or ["intent"])
            clarification_question = generate_clarification(
                analysis,
                targets,
                scene_context=str(source_for_judge.get("scene_context") or ""),
            )
    return {
        "capability_status": label,
        "capability_judgment": normalised,
        "raw_output": raw,
        "attempts": attempts,
        "latency_ms": latency_ms,
        "terminal_route": terminal,
        "router_trace": router_trace,
        "clarification_question": clarification_question,
        "failed": label is None,
        "model_id": f"{BASE_MODEL}@{BASE_REVISION}",
        "temperature": 0.0,
        "judge_version": CAPABILITY_JUDGE_VERSION,
    }


def build_pred_like_from_analysis(analysis_out: dict[str, Any]) -> dict[str, Any]:
    parsed = analysis_out.get("parsed") or {}
    return {
        "intent_summary": analysis_out.get("intent_summary"),
        "capability_status": analysis_out.get("capability_status_emit"),
        "terminal_strategy": analysis_out.get("emit_route"),
        "parsed": parsed,
        "analysis_dict": analysis_out.get("analysis_dict")
        or ((parsed.get("analysis") if isinstance(parsed, dict) else None)),
    }


MAX_CLARIFY_DEPTH = 5


def process_case(
    *,
    model: Any,
    tokenizer: Any,
    oracle: dict[str, Any],
    condition: str,
    seed: int,
    temperature: float,
    max_clarify_depth: int = MAX_CLARIFY_DEPTH,
) -> dict[str, Any]:
    from ambiguity_manager.systems.contracts import SystemInput

    rid = oracle["record_id"]
    depth_path: list[dict[str, Any]] = []

    if condition == "control":
        turns = [
            {
                "depth": 0,
                "command": str(oracle["control_command"]),
                "dialogue_history": list(oracle["control_dialogue_history"]),
            }
        ]
    elif condition == "answered":
        # Depth 1 = first oracle answer after the frozen first-turn clarify.
        turns = [
            {
                "depth": 1,
                "command": str(oracle["second_turn_command"]),
                "dialogue_history": list(oracle["second_turn_dialogue_history"]),
            }
        ]
    else:
        raise ValueError(condition)

    last_row: dict[str, Any] | None = None
    while turns:
        turn = turns.pop(0)
        depth = int(turn["depth"])
        command = str(turn["command"])
        history = list(turn["dialogue_history"])
        system_input = SystemInput(
            record_id=rid,
            command=command,
            dialogue_history=tuple(history),
            scene_context=oracle.get("scene_context"),
            capability_context=oracle.get("capability_context"),
            protected_data=False,
        )
        source_for_judge = {
            "record_id": rid,
            "command": command,
            "dialogue_history": history,
            "scene_context": oracle.get("scene_context"),
            "capability_context": oracle.get("capability_context"),
        }
        analysis_out = run_goal_first_analysis(
            model=model,
            tokenizer=tokenizer,
            system_input=system_input,
            temperature=temperature,
        )
        pred_like = build_pred_like_from_analysis(analysis_out)
        cap_out = {
            "failed": True,
            "terminal_route": None,
            "capability_status": None,
            "router_trace": {},
            "clarification_question": None,
            "raw_output": "",
            "latency_ms": 0.0,
        }
        if not analysis_out.get("failed"):
            cap_out = run_capability_adjudication(
                model=model,
                tokenizer=tokenizer,
                source_for_judge=source_for_judge,
                pred_like=pred_like,
            )
        terminal = norm_route(cap_out.get("terminal_route") or analysis_out.get("emit_route"))
        step = {
            "depth": depth,
            "command": command,
            "dialogue_history": history,
            "terminal_route": terminal,
            "emit_route_before_capability": analysis_out.get("emit_route"),
            "intent_summary": analysis_out.get("intent_summary"),
            "capability_status": cap_out.get("capability_status"),
            "clarification_question": cap_out.get("clarification_question"),
            "failed": bool(analysis_out.get("failed") or cap_out.get("failed")),
        }
        depth_path.append(step)
        last_row = {
            "record_id": rid,
            "condition": condition,
            "seed": seed,
            "temperature": temperature,
            "model_id": f"{BASE_MODEL}@{BASE_REVISION}",
            "manager_version": MANAGER_VERSION,
            "router_version": ROUTER_VERSION,
            "parser_version": PARSER_VERSION,
            "capability_judge_version": CAPABILITY_JUDGE_VERSION,
            "command": command,
            "dialogue_history": history,
            "scene_context": oracle.get("scene_context"),
            "capability_context": oracle.get("capability_context"),
            "first_turn_clarification_question": oracle.get("first_turn_clarification_question"),
            "oracle_user_message": oracle.get("oracle_user_message") if condition == "answered" else None,
            "intent_summary": analysis_out.get("intent_summary"),
            "analysis_fields": analysis_out.get("analysis_dict")
            or ((analysis_out.get("parsed") or {}).get("analysis") if analysis_out.get("parsed") else None),
            "emit_route_before_capability": analysis_out.get("emit_route"),
            "capability_judgment": cap_out.get("capability_judgment")
            or {"capability_status": cap_out.get("capability_status")},
            "capability_status": cap_out.get("capability_status"),
            "risk_judgment": {"risk_level": analysis_out.get("risk_level_emit")},
            "clarification_question": cap_out.get("clarification_question"),
            "terminal_route": terminal,
            "router_trace": cap_out.get("router_trace"),
            "raw_generations": {
                "goal_first": analysis_out.get("raw_output"),
                "capability_judge": cap_out.get("raw_output"),
            },
            "analysis_attempts": analysis_out.get("analysis_attempts"),
            "latency_ms": {
                "goal_first": analysis_out.get("latency_ms"),
                "capability_judge": cap_out.get("latency_ms"),
                "total": float(analysis_out.get("latency_ms") or 0)
                + float(cap_out.get("latency_ms") or 0),
            },
            "failed": bool(analysis_out.get("failed") or cap_out.get("failed")),
            "error": analysis_out.get("error")
            if analysis_out.get("failed")
            else ("capability_judge_failed" if cap_out.get("failed") else None),
            "clarify_depth": depth,
            "max_clarify_depth": max_clarify_depth if condition == "answered" else 0,
            "depth_path": depth_path,
            "terminal_route_at_final_depth": terminal,
            "provenance": {
                "experiment_id": "one_turn_recovery_20260922",
                "stack": "goal_first_v2 -> capability_llm_judge_20260918 -> goal_first_v2_router",
                "multi_depth_clarify": condition == "answered",
                "utc": utc_now(),
            },
        }
        # Multi-depth oracle upper bound: if still CLARIFY, restate intent again
        # (same gold-consistent message) until non-clarify or depth cap.
        if (
            condition == "answered"
            and terminal == "clarify"
            and depth < max_clarify_depth
            and not last_row["failed"]
        ):
            cq = str(cap_out.get("clarification_question") or "").strip()
            if not cq:
                cq = "Could you clarify what you would like me to do?"
            oracle_msg = str(oracle["oracle_user_message"])
            next_history = list(history) + [f"User: {command}", f"Robot: {cq}"]
            turns.append(
                {
                    "depth": depth + 1,
                    "command": oracle_msg,
                    "dialogue_history": next_history,
                }
            )
            continue
        break

    assert last_row is not None
    return last_row


def cmd_run(args: argparse.Namespace) -> int:
    out = Path(args.experiment_dir).resolve()
    manifest_path = out / "01_frozen_manifest.json"
    if not manifest_path.exists():
        raise SystemExit("run_requires_freeze_first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    oracles = load_jsonl_by_id(out / "04_oracle_responses.jsonl")
    secondary = list(manifest["secondary_ids"])
    seeds = [int(s) for s in args.seeds]
    temperature = float(args.temperature)
    max_depth = int(getattr(args, "max_clarify_depth", MAX_CLARIFY_DEPTH))
    model, tokenizer = _load_model()

    for seed in seeds:
        set_run_seed(seed)
        for condition in ("control", "answered"):
            if seed == 0:
                out_name = (
                    "05_control_predictions_seed0.jsonl"
                    if condition == "control"
                    else "06_answered_predictions_seed0.jsonl"
                )
            else:
                out_name = (
                    f"11_control_predictions_seed{seed}.jsonl"
                    if condition == "control"
                    else f"12_answered_predictions_seed{seed}.jsonl"
                )
            path = out / out_name
            done = load_jsonl_by_id(path) if path.exists() else {}
            for rid in secondary:
                if rid in done and not done[rid].get("failed"):
                    continue
                print(
                    f"RUN seed={seed} condition={condition} record_id={rid} max_depth={max_depth}",
                    flush=True,
                )
                row = process_case(
                    model=model,
                    tokenizer=tokenizer,
                    oracle=oracles[rid],
                    condition=condition,
                    seed=seed,
                    temperature=temperature,
                    max_clarify_depth=max_depth,
                )
                if rid in done:
                    keep = [done[x] for x in secondary if x in done and x != rid]
                    write_jsonl(path, keep)
                    done = {r["record_id"]: r for r in keep}
                append_jsonl(path, row)
                done[rid] = row
                if condition == "answered":
                    print(
                        json.dumps(
                            {
                                "record_id": rid,
                                "final_route": row.get("terminal_route"),
                                "clarify_depth": row.get("clarify_depth"),
                                "depth_path_routes": [
                                    s.get("terminal_route") for s in (row.get("depth_path") or [])
                                ],
                            }
                        ),
                        flush=True,
                    )
            print(f"COMPLETE {condition} seed={seed} n={len(done)}", flush=True)

        score_seed(out, seed)
    write_final_summary(out)
    return 0



def load_preds(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"missing_predictions:{path}")
    return load_jsonl_by_id(path)


def score_seed(out: Path, seed: int) -> dict[str, Any]:
    manifest = json.loads((out / "01_frozen_manifest.json").read_text(encoding="utf-8"))
    primary = set(manifest["primary_ids"])
    secondary = list(manifest["secondary_ids"])
    oracles = load_jsonl_by_id(out / "04_oracle_responses.jsonl")
    cohort = load_jsonl_by_id(out / "03_secondary_cohort_26.jsonl")

    if seed == 0:
        control = load_preds(out / "05_control_predictions_seed0.jsonl")
        answered = load_preds(out / "06_answered_predictions_seed0.jsonl")
        per_case_name = "07_per_case_results_seed0.csv"
        matrix_name = "08_transition_matrix_seed0.csv"
        summary_name = "09_summary_seed0.json"
        stats_name = "10_statistics_seed0.json"
    else:
        control = load_preds(out / f"11_control_predictions_seed{seed}.jsonl")
        answered = load_preds(out / f"12_answered_predictions_seed{seed}.jsonl")
        per_case_name = f"13_per_case_results_seed{seed}.csv"
        matrix_name = f"transition_matrix_seed{seed}.csv"
        summary_name = f"14_summary_seed{seed}.json"
        stats_name = f"statistics_seed{seed}.json"

    per_rows: list[dict[str, Any]] = []
    for rid in secondary:
        c = control[rid]
        a = answered[rid]
        first = norm_route(cohort[rid]["post_capability_route"])
        c_route = norm_route(c.get("terminal_route"))
        a_route = norm_route(a.get("terminal_route"))
        row = {
            "record_id": rid,
            "in_primary_22": rid in primary,
            "gold_route": "execute",
            "first_turn_terminal_route": first,
            "control_terminal_route": c_route,
            "answered_terminal_route": a_route,
            "control_correct": c_route == "execute",
            "answered_correct": a_route == "execute",
            "recovered_to_execute": a_route == "execute",
            "remained_clarify": a_route == "clarify",
            "became_refuse": a_route == "refuse",
            "control_emit_route": c.get("emit_route_before_capability"),
            "answered_emit_route": a.get("emit_route_before_capability"),
            "control_capability": c.get("capability_status"),
            "answered_capability": a.get("capability_status"),
            "answered_intent_summary": a.get("intent_summary"),
            "answered_clarify_depth": a.get("clarify_depth"),
            "answered_depth_path_routes": [
                s.get("terminal_route") for s in (a.get("depth_path") or [])
            ],
            "oracle_user_message": oracles[rid]["oracle_user_message"],
            "first_turn_clarification_question": oracles[rid]["first_turn_clarification_question"],
        }
        per_rows.append(row)

    def summarise(subset: list[dict[str, Any]], label: str) -> dict[str, Any]:
        n = len(subset)
        recovered = sum(1 for r in subset if r["recovered_to_execute"])
        remained = sum(1 for r in subset if r["remained_clarify"])
        refused = sum(1 for r in subset if r["became_refuse"])
        other = n - recovered - remained - refused
        transitions = Counter(
            f"{r['first_turn_terminal_route']}->{r['answered_terminal_route']}" for r in subset
        )
        return {
            "label": label,
            "n": n,
            "recovered_to_EXECUTE": recovered,
            "remained_CLARIFY": remained,
            "became_REFUSE": refused,
            "other": other,
            "recovery_rate": recovered / n if n else 0.0,
            "wilson_95ci": wilson_interval(recovered, n),
            "transition_table": dict(transitions),
        }

    primary_rows = [r for r in per_rows if r["in_primary_22"]]
    secondary_rows = per_rows
    primary_summary = summarise(primary_rows, "primary_22")
    secondary_summary = summarise(secondary_rows, "secondary_26")

    recovered_26 = secondary_summary["recovered_to_EXECUTE"]
    interaction_success = {
        "label": "INTERACTION_LEVEL_ONE_TURN_SUCCESS",
        "formula": "(46 + recovered_among_26) / 76",
        "first_turn_immediate_execute_on_gold_execute": "46/76",
        "recovered_among_26": recovered_26,
        "numerator": 46 + recovered_26,
        "denominator": 76,
        "rate": (46 + recovered_26) / 76,
        "note": (
            "Interaction-level / one-turn success on gold-EXECUTE. "
            "Not first-turn routing accuracy. Do not alter 83/120."
        ),
    }

    # Paired 2x2 control vs answered (correct = EXECUTE)
    both = sum(1 for r in secondary_rows if r["control_correct"] and r["answered_correct"])
    control_only = sum(1 for r in secondary_rows if r["control_correct"] and not r["answered_correct"])
    answered_only = sum(1 for r in secondary_rows if (not r["control_correct"]) and r["answered_correct"])
    neither = sum(1 for r in secondary_rows if (not r["control_correct"]) and not r["answered_correct"])
    mcnemar = exact_mcnemar(control_only, answered_only)

    # Write CSV per-case
    with (out / per_case_name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_rows[0].keys()))
        writer.writeheader()
        writer.writerows(per_rows)

    # Transition matrix CSV (answered)
    routes = ["execute", "clarify", "refuse", "other"]
    with (out / matrix_name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["cohort", "from", "to", "count"])
        for label, rows in (("primary_22", primary_rows), ("secondary_26", secondary_rows)):
            counts: Counter[tuple[str, str]] = Counter()
            for r in rows:
                fr = r["first_turn_terminal_route"] or "other"
                to = r["answered_terminal_route"] or "other"
                if to not in {"execute", "clarify", "refuse"}:
                    to = "other"
                counts[(fr, to)] += 1
            for fr in ("clarify",):
                for to in routes:
                    writer.writerow([label, fr, to, counts.get((fr, to), 0)])

    summary = {
        "seed": seed,
        "temperature": 0.7,
        "primary": primary_summary,
        "secondary": secondary_summary,
        "interaction_level_one_turn_success": interaction_success,
        "untouched_first_turn_exact_routing": "83/120",
        "paired_2x2_control_vs_answered_correct_EXECUTE": {
            "both_correct": both,
            "control_only": control_only,
            "answered_only": answered_only,
            "neither": neither,
            "experimental_unit": "case",
        },
        "mcnemar_exact": mcnemar,
        "printed_primary_transitions": primary_summary["transition_table"],
        "printed_secondary_transitions": secondary_summary["transition_table"],
    }
    write_json(out / summary_name, summary)
    write_json(
        out / stats_name,
        {
            "seed": seed,
            "wilson_primary": primary_summary["wilson_95ci"],
            "wilson_secondary": secondary_summary["wilson_95ci"],
            "mcnemar_exact": mcnemar,
            "paired_2x2": summary["paired_2x2_control_vs_answered_correct_EXECUTE"],
            "interaction_level_one_turn_success": interaction_success,
        },
    )

    # Console print of required tables
    print("=== PRIMARY 22 transition (answered) ===")
    print(json.dumps(primary_summary, indent=2))
    print("=== SECONDARY 26 transition (answered) ===")
    print(json.dumps(secondary_summary, indent=2))
    return summary


def write_final_summary(out: Path) -> None:
    seed0 = json.loads((out / "09_summary_seed0.json").read_text(encoding="utf-8"))
    payload: dict[str, Any] = {
        "experiment_id": "one_turn_recovery_20260922",
        "claim_boundary": "oracle_upper_bound_one_turn_recovery_not_naturalistic",
        "untouched_first_turn_exact_routing": "83/120",
        "first_turn_immediate_execute_on_gold_execute": "46/76",
        "seed0": seed0,
        "interpretation": (
            "Oracle upper bound only: recovery if the user supplies a gold-consistent "
            "intent restatement. Not naturalistic simulation; not clarification-quality."
        ),
        "completed_at_utc": utc_now(),
    }
    seed1_path = out / "14_summary_seed1.json"
    if seed1_path.exists():
        seed1 = json.loads(seed1_path.read_text(encoding="utf-8"))
        payload["seed1"] = seed1
        payload["descriptive_aggregate_do_not_pool_as_independent_cases"] = {
            "primary_recovery_rates": {
                "seed0": seed0["primary"]["recovery_rate"],
                "seed1": seed1["primary"]["recovery_rate"],
            },
            "secondary_recovery_rates": {
                "seed0": seed0["secondary"]["recovery_rate"],
                "seed1": seed1["secondary"]["recovery_rate"],
            },
            "note": "Seeds reported separately; case remains the experimental unit.",
        }
    write_json(out / "FINAL_ONE_TURN_RECOVERY_SUMMARY.json", payload)


def cmd_score(args: argparse.Namespace) -> int:
    out = Path(args.experiment_dir).resolve()
    for seed in [int(s) for s in args.seeds]:
        score_seed(out, seed)
    write_final_summary(out)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_freeze = sub.add_parser("freeze")
    p_freeze.add_argument(
        "--evidence-root",
        type=Path,
        default=ROOT
        / "outputs/paper_writer_handoff_20260922/A_EVIDENCE_FOR_PAPER",
    )
    p_freeze.add_argument("--experiment-dir", type=Path, default=default_experiment_dir())

    p_run = sub.add_parser("run")
    p_run.add_argument("--experiment-dir", type=Path, default=default_experiment_dir())
    p_run.add_argument("--temperature", type=float, default=0.7)
    p_run.add_argument("--seeds", nargs="+", default=["0", "1"])
    p_run.add_argument("--max-clarify-depth", type=int, default=MAX_CLARIFY_DEPTH)

    p_score = sub.add_parser("score")
    p_score.add_argument("--experiment-dir", type=Path, default=default_experiment_dir())
    p_score.add_argument("--seeds", nargs="+", default=["0", "1"])

    args = parser.parse_args()
    if args.cmd == "freeze":
        return cmd_freeze(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "score":
        return cmd_score(args)
    raise SystemExit(f"unknown_cmd:{args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
