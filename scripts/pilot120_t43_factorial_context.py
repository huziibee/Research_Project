#!/usr/bin/env python3
"""CPU-only T43 factorial context-manifest preparation and verification.

This module never runs inference, writes frozen Pilot-120 inputs, changes a
system/prompt/decode setting, or makes a claim-bearing result.  It freezes the
input side of a future 2^3 context study and verifies both source value bytes
and (when supplied later) runtime prompt/render/token attestations.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import itertools
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex


MANIFEST_SCHEMA_VERSION = "1.0.0"
CONTEXT_FIELD_BY_FLAG = {
    "scene_available": "scene_context",
    "dialogue_available": "dialogue_history",
    "capability_available": "capability_context",
}
FIXED_FIELDS = ("record_id", "command")
RUNTIME_ATTESTATION_FIELDS = (
    "record_id",
    "condition_id",
    "input_payload_utf8_base64",
    "input_payload_sha256",
    "prompt_input_utf8_base64",
    "prompt_input_sha256",
    "rendered_input_utf8_base64",
    "rendered_input_sha256",
    "token_ids_json_utf8_base64",
    "token_ids_sha256",
    "prompt_token_count",
)


class T43ManifestError(ValueError):
    """The prospective T43 factorial protocol no longer matches its freeze."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise T43ManifestError(f"expected_json_object:{path}")
    return payload


