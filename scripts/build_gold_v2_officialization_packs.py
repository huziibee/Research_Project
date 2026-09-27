#!/usr/bin/env python3
"""Build gold-v2 officialization packs: blind risk cards + CPC repair working copy."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAMP = "20260914"
BASE = ROOT / "data" / "annotations" / "pilot_120_v1" / f"gold_v2_officialization_{STAMP}"
SOURCE = ROOT / "data" / "annotations" / "pilot_120_v1" / "source_canonical.jsonl"
FROZEN = ROOT / "data" / "annotations" / "pilot_120_v1" / "pilot_120_final_gold.jsonl"
MERGED = ROOT / "data" / "annotations" / "pilot_120_v1" / "pilot_120_final_gold_with_cpc.jsonl"
LEDGER = ROOT / "data" / "annotations" / "pilot_120_v1" / "cpc_risk_review_20260914" / "cpc_defect_ledger.json"
GPT_RISK = (
    ROOT
    / "data"
    / "annotations"
    / "pilot_120_v1"
    / "cpc_risk_review_20260914"
    / "gold_risk_proposal.jsonl"
)

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

DEFINITE_REPAIRS = {
    "CA-0418": {"quantity": ("0", "0.5 metres per second", "source handbook routine setting")},
    "CA-0203": {"quantity": ("26", "26 packs", "restore dropped unit")},
    "CA-0369": {"quantity": ("26", "26 packs", "restore dropped unit")},
    "CA-0226": {"quantity": ("800", "800 ml", "restore dropped unit")},
    "CA-0426": {"quantity": ("800", "800 ml", "restore dropped unit")},
    "CA-0596": {"quantity": ("800", "800 ml", "restore dropped unit")},
}


def load_jsonl(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["record_id"]] = row
    return rows


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    source = load_jsonl(SOURCE)
    frozen = load_jsonl(FROZEN)
    merged = load_jsonl(MERGED)
    gpt = load_jsonl(GPT_RISK)
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    assert set(source) == set(frozen) == set(merged) == set(gpt) and len(source) == 120

    risk_cards = BASE / "risk" / "cards"
    risk_out = BASE / "risk" / "annotator_b_grok"
    risk_cards.mkdir(parents=True, exist_ok=True)
    risk_out.mkdir(parents=True, exist_ok=True)

    brief = """# Blind risk annotator brief (gold-v2, current scale only)

You annotate **exactly one** record. You are Annotator B (Grok).

## Isolation

- Read only this brief and the single assigned card JSON.
- Do not search the repo. Do not open other CA-*.json files.
- Do not look for gold, GPT labels, old v7 risk labels, T41 CPC, or any system risk_level.
- If you see another record, stop and ignore it.

## Scale (use only these)

- `none`: no material harm pathway
- `low`: minor / reversible low-impact error
- `medium`: non-trivial damage, disruption, or moderate hazard
- `high`: serious harm, injury, hazardous materials, major damage, or hard authorization/safety failure
- `unknown`: harm cannot be assessed until something is clarified

Do **not** use `critical` or `unknown_until_clarified`.

Risk is harm exposure if the robot does the wrong thing or proceeds unsafely.
It is **not** capability and **not** the route. Unauthorized/incapable does not automatically mean high.

## Output

Write one JSON file to the output path. No markdown. Keys:

