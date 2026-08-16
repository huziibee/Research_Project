#!/usr/bin/env python3
"""Pilot-120 direct-base or selected-adapter evaluation.

Evaluation-only. Does not train, select checkpoints, or mutate frozen gold.
Uses the frozen Pilot-120 repaired source + gold hashes as a hard gate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.evaluation import pilot_120 as p120  # noqa: E402
from ambiguity_manager.governance.hashing import sha256_hex  # noqa: E402

BASE_MODEL = "Qwen/Qwen3-8B"
BASE_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
SYSTEM_ID = "direct_base_llm"
SELECTED_ADAPTER_SYSTEM_ID = "t28_selected_adapter_llm"
TERMINALS = ["execute", "clarify", "face_preserving_rejection"]
CAPABILITIES = [
    "capable",
    "conditionally_capable",
    "incapable",
    "unauthorized",
    "unsafe",
]
AMBIGUITY_TYPES = [
    "pragmatic",
    "discourse_ellipsis",
    "lexical",
    "scope",
    "object_reference",
    "pronoun_reference",
    "recipient_reference",
    "destination_reference",
    "instrument_reference",
    "spatial_reference",
    "temporal_reference",
    "routine_reference",
    "action_order",
    "fuzzy_temporal",
    "fuzzy_quantity",
    "degree_vagueness",
    "endpoint_vagueness",
]


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _load_done(path: Path) -> set[str]:
    done: set[str] = set()
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        rid = str(obj.get("record_id") or "")
        if rid and not obj.get("failed"):
            done.add(rid)
    return done


def verify_freeze(root: Path) -> dict[str, Any]:
    paths = p120.default_paths(root)
    manifest = p120.load_json(paths["freeze_dir"] / "FROZEN_MANIFEST.json")
    config = p120.load_json(paths["config"])
    gold = root / config["gold_jsonl"]
    source = root / config["source_canonical_jsonl"]
    for key, path in {
        "source_canonical_jsonl": source,
        "final_gold_jsonl": gold,
        "gold_policy": paths["gold_policy"],
        "config_pilot_120_v1": paths["config"],
        "subset_manifest": paths["subset_manifest"],
    }.items():
        got = sha256_hex(path.read_bytes())
        exp = (manifest.get("hashes") or {}).get(key)
        if got != exp:
            raise p120.Pilot120Error(f"hash mismatch {key}: got={got} expected={exp}")
    p120.assert_evaluation_only("evaluate")
    return {
        "ok": True,
        "claim": manifest.get("claim"),
        "source_sha256": sha256_hex(source.read_bytes()),
        "gold_sha256": sha256_hex(gold.read_bytes()),
        "n": len(p120.load_jsonl(source)),
    }


def build_prompt(rec: dict[str, Any]) -> str:
    return (
        "You are evaluating a robot command under the compound-ambiguity v7 protocol.\n"
        "Return ONLY one JSON object with keys:\n"
        '  terminal_strategy: one of execute | clarify | face_preserving_rejection\n'
        "  ambiguity_types: array of allowed labels (may be empty)\n"
        "  capability_status: one of capable | conditionally_capable | incapable | unauthorized | unsafe\n"
        "You may reason carefully first. After any reasoning, you MUST finish with one JSON object "
        "using exactly these keys. Do not end the response before that JSON object.\n\n"
        f"record_id: {rec['record_id']}\n"
        f"command: {rec['command']}\n"
        f"dialogue_history: {json.dumps(rec.get('dialogue_history') or [], ensure_ascii=False)}\n"
        f"scene_context: {rec['scene_context']}\n"
        f"capability_context: {rec['capability_context']}\n"
    )


def extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # Qwen may emit a useful `<think>…</think>` trace before its final JSON
    # answer. Preserve that trace in `raw_output`, but select the last complete
    # JSON object rather than greedily treating reasoning examples plus the
    # final object as one invalid JSON document.
    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for match in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            candidates.append(obj)
    return candidates[-1] if candidates else None


def normalise_prediction(obj: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
    if not obj:
        return None, "no_json"
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
        "terminal_strategy": term,
        "ambiguity_types": types,
        "capability_status": caps,
    }, None


def selected_adapter_identity(
    identity: Mapping[str, Any], *, adapter_scale: float
) -> str:
    """Return an exact selected-adapter identity, including its inference scale."""
    if identity.get("selected_adapter") is not True:
        raise ValueError("pilot_adapter_requires_selected_t28_adapter")
    if identity.get("base_model") != BASE_MODEL or identity.get("base_revision") != BASE_REVISION:
        raise ValueError("pilot_adapter_base_identity_mismatch")
    adapter_id = str(identity.get("adapter_id") or "").strip()
    if not adapter_id:
        raise ValueError("pilot_adapter_identity_missing_adapter_id")
    expected_scale = float(identity.get("adapter_scale", 1.0))
    if expected_scale <= 0 or abs(expected_scale - adapter_scale) > 1e-12:
        raise ValueError("pilot_adapter_scale_identity_mismatch")
    return adapter_id


def apply_adapter_scale(model: Any, scale: float) -> int:
    """Apply the selected PEFT scale and refuse silent fallback to scale 1."""
    if scale <= 0:
        raise ValueError("adapter_scale_must_be_positive")
    applied = 0
    for module in model.modules():
        scaling = getattr(module, "scaling", None)
        set_scale = getattr(module, "set_scale", None)
        if not isinstance(scaling, dict) or not callable(set_scale):
            continue
        for adapter_name in scaling:
            set_scale(adapter_name, scale)
            applied += 1
    if applied <= 0 and abs(scale - 1.0) > 1e-12:
        raise ValueError("adapter_scale_targets_not_found")
    return applied


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-model", default=BASE_MODEL)
    parser.add_argument("--base-revision", default=BASE_REVISION)
    # Keep reasoning enabled. A small number of records exhausted 1,536 tokens
    # inside `<think>` before reaching their required final JSON.
    parser.add_argument("--max-new-tokens", type=int, default=4096)
    parser.add_argument("--system-id", default=SYSTEM_ID)
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--adapter-identity", type=Path)
    parser.add_argument("--adapter-scale", type=float, default=1.0)
    args = parser.parse_args()

    if args.base_revision != BASE_REVISION:
        raise SystemExit("refusing non-frozen base revision")
    adapter_identity: dict[str, Any] | None = None
    adapter_id: str | None = None
    if args.adapter is None:
        if (
            args.system_id != SYSTEM_ID
            or args.adapter_identity is not None
            or abs(float(args.adapter_scale) - 1.0) > 1e-12
        ):
            raise SystemExit("direct_base_requires_no_adapter")
    else:
        if args.system_id != SELECTED_ADAPTER_SYSTEM_ID or args.adapter_identity is None:
            raise SystemExit("selected_adapter_run_requires_identity")
        adapter_identity = json.loads(args.adapter_identity.read_text(encoding="utf-8"))
        try:
            adapter_id = selected_adapter_identity(
                adapter_identity, adapter_scale=float(args.adapter_scale)
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    root = args.root.resolve()
    freeze_check = verify_freeze(root)
    source_rows = p120.load_jsonl(root / "data/annotations/pilot_120_v1/source_canonical.jsonl")
    ids = [r["record_id"] for r in source_rows]

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    pred_path = out / f"{args.system_id}.predictions.jsonl"
    log_path = out / "progress.log.jsonl"
    done = _load_done(pred_path)
    _write_json(
        out / "run_manifest.json",
        {
            "system_id": args.system_id,
            "adapter_used": args.adapter is not None,
            "adapter_id": adapter_id,
            "adapter_scale": float(args.adapter_scale),
            "adapter_identity": adapter_identity,
            "base_model": args.base_model,
            "base_revision": args.base_revision,
            "freeze": freeze_check,
            "n_expected": len(ids),
            "n_done_at_start": len(done),
            "evaluation_only": True,
            "must_not_train_or_select": True,
            "pilot120_used_for_training_or_selection": False,
        },
    )
    _append_jsonl(
        log_path,
        [{"event": "started", "timestamp_epoch": time.time(), "n_done": len(done), "n_total": len(ids)}],
    )

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    tok = AutoTokenizer.from_pretrained(
        args.base_model, revision=args.base_revision, local_files_only=True
    )
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        revision=args.base_revision,
        local_files_only=True,
        quantization_config=bnb,
        device_map="auto",
    )
    if args.adapter is not None:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(args.adapter), local_files_only=True)
        apply_adapter_scale(model, float(args.adapter_scale))
    model.eval()
    _append_jsonl(log_path, [{"event": "model_loaded", "timestamp_epoch": time.time()}])

    by_id = {r["record_id"]: r for r in source_rows}
    for i, rid in enumerate(ids):
        if rid in done:
            continue
        rec = by_id[rid]
        prompt = build_prompt(rec)
        messages = [{"role": "user", "content": prompt}]
        rendered = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tok(rendered, return_tensors="pt").to(model.device)
        t0 = time.perf_counter()
        failed = False
        error = None
        raw_text = ""
        parsed = None
        try:
            with torch.inference_mode():
                out_ids = model.generate(
                    **inputs,
                    max_new_tokens=args.max_new_tokens,
                    do_sample=False,
                    pad_token_id=tok.eos_token_id,
                )
            gen = out_ids[0][inputs["input_ids"].shape[-1] :]
            raw_text = tok.decode(gen, skip_special_tokens=True)
            obj = extract_json(raw_text)
            parsed, error = normalise_prediction(obj)
            if error:
                failed = True
        except Exception as exc:  # noqa: BLE001
            failed = True
            error = f"exception:{type(exc).__name__}:{exc}"
        latency_ms = (time.perf_counter() - t0) * 1000.0
        row = {
            "record_id": rid,
            "system_id": args.system_id,
            "system_version": "1.0.0",
            "model_id": f"{args.base_model}@{args.base_revision}",
            "adapter_id": adapter_id,
            "terminal_strategy": None if failed else parsed["terminal_strategy"],
            "ambiguity_types": None if failed else parsed["ambiguity_types"],
            "capability_status": None if failed else parsed["capability_status"],
            "supports_ambiguity_prediction": True,
            "supports_capability_prediction": True,
            "raw_output": raw_text,
            "parsed": parsed,
            "schema_valid": not failed,
            "failed": failed,
            "error": error,
            "latency_ms": latency_ms,
            "execution_mode": (
                "cluster-gpu-selected-adapter" if args.adapter is not None else "cluster-gpu-base-only"
            ),
        }
        _append_jsonl(pred_path, [row])
        _append_jsonl(
            log_path,
            [
                {
                    "event": "record_finished",
                    "record_id": rid,
                    "index": i,
                    "failed": failed,
                    "latency_ms": latency_ms,
                    "timestamp_epoch": time.time(),
                }
            ],
        )

    # Final score against frozen gold (does not alter gold).
    report = p120.evaluate_predictions(
        pred_path,
        config_path=root / "configs/evaluation/pilot_120_v1.json",
        paths=p120.default_paths(root),
    )
    _write_json(out / f"{args.system_id}.eval.json", report)
    _append_jsonl(log_path, [{"event": "finished", "timestamp_epoch": time.time()}])
    print(json.dumps({"ok": True, "predictions": str(pred_path), "eval": report["terminal_strategy"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
