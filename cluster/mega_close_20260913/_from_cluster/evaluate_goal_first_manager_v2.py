#!/usr/bin/env python3
"""Run the separately versioned goal-first manager v2 on frozen Pilot-120.

Does not modify T39/T41 artifacts. One model-generated rich analysis is shared by
the full-context v2 router and a conservative router; context-blind gets its own
analysis. Gold is read only after every prediction is written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ambiguity_manager.evaluation import pilot_120 as p120  # noqa: E402
from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput  # noqa: E402
from ambiguity_manager.systems.goal_first_analysis_v2 import (  # noqa: E402
    ANALYSIS_JSON_SCHEMA,
    build_analysis_prompt,
    build_constrained_prompt,
    build_retry_prompt,
    extract_analysis_json,
    normalise_analysis_output,
)
from ambiguity_manager.systems.manager import FullManager, GoalFirstManagerV2  # noqa: E402
from ambiguity_manager.systems.variants import ContextBlindManagerSystem, DegreeBasedRouterSystem  # noqa: E402
from evaluate_pilot_120_direct_base import (  # noqa: E402
    BASE_MODEL,
    BASE_REVISION,
    apply_adapter_scale,
    sampling_generate_kwargs,
    selected_adapter_identity,
    set_run_seed,
    verify_freeze,
)

SYSTEMS = (
    "goal_first_manager_v2",
    "rich_conservative_manager_v2",
    "goal_first_context_blind_v2",
    "degree_based_router_v2",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _load_jsonl_by_id(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            item = json.loads(line)
            rid = str(item.get("record_id") or "")
            if not rid or rid in rows:
                raise ValueError(f"duplicate_or_missing_record_id:{path}:{number}")
            rows[rid] = item
    return rows


def _system_input(row: dict[str, Any]) -> SystemInput:
    return SystemInput(
        record_id=str(row["record_id"]),
        command=str(row["command"]),
        dialogue_history=tuple(str(item) for item in row.get("dialogue_history") or []),
        scene_context=row.get("scene_context"),
        capability_context=row.get("capability_context"),
        protected_data=False,
    )


@dataclass
class RichAnalysisProvider:
    model: Any
    tokenizer: Any
    max_new_tokens: int
    retry_max_new_tokens: int
    constrained_final_max_new_tokens: int
    provider_id: str
    constrained_only: bool = False
    temperature: float = 0.0
    metadata_by_input_hash: dict[str, dict[str, Any]] = field(default_factory=dict)
    raw_by_input_hash: dict[str, str] = field(default_factory=dict)
    attempts_by_input_hash: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def _generate(self, prompt: str, max_new_tokens: int) -> str:
        rendered = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer(rendered, return_tensors="pt").to(self.model.device)
        with __import__("torch").inference_mode():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                **sampling_generate_kwargs(self.temperature),
                repetition_penalty=1.12,
                no_repeat_ngram_size=6,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        generated = output_ids[0][inputs["input_ids"].shape[-1] :]
        return self.tokenizer.decode(generated, skip_special_tokens=True)

    def _generate_constrained(self, system_input: SystemInput) -> tuple[str, dict[str, Any]]:
        from ambiguity_manager.model.task_constrained_decoding import generate_with_task_constraint

        generated = generate_with_task_constraint(
            model=self.model,
            tokenizer=self.tokenizer,
            prompt=build_constrained_prompt(system_input),
            json_schema=ANALYSIS_JSON_SCHEMA,
            max_new_tokens=self.constrained_final_max_new_tokens,
            generation_config=sampling_generate_kwargs(self.temperature),
        )
        return str(generated["raw_text"]), {
            "transport_status": generated["transport_status"],
            "constraint_initialised": generated["constraint_initialised"],
            "generated_token_count": generated["generated_token_count"],
            "maximum_output_tokens": generated["maximum_output_tokens"],
            "termination_reason": generated["termination_reason"],
            "response_mode": "schema_constrained_final_emission_after_two_thinking_attempts",
        }

    def analyse(self, system_input: SystemInput) -> StructuredAnalysis:
        key = system_input.fingerprint()
        attempts: list[dict[str, Any]] = []
        validation_error = "analysis_validation_failed"
        # Repair / hard-ID mode: skip free-form thinking loops; go straight to schema constraint.
        if self.constrained_only:
            raw, constraint_metadata = self._generate_constrained(system_input)
            self.raw_by_input_hash[key] = raw
            analysis, meta, error = normalise_analysis_output(
                extract_analysis_json(raw), system_input=system_input, provider_id=self.provider_id
            )
            attempts.append(
                {
                    "attempt": 1,
                    "mode": "schema_constrained_only",
                    "max_new_tokens": self.constrained_final_max_new_tokens,
                    "raw_chars": len(raw),
                    "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    "validation_error": None if error is None else (error or "analysis_validation_failed"),
                    "constraint": constraint_metadata,
                }
            )
            self.attempts_by_input_hash[key] = attempts
            if error is None and analysis is not None and meta is not None:
                self.metadata_by_input_hash[key] = {**meta, "analysis_attempt_count": 1}
                return analysis
            # One free-form retry with strong anti-rep if constrained still fails.
            prompt = build_retry_prompt(system_input, error or "analysis_validation_failed")
            raw = self._generate(prompt, self.retry_max_new_tokens)
            self.raw_by_input_hash[key] = raw
            analysis, meta, error = normalise_analysis_output(
                extract_analysis_json(raw), system_input=system_input, provider_id=self.provider_id
            )
            attempts.append(
                {
                    "attempt": 2,
                    "mode": "thinking_retry_after_constrained",
                    "max_new_tokens": self.retry_max_new_tokens,
                    "raw_chars": len(raw),
                    "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    "validation_error": None if error is None else (error or "analysis_validation_failed"),
                }
            )
            self.attempts_by_input_hash[key] = attempts
            if error is None and analysis is not None and meta is not None:
                self.metadata_by_input_hash[key] = {**meta, "analysis_attempt_count": 2}
                return analysis
            raise ValueError(f"{error or 'analysis_validation_failed'};attempts={len(attempts)}")

        prompt = build_analysis_prompt(system_input)
        attempt_plan = (("thinking", self.max_new_tokens), ("thinking_retry", self.retry_max_new_tokens))
        for attempt_number, (mode, token_limit) in enumerate(attempt_plan, 1):
            if attempt_number == 2:
                prompt = build_retry_prompt(system_input, validation_error)
            raw = self._generate(prompt, token_limit)
            self.raw_by_input_hash[key] = raw
            analysis, meta, error = normalise_analysis_output(
                extract_analysis_json(raw), system_input=system_input, provider_id=self.provider_id
            )
            validation_error = error or "analysis_validation_failed"
            attempts.append(
                {
                    "attempt": attempt_number,
                    "mode": mode,
                    "max_new_tokens": token_limit,
                    "raw_chars": len(raw),
                    "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    "validation_error": None if error is None else validation_error,
                }
            )
            self.attempts_by_input_hash[key] = attempts
            if error is None and analysis is not None and meta is not None:
                self.metadata_by_input_hash[key] = {**meta, "analysis_attempt_count": attempt_number}
                return analysis
        raw, constraint_metadata = self._generate_constrained(system_input)
        self.raw_by_input_hash[key] = raw
        analysis, meta, error = normalise_analysis_output(
            extract_analysis_json(raw), system_input=system_input, provider_id=self.provider_id
        )
        attempts.append(
            {
                "attempt": len(attempts) + 1,
                "mode": "schema_constrained_final_emission_after_two_thinking_attempts",
                "max_new_tokens": self.constrained_final_max_new_tokens,
                "raw_chars": len(raw),
                "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                "validation_error": None if error is None else (error or "analysis_validation_failed"),
                "constraint": constraint_metadata,
            }
        )
        self.attempts_by_input_hash[key] = attempts
        if error is None and analysis is not None and meta is not None:
            self.metadata_by_input_hash[key] = {**meta, "analysis_attempt_count": len(attempts)}
            return analysis
        raise ValueError(f"{error or 'analysis_validation_failed'};attempts={len(attempts)}")


def _terminal(result: Any) -> str | None:
    sequence = [value.value if hasattr(value, "value") else str(value) for value in result.strategy_sequence]
    route = result.recommended_strategy.value if getattr(result.recommended_strategy, "value", None) else result.recommended_strategy
    if route == "face_preserving_rejection" or "face_preserving_rejection" in sequence:
        return "face_preserving_rejection"
    if route == "clarify" or "clarify" in sequence:
        return "clarify"
    if route in {"execute", "silently_resolve", "multi_step"}:
        return "execute"
    return None


def _prediction_row(
    *,
    record_id: str,
    system_id: str,
    result: Any | None,
    meta: dict[str, Any] | None,
    raw_output: str | None,
    latency_ms: float,
    error: str | None,
    analysis_attempts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    terminal = _terminal(result) if result is not None else None
    failed = bool(error) or terminal is None or meta is None
    return {
        "record_id": record_id,
        "system_id": system_id,
        "system_version": "2.0.0",
        "model_id": f"{BASE_MODEL}@{BASE_REVISION}",
        "terminal_strategy": None if failed else terminal,
        "ambiguity_types": None if failed else meta.get("pilot_ambiguity_types"),
        "capability_status": None if failed else meta.get("pilot_capability_status"),
        "intent_summary": None if failed else meta.get("intent_summary"),
        "supports_ambiguity_prediction": True,
        "supports_capability_prediction": True,
        "raw_output": raw_output,
        "parsed": result.to_dict() if result is not None else None,
        "schema_valid": not failed,
        "failed": failed,
        "error": error,
        "analysis_attempts": analysis_attempts or [],
        "latency_ms": latency_ms,
        "execution_mode": "cluster-gpu-goal-first-v2",
        "claim_boundary": "separately_versioned_from_frozen_t39",
    }


def _load_model(args: argparse.Namespace) -> tuple[Any, Any, str | None]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available():
        raise SystemExit("goal_first_v2_cuda_required_but_unavailable")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, revision=BASE_REVISION, local_files_only=True)
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
        raise SystemExit("goal_first_v2_model_not_placed_on_cuda")
    adapter_id = None
    if args.adapter:
        identity = json.loads(args.adapter_identity.read_text(encoding="utf-8"))
        adapter_id = selected_adapter_identity(identity, adapter_scale=args.adapter_scale)
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(args.adapter), local_files_only=True)
        apply_adapter_scale(model, args.adapter_scale)
    model.eval()
    return model, tokenizer, adapter_id


def _rewrite_predictions(path: Path, rows_by_id: dict[str, dict[str, Any]], expected_ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for record_id in expected_ids:
            if record_id not in rows_by_id:
                continue
            handle.write(json.dumps(rows_by_id[record_id], ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _strip_failed_rows(existing: dict[str, dict[str, dict[str, Any]]]) -> dict[str, list[str]]:
    removed: dict[str, list[str]] = {}
    for sid, rows in existing.items():
        failed_ids = sorted(rid for rid, row in rows.items() if row.get("failed") is True)
        for rid in failed_ids:
            del rows[rid]
        removed[sid] = failed_ids
    return removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-new-tokens", type=int, default=4096)
    parser.add_argument("--retry-max-new-tokens", type=int, default=8192)
    parser.add_argument("--constrained-final-max-new-tokens", type=int, default=1024)
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--adapter-identity", type=Path)
    parser.add_argument("--adapter-scale", type=float, default=1.0)
    parser.add_argument("--limit", type=int, default=0, help="If >0, only the first N source rows (canary).")
    parser.add_argument(
        "--repair-failed",
        action="store_true",
        help="Drop failed prediction rows and regenerate only those record_ids, then rewrite ordered files.",
    )
    parser.add_argument(
        "--constrained-only",
        action="store_true",
        help="Skip free-form thinking loops; schema-constrained first (for hard repair IDs).",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    if float(args.temperature) < 0:
        raise SystemExit("temperature_must_be_nonnegative")
    set_run_seed(args.seed)
    if bool(args.adapter) != bool(args.adapter_identity):
        raise SystemExit("adapter_and_adapter_identity_must_be_supplied_together")
    root = args.root.resolve()
    freeze = verify_freeze(root)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_rows = p120.load_jsonl(root / "data/annotations/pilot_120_v1/source_canonical.jsonl")
    if args.limit and args.limit > 0:
        source_rows = source_rows[: args.limit]
    expected_ids = [str(row["record_id"]) for row in source_rows]
    paths = {sid: output / "predictions" / f"{sid}.predictions.jsonl" for sid in SYSTEMS}
    existing = {sid: _load_jsonl_by_id(path) for sid, path in paths.items()}
    repaired_from: dict[str, list[str]] = {}
    if args.repair_failed:
        repaired_from = _strip_failed_rows(existing)
        for sid, path in paths.items():
            _rewrite_predictions(path, existing[sid], expected_ids)
    needs_generation = any(record_id not in existing[sid] for sid in SYSTEMS for record_id in expected_ids)
    adapter_id = None
    full_provider = blind_provider = None
    systems: dict[str, Any] = {
        "goal_first_manager_v2": GoalFirstManagerV2(),
        "rich_conservative_manager_v2": FullManager(),
        "degree_based_router_v2": DegreeBasedRouterSystem(),
    }
    if needs_generation:
        model, tokenizer, adapter_id = _load_model(args)
        full_provider = RichAnalysisProvider(
            model, tokenizer, args.max_new_tokens, args.retry_max_new_tokens,
            args.constrained_final_max_new_tokens, "goal_first_v2_full_context",
            constrained_only=bool(args.constrained_only),
            temperature=float(args.temperature),
        )
        blind_provider = RichAnalysisProvider(
            model, tokenizer, args.max_new_tokens, args.retry_max_new_tokens,
            args.constrained_final_max_new_tokens, "goal_first_v2_context_blind",
            constrained_only=bool(args.constrained_only),
            temperature=float(args.temperature),
        )
        systems["goal_first_context_blind_v2"] = ContextBlindManagerSystem(
            analysis_provider=blind_provider,
            inner=GoalFirstManagerV2(analysis_provider=blind_provider),
        )
    manifest = {
        "status": "RUNNING",
        "system_family": "goal_first_manager_v2",
        "claim_boundary": "separately_versioned_from_frozen_t39",
        "systems": list(SYSTEMS),
        "freeze": freeze,
        "adapter_used": bool(args.adapter),
        "adapter_id": adapter_id,
        "adapter_scale": args.adapter_scale,
        "base_model": BASE_MODEL,
        "base_revision": BASE_REVISION,
        "temperature": float(args.temperature),
        "do_sample": float(args.temperature) > 0,
        "seed": args.seed,
        "n_expected": len(expected_ids),
        "limit": args.limit or None,
        "evaluation_only": True,
        "pilot120_used_for_training_or_selection": False,
        "repair_failed": bool(args.repair_failed),
        "repaired_from": repaired_from,
    }
    _write_json(output / "run_manifest.json", manifest)
    started_at = time.time()

    def write_progress(status: str, current_record_id: str | None = None) -> None:
        completed = sum(all(record_id in existing[sid] for sid in SYSTEMS) for record_id in expected_ids)
        payload = {
            "status": status,
            "current_record_id": current_record_id,
            "records_completed": completed,
            "records_expected": len(expected_ids),
            "updated_at_epoch": time.time(),
            "elapsed_seconds": round(time.time() - started_at, 1),
        }
        _write_json(output / "progress.json", payload)

    write_progress("RUNNING")
    full_context_ids = ("goal_first_manager_v2", "rich_conservative_manager_v2", "degree_based_router_v2")
    for row in source_rows:
        record = _system_input(row)
        if all(record.record_id in existing[sid] for sid in SYSTEMS):
            continue
        full_analysis = full_meta = full_raw = full_error = None
        full_attempts: list[dict[str, Any]] = []
        full_latency = 0.0
        if any(record.record_id not in existing[sid] for sid in full_context_ids):
            if full_provider is None:
                raise RuntimeError("full_provider_not_loaded")
            full_started = time.perf_counter()
            try:
                full_analysis = full_provider.analyse(record)
                full_meta = full_provider.metadata_by_input_hash[record.fingerprint()]
                full_raw = full_provider.raw_by_input_hash[record.fingerprint()]
            except Exception as exc:  # noqa: BLE001
                full_error = f"analysis_exception:{type(exc).__name__}:{exc}"
                full_raw = full_provider.raw_by_input_hash.get(record.fingerprint())
            full_attempts = full_provider.attempts_by_input_hash.get(record.fingerprint(), [])
            full_latency = (time.perf_counter() - full_started) * 1000.0
        for sid in full_context_ids:
            if record.record_id in existing[sid]:
                continue
            result = None
            error = full_error
            if error is None and full_analysis is not None:
                try:
                    result = systems[sid].run(record, cached_analysis=full_analysis)
                except Exception as exc:  # noqa: BLE001
                    error = f"system_exception:{type(exc).__name__}:{exc}"
            pred = _prediction_row(
                record_id=record.record_id,
                system_id=sid,
                result=result,
                meta=full_meta,
                raw_output=full_raw,
                latency_ms=full_latency,
                error=error,
                analysis_attempts=full_attempts,
            )
            _append_jsonl(paths[sid], pred)
            existing[sid][record.record_id] = pred
        sid = "goal_first_context_blind_v2"
        if record.record_id not in existing[sid]:
            if "goal_first_context_blind_v2" not in systems or blind_provider is None:
                raise RuntimeError("blind_provider_not_loaded")
            started = time.perf_counter()
            result = error = blind_raw = blind_meta = None
            try:
                result = systems[sid].run(record)
                blind_input = record.without_context()
                blind_meta = blind_provider.metadata_by_input_hash[blind_input.fingerprint()]
                blind_raw = blind_provider.raw_by_input_hash[blind_input.fingerprint()]
            except Exception as exc:  # noqa: BLE001
                error = f"system_exception:{type(exc).__name__}:{exc}"
                blind_input = record.without_context()
                blind_raw = blind_provider.raw_by_input_hash.get(blind_input.fingerprint())
            pred = _prediction_row(
                record_id=record.record_id,
                system_id=sid,
                result=result,
                meta=blind_meta,
                raw_output=blind_raw,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                error=error,
                analysis_attempts=blind_provider.attempts_by_input_hash.get(record.without_context().fingerprint(), []),
            )
            _append_jsonl(paths[sid], pred)
            existing[sid][record.record_id] = pred
        write_progress("RUNNING", record.record_id)

    # Ensure deterministic ordered prediction files before evaluation.
    for sid, path in paths.items():
        _rewrite_predictions(path, existing[sid], expected_ids)

    write_progress("EVALUATING")
    reports: dict[str, Any] = {}
    validation: dict[str, Any] = {}
    for sid, path in paths.items():
        rows = p120.load_jsonl(path)
        ids = [str(row.get("record_id") or "") for row in rows]
        validation[sid] = {"n_rows": len(rows), "ordered_complete": ids == expected_ids}
        if ids != expected_ids:
            raise SystemExit(f"prediction_denominator_or_order_invalid:{sid}")
        if args.limit:
            gold_rows = {row["record_id"]: row for row in p120.load_jsonl(root / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl")}
            reports[sid] = {
                "n": len(rows),
                "route_accuracy": sum(row.get("terminal_strategy") == gold_rows[row["record_id"]]["terminal_strategy"] for row in rows) / len(rows),
                "intent_summary_nonnull": sum(bool(row.get("intent_summary")) for row in rows),
                "note": "limit_canary_not_official_denominator",
            }
        else:
            reports[sid] = p120.evaluate_predictions(
                path, config_path=root / "configs/evaluation/pilot_120_v1.json", paths=p120.default_paths(root)
            )
        _write_json(output / "evaluations" / f"{sid}.eval.json", reports[sid])
    failed_ids = {
        sid: sorted(rid for rid, row in existing[sid].items() if row.get("failed") is True)
        for sid in SYSTEMS
    }
    n_failed = sum(len(ids) for ids in failed_ids.values())
    ordered_ok = all(item["ordered_complete"] for item in validation.values())
    if ordered_ok and n_failed == 0:
        manifest["status"] = "VERIFY_PASSED"
    elif ordered_ok:
        # Bound row failures must not block replicas/natives. Document explicitly.
        manifest["status"] = "VERIFY_PASSED_WITH_ROW_FAILURES"
        manifest["row_failures"] = failed_ids
        manifest["row_failure_total"] = n_failed
        manifest["claim_boundary_row_failures"] = (
            "Ordered 120/120 predictions exist; some rows remain failed after repair. "
            "Route metrics treat failed rows as incorrect. Do not hide this in the report."
        )
    else:
        manifest["status"] = "VERIFY_FAILED"
    manifest["prediction_sha256"] = {sid: _sha256(path) for sid, path in paths.items()}
    manifest["validation"] = validation
    _write_json(output / "run_manifest.json", manifest)
    write_progress(manifest["status"])
    print(json.dumps({"status": manifest["status"], "systems": list(SYSTEMS), "validation": validation, "row_failure_total": n_failed}, sort_keys=True))
    return 0 if manifest["status"].startswith("VERIFY_PASSED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
