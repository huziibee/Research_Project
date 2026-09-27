#!/usr/bin/env python3
"""Apply smarter-agent leftover worksheet onto official current-scale risk gold."""
from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANN = ROOT / "data" / "annotations" / "pilot_120_v1"
BASE = ANN / "gold_v2_officialization_20260914" / "risk"
OFFICIAL = ANN / "pilot_120_gold_risk_official.jsonl"
OFFICIAL_COPY = BASE / "pilot_120_gold_risk_official.jsonl"
INDEX = json.loads((BASE / "leftover_pack" / "LEFTOVER_INDEX.json").read_text(encoding="utf-8"))
SCALE = {"none", "low", "medium", "high", "unknown"}
DECISIONS = {"prefer_A", "prefer_B", "new_value"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def validate(ws: list[dict]) -> dict[str, dict]:
    expected = INDEX["ids"]
    ids = [r["record_id"] for r in ws]
    if ids != expected:
        raise SystemExit(f"id_mismatch got={ids} expected={expected}")
    by_id = {}
    for row in ws:
        rid = row["record_id"]
        final = row.get("final_risk_level")
        decision = row.get("decision")
        rationale = (row.get("rationale") or "").strip()
        if final not in SCALE:
            raise SystemExit(f"{rid}: bad final_risk_level {final}")
        if decision not in DECISIONS:
            raise SystemExit(f"{rid}: bad decision {decision}")
        if not rationale:
            raise SystemExit(f"{rid}: empty rationale")
        if decision == "prefer_A" and final != row.get("gpt_a"):
            raise SystemExit(f"{rid}: prefer_A but final={final} gpt_a={row.get('gpt_a')}")
        if decision == "prefer_B" and final != row.get("grok_b"):
            raise SystemExit(f"{rid}: prefer_B but final={final} grok_b={row.get('grok_b')}")
        if decision == "new_value" and final in {row.get("gpt_a"), row.get("grok_b")}:
            raise SystemExit(f"{rid}: new_value collides with A or B ({final})")
        by_id[rid] = row
    return by_id


def main() -> None:
    src = Path.home() / "Downloads" / "leftover_worksheet.jsonl"
    ws = load_jsonl(src)
    leftover = validate(ws)
    gold = load_jsonl(OFFICIAL)
    assert len(gold) == 120, len(gold)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    flipped = []
    out = []
    counts = Counter()
    status_counts = Counter()
    for row in gold:
        rid = row["record_id"]
        if rid in leftover:
            lr = leftover[rid]
            prior = row.get("gold_risk_level")
            gold_val = lr["final_risk_level"]
            if gold_val != prior:
                flipped.append({"record_id": rid, "from": prior, "to": gold_val, "decision": lr["decision"]})
            if lr["gpt_a"] == lr["grok_b"] == gold_val:
                field_status = "auto_agree"
            else:
                field_status = "adjudicated"
            row = {
                **row,
                "gold_risk_level": gold_val,
                "field_status": field_status,
                "gold_lifecycle": "final_gold",
                "annotation_status": "official",
                "choice": lr["decision"],
                "rationale": lr["rationale"],
                "adjudicator": "smarter_agent_leftover_20260914",
                "prior_adjudicator": "claude_4.6_parent",
                "prior_gold_risk_level": prior,
                "human_gate": "operator_20260914_smarter_agent_leftovers",
                "leftover_decision": lr["decision"],
                "promoted_at_utc": stamp,
            }
        else:
            row = {**row, "gold_lifecycle": "final_gold", "annotation_status": "official"}
        assert row["gold_risk_level"] in SCALE
        assert row["field_status"] in {"auto_agree", "adjudicated"}
        out.append(row)
        counts[row["gold_risk_level"]] += 1
        status_counts[row["field_status"]] += 1

    dest_ws = BASE / "leftover_pack" / "leftover_worksheet.filled.jsonl"
    shutil.copy2(src, dest_ws)
    shutil.copy2(src, BASE / "leftover_pack" / "leftover_worksheet.smarter_agent.jsonl")

    text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in out)
    OFFICIAL.write_text(text, encoding="utf-8")
    OFFICIAL_COPY.write_text(text, encoding="utf-8")
    digest = sha256(OFFICIAL)

    manifest = {
        "artifact": "data/annotations/pilot_120_v1/pilot_120_gold_risk_official.jsonl",
        "n": 120,
        "gold_lifecycle": "final_gold",
        "scale": ["none", "low", "medium", "high", "unknown"],
        "counts": dict(counts),
        "field_status": dict(status_counts),
        "sha256": digest,
        "frozen_core_mutated": False,
        "leftovers_closed": 18,
        "leftover_source": str(src),
        "leftover_adjudicator": "smarter_agent_leftover_20260914",
        "leftover_flips_from_claude": flipped,
        "did_not_fold_into_running_mega_54259": True,
        "promoted_at_utc": stamp,
        "annotator_a": "gpt_review_pack_20260914",
        "annotator_b": "cursor-grok-4.5-high",
        "adjudicator": "claude_4.6_parent then smarter_agent_leftover_20260914",
    }
    (ANN / "pilot_120_gold_risk_official.manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (BASE / "LAUNCH_STATUS.json").write_text(
        json.dumps(
            {
                "annotator_a": "gpt_review_pack_20260914",
                "annotator_b_model": "cursor-grok-4.5-high",
                "leftover_adjudicator": "smarter_agent_leftover_20260914",
                "done_count": 120,
                "missing_count": 0,
                "leftover": 0,
                "gold_lifecycle": "final_gold",
                "official_path": str(OFFICIAL),
                "sha256": digest,
                "flips_from_claude": flipped,
                "note": "Official current-scale risk gold after smarter-agent leftover gate. Frozen core unchanged. CPC sidecar not promoted.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"n": 120, "counts": dict(counts), "flips": flipped, "sha256": digest}, indent=2))


if __name__ == "__main__":
    main()
