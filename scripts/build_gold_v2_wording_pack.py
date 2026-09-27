#!/usr/bin/env python3
"""Dump 23 gold-ask wording cards: source only + hidden T41 A labels."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANN = ROOT / "data" / "annotations" / "pilot_120_v1"
SOURCE = ANN / "source_canonical.jsonl"
FROZEN = ANN / "pilot_120_final_gold.jsonl"
T41 = ROOT / "pilot120_t41_complete_closure" / "final_t41" / "pilot120_interpretation_gold_final.jsonl"
OUT = ANN / "gold_v2_officialization_20260914" / "wording"


def load_jsonl(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["record_id"]] = row
    return rows


def main() -> None:
    source = load_jsonl(SOURCE)
    frozen = load_jsonl(FROZEN)
    t41 = load_jsonl(T41)
    ids = sorted(rid for rid, row in frozen.items() if row.get("terminal_strategy") == "clarify")
    assert len(ids) == 23, ids
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cards").mkdir(exist_ok=True)
    (OUT / "annotator_a_t41").mkdir(exist_ok=True)
    (OUT / "annotator_b_grok").mkdir(exist_ok=True)

    brief = """# Blind clarification-wording annotator brief

You annotate **exactly one** record. You are Annotator B.

Gold already decided this command should **ask** (clarify), not do it or refuse.
Your job is only the **wording rubric** for a good question.

Return JSON:
{
  "record_id": "...",
  "targets": ["slot names the question must ask about"],
  "must_convey": ["short licensed facts the question must make the human choose between or name"],
  "must_not_convey": ["claims the question must not make"],
  "acceptable_paraphrase": true,
  "rationale": "one or two sentences from the source card"
}

Rules:
- Use ONLY the command, dialogue, scene, and capability card. No gold, no model output, no other cards.
- targets are CPC-like slot names: object, recipient, destination, time, quantity, tool, action, conditions, constraints.
- must_convey items must be licensed by the scene (named objects, named people/roles, named times). Do not invent extra options.
- must_not_convey: do not pretend the ambiguity is already resolved; do not add an unsupported extra target.
- Paraphrase is allowed at scoring time. Write the facts, not a sample question.
"""
    (OUT / "BRIEF.md").write_text(brief, encoding="utf-8")

    cards = []
    for rid in ids:
        src = source[rid]
        clar = (t41[rid].get("gold") or t41[rid]).get("clarification") or {}
        card = {
            "record_id": rid,
            "command": src.get("command"),
            "dialogue_history": src.get("dialogue_history") or [],
            "scene_context": src.get("scene_context"),
            "capability_context": src.get("capability_context"),
        }
        (OUT / "cards" / f"{rid}.json").write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (OUT / "annotator_a_t41" / f"{rid}.json").write_text(
            json.dumps(
                {
                    "record_id": rid,
                    "annotator": "A",
                    "annotator_model": "t41_interpretation_gold",
                    "targets": clar.get("targets") or [],
                    "must_convey": (clar.get("wording_criteria") or {}).get("must_convey") or [],
                    "must_not_convey": (clar.get("wording_criteria") or {}).get("must_not_convey") or [],
                    "acceptable_paraphrase": True,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        cards.append(card)

    (OUT / "RECORD_IDS.json").write_text(json.dumps(ids, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n": len(ids), "ids": ids, "out": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