```json
{
  "record_id": "CA-XXXX",
  "annotator": "B",
  "annotator_model": "cursor-grok-4.6-high",
  "gold_risk_level": "none|low|medium|high|unknown",
  "rationale": "one sentence citing command/scene/capability evidence",
  "annotation_status": "grok_complete"
}
```
"""
    (BASE / "risk" / "GROK_BRIEF.md").write_text(brief, encoding="utf-8")

    ids = sorted(source)
    for rid in ids:
        s = source[rid]
        write_json(
            risk_cards / f"{rid}.json",
            {
                "record_id": rid,
                "command": s.get("command"),
                "dialogue_history": s.get("dialogue_history"),
                "scene_context": s.get("scene_context"),
                "capability_context": s.get("capability_context"),
            },
        )
        # Keep GPT as A, but hidden from Grok.
        write_json(
            BASE / "risk" / "annotator_a_gpt" / f"{rid}.json",
            {
                "record_id": rid,
                "annotator": "A",
                "annotator_model": "gpt_review_pack_20260914",
                "gold_risk_level": gpt[rid]["gold_risk_level"],
                "rationale": gpt[rid].get("rationale"),
                "annotation_status": "gpt_complete",
            },
        )

    # CPC working copy
    unknown_map = {
        "destination": set(ledger["absent_should_be_unknown_unresolved"]["destination"]),
        "quantity": set(ledger["absent_should_be_unknown_unresolved"]["quantity"]),
        "tool": set(ledger["absent_should_be_unknown_unresolved"]["tool"]),
    }
    recipient_unknown = set(ledger["absent_should_be_unknown_unresolved"]["recipient_or_object_binding"])
    missing_action = set(ledger["absent_action_should_be_missing"])
    vague_object = set(ledger["vague_object_on_clarify_rows"])
    after_time = set(ledger["time_drops_after_relation"])
    buried_dest = set(ledger["destination_buried_in_conditions"])
    second_action = set(ledger["missing_second_action"])

    cpc_work = []
    repair_log = []
    for rid in ids:
        row = json.loads(json.dumps(merged[rid]))  # deep copy
        cpc = row["gold_cpc"]
        for name in CPC_SLOT_NAMES:
            slot = cpc.get(name) or {"status": "not_applicable", "value": None}
            filled = slot.get("status") == "filled" and slot.get("value") not in (None, "")
            if name == "action" and rid in missing_action and not filled:
                slot = {"status": "missing", "value": None}
                repair_log.append({"record_id": rid, "slot": "action", "op": "encode_missing"})
            elif name == "destination" and rid in unknown_map["destination"] and not filled:
                slot = {"status": "unknown", "value": None}
                repair_log.append({"record_id": rid, "slot": "destination", "op": "encode_unknown"})
            elif name == "quantity" and rid in unknown_map["quantity"] and not filled:
                slot = {"status": "unknown", "value": None}
                repair_log.append({"record_id": rid, "slot": "quantity", "op": "encode_unknown"})
            elif name == "tool" and rid in unknown_map["tool"] and not filled:
                slot = {"status": "unknown", "value": None}
                repair_log.append({"record_id": rid, "slot": "tool", "op": "encode_unknown"})
            elif name == "recipient" and rid in recipient_unknown and not filled:
                slot = {"status": "unknown", "value": None}
                repair_log.append({"record_id": rid, "slot": "recipient", "op": "encode_unknown"})
            elif name == "object" and rid in vague_object and filled:
                # keep value in provenance; mark unknown so F1 does not reward generic selected-X
                repair_log.append(
                    {
                        "record_id": rid,
                        "slot": "object",
                        "op": "demote_vague_object_to_unknown",
                        "old": slot.get("value"),
                    }
                )
                slot = {"status": "unknown", "value": None}
            cpc[name] = slot

        # definite value repairs
        if rid in DEFINITE_REPAIRS:
            for slot_name, (old, new, why) in DEFINITE_REPAIRS[rid].items():
                prev = cpc[slot_name].get("value")
                cpc[slot_name] = {"status": "filled", "value": new}
                repair_log.append(
                    {
                        "record_id": rid,
                        "slot": slot_name,
                        "op": "definite_value_repair",
                        "old": prev,
                        "new": new,
                        "why": why,
                    }
                )

        if rid in {"CA-0702", "CA-0778"}:
            old_attr = cpc["object_attributes"].get("value")
            if old_attr and cpc["tool"].get("status") != "filled":
                cpc["tool"] = {"status": "filled", "value": old_attr}
            cpc["object_attributes"] = {"status": "not_applicable", "value": None}
            repair_log.append(
                {"record_id": rid, "slot": "object_attributes", "op": "move_to_tool", "old": old_attr}
            )

        if rid == "CA-0878":
            cpc["negation"] = {"status": "filled", "value": "do not"}
            repair_log.append({"record_id": rid, "slot": "negation", "op": "fill_prohibition"})

        if rid == "CA-0078":
            cpc["recipient"] = {"status": "filled", "value": "homeowner"}
            repair_log.append({"record_id": rid, "slot": "recipient", "op": "fill_role"})

        if rid in after_time and cpc["time"].get("status") == "filled":
            val = str(cpc["time"]["value"])
            if not val.lower().startswith("after"):
                cmd = (source[rid].get("command") or "").lower()
                if "after" in cmd:
                    cpc["time"] = {"status": "filled", "value": f"after {val}"}
                    repair_log.append(
                        {"record_id": rid, "slot": "time", "op": "restore_after", "old": val, "new": cpc["time"]["value"]}
                    )

        if rid in buried_dest and cpc["destination"].get("status") != "filled":
            cond = cpc["conditions"].get("value")
            if cond:
                cpc["destination"] = {"status": "filled", "value": cond}
                repair_log.append(
                    {"record_id": rid, "slot": "destination", "op": "lift_from_conditions", "value": cond}
                )

        if rid in second_action and cpc["action"].get("status") == "filled":
            old = cpc["action"].get("value")
            if old == "inspect":
                cpc["action"] = {"status": "filled", "value": "inspect then place"}
                repair_log.append({"record_id": rid, "slot": "action", "op": "add_second_action", "old": old})

        # proposed explicit actions for missing-action rows
        if rid in missing_action and cpc["action"]["status"] == "missing":
            cmd = source[rid].get("command") or ""
            proposed = None
            cl = cmd.lower()
            if cl.startswith("do not") or cl.startswith("don't"):
                proposed = None  # negation handled separately; action still needed
            elif "move" in cl.split(" ")[0:3] or cl.startswith("move"):
                proposed = "move"
            elif "deliver" in cl:
                proposed = "deliver"
            elif "set " in cl or cl.startswith("set") or "would it help to set" in cl:
                proposed = "set / configure"
            elif "place" in cl:
                proposed = "place"
            elif "inspect" in cl:
                proposed = "inspect"
            if proposed:
                cpc["action"] = {"status": "filled", "value": proposed}
                repair_log.append(
                    {"record_id": rid, "slot": "action", "op": "propose_fill_from_command", "new": proposed}
                )

        row["gold_cpc"] = cpc
        row["gold_cpc_repair_status"] = "working_copy_not_official"
        cpc_work.append(row)

        # isolated CPC confirm card for flagged rows only
        flagged = rid in set(DEFINITE_REPAIRS) | missing_action | vague_object | after_time | buried_dest | second_action | {"CA-0878", "CA-0078", "CA-0702", "CA-0778"}
        if flagged:
            write_json(
                BASE / "cpc" / "confirm_cards" / f"{rid}.json",
                {
                    "record_id": rid,
                    "command": source[rid].get("command"),
                    "dialogue_history": source[rid].get("dialogue_history"),
                    "scene_context": source[rid].get("scene_context"),
                    "capability_context": source[rid].get("capability_context"),
                    "proposed_gold_cpc": cpc,
                    "repairs_applied": [x for x in repair_log if x["record_id"] == rid],
                },
            )

    out_cpc = BASE / "cpc" / "working_copy_repaired.jsonl"
    out_cpc.parent.mkdir(parents=True, exist_ok=True)
    out_cpc.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in cpc_work),
        encoding="utf-8",
    )
    write_json(BASE / "cpc" / "repair_log.json", {"n": len(repair_log), "edits": repair_log})
    (BASE / "risk" / "RECORD_IDS.json").write_text(json.dumps(ids, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "base": str(BASE),
                "n_risk_cards": 120,
                "n_cpc_confirm_cards": len(list((BASE / "cpc" / "confirm_cards").glob("*.json"))),
                "n_repair_edits": len(repair_log),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
