#!/usr/bin/env python3
"""Resumable T28 source-dev evaluation using frozen T27F task contracts.

Evaluates each frozen (record_id, task_id) call with:
- build_task_prompt (same prompt-hash gate as T28-R3 freeze)
- Qwen chat template rendering
- LMFE constrained decoding (no unconstrained fallback)
- one 4-bit base+adapter load, base via PeftModel.disable_adapter()

Does not use Pilot-120 / final gold. Outputs are keyed by call_id for resume.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex  # noqa: E402
from ambiguity_manager.model.generation_schema import effective_task_registry  # noqa: E402
from ambiguity_manager.model.t28 import T28Error, assert_dev_only  # noqa: E402
from ambiguity_manager.model.t28_integrity import (  # noqa: E402
    AUTHORITATIVE_HASHES,
    T28IntegrityError,
    load_source_dev_view_index,
    record_for_manifest_row,
)
from ambiguity_manager.model.t28_trainer import iter_jsonl, sha256_file  # noqa: E402
from ambiguity_manager.model.task_constrained_decoding import (  # noqa: E402
    ConstrainedDecodingError,
    generate_with_task_constraint,
)
from ambiguity_manager.model.task_prediction_contract import (  # noqa: E402
    build_task_prompt,
    get_task_spec,
    task_schema_hash,
    validate_task_schema,
    validate_task_semantics,
    _extract_json_object,
)


EXPECTED_DEV_SHA256 = AUTHORITATIVE_HASHES["dev_manifest"]
EXPECTED_PERMITTED_SHA256 = AUTHORITATIVE_HASHES["permitted_view"]
EXPECTED_BASE_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
ROUTING_EVAL_CONTRACT = "t28_t27f_task_conditioned_source_dev_routing_eval_v1"
INTERPRETATIONS_DECODER_BOUNDS_CONTRACT = "t28_interpretations_decoder_bounds_v1"
INTERPRETATIONS_TEXT_BOUNDED_DECODER_CONTRACT = "t28_interpretations_decoder_bounds_v2"
INTERPRETATIONS_SUPPORTED_FIELDS_DECODER_CONTRACT = "t28_interpretations_decoder_bounds_v3"
T28_CPC_VALUE_BOUNDED_DECODER_CONTRACT = "t28_decoder_bounds_v4"


def load_decoder_bounds(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    """Load the explicit, source-compatible inference-only bound contract.

    The frozen prompt/schema continue to be hash-checked unchanged. This config
    narrows only the LMFE grammar to the observed non-lossy source target shape.
    """
    if path is None:
        return None, None
    if not path.is_file():
        raise T28Error(f"decoder_bounds_config_missing:{path}")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise T28Error(f"decoder_bounds_config_invalid_json:{path}") from exc
    if payload.get("contract_id") not in {
        INTERPRETATIONS_DECODER_BOUNDS_CONTRACT,
        INTERPRETATIONS_TEXT_BOUNDED_DECODER_CONTRACT,
        INTERPRETATIONS_SUPPORTED_FIELDS_DECODER_CONTRACT,
        T28_CPC_VALUE_BOUNDED_DECODER_CONTRACT,
    }:
        raise T28Error("decoder_bounds_contract_id_mismatch")
    if payload.get("frozen") is not True:
        raise T28Error("decoder_bounds_contract_not_frozen")
    if payload.get("task_id") != "predict_interpretations_v1":
        raise T28Error("decoder_bounds_task_id_mismatch")
    if payload.get("max_candidate_interpretations") != 4:
        raise T28Error("decoder_bounds_not_source_compatible")
    text_limit = payload.get("max_candidate_text_characters")
    if payload["contract_id"] in {
        INTERPRETATIONS_TEXT_BOUNDED_DECODER_CONTRACT,
        INTERPRETATIONS_SUPPORTED_FIELDS_DECODER_CONTRACT,
        T28_CPC_VALUE_BOUNDED_DECODER_CONTRACT,
    }:
        if text_limit != 256:
            raise T28Error("decoder_bounds_text_limit_not_source_compatible")
    elif text_limit is not None:
        raise T28Error("decoder_bounds_unexpected_text_limit")
    if payload["contract_id"] in {
        INTERPRETATIONS_SUPPORTED_FIELDS_DECODER_CONTRACT,
        T28_CPC_VALUE_BOUNDED_DECODER_CONTRACT,
    }:
        if payload.get("suppress_unsupported_optional_fields") is not True:
            raise T28Error("decoder_bounds_unsupported_fields_not_suppressed")
    elif payload.get("suppress_unsupported_optional_fields") is not None:
        raise T28Error("decoder_bounds_unexpected_unsupported_fields_switch")
    cpc_limit = payload.get("max_cpc_value_characters")
    if payload["contract_id"] == T28_CPC_VALUE_BOUNDED_DECODER_CONTRACT:
        if cpc_limit != 64:
            raise T28Error("decoder_bounds_cpc_value_limit_not_source_compatible")
    elif cpc_limit is not None:
        raise T28Error("decoder_bounds_unexpected_cpc_value_limit")
    return payload, sha256_hex(raw)


def decoder_schema_for_task(
    task_spec: dict[str, Any], decoder_bounds: dict[str, Any] | None
) -> dict[str, Any]:
    """Return the grammar schema, retaining the frozen prompt schema verbatim."""
    schema = task_spec["json_schema"]
    if decoder_bounds is None:
        return schema
    if task_spec.get("task_id") == "predict_cpc_v1" and decoder_bounds.get("max_cpc_value_characters") is not None:
        bounded = copy.deepcopy(schema)
        value = bounded.get("$defs", {}).get("cpc_slot", {}).get("properties", {}).get("value")
        if not isinstance(value, dict):
            raise T28Error("decoder_bounds_cpc_value_missing")
        value["maxLength"] = int(decoder_bounds["max_cpc_value_characters"])
        return bounded
    if task_spec.get("task_id") != decoder_bounds["task_id"]:
        return schema
    bounded = copy.deepcopy(schema)
    candidates = bounded.get("properties", {}).get("candidate_interpretations")
    if not isinstance(candidates, dict) or candidates.get("type") != "array":
        raise T28Error("decoder_bounds_candidate_array_missing")
    candidates["maxItems"] = int(decoder_bounds["max_candidate_interpretations"])
    text_limit = decoder_bounds.get("max_candidate_text_characters")
    if text_limit is not None:
        item_props = candidates.get("items", {}).get("properties", {})
        text = item_props.get("text")
        if not isinstance(text, dict):
            raise T28Error("decoder_bounds_candidate_text_missing")
        text["maxLength"] = int(text_limit)
    if decoder_bounds.get("suppress_unsupported_optional_fields"):
        bounded["properties"].pop("selected_interpretation", None)
        candidates.get("items", {}).get("properties", {}).pop("cpc", None)
    return bounded


def parse_task_ids(raw: str | None) -> set[str] | None:
    """Parse comma-separated task ids. Empty/None means no filter."""
    if raw is None:
        return None
    values = {part.strip() for part in str(raw).split(",") if part.strip()}
    return values or None


def load_call_ids_file(path: Path | None) -> list[str] | None:
    """Load ordered call_ids (one per line; '#' comments / blanks ignored)."""
    if path is None:
        return None
    if not path.is_file():
        raise T28Error(f"call_ids_file_missing:{path}")
    call_ids: list[str] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text in seen:
            raise T28Error(f"duplicate_call_id_in_file:{path}:{line_number}:{text}")
        seen.add(text)
        call_ids.append(text)
    if not call_ids:
        raise T28Error(f"call_ids_file_empty:{path}")
    return call_ids


def select_calls(
    calls: list[dict[str, Any]],
    *,
    task_ids: set[str] | None = None,
    call_ids: list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Filter built calls for subset smoke runs. Fail closed on unknown call_ids.

    Hash gates must already have been applied while building ``calls``.
    """
    selected = list(calls)
    if task_ids is not None:
        selected = [call for call in selected if str(call["task_id"]) in task_ids]
    if call_ids is not None:
        by_id = {str(call["call_id"]): call for call in selected}
        missing = [cid for cid in call_ids if cid not in by_id]
        if missing:
            raise T28Error("call_ids_not_in_selected_set:" + ",".join(missing[:10]))
        selected = [by_id[cid] for cid in call_ids]
    if limit is not None:
        if limit <= 0:
            raise T28Error("limit_must_be_positive")
        selected = selected[: int(limit)]
    if not selected:
        raise T28Error("no_task_calls_after_subset_filters")
    return selected


