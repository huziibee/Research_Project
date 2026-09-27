#!/usr/bin/env python3
"""Run the three missing manager systems on frozen Pilot-120 without gold leakage.

One model-generated StructuredAnalysis is shared by the full-context systems;
the context-blind manager receives a separately generated analysis over an
ablated SystemInput.  The script never reads Pilot-120 gold until every
prediction has been written, when the existing evaluator scores the artifact.
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
from ambiguity_manager.schema.v2.records import ContextSamplingUncertainty, UnresolvedSlot  # noqa: E402
from ambiguity_manager.systems.contracts import AnalysisProvenance, StructuredAnalysis, SystemInput  # noqa: E402
from ambiguity_manager.systems.variants import (  # noqa: E402
    ContextBlindManagerSystem,
    DegreeBasedRouterSystem,
    FullTypeRiskAwareManagerSystem,
)
from evaluate_pilot_120_direct_base import (  # noqa: E402
    AMBIGUITY_TYPES,
    BASE_MODEL,
    BASE_REVISION,
    CAPABILITIES,
    apply_adapter_scale,
    extract_json,
    sampling_generate_kwargs,
    selected_adapter_identity,
    set_run_seed,
    verify_freeze,
)


SYSTEMS = (
    "degree_based_router",
    "context_blind_manager",
    "full_type_risk_aware_manager",
)
CANONICAL_AMBIGUITY = {
    "pragmatic": "pragmatic",
    "discourse_ellipsis": "contextual",
    "lexical": "referential",
    "scope": "referential",
    "object_reference": "referential",
    "pronoun_reference": "referential",
    "recipient_reference": "referential",
    "destination_reference": "spatial",
    "instrument_reference": "capability",
    "spatial_reference": "spatial",
    "temporal_reference": "temporal",
    "routine_reference": "contextual",
    "action_order": "temporal",
    "fuzzy_temporal": "temporal",
    "fuzzy_quantity": "quantitative",
    "degree_vagueness": "quantitative",
    "endpoint_vagueness": "spatial",
}
CANONICAL_CAPABILITY = {
    "capable": "capable",
    "conditionally_capable": "conditional",
    "incapable": "incapable",
    "unauthorized": "unknown",
    "unsafe": "unknown",
}
CANONICAL_RISKS = {"none", "low", "medium", "high", "unknown"}
SPEECH_ACTS = {
    "directive_command",
    "indirect_request",
    "information_question",
    "permission_request",
    "prohibition",
    "conditional_directive",
    "multi_intent",
    "other_non_actionable",
}
SLOT_NAMES = {
    "action", "actor", "object", "object_attributes", "destination",
    "spatial_relation", "quantity", "time", "recipient", "tool",
    "conditions", "constraints", "negation", "intent",
}
MANAGER_ANALYSIS_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "speech_act",
        "pilot_ambiguity_types",
        "pilot_capability_status",
        "risk_level",
        "unresolved_slots",
        "uncertainty",
    ],
    "properties": {
        "speech_act": {"type": "string", "enum": sorted(SPEECH_ACTS)},
        "pilot_ambiguity_types": {"type": "array", "items": {"type": "string", "enum": AMBIGUITY_TYPES}},
        "pilot_capability_status": {"type": "string", "enum": CAPABILITIES},
        "risk_level": {"type": "string", "enum": sorted(CANONICAL_RISKS)},
        "unresolved_slots": {"type": "array", "items": {"type": "string", "enum": sorted(SLOT_NAMES)}},
        "uncertainty": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
}


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
        if not line.strip():
            continue
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
        dialogue_history=tuple(str(v) for v in row.get("dialogue_history") or []),
        scene_context=row.get("scene_context"),
        capability_context=row.get("capability_context"),
        protected_data=False,
    )


def _analysis_prompt(system_input: SystemInput) -> str:
    return (
        "Analyse this robot command for a routing manager. Do not choose a final route. "
        "Return ONLY one JSON object with these exact keys:\n"
        "speech_act (one allowed label), pilot_ambiguity_types (array), "
        "pilot_capability_status (one allowed label), risk_level, "
        "unresolved_slots (array of CPC slot names), uncertainty (0 to 1).\n"
        "Allowed speech_act: " + ", ".join(sorted(SPEECH_ACTS)) + "\n"
        "Allowed pilot_ambiguity_types: " + ", ".join(AMBIGUITY_TYPES) + "\n"
        "Allowed pilot_capability_status: " + ", ".join(CAPABILITIES) + "\n"
        "Allowed risk_level: none, low, medium, high, unknown.\n"
        "Allowed unresolved_slots: " + ", ".join(sorted(SLOT_NAMES)) + "\n"
        "You may reason carefully first, but must finish with the JSON object.\n\n"
        f"record_id: {system_input.record_id}\n"
        f"command: {system_input.command}\n"
        f"dialogue_history: {json.dumps(list(system_input.dialogue_history), ensure_ascii=False)}\n"
        f"scene_context: {system_input.scene_context}\n"
        f"capability_context: {system_input.capability_context}\n"
    )


def _retry_analysis_prompt(system_input: SystemInput, validation_error: str) -> str:
    """Ask the same model to re-analyse an invalid non-gold response once."""
    return (
        "Your prior answer did not satisfy the required machine-readable schema "
        f"(validation error: {validation_error}). Re-analyse the source record. "
        "You may reason carefully, but ensure the response completes with exactly one "
        "valid JSON object and uses only the listed labels. Do not infer any hidden gold labels.\n\n"
        + _analysis_prompt(system_input)
    )


def _constrained_analysis_prompt(system_input: SystemInput) -> str:
    """Minimal final-emission request after the normal thinking attempts failed."""
    return (
        "Produce the routing-manager analysis for this source record. "
        "The JSON schema enforces the allowed fields and labels. Do not use gold labels.\n\n"
        f"record_id: {system_input.record_id}\n"
        f"command: {system_input.command}\n"
        f"dialogue_history: {json.dumps(list(system_input.dialogue_history), ensure_ascii=False)}\n"
        f"scene_context: {system_input.scene_context}\n"
        f"capability_context: {system_input.capability_context}\n"
    )


def normalise_analysis_output(
    obj: dict[str, Any] | None, *, system_input: SystemInput, provider_id: str
) -> tuple[StructuredAnalysis | None, dict[str, Any] | None, str | None]:
    """Validate a model result into the manager's schema without inventing labels."""
    if not isinstance(obj, dict):
        return None, None, "no_json"
    speech_act = obj.get("speech_act")
    if speech_act not in SPEECH_ACTS:
        return None, None, f"bad_speech_act:{speech_act}"
    raw_types = obj.get("pilot_ambiguity_types")
    if not isinstance(raw_types, list):
        return None, None, "bad_pilot_ambiguity_types"
    types = sorted({str(value) for value in raw_types if str(value) in AMBIGUITY_TYPES})
    if any(str(value) not in AMBIGUITY_TYPES for value in raw_types):
        return None, None, "unknown_pilot_ambiguity_type"
    pilot_capability = obj.get("pilot_capability_status")
    if pilot_capability not in CAPABILITIES:
        return None, None, f"bad_pilot_capability_status:{pilot_capability}"
    risk = obj.get("risk_level")
    if risk not in CANONICAL_RISKS:
        return None, None, f"bad_risk_level:{risk}"
    raw_slots = obj.get("unresolved_slots")
    if not isinstance(raw_slots, list) or any(str(slot) not in SLOT_NAMES for slot in raw_slots):
        return None, None, "bad_unresolved_slots"
    try:
        uncertainty = float(obj.get("uncertainty"))
    except (TypeError, ValueError):
        return None, None, "bad_uncertainty"
    if not 0.0 <= uncertainty <= 1.0:
        return None, None, "uncertainty_out_of_range"
    canonical = sorted({CANONICAL_AMBIGUITY[value] for value in types})
    primary = canonical[0] if canonical else None
    analysis = StructuredAnalysis.from_dict(
        {
            "speech_act": speech_act,
            "intent_summary": None,
            "ambiguity_present": bool(types),
            "ambiguity_types": canonical,
            "primary_ambiguity_type": primary,
            "compound_ambiguity": len(types) > 1,
            "compound_ambiguity_count": len(types),
            "risk_relevant": risk not in {"none", "unknown"},
            "risk_level": risk,
            "capability_status": CANONICAL_CAPABILITY[pilot_capability],
            "unresolved_slots": [
                UnresolvedSlot(slot_name=str(slot), reason="model_identified_uncertainty").to_dict()
                for slot in sorted(set(str(slot) for slot in raw_slots))
            ],
            "context_sampling_uncertainty": ContextSamplingUncertainty(
                score=uncertainty, variant_count=1, agreement=1.0 - uncertainty
            ).to_dict(),
            "analysis_provenance": AnalysisProvenance(
                provider_id=provider_id,
                provider_version="pilot120-manager-r1",
                analysis_id=system_input.fingerprint(),
                method="model_generated",
                notes=f"source_input_hash={system_input.fingerprint()};no_gold_in_prompt",
            ).to_dict(),
            "findings": [
                f"pilot_ambiguity_types:{json.dumps(types, separators=(',', ':'))}",
                f"pilot_capability_status:{pilot_capability}",
            ],
        }
    )
    meta = {"pilot_ambiguity_types": types, "pilot_capability_status": pilot_capability}
    return analysis, meta, None


