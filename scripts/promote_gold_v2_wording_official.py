#!/usr/bin/env python3
"""Promote official clarification-wording gold for the 23 gold-ask rows.

Annotator A = T41 interpretation sidecar (historical).
Annotator B = independent Grok from source cards only.
Adjudicator = Claude parent on target-set diffs; official must_convey prefers
Grok's licensed named alternatives (scoreable). Frozen core is not mutated.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANN = ROOT / "data" / "annotations" / "pilot_120_v1"
BASE = ANN / "gold_v2_officialization_20260914" / "wording"
OFFICIAL = ANN / "pilot_120_gold_wording_official.jsonl"

# Target-set diffs only. Concrete must_convey always taken from B unless listed.
TARGET_DECISION = {
    "CA-0215": {"targets": ["action", "destination"], "choice": "B", "why": "Filing medium is physical vs digital, which is both action and destination."},
    "CA-0225": {"targets": ["action", "destination"], "choice": "B", "why": "Same filing-medium pair as CA-0215."},
    "CA-0394": {"targets": ["object", "recipient"], "choice": "A", "why": "Two packets are pending; CPC left object and recipient unknown. Question must name both assignments."},
    "CA-0512": {"targets": ["object", "recipient"], "choice": "A", "why": "Same selected-delivery twin: object and recipient both unresolved."},
    "CA-0671": {"targets": ["tool"], "choice": "B", "why": "Unresolved choice is which calibrated gauge (range), not a numeric quantity."},
    "CA-0735": {"targets": ["object", "recipient"], "choice": "A", "why": "Same selected-delivery twin."},
    "CA-0762": {
        "targets": ["action", "destination"],
        "choice": "neither",
        "why": "Ask filing medium only. Setup is already mapped by WO-728; do not force a setup question.",
        "must_convey": [
            "physical filing at the pass counter",
            "digital filing in the records system",
        ],
    },
    "CA-0845": {"targets": ["tool"], "choice": "B", "why": "Unresolved choice is which voltage meter (range), not a numeric quantity."},
    "CA-0878": {
        "targets": ["action"],
        "choice": "B",
        "why": "Question is prohibition scope: inspect-without-move vs cancel both. Negation is already gold; do not require a constraints slot in the question.",
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def load_folder(folder: Path) -> dict[str, dict]:
    rows = {}
    for path in folder.glob("CA-*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        rows[row["record_id"]] = row
    return rows


def main() -> None:
    a = load_folder(BASE / "annotator_a_t41")
    b = load_folder(BASE / "annotator_b_grok")
    ids = json.loads((BASE / "RECORD_IDS.json").read_text(encoding="utf-8"))
    assert set(a) == set(b) == set(ids) and len(ids) == 23
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    official = []
    status_counts = Counter()
    for rid in ids:
        ta, tb = set(a[rid]["targets"]), set(b[rid]["targets"])
        if ta == tb:
            field_status = "auto_agree"
            choice = "agree"
            targets = sorted(ta)
            must = list(b[rid]["must_convey"])
            must_not = list(b[rid]["must_not_convey"])
            why = "Target set agreed. Official must_convey uses Grok licensed names."
        else:
            spec = TARGET_DECISION[rid]
            field_status = "adjudicated"
            choice = spec["choice"]
            targets = spec["targets"]
            must = list(spec.get("must_convey") or b[rid]["must_convey"])
            must_not = list(b[rid]["must_not_convey"])
            why = spec["why"]
        status_counts[field_status] += 1
        official.append(
            {
                "record_id": rid,
                "gold_clarification": {
                    "required": True,
                    "targets": targets,
                    "wording_criteria": {
                        "must_convey": must,
                        "must_not_convey": must_not,
                        "acceptable_paraphrase": True,
                    },
                },
                "field_status": field_status,
                "choice": choice,
                "rationale": why,
                "gold_lifecycle": "final_gold",
                "annotation_status": "official",
                "annotator_a": "t41_interpretation_gold",
                "annotator_b": "cursor-grok-4.5-high",
                "adjudicator": "claude_4.6_parent",
                "promoted_at_utc": stamp,
            }
        )

    text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in official)
    OFFICIAL.write_text(text, encoding="utf-8")
    (BASE / "pilot_120_gold_wording_official.jsonl").write_text(text, encoding="utf-8")
    digest = sha256(OFFICIAL)
    manifest = {
        "artifact": "data/annotations/pilot_120_v1/pilot_120_gold_wording_official.jsonl",
        "n": 23,
        "gold_lifecycle": "final_gold",
        "sha256": digest,
        "frozen_core_mutated": False,
        "field_status": dict(status_counts),
        "annotator_a": "t41_interpretation_gold",
        "annotator_b": "cursor-grok-4.5-high",
        "adjudicator": "claude_4.6_parent",
        "scoring_rule": (
            "Denominator is the 23 gold-ask rows. A predicted question is wording-correct "
            "if it covers the distinctive licensed alternatives in every must_convey item "
            "(paraphrase OK). No question scores 0. must_not_convey is documentation, "
            "not a brittle string fail."
        ),
        "promoted_at_utc": stamp,
    }
    (ANN / "pilot_120_gold_wording_official.manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"official": str(OFFICIAL), **{k: manifest[k] for k in ("n", "field_status", "sha256")}}, indent=2))


if __name__ == "__main__":
    main()
