#!/usr/bin/env python3
"""Fresh, evaluation-only Pilot-120 emission for the proposed Figure 6 flow.

No gold or previous prediction is passed to the model. Outputs are append-only
per case and remain separate from frozen Pilot-120 and ABLE IX evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ambiguity_manager.model.task_constrained_decoding import generate_with_task_constraint  # noqa: E402
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES  # noqa: E402
from ambiguity_manager.systems.fig6_flow_v1 import Fig6GateInput, GATE_ORDER, route_fig6  # noqa: E402
from ambiguity_manager.systems.goal_first_analysis_v2 import AMBIGUITY_TYPES, AMBIGUITY_TYPE_HINTS  # noqa: E402

SOURCE = ROOT / "data/annotations/pilot_120_v1/source_canonical.jsonl"
SOURCE_SHA256 = "f33b1e29f1e8aa256a475f07213aa07247def47d8e2148d54a472a40b71b05c9"
RUN_ID = "pilot120_fig6_flow_v1_20260927"
MODEL_ID = "Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218"
FIELDS = ("command", "dialogue_history", "scene_context", "capability_context")
MATERIAL_SLOTS = tuple(name for name in CPC_SLOT_NAMES if name != "actor")
GATE_EVIDENCE = {
    "type": "object", "additionalProperties": False,
    "required": ["field", "quote"],
    "properties": {
        "field": {"type": "string", "enum": list(FIELDS)},
        "quote": {"type": "string", "maxLength": 240},
    },
}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["intent_summary", "cpc", "unresolved_slots", "pilot_ambiguity_types",
                 "alternative_interpretation", "slot_evidence", "gates", "gate_evidence"],
    "properties": {
        "intent_summary": {"type": "string", "maxLength": 400},
        "cpc": {
            "type": "object", "additionalProperties": False,
            "required": list(CPC_SLOT_NAMES),
            "properties": {
                name: {"type": ["string", "null"], "maxLength": 120}
                for name in CPC_SLOT_NAMES
            },
        },
        "unresolved_slots": {
            "type": "array", "uniqueItems": True,
            "items": {"type": "string", "enum": list(CPC_SLOT_NAMES)},
        },
        "pilot_ambiguity_types": {
            "type": "array", "uniqueItems": True,
            "items": {"type": "string", "enum": AMBIGUITY_TYPES},
        },
        "alternative_interpretation": {"type": ["string", "null"], "maxLength": 200},
        "slot_evidence": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["slot", "field", "quote"],
                "properties": {
                    "slot": {"type": "string", "enum": list(MATERIAL_SLOTS)},
                    "field": {"type": "string", "enum": list(FIELDS)},
                    "quote": {"type": "string", "maxLength": 240},
                },
            },
        },
        "gates": {
            "type": "object", "additionalProperties": False,
            "required": list(GATE_ORDER),
            "properties": {name: {"type": ["boolean", "null"]} for name in GATE_ORDER},
        },
        "gate_evidence": {
            "type": "object", "additionalProperties": False,
            "required": list(GATE_ORDER),
            "properties": {name: GATE_EVIDENCE for name in GATE_ORDER},
        },
    },
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_source() -> list[dict[str, Any]]:
    data = SOURCE.read_bytes()
    if sha256(data) != SOURCE_SHA256:
        raise ValueError("frozen_source_sha256_mismatch")
    rows = [json.loads(line) for line in data.splitlines() if line.strip()]
    ids = [row["record_id"] for row in rows]
    if len(rows) != 120 or len(set(ids)) != 120:
        raise ValueError("frozen_source_coverage_mismatch")
    return rows


def build_prompt(source: dict[str, Any]) -> str:
    payload = {field: source.get(field) for field in FIELDS}
    ambiguity_guide = "; ".join(f"{name}: {AMBIGUITY_TYPE_HINTS[name]}" for name in AMBIGUITY_TYPES)
    return (
        "You are a text-only robot task analyst. Return exactly one JSON object "
        "matching the supplied schema. Do not output a route or a recommendation. "
        "Use only the command, dialogue, scene, and capability context below. "
        "Interpret indirect requests using dialogue. Keep each CPC value short and "
        "concrete. For a material ambiguous or unsupported slot, use null and list "
        "it in unresolved_slots; do not guess an object, recipient, time, tool, "
        "destination, or constraint. Null can also mean not applicable when it is "
        "not in unresolved_slots. For each filled CPC slot other than actor, "
        "provide slot_evidence with one exact source quote and field. Do not "
        "claim a slot is grounded without its source evidence. If two material "
        "task readings remain possible, give the other reading in "
        "alternative_interpretation and set grounded false.\n"
        "pilot_ambiguity_types describes ambiguity present in the request, "
        "including types that context resolves; unresolved_slots describes only "
        "what remains unresolved after context. Do not tag action_order merely "
        "because a clearly ordered job has multiple steps. Use only these types: "
        f"{ambiguity_guide}.\n"
        "Assess five distinct yes/no questions. grounded: is every referent "
        "needed to carry out the interpreted task uniquely grounded in the supplied "
        "text? one_atomic_action: is exactly one atomic executable action specified "
        "(two sequential operations count as more than one)? capable: can the robot "
        "physically/technically perform that action? authorized: may this robot "
        "perform it under the stated permissions? risk_acceptable: is performing "
        "the task acceptable under the stated safety/risk constraints? Keep "
        "capability, permission, and risk separate. Use null whenever evidence is "
        "insufficient, never infer permission from physical ability. For each "
        "gate_evidence give one exact, short quote and its source field. Use an "
        "empty quote when the text contains no supporting evidence. Do not use "
        "gold labels or an assumed desired route.\n"
        f"INPUT_JSON={json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n"
        f"OUTPUT_JSON_SCHEMA={json.dumps(SCHEMA, ensure_ascii=False, sort_keys=True)}"
    )


def _field_text(source: dict[str, Any], field: str) -> str:
    value = source.get(field)
    return " ".join(str(part) for part in value) if isinstance(value, list) else str(value or "")


def validate_output(obj: Any, source: dict[str, Any]) -> tuple[dict[str, Any], dict[str, bool], dict[str, bool]]:
    if not isinstance(obj, dict) or set(obj) != set(SCHEMA["required"]):
        raise ValueError("output_keys_invalid")
    cpc = obj["cpc"]
    if not isinstance(cpc, dict) or set(cpc) != set(CPC_SLOT_NAMES):
        raise ValueError("cpc_keys_invalid")
    for value in cpc.values():
        if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 120):
            raise ValueError("cpc_value_invalid")
    unresolved = obj["unresolved_slots"]
    if not isinstance(unresolved, list) or len(set(unresolved)) != len(unresolved):
        raise ValueError("unresolved_slots_invalid")
    if any(name not in CPC_SLOT_NAMES or cpc[name] is not None for name in unresolved):
        raise ValueError("unresolved_slot_has_value_or_unknown_name")
    types = obj["pilot_ambiguity_types"]
    if not isinstance(types, list) or len(set(types)) != len(types) or any(name not in AMBIGUITY_TYPES for name in types):
        raise ValueError("pilot_ambiguity_types_invalid")
    alternative = obj["alternative_interpretation"]
    if alternative is not None and (not isinstance(alternative, str) or not alternative.strip() or len(alternative) > 200):
        raise ValueError("alternative_interpretation_invalid")
    slot_refs = obj["slot_evidence"]
    if not isinstance(slot_refs, list):
        raise ValueError("slot_evidence_invalid")
    slot_quote_supported: dict[str, bool] = {}
    for item in slot_refs:
        if not isinstance(item, dict) or set(item) != {"slot", "field", "quote"}:
            raise ValueError("slot_evidence_invalid")
        slot, field, quote = item["slot"], item["field"], item["quote"]
        if slot not in MATERIAL_SLOTS or slot in slot_quote_supported or field not in FIELDS or not isinstance(quote, str) or len(quote) > 240:
            raise ValueError("slot_evidence_invalid")
        slot_quote_supported[slot] = bool(quote.strip()) and quote.casefold() in _field_text(source, field).casefold()
    if not isinstance(obj["intent_summary"], str) or not obj["intent_summary"].strip():
        raise ValueError("intent_summary_invalid")
    gates, evidence = obj["gates"], obj["gate_evidence"]
    if not isinstance(gates, dict) or not isinstance(evidence, dict):
        raise ValueError("gates_invalid")
    if set(gates) != set(GATE_ORDER) or set(evidence) != set(GATE_ORDER):
        raise ValueError("gate_keys_invalid")
    effective = dict(gates)
    quote_supported: dict[str, bool] = {}
    for name in GATE_ORDER:
        if gates[name] is not None and type(gates[name]) is not bool:
            raise ValueError(f"gate_value_invalid:{name}")
        item = evidence[name]
        if not isinstance(item, dict) or set(item) != {"field", "quote"}:
            raise ValueError(f"gate_evidence_invalid:{name}")
        field, quote = item["field"], item["quote"]
        if field not in FIELDS or not isinstance(quote, str) or len(quote) > 240:
            raise ValueError(f"gate_evidence_invalid:{name}")
        supported = bool(quote.strip()) and quote.casefold() in _field_text(source, field).casefold()
        quote_supported[name] = supported
        if gates[name] is True and not supported:
            effective[name] = None
    if unresolved and effective["grounded"] is True:
        effective["grounded"] = False
    if alternative is not None and effective["grounded"] is True:
        effective["grounded"] = False
    if effective["grounded"] is True and any(
        cpc[name] is not None and not slot_quote_supported.get(name, False)
        for name in MATERIAL_SLOTS
    ):
        effective["grounded"] = None
    if cpc["action"] is None and effective["one_atomic_action"] is True:
        effective["one_atomic_action"] = None
    return effective, quote_supported, slot_quote_supported


def as_cpc(obj: dict[str, Any]) -> dict[str, dict[str, str | None]]:
    unresolved = set(obj["unresolved_slots"])
    return {
        name: {
            "status": "filled" if obj["cpc"][name] is not None else ("unknown" if name in unresolved else "not_applicable"),
            "value": obj["cpc"][name],
        }
        for name in CPC_SLOT_NAMES
    }


def load_existing(path: Path, expected: set[str]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        row = json.loads(line)
        rid = row.get("record_id")
        if rid not in expected or rid in rows or row.get("run_id") != RUN_ID:
            raise ValueError(f"invalid_existing_prediction:{number}:{rid}")
        rows[rid] = row
    return rows


def append_row(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--check-constraint", action="store_true")
    parser.add_argument("--record-id", action="append", default=[], help="technical smoke subset only")
    args = parser.parse_args()
    source = load_source()
    selected_ids = set(args.record_id)
    if selected_ids and (len(selected_ids) != len(args.record_id) or not selected_ids <= {row["record_id"] for row in source}):
        raise ValueError("invalid_smoke_record_ids")
    selected = [row for row in source if not selected_ids or row["record_id"] in selected_ids]
    output = args.out.resolve()
    if output == ROOT or output == SOURCE.parent or SOURCE.parent in output.parents:
        raise ValueError("output_must_be_separate")
    prompts = {row["record_id"]: build_prompt(row) for row in source}
    schema_hash = sha256(json.dumps(SCHEMA, sort_keys=True).encode())
    print(f"FIG6_PREFLIGHT_OK n=120 source={SOURCE_SHA256} schema={schema_hash}", flush=True)
    if args.check_constraint:
        from ambiguity_manager.model.task_constrained_decoding import compile_task_constraint
        compile_task_constraint(SCHEMA)
        print("FIG6_CONSTRAINT_OK", flush=True)
    if not args.run:
        return 0
    from one_turn_recovery_20260922 import BASE_MODEL, BASE_REVISION, _load_model  # noqa: E402

    if f"{BASE_MODEL}@{BASE_REVISION}" != MODEL_ID:
        raise ValueError("model_identity_changed")

    output.mkdir(parents=True, exist_ok=True)
    pred_path = output / "predictions.jsonl"
    existing = load_existing(pred_path, {row["record_id"] for row in selected})
    model, tokenizer = _load_model()
    for index, row in enumerate(selected):
        rid = row["record_id"]
        if rid in existing:
            continue
        prompt = prompts[rid]
        generation = generate_with_task_constraint(
            model=model, tokenizer=tokenizer, prompt=prompt, json_schema=SCHEMA,
            max_new_tokens=4096, generation_config={"do_sample": False, "repetition_penalty": 1.08},
        )
        raw = str(generation["raw_text"])
        prediction: dict[str, Any] = {
            "record_id": rid, "run_id": RUN_ID, "model_id": MODEL_ID,
            "source_sha256": SOURCE_SHA256, "schema_sha256": schema_hash,
            "prompt_sha256": sha256(prompt.encode()), "raw_sha256": sha256(raw.encode()),
            "raw_output": raw,
            "generated_token_count": generation["generated_token_count"],
            "termination_reason": generation["termination_reason"],
            "failed": False,
        }
        try:
            obj = json.loads(raw)
            effective, supported, slot_supported = validate_output(obj, row)
            gate_quotes = {name: obj["gate_evidence"][name]["quote"] for name in GATE_ORDER}
            decision = route_fig6(Fig6GateInput(**effective, evidence=gate_quotes))
            prediction.update({
                "parsed": obj, "gates": effective, "gate_quote_supported": supported,
                "slot_quote_supported": slot_supported,
                "cpc": as_cpc(obj), "route": decision.route.value,
                "first_blocking_gate": decision.first_blocking_gate,
                "gate_trace": [
                    {"gate": step.gate, "value": step.value, "evidence": step.evidence}
                    for step in decision.trace
                ],
            })
        except (ValueError, KeyError, TypeError) as exc:
            prediction.update({"failed": True, "error": f"schema_or_parser:{type(exc).__name__}:{exc}", "route": None})
        append_row(pred_path, prediction)
        print(f"FIG6_ROW {index + 1}/{len(selected)} {rid} route={prediction['route']} failed={prediction['failed']}", flush=True)
    print(f"FIG6_EMIT_DONE n={len(selected)} {pred_path} sha256={sha256(pred_path.read_bytes())}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