def apply_adapter_scale(model: Any, scale: float) -> int:
    """Attenuate/amplify active LoRA scaling (peft LoraLayer.set_scale). scale=1.0 is default."""
    if scale <= 0:
        raise T28Error("adapter_scale_must_be_positive")
    applied = 0
    for module in model.modules():
        scaling = getattr(module, "scaling", None)
        set_scale = getattr(module, "set_scale", None)
        if not isinstance(scaling, dict) or not callable(set_scale):
            continue
        for adapter_name in list(scaling.keys()):
            set_scale(adapter_name, float(scale))
            applied += 1
    if applied <= 0 and abs(float(scale) - 1.0) > 1e-12:
        raise T28Error("adapter_scale_targets_not_found")
    return applied


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
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
            call_id = str(row.get("call_id") or "")
            if not call_id or call_id in completed:
                raise T28Error(f"duplicate_or_missing_eval_call_id:{path}:{line_number}")
            completed[call_id] = row
    return completed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verdict(task_spec: dict[str, Any], raw_text: str) -> dict[str, Any]:
    parsed = _extract_json_object(raw_text)
    if parsed is None:
        return {
            "status": "no_json",
            "accepted": False,
            "parsed_output": None,
            "schema_errors": ["json_parse_failed"],
            "semantic_errors": [],
            "raw_output": raw_text,
        }
    schema_errors = validate_task_schema(task_spec, parsed)
    semantic_errors = validate_task_semantics(task_spec, parsed)
    accepted = not schema_errors and not semantic_errors
    return {
        "status": "schema_valid" if accepted else "schema_invalid",
        "accepted": accepted,
        "parsed_output": parsed,
        "schema_errors": schema_errors,
        "semantic_errors": semantic_errors,
        "raw_output": raw_text,
    }