def _write_once(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise T43ManifestError(f"output_already_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    os.replace(temporary, path)


def _stable_locator(path: Path) -> str:
    """Use repository-relative locators so a prepared manifest is portable."""
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _skip_ws(text: str, offset: int) -> int:
    while offset < len(text) and text[offset] in " \t\r\n":
        offset += 1
    return offset


def _raw_top_level_value_bytes(raw_line: bytes, field: str) -> bytes:
    """Return the source UTF-8 JSON token for one top-level field unchanged."""
    text = raw_line.decode("utf-8")
    decoder = json.JSONDecoder()
    position = _skip_ws(text, 0)
    if position >= len(text) or text[position] != "{":
        raise T43ManifestError("source_line_is_not_object")
    position += 1
    while True:
        position = _skip_ws(text, position)
        if position >= len(text):
            break
        if text[position] == "}":
            break
        key, position = decoder.raw_decode(text, position)
        if not isinstance(key, str):
            raise T43ManifestError("source_object_key_not_string")
        position = _skip_ws(text, position)
        if position >= len(text) or text[position] != ":":
            raise T43ManifestError("source_object_missing_colon")
        value_start = _skip_ws(text, position + 1)
        _value, value_end = decoder.raw_decode(text, value_start)
        if key == field:
            return text[value_start:value_end].encode("utf-8")
        position = _skip_ws(text, value_end)
        if position < len(text) and text[position] == ",":
            position += 1
            continue
        if position < len(text) and text[position] == "}":
            break
        raise T43ManifestError("source_object_missing_separator")
    raise T43ManifestError(f"source_field_missing:{field}")


def _source_rows(path: Path) -> list[tuple[dict[str, Any], bytes]]:
    rows: list[tuple[dict[str, Any], bytes]] = []
    for line_number, raw_line in enumerate(path.read_bytes().splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            parsed = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise T43ManifestError(f"invalid_source_jsonl_line:{line_number}") from error
        if not isinstance(parsed, dict):
            raise T43ManifestError(f"source_row_not_object:{line_number}")
        rows.append((parsed, raw_line))
    return rows


def _availability(record: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "scene": isinstance(record.get("scene_context"), str) and bool(str(record["scene_context"]).strip()),
        "dialogue": isinstance(record.get("dialogue_history"), list) and bool(record["dialogue_history"]),
        "capability": isinstance(record.get("capability_context"), str) and bool(str(record["capability_context"]).strip()),
    }


def _canonical_conditions(policy: Mapping[str, Any]) -> list[dict[str, Any]]:
    supplied = policy.get("conditions")
    if not isinstance(supplied, list) or len(supplied) != 8:
        raise T43ManifestError("policy_must_define_eight_conditions")
    expected = {
        (scene, dialogue, capability)
        for scene, dialogue, capability in itertools.product((False, True), repeat=3)
    }
    seen: set[tuple[bool, bool, bool]] = set()
    ids: set[str] = set()
    conditions: list[dict[str, Any]] = []
    for raw in supplied:
        if not isinstance(raw, dict):
            raise T43ManifestError("policy_condition_not_object")
        try:
            condition_id = str(raw["condition_id"])
            flags = (
                bool(raw["scene_available"]),
                bool(raw["dialogue_available"]),
                bool(raw["capability_available"]),
            )
        except KeyError as error:
            raise T43ManifestError(f"policy_condition_missing:{error.args[0]}") from error
        if flags in seen or condition_id in ids:
            raise T43ManifestError("policy_condition_duplicate")
        seen.add(flags)
        ids.add(condition_id)
        conditions.append({
            "condition_id": condition_id,
            "scene_available": flags[0],
            "dialogue_available": flags[1],
            "capability_available": flags[2],
        })
    if seen != expected:
        raise T43ManifestError("policy_condition_matrix_not_complete_2x2x2")
    return conditions


def _require_frozen_source(
    *, source_path: Path, frozen_manifest: Mapping[str, Any], policy: Mapping[str, Any], rows: list[tuple[dict[str, Any], bytes]]
) -> list[str]:
    source_sha256 = _sha256(source_path)
    hashes = frozen_manifest.get("hashes") or {}
    if source_sha256 != hashes.get("source_canonical_jsonl"):
        raise T43ManifestError("frozen_source_sha256_mismatch")
    if source_sha256 != policy.get("expected_frozen_source_sha256"):
        raise T43ManifestError("policy_source_sha256_mismatch")
    expected_ids = frozen_manifest.get("record_ids")
    if not isinstance(expected_ids, list) or not all(isinstance(record_id, str) for record_id in expected_ids):
        raise T43ManifestError("frozen_manifest_record_ids_invalid")
    observed_ids = [str(row.get("record_id") or "") for row, _raw in rows]
    if observed_ids != expected_ids:
        raise T43ManifestError("frozen_source_record_order_mismatch")
    expected_n = int(policy.get("expected_record_count") or 0)
    if len(rows) != expected_n or len(rows) != int(frozen_manifest.get("n_records") or 0):
        raise T43ManifestError("frozen_source_record_count_mismatch")
    for record, _raw in rows:
        for field in (*FIXED_FIELDS, "scene_context", "dialogue_history", "capability_context"):
            if field not in record:
                raise T43ManifestError(f"frozen_source_field_missing:{record.get('record_id')}:{field}")
    return expected_ids


def _payload_for_condition(record: Mapping[str, Any], condition: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "record_id": record["record_id"],
        "command": record["command"],
        "scene_context": record["scene_context"] if condition["scene_available"] else None,
        "dialogue_history": list(record["dialogue_history"]) if condition["dialogue_available"] else [],
        "capability_context": record["capability_context"] if condition["capability_available"] else None,
    }


def _retained_source_fields(condition: Mapping[str, Any]) -> list[str]:
    retained = list(FIXED_FIELDS)
    for flag, field in CONTEXT_FIELD_BY_FLAG.items():
        if condition[flag]:
            retained.append(field)
    return retained


def _raw_attestations(raw_line: bytes, fields: Iterable[str]) -> dict[str, dict[str, str]]:
    return {
        field: {
            "source_value_utf8_base64": base64.b64encode(_raw_top_level_value_bytes(raw_line, field)).decode("ascii"),
            "source_value_sha256": sha256_hex(_raw_top_level_value_bytes(raw_line, field)),
        }
        for field in fields
    }


def _placeholder() -> dict[str, Any]:
    return {
        "status": "NOT_COMPUTED",
        "reason": "CPU preparation does not render an unchanged T39 manager prompt or tokenize it. Runtime must supply exact base64 bytes and SHA-256 values under the separately frozen execution binding.",
        "prompt_input_sha256": None,
        "rendered_input_sha256": None,
        "token_ids_sha256": None,
        "prompt_token_count": None,
    }


def build_manifest(*, source_path: Path, frozen_manifest_path: Path, policy_path: Path) -> dict[str, Any]:
    """Build a prospective eight-cell input manifest without changing source data."""
    source_path = source_path.resolve()
    frozen_manifest_path = frozen_manifest_path.resolve()
    policy_path = policy_path.resolve()
    frozen = _load_json(frozen_manifest_path)
    policy = _load_json(policy_path)
    if policy.get("preparation_only") is not True or policy.get("inference_permitted_by_this_policy") is not False:
        raise T43ManifestError("policy_must_be_cpu_preparation_only")
    rows = _source_rows(source_path)
    expected_ids = _require_frozen_source(source_path=source_path, frozen_manifest=frozen, policy=policy, rows=rows)
    conditions = _canonical_conditions(policy)
    records: list[dict[str, Any]] = []
    availability_counts = {"scene": 0, "dialogue": 0, "capability": 0}
    for record, raw_line in rows:
        availability = _availability(record)
        for source in availability_counts:
            availability_counts[source] += int(availability[source])
        condition_rows: list[dict[str, Any]] = []
        for condition in conditions:
            payload = _payload_for_condition(record, condition)
            retained = _retained_source_fields(condition)
            requested_but_empty = [
                source
                for source, flag in (("scene", "scene_available"), ("dialogue", "dialogue_available"), ("capability", "capability_available"))
                if condition[flag] and not availability[source]
            ]
            condition_rows.append({
                **condition,
                "input_payload": payload,
                "input_payload_sha256": sha256_hex(canonical_json_bytes(payload)),
                "retained_source_fields": retained,
                "retained_source_value_attestations": _raw_attestations(raw_line, retained),
                "withheld_source_fields": [field for field in CONTEXT_FIELD_BY_FLAG.values() if field not in retained],
                "requested_but_structurally_empty_sources": requested_but_empty,
                "dialogue_effect_eligible": availability["dialogue"],
                "prompt_render_token_placeholder": _placeholder(),
            })
        records.append({
            "record_id": record["record_id"],
            "source_line_sha256": sha256_hex(raw_line),
            "natural_context_availability": availability,
            "conditions": condition_rows,
        })
    factor_specs = {str(item["factor_id"]): item for item in policy["factors"]}
    expected_availability = {name: int(spec["expected_naturally_present"]) for name, spec in factor_specs.items()}
    if availability_counts != expected_availability:
        raise T43ManifestError(f"source_availability_count_mismatch:{availability_counts}")
    return {
        "status": "T43_CPU_ONLY_FACTORIAL_CONTEXT_MANIFEST_PREPARED",
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "scope": policy["scope"],
        "valid_for_official_use": False,
        "must_not_influence_training_selection_or_tuning": True,
        "preparation_only": True,
        "inference_has_not_run": True,
        "execution_readiness": "NOT_COMPUTED",
        "execution_readiness_reason": "T39 final reproducibility audit, T40 audit, unchanged-system binding, and runtime prompt/render/token attestation remain required before T43 inference.",
        "frozen_inputs": {
            "source_path": _stable_locator(source_path),
            "source_sha256": _sha256(source_path),
            "frozen_manifest_path": _stable_locator(frozen_manifest_path),
            "frozen_manifest_sha256": _sha256(frozen_manifest_path),
            "policy_path": _stable_locator(policy_path),
            "policy_sha256": _sha256(policy_path),
            "record_ids": expected_ids,
        },
        "factor_definitions": policy["factors"],
        "conditions": conditions,
        "natural_context_availability_counts": availability_counts,
        "dialogue_effect_population": {
            "n_eligible": availability_counts["dialogue"],
            "eligibility_rule": policy["factors"][1]["effect_eligibility"],
            "noneligible_records_are_not_relabelled_as_removed": True,
        },
        "runtime_attestation_schema": policy["runtime_attestation_schema"],
        "system_execution_binding": policy["system_execution_binding"],
        "paired_analysis_preregistration": policy["paired_analysis_preregistration"],
        "claim_boundary": policy["claim_boundary"],
        "completion_gates": policy["completion_gates"],
        "records": records,
    }


def _condition_index(manifest: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    index: dict[tuple[str, str], Mapping[str, Any]] = {}
    for record in manifest.get("records") or []:
        record_id = record.get("record_id")
        if not isinstance(record_id, str):
            raise T43ManifestError("manifest_record_id_invalid")
        conditions = record.get("conditions")
        if not isinstance(conditions, list):
            raise T43ManifestError(f"manifest_conditions_invalid:{record_id}")
        for condition in conditions:
            if not isinstance(condition, dict) or not isinstance(condition.get("condition_id"), str):
                raise T43ManifestError(f"manifest_condition_invalid:{record_id}")
            key = (record_id, condition["condition_id"])
            if key in index:
                raise T43ManifestError(f"manifest_duplicate_condition:{record_id}:{condition['condition_id']}")
            index[key] = condition
    return index


def verify_static_manifest(
    *, manifest: Mapping[str, Any], source_path: Path, frozen_manifest_path: Path, policy_path: Path
) -> dict[str, Any]:
    """Verify every prospective input against the exact frozen source bytes."""
    rebuilt = build_manifest(source_path=source_path, frozen_manifest_path=frozen_manifest_path, policy_path=policy_path)
    keys = (
        "status", "manifest_schema_version", "scope", "valid_for_official_use", "must_not_influence_training_selection_or_tuning",
        "preparation_only", "inference_has_not_run", "execution_readiness", "execution_readiness_reason",
        "frozen_inputs", "factor_definitions", "conditions",
        "natural_context_availability_counts", "dialogue_effect_population", "runtime_attestation_schema",
        "system_execution_binding", "paired_analysis_preregistration", "claim_boundary", "completion_gates", "records",
    )
    for key in keys:
        if manifest.get(key) != rebuilt.get(key):
            raise T43ManifestError(f"manifest_static_mismatch:{key}")
    source_count = len(rebuilt["records"])
    condition_count = len(_condition_index(rebuilt))
    if source_count != 120 or condition_count != 960:
        raise T43ManifestError("manifest_expected_120x8_shape_invalid")
    return {
        "status": "T43_STATIC_MANIFEST_VERIFY_PASSED",
        "record_count": source_count,
        "condition_input_count": condition_count,
        "dialogue_effect_eligible_record_count": rebuilt["dialogue_effect_population"]["n_eligible"],
        "source_sha256": rebuilt["frozen_inputs"]["source_sha256"],
        "policy_sha256": rebuilt["frozen_inputs"]["policy_sha256"],
        "verification_scope": "all 120 source rows, all eight condition inputs, exact retained UTF-8 source-value tokens, source order, source hash, and policy hash",
    }


def _decode_base64(value: Any, *, label: str) -> bytes:
    if not isinstance(value, str):
        raise T43ManifestError(f"runtime_attestation_not_base64_string:{label}")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as error:
        raise T43ManifestError(f"runtime_attestation_invalid_base64:{label}") from error


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_bytes().splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise T43ManifestError(f"runtime_attestation_invalid_jsonl_line:{line_number}") from error
        if not isinstance(row, dict):
            raise T43ManifestError(f"runtime_attestation_not_object:{line_number}")
        rows.append(row)
    return rows


def verify_runtime_attestations(*, manifest: Mapping[str, Any], path: Path) -> dict[str, Any]:
    """Check a later runtime's exact input bytes and self-consistent render/token bytes.

    This deliberately does not execute a model or reconstruct prompts.  The
    binding to the unchanged renderer/tokenizer is a separate execution gate;
    the submitted attestation must make all bytes available for audit.
    """
    expected = _condition_index(manifest)
    observed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _load_jsonl(path):
        missing = [field for field in RUNTIME_ATTESTATION_FIELDS if field not in row]
        if missing:
            raise T43ManifestError(f"runtime_attestation_missing_fields:{','.join(missing)}")
        key = (str(row["record_id"]), str(row["condition_id"]))
        if key not in expected:
            raise T43ManifestError(f"runtime_attestation_unknown_condition:{key[0]}:{key[1]}")
        if key in observed:
            raise T43ManifestError(f"runtime_attestation_duplicate_condition:{key[0]}:{key[1]}")
        expected_payload = canonical_json_bytes(expected[key]["input_payload"])
        input_bytes = _decode_base64(row["input_payload_utf8_base64"], label="input_payload")
        if input_bytes != expected_payload:
            raise T43ManifestError(f"runtime_input_bytes_do_not_match_manifest:{key[0]}:{key[1]}")
        if sha256_hex(input_bytes) != row["input_payload_sha256"] or row["input_payload_sha256"] != expected[key]["input_payload_sha256"]:
            raise T43ManifestError(f"runtime_input_hash_mismatch:{key[0]}:{key[1]}")
        for bytes_key, hash_key in (
            ("prompt_input_utf8_base64", "prompt_input_sha256"),
            ("rendered_input_utf8_base64", "rendered_input_sha256"),
            ("token_ids_json_utf8_base64", "token_ids_sha256"),
        ):
            attested_bytes = _decode_base64(row[bytes_key], label=bytes_key)
            if sha256_hex(attested_bytes) != row[hash_key]:
                raise T43ManifestError(f"runtime_attestation_hash_mismatch:{key[0]}:{key[1]}:{hash_key}")
        token_bytes = _decode_base64(row["token_ids_json_utf8_base64"], label="token_ids_json_utf8_base64")
        try:
            token_ids = json.loads(token_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise T43ManifestError(f"runtime_token_ids_not_json:{key[0]}:{key[1]}") from error
        if not isinstance(token_ids, list) or not all(isinstance(token_id, int) and not isinstance(token_id, bool) for token_id in token_ids):
            raise T43ManifestError(f"runtime_token_ids_invalid:{key[0]}:{key[1]}")
        if row["prompt_token_count"] != len(token_ids):
            raise T43ManifestError(f"runtime_prompt_token_count_mismatch:{key[0]}:{key[1]}")
        observed[key] = row
    missing_conditions = sorted(set(expected) - set(observed))
    if missing_conditions:
        raise T43ManifestError(f"runtime_attestation_missing_conditions:{len(missing_conditions)}")
    return {
        "status": "T43_RUNTIME_INPUT_RENDER_TOKEN_ATTESTATION_VERIFY_PASSED",
        "attestation_sha256": _sha256(path),
        "record_count": len({record_id for record_id, _condition_id in observed}),
        "condition_input_count": len(observed),
        "verification_scope": "exact canonical input bytes plus SHA-256 self-consistency for prompt, rendered input, and token-ID bytes; renderer/tokenizer identity must be validated by the separate frozen execution binding",
    }


def _default_paths(root: Path) -> tuple[Path, Path, Path]:
    return (
        root / "data/annotations/pilot_120_v1/source_canonical.jsonl",
        root / "data/annotations/pilot_120_v1/frozen/FROZEN_MANIFEST.json",
        root / "configs/evaluation/pilot120_t43_factorial_context_policy_v1.json",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "verify"):
        command = subparsers.add_parser(name)
        command.add_argument("--source", type=Path)
        command.add_argument("--frozen-manifest", type=Path)
        command.add_argument("--policy", type=Path)
        command.add_argument("--manifest", type=Path, required=name == "verify")
        command.add_argument("--runtime-attestations", type=Path)
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_default, frozen_default, policy_default = _default_paths(args.root.resolve())
    source = (args.source or source_default).resolve()
    frozen = (args.frozen_manifest or frozen_default).resolve()
    policy = (args.policy or policy_default).resolve()
    if args.command == "build":
        if args.runtime_attestations is not None:
            raise SystemExit("runtime_attestations_are_not_valid_for_cpu_manifest_build")
        payload = build_manifest(source_path=source, frozen_manifest_path=frozen, policy_path=policy)
    else:
        manifest = _load_json(args.manifest.resolve())
        static = verify_static_manifest(manifest=manifest, source_path=source, frozen_manifest_path=frozen, policy_path=policy)
        payload = {"static_manifest": static}
        if args.runtime_attestations is None:
            payload.update({
                "status": static["status"],
                "runtime_attestation": {
                    "status": "NOT_COMPUTED",
                    "reason": "No T43 runtime exists during CPU-only preparation.",
                },
            })
        else:
            runtime = verify_runtime_attestations(manifest=manifest, path=args.runtime_attestations.resolve())
            payload.update({"status": runtime["status"], "runtime_attestation": runtime})
    _write_once(args.output.resolve(), payload)
    print(json.dumps({"status": payload["status"], "output": str(args.output.resolve())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
