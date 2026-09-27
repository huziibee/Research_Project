#!/usr/bin/env python3
"""Promote Pilot-120 CPC sidecar to final_gold.

Does not mutate frozen core gold or the raw T41 merge
(`pilot_120_final_gold_with_cpc.jsonl`). Evaluator scores filled cells only;
missing/unknown/not_applicable stay ineligible.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANN = ROOT / "data" / "annotations" / "pilot_120_v1"
BASE = ANN / "gold_v2_officialization_20260914" / "cpc"
FROZEN = ANN / "pilot_120_final_gold.jsonl"
MERGED = ANN / "pilot_120_final_gold_with_cpc.jsonl"
WORK = BASE / "working_copy_repaired.jsonl"
REPAIR_LOG = BASE / "repair_log.json"
OFFICIAL = ANN / "pilot_120_gold_cpc_official.jsonl"
OFFICIAL_COPY = BASE / "pilot_120_gold_cpc_official.jsonl"
MANIFEST = ANN / "pilot_120_gold_cpc_official.manifest.json"

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

# Command-licensed fills the original heuristic missed (stock / top up / take-to).
LICENSED_ACTION_FILLS = {
    "CA-0203": "stock",
    "CA-0369": "stock",
    "CA-0226": "top up then return",
    "CA-0426": "top up then return",
    "CA-0596": "top up then return",
    # Twin of CA-0904 ("Take … to …"); T41 already used transport there.
    "CA-0336": "transport",
}

# Heuristic matched "inspect" inside the after-time phrase "closing inspection".
# Command is Take X to Y (same family as CA-0336 / CA-0904).
HEURISTIC_ACTION_FIXES = {
    "CA-0253": ("inspect", "transport"),
}

LEAVE_ACTION_MISSING = {"CA-0878"}

KEEP_UNKNOWN = {
    "object": {"CA-0007", "CA-0056", "CA-0092", "CA-0394", "CA-0512", "CA-0735"},
    "recipient": {"CA-0007", "CA-0056", "CA-0092", "CA-0394", "CA-0512", "CA-0735", "CA-0836"},
    "destination": {"CA-0070", "CA-0552", "CA-0714", "CA-0727", "CA-0786"},
    "quantity": {"CA-0133", "CA-0608", "CA-0798", "CA-0889"},
    "tool": {"CA-0671", "CA-0845"},
}

DEFINITE = ["CA-0418", "CA-0203", "CA-0369", "CA-0226", "CA-0426", "CA-0596", "CA-0702", "CA-0778"]
RANDOM15 = [
    "CA-0007",
    "CA-0326",
    "CA-0397",
    "CA-0470",
    "CA-0576",
    "CA-0648",
    "CA-0686",
    "CA-0733",
    "CA-0735",
    "CA-0797",
    "CA-0846",
    "CA-0851",
    "CA-0909",
    "CA-0940",
    "CA-0961",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def load_jsonl(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["record_id"]] = row
    return rows


def slot_tuple(slot: dict | None) -> tuple[str, str | None]:
    slot = slot or {}
    status = slot.get("status") or "not_applicable"
    value = slot.get("value")
    if status != "filled":
        value = None
    return status, value


def eligibility(status: str) -> str:
    return "eligible" if status == "filled" else "ineligible"


def main() -> None:
    frozen = load_jsonl(FROZEN)
    merged = load_jsonl(MERGED)
    work = load_jsonl(WORK)
    prior_edits = json.loads(REPAIR_LOG.read_text(encoding="utf-8")).get("edits", [])
    assert len(frozen) == len(merged) == len(work) == 120
    assert set(frozen) == set(merged) == set(work)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    extra_edits: list[dict] = []
    official: list[dict] = []
    status_counts = Counter()
    slot_status_counts = Counter()
    eligible_cells = 0
    ineligible_cells = 0

    for rid in sorted(work):
        cpc = deepcopy(work[rid]["gold_cpc"])
        for name in CPC_SLOT_NAMES:
            cpc.setdefault(name, {"status": "not_applicable", "value": None})

        if rid in LICENSED_ACTION_FILLS:
            assert cpc["action"]["status"] == "missing", rid
            new = LICENSED_ACTION_FILLS[rid]
            cpc["action"] = {"status": "filled", "value": new}
            extra_edits.append(
                {"record_id": rid, "slot": "action", "op": "licensed_fill_from_command", "new": new}
            )
        if rid in HEURISTIC_ACTION_FIXES:
            old, new = HEURISTIC_ACTION_FIXES[rid]
            assert cpc["action"]["status"] == "filled" and cpc["action"]["value"] == old, rid
            cpc["action"] = {"status": "filled", "value": new}
            extra_edits.append(
                {
                    "record_id": rid,
                    "slot": "action",
                    "op": "fix_heuristic_time_phrase_as_action",
                    "old": old,
                    "new": new,
                    "why": "command is Take X to Y; inspection is the after-time, not the action",
                }
            )
        if rid in LEAVE_ACTION_MISSING:
            assert cpc["action"]["status"] == "missing", rid
            assert cpc["negation"]["status"] == "filled" and cpc["negation"]["value"] == "do not", rid

        for slot_name, ids in KEEP_UNKNOWN.items():
            if rid in ids:
                assert cpc[slot_name]["status"] == "unknown", (rid, slot_name)

        raw = merged[rid].get("gold_cpc") or {}
        repairs = [e for e in prior_edits if e["record_id"] == rid] + [
            e for e in extra_edits if e["record_id"] == rid
        ]
        changed = bool(repairs)
        if not changed:
            for name in CPC_SLOT_NAMES:
                if slot_tuple(cpc.get(name)) != slot_tuple(raw.get(name)):
                    changed = True
                    break
        field_status = "repaired" if changed else "t41_accepted"

        slot_eligibility = {}
        slot_status = {}
        for name in CPC_SLOT_NAMES:
            status, _ = slot_tuple(cpc[name])
            slot_status[name] = status
            slot_eligibility[name] = eligibility(status)
            slot_status_counts[status] += 1
            if status == "filled":
                eligible_cells += 1
            else:
                ineligible_cells += 1

        official.append(
            {
                "record_id": rid,
                "gold_cpc": {name: cpc[name] for name in CPC_SLOT_NAMES},
                "slot_status": slot_status,
                "slot_eligibility": slot_eligibility,
                "field_status": field_status,
                "gold_lifecycle": "final_gold",
                "annotation_status": "official",
                "repair_ops": repairs,
                "independent_auditor": "claude_parent_spotcheck_20260914",
                "human_gate": "operator_20260914_make_cpc_official",
                "promoted_at_utc": stamp,
            }
        )
        status_counts[field_status] += 1

    assert all(r["gold_lifecycle"] == "final_gold" for r in official)
    assert official[-1]["record_id"]  # non-empty
    missing_action_left = [
        r["record_id"]
        for r in official
        if r["gold_cpc"]["action"]["status"] == "missing"
    ]
    assert missing_action_left == ["CA-0878"], missing_action_left

    frozen_bytes = FROZEN.read_bytes()
    merged_bytes = MERGED.read_bytes()

    text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in official)
    OFFICIAL.write_text(text, encoding="utf-8")
    OFFICIAL_COPY.write_text(text, encoding="utf-8")
    digest = sha256(OFFICIAL)

    assert FROZEN.read_bytes() == frozen_bytes
    assert MERGED.read_bytes() == merged_bytes

    spotcheck = {
        "independent_auditor": "claude_parent_spotcheck_20260914",
        "not_same_family_as_gpt": True,
        "definite8": {
            "ids": DEFINITE,
            "verdict": "pass",
            "notes": [
                "CA-0418 quantity 0 -> 0.5 metres per second (handbook routine setting)",
                "CA-0203/CA-0369 quantity 26 -> 26 packs",
                "CA-0226/CA-0426/CA-0596 quantity 800 -> 800 ml",
                "CA-0702/CA-0778 refill jug re-slotted object_attributes -> tool",
            ],
        },
        "random15": {
            "ids": RANDOM15,
            "seed": 20260914,
            "verdict": "pass",
            "notes": [
                "Vague objects on CA-0007/CA-0735 correctly unknown",
                "CA-0797 time restored after 13:00 lesson change",
                "CA-0909 missing action filled move from command",
                "No invented slot values on sampled unknowns",
            ],
        },
        "post_spotcheck_licensed_fills": extra_edits,
        "left_action_missing": sorted(LEAVE_ACTION_MISSING),
        "unknown_slots_kept": {k: sorted(v) for k, v in KEEP_UNKNOWN.items()},
    }
    (BASE / "spotcheck_report.json").write_text(
        json.dumps(spotcheck, indent=2) + "\n", encoding="utf-8"
    )
    (BASE / "licensed_action_fills.json").write_text(
        json.dumps({"edits": extra_edits}, indent=2) + "\n", encoding="utf-8"
    )

    manifest = {
        "artifact": str(OFFICIAL.relative_to(ROOT)).replace("\\", "/"),
        "n": 120,
        "gold_lifecycle": "final_gold",
        "sha256": digest,
        "frozen_core_mutated": False,
        "raw_t41_merge_mutated": False,
        "raw_t41_provenance": str(MERGED.relative_to(ROOT)).replace("\\", "/"),
        "working_copy": str(WORK.relative_to(ROOT)).replace("\\", "/"),
        "field_status": dict(status_counts),
        "slot_status_cells": dict(slot_status_counts),
        "eligible_filled_cells": eligible_cells,
        "ineligible_cells": ineligible_cells,
        "scoring_rule": "Evaluator scores filled cells only; missing/unknown/not_applicable are ineligible.",
        "licensed_action_fills": LICENSED_ACTION_FILLS,
        "heuristic_action_fixes": {
            rid: {"from": old, "to": new} for rid, (old, new) in HEURISTIC_ACTION_FIXES.items()
        },
        "left_action_missing": sorted(LEAVE_ACTION_MISSING),
        "independent_auditor": "claude_parent_spotcheck_20260914",
        "spotcheck": {
            "definite8": DEFINITE,
            "random15_seed": 20260914,
            "random15": RANDOM15,
            "verdict": "pass",
        },
        "did_not_fold_into_running_mega_54259": True,
        "promoted_at_utc": stamp,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (BASE / "pilot_120_gold_cpc_official.manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    launch = BASE.parent / "risk" / "LAUNCH_STATUS.json"
    if launch.exists():
        payload = json.loads(launch.read_text(encoding="utf-8"))
        payload["cpc_official_path"] = str(OFFICIAL)
        payload["cpc_sha256"] = digest
        payload["note"] = (
            "Official current-scale risk gold and official CPC sidecar. "
            "Frozen core and raw T41 merge unchanged. Mega 54259 does not pick these up."
        )
        launch.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "official": str(OFFICIAL),
                "n": 120,
                "field_status": dict(status_counts),
                "eligible_filled_cells": eligible_cells,
                "sha256": digest,
                "licensed_fills": extra_edits,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