def build_calls(rows: list[dict[str, Any]], view_index: dict[str, dict[str, Any]], registry: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for row in rows:
        record_id = str(row["record_id"])
        try:
            record = record_for_manifest_row(row, view_index)
        except T28IntegrityError as exc:
            raise T28Error(str(exc)) from exc
        task_ids = [str(t) for t in row.get("task_ids") or []]
        if not task_ids:
            continue
        for task_id in task_ids:
            task_spec = get_task_spec(registry, task_id)
            observed_schema = task_schema_hash(task_spec)
            expected_schema = str((row.get("schema_hashes") or {}).get(task_id) or "")
            if expected_schema and observed_schema != expected_schema:
                raise T28Error(f"schema_hash_mismatch:{record_id}:{task_id}:{observed_schema}:{expected_schema}")
            prompt = build_task_prompt(
                task_spec=task_spec,
                command=str(record.get("command") or ""),
                scene_context=record.get("scene_context"),
                dialogue_history=record.get("dialogue_history") or [],
                capability_context=record.get("capability_context"),
                analysis_variant="full_context",
            )
            prompt_hash = sha256_hex(prompt.encode("utf-8"))
            expected_prompt = str((row.get("prompt_hashes") or {}).get(task_id) or "")
            if expected_prompt and prompt_hash != expected_prompt:
                raise T28Error(f"prompt_hash_mismatch:{record_id}:{task_id}")
            calls.append(
                {
                    "call_id": f"{record_id}::{task_id}",
                    "record_id": record_id,
                    "task_id": task_id,
                    "split": row["split"],
                    "prompt": prompt,
                    "prompt_hash": prompt_hash,
                    "schema_hash": observed_schema,
                    "max_new_tokens": int(task_spec.get("maximum_output_tokens") or 128),
                    "task_spec": task_spec,
                }
            )
    return calls


def build_routing_eval_rows(
    view_index: dict[str, dict[str, Any]], registry: dict[str, Any]
) -> list[dict[str, Any]]:
    """Build the deterministic full-manager source-dev routing cohort.

    The frozen task manifest contains only supervised task targets.  That is
    sufficient for task metrics, but not for a full-manager routing metric:
    most records have only one of the required CPC/ambiguity targets.  This
    derived cohort uses only source-dev records already marked routing-eligible
    and requests every task schema at inference time.  It neither changes
    source membership nor manufactures a task target for scoring.
    """
    task_ids = [str(task["task_id"]) for task in registry.get("tasks") or []]
    if not task_ids:
        raise T28Error("routing_eval_task_registry_empty")
    rows: list[dict[str, Any]] = []
    for record_id in sorted(view_index):
        view = view_index[record_id]
        record = view.get("record")
        if not isinstance(record, dict):
            raise T28Error(f"routing_eval_missing_record:{record_id}")
        eligibility = record.get("label_eligibility") or {}
        route = record.get("recommended_strategy")
        if eligibility.get("routing") is not True or not isinstance(route, str) or not route:
            continue
        if view.get("source_holdout") or view.get("protected_data"):
            raise T28Error(f"routing_eval_protected_or_holdout_record:{record_id}")
        rows.append(
            {
                "record_id": record_id,
                "split": "source_dev",
                "source_holdout": False,
                "protected_data": False,
                "task_ids": task_ids,
                "routing_label": route,
            }
        )
    if not rows:
        raise T28Error("routing_eval_no_eligible_records")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--dev-manifest", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--base-model", default="Qwen/Qwen3-8B")
    parser.add_argument("--base-revision", default=EXPECTED_BASE_REVISION)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Evaluate at most N calls after other filters (subset smoke).",
    )
    parser.add_argument(
        "--task-ids",
        default=None,
        help="Comma-separated task ids to keep (e.g. predict_ambiguity_v1).",
    )
    parser.add_argument(
        "--call-ids-file",
        type=Path,
        default=None,
        help="Optional ordered call_id list for a fixed smoke subset.",
    )
    parser.add_argument(
        "--adapter-scale",
        type=float,
        default=1.0,
        help="LoRA inference scale via peft LoraLayer.set_scale (1.0=trained default).",
    )
    parser.add_argument(
        "--max-new-tokens-multiplier",
        type=float,
        default=1.0,
        help="Multiply per-task maximum_output_tokens at eval only (prompt/schema hashes unchanged).",
    )
    parser.add_argument(
        "--repetition-penalty",
        type=float,
        default=1.0,
        help="Inference-only HF repetition penalty; must be >= 1.0.",
    )
    parser.add_argument(
        "--no-repeat-ngram-size",
        type=int,
        default=0,
        help="Inference-only HF no-repeat n-gram guard; 0 disables it.",
    )
    parser.add_argument(
        "--decoder-bounds-config",
        type=Path,
        default=None,
        help="Frozen inference-only decoder-bound contract; frozen prompt/schema hashes remain unchanged.",
    )
    parser.add_argument(
        "--routing-eval",
        action="store_true",
        help=(
            "Evaluate every task schema for the deterministic source-dev routing cohort. "
            "This is inference-only for task fields without a supervised target."
        ),
    )
    args = parser.parse_args()

    if args.base_revision != EXPECTED_BASE_REVISION:
        raise T28Error("base_revision_not_frozen")
    if sha256_file(args.dev_manifest) != EXPECTED_DEV_SHA256:
        raise T28Error("dev_manifest_hash_mismatch")
    permitted_view = args.bundle_root / "data/processed/weak_pool/t28_permitted_train_dev.jsonl"
    if sha256_file(permitted_view) != EXPECTED_PERMITTED_SHA256:
        raise T28Error("permitted_view_hash_mismatch")
    frozen_rows = list(iter_jsonl(args.dev_manifest))
    rows = frozen_rows
    assert_dev_only(frozen_rows)
    if not frozen_rows or any(str(row.get("split")) != "source_dev" for row in frozen_rows):
        raise T28Error("dev_manifest_not_source_dev_only")
    if any(row.get("source_holdout") or row.get("protected_data") for row in rows):
        raise T28Error("protected_or_holdout_record_detected")
    try:
        view_index = load_source_dev_view_index(permitted_view)
    except T28IntegrityError as exc:
        raise T28Error(str(exc)) from exc
    registry = effective_task_registry(ROOT)
    decoder_bounds, decoder_bounds_sha256 = load_decoder_bounds(args.decoder_bounds_config)
    if args.routing_eval:
        rows = build_routing_eval_rows(view_index, registry)
    all_calls = build_calls(rows, view_index, registry)
    if not all_calls:
        raise T28Error("no_task_calls_in_dev_manifest")
    task_ids = parse_task_ids(args.task_ids)
    call_ids = load_call_ids_file(args.call_ids_file)
    calls = select_calls(
        all_calls,
        task_ids=task_ids,
        call_ids=call_ids,
        limit=args.limit,
    )
    if float(args.max_new_tokens_multiplier) <= 0:
        raise T28Error("max_new_tokens_multiplier_must_be_positive")
    if float(args.repetition_penalty) < 1.0:
        raise T28Error("repetition_penalty_must_be_at_least_one")
    if int(args.no_repeat_ngram_size) < 0:
        raise T28Error("no_repeat_ngram_size_must_be_nonnegative")
    if abs(float(args.max_new_tokens_multiplier) - 1.0) > 1e-12:
        for call in calls:
            base_tokens = int(call["max_new_tokens"])
            call["max_new_tokens"] = max(1, int(round(base_tokens * float(args.max_new_tokens_multiplier))))
            call["max_new_tokens_base"] = base_tokens
    if not args.adapter.is_dir() or not (args.adapter / "adapter_config.json").is_file():
        raise T28Error("adapter_missing_or_incomplete")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results_path = args.output_dir / "dev_raw_and_parsed.jsonl"
    log_path = args.output_dir / "evaluation_progress.log.jsonl"
    completed = _load_completed(results_path)
    pending = [call for call in calls if call["call_id"] not in completed]
    started_epoch = time.time()
    run_meta = {
        "status": "RUNNING",
        "contract": ROUTING_EVAL_CONTRACT if args.routing_eval else "t28_t27f_task_conditioned_source_dev_eval_v1",
        "dev_manifest_sha256": sha256_file(args.dev_manifest),
        "permitted_view_sha256": sha256_file(permitted_view),
        "dev_manifest_count": len(frozen_rows),
        "evaluation_record_count": len(rows),
        "routing_eval": bool(args.routing_eval),
        "task_call_count_full": len(all_calls),
        "task_call_count": len(calls),
        "subset_filters": {
            "limit": args.limit,
            "task_ids": sorted(task_ids) if task_ids is not None else None,
            "call_ids_file": str(args.call_ids_file) if args.call_ids_file is not None else None,
            "call_ids_count": len(call_ids) if call_ids is not None else None,
        },
        "adapter_scale": float(args.adapter_scale),
        "max_new_tokens_multiplier": float(args.max_new_tokens_multiplier),
        "repetition_penalty": float(args.repetition_penalty),
        "no_repeat_ngram_size": int(args.no_repeat_ngram_size),
        "decoder_bounds": (
            {
                "contract_id": decoder_bounds["contract_id"],
                "sha256": decoder_bounds_sha256,
                "task_id": decoder_bounds["task_id"],
                "max_candidate_interpretations": decoder_bounds["max_candidate_interpretations"],
                "max_candidate_text_characters": decoder_bounds.get("max_candidate_text_characters"),
                "suppress_unsupported_optional_fields": decoder_bounds.get("suppress_unsupported_optional_fields", False),
                "max_cpc_value_characters": decoder_bounds.get("max_cpc_value_characters"),
                "prompt_schema_unchanged": True,
            }
            if decoder_bounds is not None
            else None
        ),
        "completed_before_start": len(completed),
        "base_model": args.base_model,
        "base_revision": args.base_revision,
        "adapter_path": str(args.adapter),
        "bundle_root": str(args.bundle_root),
        "log_path": str(log_path),
        "source_holdout_loaded": 0,
        "protected_records_loaded": 0,
        "evaluation_leakage_detected": False,
        "pilot120_used": False,
        "started_at_epoch": started_epoch,
    }
    _write_json(args.output_dir / "evaluation_manifest.json", run_meta)
    _append_log(log_path, "evaluation_started", total=len(calls), completed=len(completed), remaining=len(pending))
    if not pending:
        return _finalize(args.output_dir, calls, completed, run_meta)

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    _append_log(log_path, "model_loading_started", completed=len(completed))
    tokenizer = AutoTokenizer.from_pretrained(
        args.base_model, revision=args.base_revision, local_files_only=True
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    base = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        revision=args.base_revision,
        local_files_only=True,
        quantization_config=bnb,
        device_map="auto",
    )
    adapted = PeftModel.from_pretrained(base, str(args.adapter), is_trainable=False)
    adapted.eval()
    scale_layers = apply_adapter_scale(adapted, float(args.adapter_scale))
    _append_log(
        log_path,
        "model_loading_finished",
        completed=len(completed),
        model_mode="single_peft_disable_adapter",
        adapter_scale=float(args.adapter_scale),
        adapter_scale_layers=scale_layers,
    )

    for index, call in enumerate(pending, 1):
        task_spec = call["task_spec"]
        decoder_schema = decoder_schema_for_task(task_spec, decoder_bounds)
        call_started = time.time()
        try:
            with adapted.disable_adapter():
                base_gen = generate_with_task_constraint(
                    model=adapted,
                    tokenizer=tokenizer,
                    prompt=call["prompt"],
                    json_schema=decoder_schema,
                    max_new_tokens=call["max_new_tokens"],
                    generation_config={
                        "do_sample": False,
                        "repetition_penalty": float(args.repetition_penalty),
                        "no_repeat_ngram_size": int(args.no_repeat_ngram_size),
                    },
                )
            adapter_gen = generate_with_task_constraint(
                model=adapted,
                tokenizer=tokenizer,
                prompt=call["prompt"],
                json_schema=decoder_schema,
                    max_new_tokens=call["max_new_tokens"],
                    generation_config={
                        "do_sample": False,
                        "repetition_penalty": float(args.repetition_penalty),
                        "no_repeat_ngram_size": int(args.no_repeat_ngram_size),
                    },
            )
        except ConstrainedDecodingError as exc:
            raise T28Error(f"constraint_failed_no_unconstrained_fallback:{call['call_id']}:{exc}") from exc
        if base_gen.get("unconstrained_fallback") or adapter_gen.get("unconstrained_fallback"):
            raise T28Error(f"unconstrained_fallback_refused:{call['call_id']}")
        base_verdict = _verdict(task_spec, str(base_gen.get("raw_text") or ""))
        adapter_verdict = _verdict(task_spec, str(adapter_gen.get("raw_text") or ""))
        emitted = {
            "call_id": call["call_id"],
            "record_id": call["record_id"],
            "task_id": call["task_id"],
            "split": call["split"],
            "prompt_hash": call["prompt_hash"],
            "schema_hash": call["schema_hash"],
            "decoder_schema_hash": sha256_hex(canonical_json_bytes(decoder_schema)),
            "max_new_tokens": call["max_new_tokens"],
            "prompt_chars": len(call["prompt"]),
            "base_raw_output": base_verdict["raw_output"],
            "adapter_raw_output": adapter_verdict["raw_output"],
            "base_parsed": base_verdict,
            "adapter_parsed": adapter_verdict,
            "outputs_differ": base_verdict["raw_output"] != adapter_verdict["raw_output"],
            "base_transport": {k: base_gen.get(k) for k in ("transport_status", "constraint_initialised", "generated_token_count", "termination_reason")},
            "adapter_transport": {k: adapter_gen.get(k) for k in ("transport_status", "constraint_initialised", "generated_token_count", "termination_reason")},
            "seconds": time.time() - call_started,
        }
        _append_jsonl(results_path, [emitted])
        completed[call["call_id"]] = emitted
        elapsed = max(time.time() - started_epoch, 1e-6)
        rate = len(completed) / elapsed
        progress = {
            "status": "RUNNING",
            "completed": len(completed),
            "total": len(calls),
            "remaining": len(calls) - len(completed),
            "records_per_second": rate,
            "eta_seconds": ((len(calls) - len(completed)) / rate if rate > 0 else None),
            "last_call_id": call["call_id"],
            "last_call_seconds": emitted["seconds"],
            "last_event_epoch": time.time(),
        }
        _write_json(args.output_dir / "evaluation_progress.json", progress)
        _append_log(log_path, "call_finished", index=index, **progress)
        print(json.dumps({"event": "call_finished", **progress}, sort_keys=True), flush=True)
    return _finalize(args.output_dir, calls, completed, run_meta)


