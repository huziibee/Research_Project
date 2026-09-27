#!/usr/bin/env python3
"""Attach T41 CPC gold onto Pilot-120 core gold without rewriting frozen fields.

Leaves data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl untouched.
Writes a merged sibling with every original key copied verbatim, plus gold_cpc.
Does not invent risk_level.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN_GOLD = ROOT / "data" / "annotations" / "pilot_120_v1" / "pilot_120_final_gold.jsonl"
T41_GOLD = (
    ROOT
    / "pilot120_t41_complete_closure"
    / "final_t41"
    / "pilot120_interpretation_gold_final.jsonl"
)
OUT = ROOT / "data" / "annotations" / "pilot_120_v1" / "pilot_120_final_gold_with_cpc.jsonl"
MANIFEST = ROOT / "data" / "annotations" / "pilot_120_v1" / "pilot_120_cpc_merge_manifest.json"

CPC_SLOT_NAMES = (
    "action",
    "actor",
    "object",
    "object_attributes",
    "destination",
    "spatial_relation",
    "quantity",
    "time",
    "recipient",
    "tool",
    "conditions",
    "constraints",
    "negation",
)
NEW_KEYS = {
    "gold_cpc",
    "gold_cpc_field_status",
    "gold_cpc_provenance",
}


def load_jsonl(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows[row["record_id"]] = row
    return rows


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slots_to_gold_cpc(slots: dict) -> dict:
    out = {}
    slots = slots or {}
    for name in CPC_SLOT_NAMES:
        raw = slots.get(name)
        if raw is None or raw == "":
            out[name] = {"status": "not_applicable", "value": None}
        else:
            out[name] = {"status": "filled", "value": str(raw)}
    return out


def main() -> None:
    frozen = load_jsonl(FROZEN_GOLD)
    t41 = load_jsonl(T41_GOLD)
    if set(frozen) != set(t41) or len(frozen) != 120:
        raise SystemExit(
            f"ID mismatch: frozen={len(frozen)} t41={len(t41)} "
            f"only_frozen={sorted(set(frozen) - set(t41))[:5]} "
            f"only_t41={sorted(set(t41) - set(frozen))[:5]}"
        )

    filled_cells = 0
    filled_per_slot: Counter[str] = Counter()
    cpc_status: Counter[str] = Counter()
    merged_rows = []

    for rid in sorted(frozen):
        original = frozen[rid]
        t_row = t41[rid]
        gold = t_row.get("gold") or {}
        cpc_obj = gold.get("cpc") or {}
        slots = cpc_obj.get("slots") or {}
        gold_cpc = slots_to_gold_cpc(slots)
        for name, slot in gold_cpc.items():
            if slot["status"] == "filled":
                filled_cells += 1
                filled_per_slot[name] += 1
        status = str((t_row.get("field_status") or {}).get("cpc"))
        cpc_status[status] += 1

        row = dict(original)
        row["gold_cpc"] = gold_cpc
        row["gold_cpc_field_status"] = status
        row["gold_cpc_provenance"] = {
            "source": "pilot120_t41_complete_closure/final_t41/pilot120_interpretation_gold_final.jsonl",
            "field_status_cpc": status,
            "annotation_status": t_row.get("annotation_status"),
            "blind_adjudicator_pseudonym": "blind_chatgpt_gpt56sol",
            "critical_slots": cpc_obj.get("critical_slots"),
            "raw_slots": slots,
            "did_not_mutate_frozen_core_fields": True,
        }
        for key, value in original.items():
            if row[key] != value:
                raise SystemExit(f"Core field mutated on {rid}: {key}")
        extra = set(row) - set(original)
        if extra != NEW_KEYS:
            raise SystemExit(f"Unexpected extra keys on {rid}: {sorted(extra)}")
        merged_rows.append(row)

    OUT.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in merged_rows),
        encoding="utf-8",
    )

    # Re-read and prove frozen file is byte-identical to pre-merge expectations.
    frozen_after = load_jsonl(FROZEN_GOLD)
    if frozen_after != frozen:
        raise SystemExit("Frozen gold changed during merge; abort.")

    manifest = {
        "n_records": len(merged_rows),
        "frozen_gold_path": str(FROZEN_GOLD.relative_to(ROOT)).replace("\\", "/"),
        "frozen_gold_sha256": sha256_file(FROZEN_GOLD),
        "t41_source": str(T41_GOLD.relative_to(ROOT)).replace("\\", "/"),
        "t41_sha256": sha256_file(T41_GOLD),
        "merged_path": str(OUT.relative_to(ROOT)).replace("\\", "/"),
        "merged_sha256": sha256_file(OUT),
        "mutated_pilot_120_final_gold": False,
        "did_not_invent_gold_cpc": True,
        "did_not_add_gold_risk_level": True,
        "cpc_field_status": dict(cpc_status),
        "cpc_filled_slot_cells": filled_cells,
        "cpc_filled_per_slot": dict(filled_per_slot),
        "absent_slots_encoded_as": "not_applicable",
        "note": (
            "Merged file copies every frozen gold key verbatim and adds gold_cpc "
            "from T41 interpretation gold. Risk stays out: gold-v1 never promoted it."
        ),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