@dataclass
class TransformerAnalysisProvider:
    model: Any
    tokenizer: Any
    max_new_tokens: int
    retry_max_new_tokens: int
    constrained_final_max_new_tokens: int
    provider_id: str
    provider_version: str = "pilot120-manager-r1"
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
                pad_token_id=self.tokenizer.eos_token_id,
            )
        generated = output_ids[0][inputs["input_ids"].shape[-1] :]
        return self.tokenizer.decode(generated, skip_special_tokens=True)

    def _generate_constrained(self, system_input: SystemInput) -> tuple[str, dict[str, Any]]:
        """Emit only the final JSON after two preserved thinking attempts fail."""
        from ambiguity_manager.model.task_constrained_decoding import generate_with_task_constraint

        generated = generate_with_task_constraint(
            model=self.model,
            tokenizer=self.tokenizer,
            prompt=_constrained_analysis_prompt(system_input),
            json_schema=MANAGER_ANALYSIS_JSON_SCHEMA,
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
        prompt = _analysis_prompt(system_input)
        validation_error = "analysis_validation_failed"
        attempt_plan = (("thinking", self.max_new_tokens), ("thinking_retry", self.retry_max_new_tokens))
        for attempt_number, (mode, token_limit) in enumerate(attempt_plan, 1):
            if attempt_number == 2:
                prompt = _retry_analysis_prompt(system_input, validation_error)
            raw = self._generate(prompt, token_limit)
            self.raw_by_input_hash[key] = raw  # Preserve invalid model output for audit/recovery.
            analysis, meta, error = normalise_analysis_output(
                extract_json(raw), system_input=system_input, provider_id=self.provider_id
            )
            validation_error = error or "analysis_validation_failed"
            attempts.append(
                {
                    "attempt": attempt_number,
                    "mode": mode,
                    "max_new_tokens": token_limit,
                    "raw_chars": len(raw),
                    "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    "validation_error": None if error is None and analysis is not None and meta is not None else validation_error,
                }
            )
            self.attempts_by_input_hash[key] = attempts
            if error is None and analysis is not None and meta is not None:
                self.metadata_by_input_hash[key] = {**meta, "analysis_attempt_count": attempt_number}
                return analysis
        raw, constraint_metadata = self._generate_constrained(system_input)
        self.raw_by_input_hash[key] = raw
        analysis, meta, error = normalise_analysis_output(
            extract_json(raw), system_input=system_input, provider_id=self.provider_id
        )
        validation_error = error or "analysis_validation_failed"
        attempts.append(
            {
                "attempt": len(attempts) + 1,
                "mode": "schema_constrained_final_emission_after_two_thinking_attempts",
                "max_new_tokens": self.constrained_final_max_new_tokens,
                "raw_chars": len(raw),
                "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                "validation_error": None if error is None and analysis is not None and meta is not None else validation_error,
                "constraint": constraint_metadata,
            }
        )
        self.attempts_by_input_hash[key] = attempts
        if error is None and analysis is not None and meta is not None:
            self.metadata_by_input_hash[key] = {**meta, "analysis_attempt_count": len(attempts)}
            return analysis
        raise ValueError(f"{validation_error};attempts={len(attempts)}")


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
    *, record_id: str, system_id: str, result: Any | None, meta: dict[str, Any] | None,
    raw_output: str | None, latency_ms: float, error: str | None,
    analysis_attempts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    terminal = _terminal(result) if result is not None else None
    failed = bool(error) or terminal is None or meta is None
    return {
        "record_id": record_id,
        "system_id": system_id,
        "system_version": "1.0.0",
        "model_id": f"{BASE_MODEL}@{BASE_REVISION}",
        "terminal_strategy": None if failed else terminal,
        "ambiguity_types": None if failed else meta["pilot_ambiguity_types"],
        "capability_status": None if failed else meta["pilot_capability_status"],
        "supports_ambiguity_prediction": True,
        "supports_capability_prediction": True,
        "raw_output": raw_output,
        "parsed": result.to_dict() if result is not None else None,
        "schema_valid": not failed,
        "failed": failed,
        "error": error,
        "analysis_attempts": analysis_attempts or [],
        "latency_ms": latency_ms,
        "execution_mode": "cluster-gpu-manager-pipeline",
    }


def _load_model(args: argparse.Namespace) -> tuple[Any, Any, str | None]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available():
        raise SystemExit("pilot120_manager_cuda_required_but_unavailable")

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
        raise SystemExit("pilot120_manager_model_not_placed_on_cuda")
    adapter_id = None
    if args.adapter:
        identity = json.loads(args.adapter_identity.read_text(encoding="utf-8"))
        adapter_id = selected_adapter_identity(identity, adapter_scale=args.adapter_scale)
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, str(args.adapter), local_files_only=True)
        apply_adapter_scale(model, args.adapter_scale)
    model.eval()
    return model, tokenizer, adapter_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-new-tokens", type=int, default=4096)
    parser.add_argument("--retry-max-new-tokens", type=int, default=8192)
    parser.add_argument("--constrained-final-max-new-tokens", type=int, default=512)
    parser.add_argument("--resume-from", type=Path)
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--adapter-identity", type=Path)
    parser.add_argument("--adapter-scale", type=float, default=1.0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    if float(args.temperature) < 0:
        raise SystemExit("temperature_must_be_nonnegative")
    set_run_seed(args.seed)
    if bool(args.adapter) != bool(args.adapter_identity):
        raise SystemExit("adapter_and_adapter_identity_must_be_supplied_together")
    if (
        args.adapter_scale <= 0
        or args.max_new_tokens <= 0
        or args.retry_max_new_tokens <= 0
        or args.constrained_final_max_new_tokens <= 0
    ):
        raise SystemExit("adapter_scale_must_be_positive")

    root = args.root.resolve()
    freeze = verify_freeze(root)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_rows = p120.load_jsonl(root / "data/annotations/pilot_120_v1/source_canonical.jsonl")
    expected_ids = [str(row["record_id"]) for row in source_rows]
    if len(source_rows) != p120.EXPECTED_N or len(set(expected_ids)) != p120.EXPECTED_N:
        raise SystemExit("pilot120_source_denominator_invalid")
    paths = {sid: output / "predictions" / f"{sid}.predictions.jsonl" for sid in SYSTEMS}
    resume_metadata: dict[str, Any] | None = None
    seeded_valid_rows: dict[str, dict[str, dict[str, Any]]] = {sid: {} for sid in SYSTEMS}
    if args.resume_from is not None:
        resume = args.resume_from.resolve()
        seed_manifest = json.loads((resume / "run_manifest.json").read_text(encoding="utf-8"))
        if seed_manifest.get("adapter_scale") != args.adapter_scale or seed_manifest.get("base_revision") != BASE_REVISION:
            raise SystemExit("resume_parent_model_or_scale_mismatch")
        failed_seed_rows: dict[str, list[dict[str, Any]]] = {}
        for sid in SYSTEMS:
            seed_path = resume / "predictions" / f"{sid}.predictions.jsonl"
            seed_rows = p120.load_jsonl(seed_path)
            ids = [str(item.get("record_id") or "") for item in seed_rows]
            if ids != expected_ids:
                raise SystemExit(f"resume_parent_denominator_or_order_invalid:{sid}")
            failed_seed_rows[sid] = []
            for item in seed_rows:
                if item.get("failed") is True:
                    failed_seed_rows[sid].append(
                        {
                            "record_id": item["record_id"],
                            "error": item.get("error"),
                            "raw_sha256": hashlib.sha256(str(item.get("raw_output") or "").encode("utf-8")).hexdigest(),
                            "analysis_attempts": item.get("analysis_attempts") or [],
                        }
                    )
                else:
                    # Do not write here: rows must be emitted in canonical source order,
                    # interleaved with any regenerated failures below.
                    seeded_valid_rows[sid][str(item["record_id"])] = item
        resume_metadata = {
            "parent_dir": str(resume),
            "parent_manifest_sha256": _sha256(resume / "run_manifest.json"),
            "parent_prediction_sha256": {sid: _sha256(resume / "predictions" / f"{sid}.predictions.jsonl") for sid in SYSTEMS},
            "excluded_failed_rows": failed_seed_rows,
        }
    existing = {sid: _load_jsonl_by_id(path) for sid, path in paths.items()}
    needs_generation = any(
        record_id not in existing[sid] and record_id not in seeded_valid_rows[sid]
        for sid in SYSTEMS for record_id in expected_ids
    )
    model = tokenizer = adapter_id = None
    full_provider = blind_provider = None
    systems: dict[str, Any] = {
        "degree_based_router": DegreeBasedRouterSystem(),
        "full_type_risk_aware_manager": FullTypeRiskAwareManagerSystem(),
    }
    if needs_generation:
        model, tokenizer, adapter_id = _load_model(args)
        full_provider = TransformerAnalysisProvider(
            model, tokenizer, args.max_new_tokens, args.retry_max_new_tokens,
            args.constrained_final_max_new_tokens, "pilot120_full_context",
            temperature=float(args.temperature),
        )
        blind_provider = TransformerAnalysisProvider(
            model, tokenizer, args.max_new_tokens, args.retry_max_new_tokens,
            args.constrained_final_max_new_tokens, "pilot120_context_blind",
            temperature=float(args.temperature),
        )
        systems["context_blind_manager"] = ContextBlindManagerSystem(analysis_provider=blind_provider)
    manifest = {
        "status": "RUNNING",
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
        "max_new_tokens": args.max_new_tokens,
        "retry_max_new_tokens": args.retry_max_new_tokens,
        "constrained_final_max_new_tokens": args.constrained_final_max_new_tokens,
        "constrained_final_emission_after_thinking_failures": True,
        "invalid_analysis_retry_attempts": 1,
        "evaluation_only": True,
        "pilot120_used_for_training_or_selection": False,
        "protected_data_accessed": False,
        "n_expected": len(expected_ids),
    }
    if resume_metadata is not None:
        manifest["resume"] = resume_metadata
    _write_json(output / "run_manifest.json", manifest)
    started_at = time.time()

    def write_progress(status: str, current_record_id: str | None = None) -> None:
        completed = sum(all(record_id in existing[sid] for sid in SYSTEMS) for record_id in expected_ids)
        elapsed_seconds = time.time() - started_at
        seconds_per_record = elapsed_seconds / completed if completed else None
        payload = {
            "status": status,
            "current_record_id": current_record_id,
            "records_completed": completed,
            "records_expected": len(expected_ids),
            "percent_complete": round(100.0 * completed / len(expected_ids), 2),
            "failed_rows_so_far": sum(
                row.get("failed") is True for sid in SYSTEMS for row in existing[sid].values()
            ),
            "elapsed_seconds": round(elapsed_seconds, 1),
            "estimated_remaining_seconds": (
                round(seconds_per_record * (len(expected_ids) - completed), 1)
                if seconds_per_record is not None else None
            ),
            "updated_at_epoch": time.time(),
        }
        _write_json(output / "progress.json", payload)
        _append_jsonl(output / "progress.log.jsonl", payload)

    write_progress("RUNNING")
    for row in source_rows:
        record = _system_input(row)
        # Materialise valid parent rows only when their canonical position is
        # reached. This prevents repaired middle rows being appended after all
        # seeded rows, which would invalidate the evaluator's ordered denominator.
        for sid in SYSTEMS:
            seed = seeded_valid_rows[sid].get(record.record_id)
            if seed is not None and record.record_id not in existing[sid]:
                _append_jsonl(paths[sid], seed)
                existing[sid][record.record_id] = seed
        if all(record.record_id in existing[sid] for sid in SYSTEMS):
            continue
        full_analysis = None
        full_meta = None
        full_raw = None
        full_error = None
        full_latency = 0.0
        full_attempts: list[dict[str, Any]] = []
        if any(record.record_id not in existing[sid] for sid in ("degree_based_router", "full_type_risk_aware_manager")):
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
        for sid in ("degree_based_router", "full_type_risk_aware_manager"):
            if record.record_id in existing[sid]:
                continue
            started = time.perf_counter()
            result = None
            error = full_error
            if error is None and full_analysis is not None:
                try:
                    result = systems[sid].run(record, cached_analysis=full_analysis)
                except Exception as exc:  # noqa: BLE001
                    error = f"system_exception:{type(exc).__name__}:{exc}"
            pred = _prediction_row(
                record_id=record.record_id, system_id=sid, result=result, meta=full_meta,
                raw_output=full_raw, latency_ms=full_latency + (time.perf_counter() - started) * 1000.0,
                error=error, analysis_attempts=full_attempts,
            )
            _append_jsonl(paths[sid], pred)
            existing[sid][record.record_id] = pred
        sid = "context_blind_manager"
        if record.record_id not in existing[sid]:
            if blind_provider is None:
                raise RuntimeError("blind_provider_not_loaded")
            started = time.perf_counter()
            result = None
            error = None
            blind_raw = None
            blind_meta = None
            try:
                result = systems[sid].run(record)
                blind_input = record.without_context()
                blind_meta = blind_provider.metadata_by_input_hash[blind_input.fingerprint()]
                blind_raw = blind_provider.raw_by_input_hash[blind_input.fingerprint()]
            except Exception as exc:  # noqa: BLE001
                error = f"system_exception:{type(exc).__name__}:{exc}"
                blind_input = record.without_context()
                blind_raw = blind_provider.raw_by_input_hash.get(blind_input.fingerprint())
            blind_attempts = blind_provider.attempts_by_input_hash.get(record.without_context().fingerprint(), [])
            pred = _prediction_row(
                record_id=record.record_id, system_id=sid, result=result, meta=blind_meta,
                raw_output=blind_raw, latency_ms=(time.perf_counter() - started) * 1000.0,
                error=error, analysis_attempts=blind_attempts,
            )
            _append_jsonl(paths[sid], pred)
            existing[sid][record.record_id] = pred
        write_progress("RUNNING", record.record_id)

    write_progress("EVALUATING")
    reports: dict[str, Any] = {}
    validation: dict[str, Any] = {}
    for sid, path in paths.items():
        rows = p120.load_jsonl(path)
        ids = [str(row.get("record_id") or "") for row in rows]
        validation[sid] = {"n_rows": len(rows), "ordered_complete": ids == expected_ids}
        if ids != expected_ids:
            raise SystemExit(f"prediction_denominator_or_order_invalid:{sid}")
        reports[sid] = p120.evaluate_predictions(
            path, config_path=root / "configs/evaluation/pilot_120_v1.json", paths=p120.default_paths(root)
        )
        _write_json(output / "evaluations" / f"{sid}.eval.json", reports[sid])
    manifest["status"] = "VERIFY_PASSED" if all(
        report["operational"]["denominator"] == p120.EXPECTED_N
        and report["operational"]["schema_valid_rate"] == 1.0
        and report["operational"]["failure_error_rate"] == 0.0
        for report in reports.values()
    ) else "VERIFY_FAILED"
    manifest["prediction_sha256"] = {sid: _sha256(path) for sid, path in paths.items()}
    manifest["validation"] = validation
    manifest["reports"] = {sid: str((output / "evaluations" / f"{sid}.eval.json").as_posix()) for sid in SYSTEMS}
    _write_json(output / "run_manifest.json", manifest)
    write_progress(manifest["status"])
    print(json.dumps({"status": manifest["status"], "systems": list(SYSTEMS), "validation": validation}, sort_keys=True))
    return 0 if manifest["status"] == "VERIFY_PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
