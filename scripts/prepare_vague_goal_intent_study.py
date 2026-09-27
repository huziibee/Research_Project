#!/usr/bin/env python3
"""Prepare hash-bound paired VAGUE inputs for goal-intent context ablation.

The output is source-development preparation only. It duplicates each VAGUE
record into command-only and command-plus-textual-caption conditions, preserves
the source-native targets, and runs no model inference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_not_object:{path}")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"jsonl_row_not_object:{path}:{number}")
            rows.append(value)
    return rows


def write_new(path: Path, content: str) -> None:
    if path.exists():
        raise ValueError(f"output_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def source_target(row: dict[str, Any]) -> dict[str, Any]:
    required = ("id", "command", "scene_context", "intent", "slots", "resolved_interpretation", "candidate_interpretations")
    missing = [field for field in required if not row.get(field)]
    if missing:
        raise ValueError(f"vague_target_missing:{row.get('id')}:{','.join(missing)}")
    return {
        "intent_goal": row["intent"],
        "slots": row["slots"],
        "resolved_interpretation": row["resolved_interpretation"],
        "candidate_interpretations": row["candidate_interpretations"],
    }


def prepare(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        record_id = str(row.get("id") or "")
        if not record_id or record_id in seen:
            raise ValueError(f"record_id_invalid_or_duplicate:{record_id}")
        seen.add(record_id)
        target = source_target(row)
        source_fingerprint = sha256_bytes(canonical_bytes(row))
        for condition, caption in (("command_only", None), ("command_plus_textual_caption", row["scene_context"])):
            prepared.append(
                {
                    "study_id": "vague_goal_intent_context_ablation_v1",
                    "pair_id": record_id,
                    "record_id": record_id,
                    "condition": condition,
                    "command": row["command"],
                    "textual_caption": caption,
                    "source_fingerprint_sha256": source_fingerprint,
                    "source_target": target,
                    "label_status": "EXPLORATORY_WEAK_SOURCE_LABEL",
                }
            )
    return prepared


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--records-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    args = parser.parse_args()
    protocol = load_json(args.protocol)
    if protocol.get("protocol_id") != "dataset_native_exploratory_evaluation_v1":
        raise ValueError("protocol_id_invalid")
    vague = (protocol.get("datasets") or {}).get("vague") or {}
    if vague.get("conditions") != ["command_only", "command_plus_textual_caption"]:
        raise ValueError("vague_conditions_not_frozen")
    rows = load_jsonl(args.source)
    prepared = prepare(rows)
    records_text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in prepared)
    manifest = {
        "study_id": "vague_goal_intent_context_ablation_v1",
        "status": "PREPARED_NOT_FROZEN_NOT_RUN",
        "claim_boundary": "source-development exploratory preparation; no inference, result, or causal claim",
        "source_path": str(args.source).replace("\\", "/"),
        "source_sha256": sha256_file(args.source),
        "protocol_sha256": sha256_file(args.protocol),
        "records_sha256": sha256_bytes(records_text.encode("utf-8")),
        "source_record_count": len(rows),
        "paired_input_count": len(prepared),
        "conditions": ["command_only", "command_plus_textual_caption"],
        "system_binding": "NOT_FROZEN",
        "prediction_output_contract": "NOT_FROZEN",
        "inference_run": False,
        "metrics": {
            "goal_intent": "NOT_COMPUTED_PENDING_DETERMINISTIC_SCORER_AND_FROZEN_OUTPUT_CONTRACT",
            "paired_caption_benefit": "NOT_COMPUTED_PENDING_FROZEN_SYSTEM_AND_ANALYSIS"
        },
    }
    write_new(args.records_output, records_text)
    write_new(args.manifest_output, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"], "source_records": len(rows), "paired_inputs": len(prepared)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
