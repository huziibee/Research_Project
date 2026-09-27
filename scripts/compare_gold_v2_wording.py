#!/usr/bin/env python3
"""Compare T41 A vs Grok B wording labels."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "annotations" / "pilot_120_v1" / "gold_v2_officialization_20260914" / "wording"


def load(folder: Path) -> dict[str, dict]:
    rows = {}
    for path in sorted(folder.glob("CA-*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        rows[row["record_id"]] = row
    return rows


def main() -> None:
    a = load(BASE / "annotator_a_t41")
    b = load(BASE / "annotator_b_grok")
    assert set(a) == set(b) and len(a) == 23
    rows = []
    for rid in sorted(a):
        ta, tb = set(a[rid].get("targets") or []), set(b[rid].get("targets") or [])
        rows.append(
            {
                "record_id": rid,
                "targets_equal": ta == tb,
                "targets_a": sorted(ta),
                "targets_b": sorted(tb),
                "must_convey_a": a[rid].get("must_convey"),
                "must_convey_b": b[rid].get("must_convey"),
                "must_not_a": a[rid].get("must_not_convey"),
                "must_not_b": b[rid].get("must_not_convey"),
            }
        )
        print(rid, "targets", "AGREE" if ta == tb else f"A={sorted(ta)} B={sorted(tb)}")
    (BASE / "compare_ab.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("agree_targets", sum(r["targets_equal"] for r in rows), "/ 23")


if __name__ == "__main__":
    main()
