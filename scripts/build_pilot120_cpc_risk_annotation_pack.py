#!/usr/bin/env python3
"""Build a Pilot-120 *risk* worksheet only.

CPC gold is already merged from T41. Do not blank those frames.
This pack is for the later risk pass the user will run.
"""
from __future__ import annotations

import json
from pathlib import Path

from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data" / "annotations" / "pilot_120_v1" / "pilot_120_final_gold.jsonl"
SOURCE = ROOT / "data" / "annotations" / "pilot_120_v1" / "source_canonical.jsonl"
OUT_DIR = ROOT / "data" / "annotations" / "pilot_120_v1" / "cpc_risk_annotation_20260913"
OUT_JSONL = OUT_DIR / "annotation_worksheet.jsonl"
OUT_PROTO = OUT_DIR / "PROTOCOL.md"

RISKS = ("none", "low", "medium", "high", "unknown")


def empty_cpc() -> dict:
    return {name: {"status": "unknown", "value": None} for name in CPC_SLOT_NAMES}


def main() -> None:
    gold = {
        json.loads(line)["record_id"]: json.loads(line)
        for line in GOLD.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    source = {
        json.loads(line)["record_id"]: json.loads(line)
        for line in SOURCE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert set(gold) == set(source) and len(gold) == 120

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for rid in sorted(gold):
        g = gold[rid]
        s = source[rid]
        rows.append(
            {
                "record_id": rid,
                "command": s.get("command"),
                "scene_context": s.get("scene_context"),
                "dialogue_history": s.get("dialogue_history"),
                "capability_context": s.get("capability_context"),
                "existing_gold_capability_status": g.get("capability_status"),
                "existing_gold_terminal_strategy": g.get("terminal_strategy"),
                "existing_gold_ambiguity_types": g.get("ambiguity_types"),
                "gold_cpc": empty_cpc(),
                "gold_risk_level": None,
                "annotation_status": "blank_pending_human",
                "annotator": None,
                "notes": None,
            }
        )

    OUT_JSONL.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    OUT_PROTO.write_text(
        f"""# Pilot-120 CPC + risk gold annotation

**Status.** Blank worksheet. Official slot-binding F1 and risk-sensitive accuracy
stay blocked until every row has `annotation_status = human_complete`.

## Why this exists

`pilot_120_final_gold.jsonl` has route / capability / ambiguity only.
It has **no** `gold_cpc` and **no** `gold_risk_level`.
A GPU job cannot mint those metrics.

## Fields to fill

1. `gold_risk_level`: one of {", ".join(RISKS)}.
2. `gold_cpc`: every slot in {", ".join(CPC_SLOT_NAMES)}.
   Each slot is `{{"status": "filled|missing|unknown|not_applicable", "value": string|null}}`.
   If `status` is `filled`, `value` must be a non-empty string.
   If `status` is not `filled`, `value` must be null.

## Rules

- Do **not** copy the system's live `risk_level` or `cpc` into gold.
- Prefer `missing` when the command needs a slot that is not specified.
- Prefer `not_applicable` when the command does not involve that slot.
- Prefer `unknown` only when the text is genuinely underspecified even after scene/dialogue.
- Risk is harm/safety exposure of doing the wrong thing silently, not capability.
  Unauthorized/incapable capability does **not** automatically set high risk.

## After labeling

```bash
python scripts/score_pilot120_cpc_and_risk.py --sidecar {OUT_JSONL.as_posix()}
```

The scorer refuses to print official numbers unless all 120 rows are `human_complete`.
""",
        encoding="utf-8",
    )
    print(json.dumps({"wrote": str(OUT_JSONL), "n": len(rows), "slots": list(CPC_SLOT_NAMES)}, indent=2))


if __name__ == "__main__":
    main()
