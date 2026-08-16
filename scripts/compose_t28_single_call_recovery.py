#!/usr/bin/env python3
"""Compose a transparent T28 full-evaluation recovery from one re-executed call.

This is intentionally stricter than editing an artifact: every reused output
must validate against the final decoder grammar, the primary result set must
match the frozen routing call set exactly, and the retry must replace precisely
one previously rejected call.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from jsonschema import Draft202012Validator  # noqa: E402

from ambiguity_manager.model.generation_schema import effective_task_registry  # noqa: E402
from ambiguity_manager.model.t28 import T28Error  # noqa: E402
from ambiguity_manager.model.t28_integrity import (  # noqa: E402
    AUTHORITATIVE_HASHES,
    load_source_dev_view_index,
)
from ambiguity_manager.model.t28_trainer import sha256_file  # noqa: E402
from evaluate_t28_checkpoint_dev import (  # noqa: E402
    EXPECTED_BASE_REVISION,
    ROUTING_EVAL_CONTRACT,
    _finalize,
    _sha256,
    build_calls,
    build_routing_eval_rows,
    decoder_schema_for_task,
    load_decoder_bounds,
)


PRIMARY_DECODER_CONTRACT = "t28_interpretations_decoder_bounds_v3"
RECOVERY_DECODER_CONTRACT = "t28_decoder_bounds_v4"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise T28Error(f"t28_recovery_json_unreadable:{path}:{type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise T28Error(f"t28_recovery_json_not_object:{path}")
    return payload


def _load_rows(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise T28Error(f"t28_recovery_results_unreadable:{path}:{type(exc).__name__}") from exc
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise T28Error(f"t28_recovery_results_invalid_json:{path}:{number}") from exc
        call_id = str(row.get("call_id") or "")
        if not call_id or call_id in rows:
            raise T28Error(f"t28_recovery_duplicate_or_missing_call_id:{path}:{number}")
        rows[call_id] = row
    return rows


def _accepted_under_final_decoder(
    *, row: Mapping[str, Any], task_spec: Mapping[str, Any], decoder_bounds: Mapping[str, Any]
) -> None:
    schema = decoder_schema_for_task(dict(task_spec), dict(decoder_bounds))
    validator = Draft202012Validator(schema)
    for mode in ("base", "adapter"):
        verdict = row.get(f"{mode}_parsed") or {}
        parsed = verdict.get("parsed_output")
        if verdict.get("accepted") is not True or not isinstance(parsed, dict):
            raise T28Error(f"t28_recovery_reused_{mode}_not_accepted:{row.get('call_id')}")
        errors = list(validator.iter_errors(parsed))
        if errors:
            raise T28Error(f"t28_recovery_reused_{mode}_violates_final_decoder:{row.get('call_id')}")


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--dev-manifest", type=Path, required=True)
    parser.add_argument("--primary-evaluation-dir", type=Path, required=True)
    parser.add_argument("--repair-evaluation-dir", type=Path, required=True)
    parser.add_argument("--decoder-bounds-config", type=Path, required=True)
    parser.add_argument("--repair-call-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists():
        raise T28Error("t28_recovery_output_exists")
    if sha256_file(args.dev_manifest) != AUTHORITATIVE_HASHES["dev_manifest"]:
        raise T28Error("t28_recovery_dev_manifest_hash_mismatch")
    permitted = args.bundle_root / "data/processed/weak_pool/t28_permitted_train_dev.jsonl"
    if sha256_file(permitted) != AUTHORITATIVE_HASHES["permitted_view"]:
        raise T28Error("t28_recovery_permitted_view_hash_mismatch")

    decoder_bounds, decoder_bounds_sha256 = load_decoder_bounds(args.decoder_bounds_config)
    if decoder_bounds is None or decoder_bounds.get("contract_id") != RECOVERY_DECODER_CONTRACT:
        raise T28Error("t28_recovery_decoder_contract_mismatch")
    primary_manifest = _load_json(args.primary_evaluation_dir / "evaluation_manifest.json")
    repair_manifest = _load_json(args.repair_evaluation_dir / "evaluation_manifest.json")
    if primary_manifest.get("contract") != ROUTING_EVAL_CONTRACT or primary_manifest.get("routing_eval") is not True:
        raise T28Error("t28_recovery_primary_not_full_routing_evaluation")
    if primary_manifest.get("base_revision") != EXPECTED_BASE_REVISION:
        raise T28Error("t28_recovery_primary_base_revision_mismatch")
    if (primary_manifest.get("decoder_bounds") or {}).get("contract_id") != PRIMARY_DECODER_CONTRACT:
        raise T28Error("t28_recovery_primary_decoder_contract_mismatch")
    if repair_manifest.get("routing_eval") is not True or repair_manifest.get("task_call_count") != 1:
        raise T28Error("t28_recovery_repair_not_single_call")
    if (repair_manifest.get("decoder_bounds") or {}).get("contract_id") != RECOVERY_DECODER_CONTRACT:
        raise T28Error("t28_recovery_repair_decoder_contract_mismatch")
    if repair_manifest.get("adapter_scale") != primary_manifest.get("adapter_scale"):
        raise T28Error("t28_recovery_adapter_scale_mismatch")
    if repair_manifest.get("adapter_path") != primary_manifest.get("adapter_path"):
        raise T28Error("t28_recovery_adapter_path_mismatch")

    registry = effective_task_registry(ROOT)
    view_index = load_source_dev_view_index(permitted)
    calls = build_calls(build_routing_eval_rows(view_index, registry), view_index, registry)
    expected = {str(call["call_id"]): call for call in calls}
    primary_rows = _load_rows(args.primary_evaluation_dir / "dev_raw_and_parsed.jsonl")
    repair_rows = _load_rows(args.repair_evaluation_dir / "dev_raw_and_parsed.jsonl")
    if set(primary_rows) != set(expected):
        raise T28Error("t28_recovery_primary_call_set_mismatch")
    if set(repair_rows) != {args.repair_call_id} or args.repair_call_id not in expected:
        raise T28Error("t28_recovery_repair_call_set_mismatch")
    primary_bad = primary_rows[args.repair_call_id]
    if any((primary_bad.get(f"{mode}_parsed") or {}).get("accepted") is True for mode in ("base", "adapter")):
        raise T28Error("t28_recovery_primary_call_not_rejected_for_both_modes")
    _accepted_under_final_decoder(
        row=repair_rows[args.repair_call_id],
        task_spec=expected[args.repair_call_id]["task_spec"],
        decoder_bounds=decoder_bounds,
    )

    merged: dict[str, dict[str, Any]] = {}
    for call_id, call in expected.items():
        row = repair_rows[call_id] if call_id == args.repair_call_id else primary_rows[call_id]
        _accepted_under_final_decoder(row=row, task_spec=call["task_spec"], decoder_bounds=decoder_bounds)
        merged[call_id] = row

    args.output_dir.mkdir(parents=True)
    results_path = args.output_dir / "dev_raw_and_parsed.jsonl"
    with results_path.open("w", encoding="utf-8", newline="\n") as handle:
        for call in calls:
            handle.write(json.dumps(merged[str(call["call_id"])], sort_keys=True, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())

    metadata = {
        "status": "RECOVERY_COMPOSED",
        "contract": ROUTING_EVAL_CONTRACT,
        "routing_eval": True,
        "base_model": primary_manifest.get("base_model"),
        "base_revision": primary_manifest.get("base_revision"),
        "adapter_path": primary_manifest.get("adapter_path"),
        "adapter_scale": primary_manifest.get("adapter_scale"),
        "bundle_root": str(args.bundle_root),
        "dev_manifest_sha256": sha256_file(args.dev_manifest),
        "permitted_view_sha256": sha256_file(permitted),
        "dev_manifest_count": primary_manifest.get("dev_manifest_count"),
        "evaluation_record_count": primary_manifest.get("evaluation_record_count"),
        "task_call_count": len(calls),
        "task_call_count_full": len(calls),
        "decoder_bounds": {
            "contract_id": decoder_bounds["contract_id"],
            "sha256": decoder_bounds_sha256,
            "task_id": decoder_bounds["task_id"],
            "max_candidate_interpretations": decoder_bounds["max_candidate_interpretations"],
            "max_candidate_text_characters": decoder_bounds["max_candidate_text_characters"],
            "suppress_unsupported_optional_fields": decoder_bounds["suppress_unsupported_optional_fields"],
            "max_cpc_value_characters": decoder_bounds["max_cpc_value_characters"],
            "prompt_schema_unchanged": True,
        },
        "source_holdout_loaded": 0,
        "protected_records_loaded": 0,
        "evaluation_leakage_detected": False,
        "pilot120_used": False,
        "recovery": {
            "policy": "single_reexecuted_call_with_full_final_decoder_validation",
            "primary_evaluation_dir": str(args.primary_evaluation_dir),
            "primary_results_sha256": _sha256(args.primary_evaluation_dir / "dev_raw_and_parsed.jsonl"),
            "repair_evaluation_dir": str(args.repair_evaluation_dir),
            "repair_results_sha256": _sha256(args.repair_evaluation_dir / "dev_raw_and_parsed.jsonl"),
            "repaired_call_id": args.repair_call_id,
            "repair_routing_eval": True,
            "reused_call_count": len(calls) - 1,
            "all_reused_outputs_validate_final_decoder": True,
        },
    }
    _atomic_json(args.output_dir / "evaluation_manifest.json", metadata)
    _finalize(args.output_dir, calls, merged, metadata)
    print(json.dumps({"status": "VERIFY_PASSED", "calls": len(calls), "repaired_call_id": args.repair_call_id}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except T28Error as exc:
        print(f"T28_SINGLE_CALL_RECOVERY_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
