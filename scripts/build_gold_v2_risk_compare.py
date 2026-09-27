#!/usr/bin/env python3
"""Dump GPT vs Grok risk comparison and adjudication packets."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "annotations" / "pilot_120_v1" / "gold_v2_officialization_20260914" / "risk"
IDS = json.loads((BASE / "RECORD_IDS.json").read_text(encoding="utf-8"))


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> None:
    agrees = []
    diffs = []
    a_counts = Counter()
    b_counts = Counter()
    pair_counts = Counter()
    high_flips = []
    unknowns = []

    for rid in IDS:
        a = load(BASE / "annotator_a_gpt" / f"{rid}.json")
        b = load(BASE / "annotator_b_grok" / f"{rid}.json")
        card = load(BASE / "cards" / f"{rid}.json")
        al = a["gold_risk_level"]
        bl = b["gold_risk_level"]
        a_counts[al] += 1
        b_counts[bl] += 1
        row = {
            "record_id": rid,
            "gpt_a": al,
            "grok_b": bl,
            "gpt_rationale": a.get("rationale"),
            "grok_rationale": b.get("rationale"),
            "command": card.get("command"),
            "dialogue_history": card.get("dialogue_history"),
            "scene_context": card.get("scene_context"),
            "capability_context": card.get("capability_context"),
        }
        if al == "unknown" or bl == "unknown":
            unknowns.append(row)
        if {al, bl} & {"high"} and al != bl:
            high_flips.append(row)
        if al == bl:
            agrees.append(row)
        else:
            pair = f"{al}->{bl}"
            pair_counts[pair] += 1
            row["pair"] = pair
            diffs.append(row)

    out = {
        "n": 120,
        "agree": len(agrees),
        "disagree": len(diffs),
        "gpt_counts": dict(a_counts),
        "grok_counts": dict(b_counts),
        "pair_counts": dict(pair_counts),
        "n_high_flips": len(high_flips),
        "n_unknowns": len(unknowns),
        "agrees": agrees,
        "diffs": diffs,
        "high_flips": high_flips,
        "unknowns": unknowns,
    }
    dest = BASE / "COMPARE.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    packet_dir = BASE / "adjudication_packets"
    packet_dir.mkdir(exist_ok=True)
    for row in diffs:
        (packet_dir / f"{row['record_id']}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    print(
        json.dumps(
            {
                "agree": len(agrees),
                "disagree": len(diffs),
                "gpt_counts": dict(a_counts),
                "grok_counts": dict(b_counts),
                "pair_counts": dict(sorted(pair_counts.items())),
                "n_high_flips": len(high_flips),
                "high_flip_ids": [r["record_id"] for r in high_flips],
                "n_unknowns": len(unknowns),
                "unknown_ids": [r["record_id"] for r in unknowns],
                "agree_ids": [r["record_id"] for r in agrees],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
