#!/usr/bin/env python3
"""Dump CPC spot-check packets: 8 definite repairs + seeded random 15."""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANN = ROOT / "data" / "annotations" / "pilot_120_v1"
BASE = ANN / "gold_v2_officialization_20260914" / "cpc"
SOURCE = ANN / "source_canonical.jsonl"
WORK = BASE / "working_copy_repaired.jsonl"
MERGED = ANN / "pilot_120_final_gold_with_cpc.jsonl"
LEDGER = ANN / "cpc_risk_review_20260914" / "cpc_defect_ledger.json"

DEFINITE = ["CA-0418", "CA-0203", "CA-0369", "CA-0226", "CA-0426", "CA-0596", "CA-0702", "CA-0778"]
SLOTS = (
    "action", "actor", "object", "object_attributes", "destination",
    "spatial_relation", "quantity", "time", "recipient", "tool",
    "conditions", "constraints", "negation",
)


def load_jsonl(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["record_id"]] = row
    return rows


def slim_cpc(cpc: dict) -> dict:
    out = {}
    for name in SLOTS:
        slot = (cpc or {}).get(name) or {}
        if slot.get("status") == "filled" and slot.get("value") not in (None, ""):
            out[name] = {"status": "filled", "value": slot.get("value")}
        elif slot.get("status") in {"missing", "unknown"}:
            out[name] = {"status": slot.get("status"), "value": None}
    return out


def main() -> None:
    source = load_jsonl(SOURCE)
    work = load_jsonl(WORK)
    merged = load_jsonl(MERGED)
    ids = sorted(source)
    rng = random.Random(20260914)
    pool = [i for i in ids if i not in set(DEFINITE)]
    random15 = sorted(rng.sample(pool, 15))
    packets = []
    for rid in DEFINITE + random15:
        packets.append(
            {
                "record_id": rid,
                "bucket": "definite" if rid in DEFINITE else "random15",
                "command": source[rid].get("command"),
                "dialogue_history": source[rid].get("dialogue_history"),
                "scene_context": source[rid].get("scene_context"),
                "capability_context": source[rid].get("capability_context"),
                "raw_t41_cpc": slim_cpc(merged[rid].get("gold_cpc")),
                "repaired_cpc": slim_cpc(work[rid].get("gold_cpc")),
            }
        )
    dest = BASE / "spotcheck_pack.json"
    dest.write_text(json.dumps({"definite": DEFINITE, "random15": random15, "packets": packets}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n": len(packets), "definite": DEFINITE, "random15": random15}, indent=2))


if __name__ == "__main__":
    main()
