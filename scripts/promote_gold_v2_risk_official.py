#!/usr/bin/env python3
"""Promote Pilot-120 current-scale risk gold to final_gold.

Human gate: operator asked to close the 18 leftover rows and make gold official.
Leftover values are the already-written Claude recommendations (prefer A/B, or
new_value=low on the seven neither rows). Frozen core gold is not mutated.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "annotations" / "pilot_120_v1" / "gold_v2_officialization_20260914" / "risk"
ANN = ROOT / "data" / "annotations" / "pilot_120_v1"
PROVISIONAL = BASE / "pilot_120_gold_risk_provisional.jsonl"
OFFICIAL = ANN / "pilot_120_gold_risk_official.jsonl"
OFFICIAL_COPY = BASE / "pilot_120_gold_risk_official.jsonl"
SCALE = ["none", "low", "medium", "high", "unknown"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main() -> None:
    rows = []
    for line in PROVISIONAL.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    assert len(rows) == 120, len(rows)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    leftover_filled = []
    official = []
    counts = Counter()
    status_counts = Counter()

    for row in rows:
        leftover = bool(row.get("leftover_reason"))
        gold = row["gold_risk_level"]
        assert gold in SCALE, row["record_id"]
        if leftover:
            if row["choice"] == "agree":
                field_status = "auto_agree"
                decision = "prefer_A"  # same as B
            elif row["choice"] == "neither":
                field_status = "adjudicated"
                decision = "new_value"
            elif row["choice"] == "A":
                field_status = "adjudicated"
                decision = "prefer_A"
            elif row["choice"] == "B":
                field_status = "adjudicated"
                decision = "prefer_B"
            else:
                raise SystemExit(f"bad leftover choice {row['record_id']} {row['choice']}")
            leftover_filled.append(
                {
                    "record_id": row["record_id"],
                    "gpt_a": row["gpt_a"],
                    "grok_b": row["grok_b"],
                    "claude_recommendation": gold,
                    "claude_choice": row["choice"],
                    "leftover_reason": row["leftover_reason"],
                    "final_risk_level": gold,
                    "decision": decision,
                    "rationale": row["rationale"],
                }
            )
        else:
            field_status = "auto_agree" if row["choice"] == "agree" else "adjudicated"

        out = {
            "record_id": row["record_id"],
            "gold_risk_level": gold,
            "field_status": field_status,
            "gold_lifecycle": "final_gold",
            "annotation_status": "official",
            "gpt_a": row["gpt_a"],
            "grok_b": row["grok_b"],
            "choice": row["choice"],
            "rationale": row["rationale"],
            "adjudicator": "claude_4.6_parent",
            "human_gate": "operator_20260914_close_leftovers" if leftover else None,
            "leftover_reason": row.get("leftover_reason") or [],
            "scale": SCALE,
            "promoted_at_utc": stamp,
        }
        official.append(out)
        counts[gold] += 1
        status_counts[field_status] += 1

    assert len(leftover_filled) == 18, len(leftover_filled)
    assert set(status_counts) <= {"auto_agree", "adjudicated"}
    assert all(r["gold_lifecycle"] == "final_gold" for r in official)

    text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in official)
    OFFICIAL.write_text(text, encoding="utf-8")
    OFFICIAL_COPY.write_text(text, encoding="utf-8")
    digest = sha256(OFFICIAL)

    leftover_path = BASE / "leftover_pack" / "leftover_worksheet.filled.jsonl"
    leftover_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in leftover_filled),
        encoding="utf-8",
    )

    manifest = {
        "artifact": str(OFFICIAL.relative_to(ROOT)).replace("\\", "/"),
        "n": 120,
        "gold_lifecycle": "final_gold",
        "scale": SCALE,
        "counts": dict(counts),
        "field_status": dict(status_counts),
        "sha256": digest,
        "frozen_core_mutated": False,
        "leftovers_closed": 18,
        "leftover_policy": (
            "Operator closed leftovers on 2026-09-14 using existing Claude "
            "recommendations: prefer A/B on high-flips/unknowns; new_value=low on seven neithers."
        ),
        "did_not_fold_into_running_mega_54259": True,
        "promoted_at_utc": stamp,
        "annotator_a": "gpt_review_pack_20260914",
        "annotator_b": "cursor-grok-4.5-high",
        "adjudicator": "claude_4.6_parent",
    }
    (ANN / "pilot_120_gold_risk_official.manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (BASE / "LAUNCH_STATUS.json").write_text(
        json.dumps(
            {
                "annotator_a": "gpt_review_pack_20260914",
                "annotator_b_model": "cursor-grok-4.5-high",
                "adjudicator": "claude_4.6_parent",
                "done_count": 120,
                "missing_count": 0,
                "agree": 53,
                "disagree": 67,
                "leftover": 0,
                "gold_lifecycle": "final_gold",
                "official_path": str(OFFICIAL),
                "sha256": digest,
                "note": "Official current-scale risk gold. Frozen core unchanged. CPC sidecar not promoted.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"official": str(OFFICIAL), **{k: manifest[k] for k in ("n", "counts", "field_status", "sha256")}}, indent=2))


if __name__ == "__main__":
    main()