def _finalize(output_dir: Path, calls: list[dict[str, Any]], completed: dict[str, dict[str, Any]], meta: dict[str, Any]) -> int:
    if len(completed) != len(calls):
        raise T28Error("dev_evaluation_incomplete")
    adapter_status: dict[str, int] = {}
    base_status: dict[str, int] = {}
    by_task: dict[str, dict[str, int]] = {}
    base_by_task: dict[str, dict[str, int]] = {}
    ambiguity_matrix: dict[str, int] = {}
    for row in completed.values():
        adapter_status[str(row["adapter_parsed"].get("status"))] = adapter_status.get(str(row["adapter_parsed"].get("status")), 0) + 1
        base_status[str(row["base_parsed"].get("status"))] = base_status.get(str(row["base_parsed"].get("status")), 0) + 1
        task = str(row["task_id"])
        by_task.setdefault(task, {})
        by_task[task][str(row["adapter_parsed"].get("status"))] = by_task[task].get(str(row["adapter_parsed"].get("status")), 0) + 1
        base_by_task.setdefault(task, {})
        base_by_task[task][str(row["base_parsed"].get("status"))] = base_by_task[task].get(str(row["base_parsed"].get("status")), 0) + 1
        if task == "predict_ambiguity_v1":
            base_val = (row.get("base_parsed") or {}).get("parsed_output") or {}
            adapter_val = (row.get("adapter_parsed") or {}).get("parsed_output") or {}
            key = f"({base_val.get('ambiguity_present')},{adapter_val.get('ambiguity_present')})"
            ambiguity_matrix[key] = ambiguity_matrix.get(key, 0) + 1
    summary = {
        **meta,
        "status": "VERIFY_PASSED",
        "completed": len(completed),
        "remaining": 0,
        "silent_skips": 0,
        "adapter_status_counts": adapter_status,
        "base_status_counts": base_status,
        "adapter_status_by_task": by_task,
        "base_status_by_task": base_by_task,
        "ambiguity_present_matrix_base_adapter": ambiguity_matrix,
        "adapter_schema_valid_rate": adapter_status.get("schema_valid", 0) / max(len(completed), 1),
        "base_schema_valid_rate": base_status.get("schema_valid", 0) / max(len(completed), 1),
        "adapter_differs_from_base_count": sum(bool(row["outputs_differ"]) for row in completed.values()),
        "results_sha256": _sha256(output_dir / "dev_raw_and_parsed.jsonl"),
        "finished_at_epoch": time.time(),
    }
    _write_json(output_dir / "dev_evaluation.json", summary)
    _write_json(output_dir / "evaluation_progress.json", summary)
    _append_log(
        output_dir / "evaluation_progress.log.jsonl",
        "evaluation_finished",
        **{
            k: summary[k]
            for k in (
                "status",
                "completed",
                "adapter_schema_valid_rate",
                "base_schema_valid_rate",
                "ambiguity_present_matrix_base_adapter",
                "adapter_scale",
            )
            if k in summary
        },
    )
    print(
        json.dumps(
            {
                "event": "evaluation_finished",
                "status": summary["status"],
                "completed": summary["completed"],
                "adapter_schema_valid_rate": summary["adapter_schema_valid_rate"],
                "adapter_scale": summary.get("adapter_scale"),
                "ambiguity_present_matrix_base_adapter": summary.get("ambiguity_present_matrix_base_adapter"),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except T28Error as exc:
        print(f"T28_DEV_EVAL_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
