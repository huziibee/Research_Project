#!/usr/bin/env python3
"""Freeze exact-effective-input grouping before native prediction scoring.

The ledger is a diagnostic weighting map. It neither removes source rows nor
changes primary row-weighted metrics. Inconsistent exact-input groups are made
visible before predictions are read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def canon(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(value: object) -> str:
    return hashlib.sha256(canon(value).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--task", choices=("clara", "indirect"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError(f"output_exists:{args.out}")
    packet = load(args.packet)
    if args.task == "clara":
        packet = [row for row in packet if row.get("condition") == "full_context"]
        prompt_fields = ("command", "scene_context", "capability_context")
        target_fields = ("ambiguity_present", "capability_status", "recommended_strategy")
    else:
        prompt_fields = ("command", "scene_context")
        target_fields = ("ambiguity_present", "ambiguity_types", "missing_slots")
    key = {str(row["record_id"]): row for row in load(args.key)}
    groups: dict[str, list[str]] = defaultdict(list)
    for row in packet:
        record_id = str(row["record_id"])
        groups[sha({field: row.get(field) for field in prompt_fields})].append(record_id)
    ledger = []
    for group_id, record_ids in sorted(groups.items()):
        target_hashes = {sha({field: key[record_id].get(field) for field in target_fields}) for record_id in record_ids}
        ledger.append({
            "task": args.task,
            "effective_input_sha256": group_id,
            "record_ids": sorted(record_ids),
            "multiplicity": len(record_ids),
            "target_variant_count": len(target_hashes),
            "source_target_consistency": "CONSISTENT" if len(target_hashes) == 1 else "INCONSISTENT_EXACT_INPUT",
            "primary_metric_treatment": "INCLUDED_ROW_WEIGHTED",
            "unique_input_sensitivity_treatment": "INCLUDED_IF_SOURCE_TARGET_CONSISTENT",
        })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(canon(row) + "\n" for row in ledger), encoding="utf-8", newline="\n")
    print(json.dumps({"status": "LEDGER_FROZEN", "task": args.task, "groups": len(ledger), "inconsistent_groups": sum(row["source_target_consistency"] != "CONSISTENT" for row in ledger), "sha256": hashlib.sha256(args.out.read_bytes()).hexdigest()}, sort_keys=True))


if __name__ == "__main__":
    main()
