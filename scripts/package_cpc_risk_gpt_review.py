#!/usr/bin/env python3
"""Build a compact GPT review zip for Pilot-120 CPC + risk."""
from __future__ import annotations

import json
import shutil
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAMP = "20260914"
PACK = ROOT / "review_packs" / f"pilot120_cpc_risk_gpt_{STAMP}"
ZIP_PATH = ROOT / "review_packs" / f"pilot120_cpc_risk_gpt_{STAMP}.zip"

FROZEN = ROOT / "data" / "annotations" / "pilot_120_v1" / "pilot_120_final_gold.jsonl"
MERGED = ROOT / "data" / "annotations" / "pilot_120_v1" / "pilot_120_final_gold_with_cpc.jsonl"
SOURCE = ROOT / "data" / "annotations" / "pilot_120_v1" / "source_canonical.jsonl"
T41 = ROOT / "pilot120_t41_complete_closure" / "final_t41" / "pilot120_interpretation_gold_final.jsonl"
HIST = (
    ROOT
    / "pilot120_t41_complete_closure"
    / "frozen_evidence"
    / "historical_adjudication"
    / "ALL_ANNOTATIONS_FACTCHECK.jsonl"
)
CPC_POLICY = ROOT / "pilot120_t41_complete_closure" / "frozen_evidence" / "cpc_normalisation_v1_1_frozen.json"
HANDBOOK_V7 = ROOT / "pilot120_historical_annotation_handoff" / "annotations" / "manual_kappa_v7" / "briefs" / "handbook_v7.md"
SCHEMA_V7 = ROOT / "pilot120_historical_annotation_handoff" / "annotations" / "manual_kappa_v7" / "briefs" / "output_schema_v7.json"
GOLD_RULES = ROOT / "pilot120_historical_annotation_handoff" / "annotations" / "manual_kappa_v7" / "GOLD_ADJUDICATION_RULES.md"
HANDBOOK_V1 = ROOT / "docs" / "protocols" / "annotation_handbook_v1.md"
SCORE = ROOT / "outputs" / "pilot120_cpc_risk_scores_20260913.json"
MANIFEST = ROOT / "data" / "annotations" / "pilot_120_v1" / "pilot_120_cpc_merge_manifest.json"
RISK_INV = ROOT / "data" / "annotations" / "pilot_120_v1" / "pilot_120_risk_inventory_20260913.json"

OFFICIAL_RISKS = ("none", "low", "medium", "high", "unknown")
V7_RISKS = ("low", "medium", "high", "critical")


def load_jsonl(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["record_id"]] = row
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8",
    )


def excerpt(path: Path, start: str, end: str | None = None) -> str:
    text = path.read_text(encoding="utf-8")
    i = text.find(start)
    if i < 0:
        return text[:4000]
    if end is None:
        return text[i : i + 2500]
    j = text.find(end, i + 1)
    return text[i : j if j > 0 else i + 2500]


def main() -> None:
    if PACK.exists():
        shutil.rmtree(PACK)
    data = PACK / "data"
    refs = PACK / "refs"
    scores = PACK / "scores"
    for d in (data, refs, scores):
        d.mkdir(parents=True)

    frozen = load_jsonl(FROZEN)
    merged = load_jsonl(MERGED)
    source = load_jsonl(SOURCE)
    t41 = load_jsonl(T41)
    hist = load_jsonl(HIST)
    assert set(frozen) == set(merged) == set(source) == set(t41) == set(hist) == set(frozen)
    assert len(frozen) == 120

    shutil.copy2(FROZEN, data / "pilot_120_final_gold.FROZEN.jsonl")
    shutil.copy2(MERGED, data / "pilot_120_final_gold_with_cpc.jsonl")
    shutil.copy2(SOURCE, data / "source_canonical.jsonl")
    shutil.copy2(CPC_POLICY, refs / "cpc_normalisation_v1_1_frozen.json")
    if SCORE.exists():
        shutil.copy2(SCORE, scores / "cpc_live_v2_score.json")
    if MANIFEST.exists():
        shutil.copy2(MANIFEST, scores / "cpc_merge_manifest.json")
    if RISK_INV.exists():
        shutil.copy2(RISK_INV, scores / "risk_inventory.json")

    slim_cpc = []
    ab_rows = []
    disagree = []
    worksheet = []
    for rid in sorted(frozen):
        t = t41[rid]
        h = hist[rid]
        g = frozen[rid]
        s = source[rid]
        slots = ((t.get("gold") or {}).get("cpc") or {}).get("slots") or {}
        slim_cpc.append(
            {
                "record_id": rid,
                "cpc_field_status": (t.get("field_status") or {}).get("cpc"),
                "annotation_status": t.get("annotation_status"),
                "critical_slots": ((t.get("gold") or {}).get("cpc") or {}).get("critical_slots"),
                "t41_raw_slots": slots,
                "merged_gold_cpc": merged[rid].get("gold_cpc"),
                "gold_terminal_strategy": g.get("terminal_strategy"),
                "gold_capability_status": g.get("capability_status"),
                "gold_ambiguity_types": g.get("ambiguity_types"),
            }
        )
        a_risk = (h.get("annotator_a") or {}).get("risk_level")
        b_risk = (h.get("annotator_b") or {}).get("risk_level")
        ab = {
            "record_id": rid,
            "annotator_a_model": "cursor-grok-4.5-high-fast",
            "annotator_b_model": h.get("annotator_b_model"),
            "annotator_b_era": h.get("annotator_b_era"),
            "annotator_a_risk_level_v7": a_risk,
            "annotator_b_risk_level_v7": b_risk,
            "agree": a_risk == b_risk,
            "official_gold_risk_level": None,
            "gold_terminal_strategy": g.get("terminal_strategy"),
            "gold_capability_status": g.get("capability_status"),
        }
        ab_rows.append(ab)
        if a_risk != b_risk:
            disagree.append(ab)
        worksheet.append(
            {
                "record_id": rid,
                "command": s.get("command"),
                "dialogue_history": s.get("dialogue_history"),
                "scene_context": s.get("scene_context"),
                "capability_context": s.get("capability_context"),
                "gold_terminal_strategy": g.get("terminal_strategy"),
                "gold_capability_status": g.get("capability_status"),
                "gold_ambiguity_types": g.get("ambiguity_types"),
                "t41_cpc_slots": slots,
                "prior_annotator_a_risk_v7": a_risk,
                "prior_annotator_b_risk_v7": b_risk,
                "prior_v7_scale": list(V7_RISKS),
                "label_on_THIS_scale": list(OFFICIAL_RISKS),
                "gold_risk_level": None,
                "rationale": None,
                "annotation_status": "blank_pending_reviewer",
            }
        )

    write_jsonl(data / "t41_cpc_slim.jsonl", slim_cpc)
    write_jsonl(data / "ab_risk_labels_v7.jsonl", ab_rows)
    write_jsonl(data / "ab_risk_disagrees_25.jsonl", disagree)
    write_jsonl(data / "risk_worksheet_official_scale.jsonl", worksheet)

    refs.joinpath("handbook_v7_risk_excerpt.md").write_text(
        excerpt(HANDBOOK_V7, "## 8. Risk and capability", "## 9.")
        if "## 9." in HANDBOOK_V7.read_text(encoding="utf-8")
        else excerpt(HANDBOOK_V7, "## 8. Risk and capability", "##"),
        encoding="utf-8",
    )
    # handbook v7 has no ## 9; take a bounded slice
    v7 = HANDBOOK_V7.read_text(encoding="utf-8")
    i = v7.find("## 8. Risk and capability")
    refs.joinpath("handbook_v7_risk_excerpt.md").write_text(v7[i : i + 1600], encoding="utf-8")
    v1 = HANDBOOK_V1.read_text(encoding="utf-8")
    j = v1.find("### Risk (`risk_level`)")
    refs.joinpath("handbook_v1_risk_excerpt.md").write_text(v1[j : j + 900], encoding="utf-8")
    schema_v7 = json.loads(SCHEMA_V7.read_text(encoding="utf-8"))
    refs.joinpath("output_schema_v7_risk.json").write_text(
        json.dumps(
            {
                "risk_level": schema_v7.get("properties", {}).get("risk_level")
                or schema_v7.get("risk_level"),
                "note": "Pilot kappa v7 used this enum. Confirm from file.",
                "raw_from_file": schema_v7["properties"]["risk_level"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    refs.joinpath("schema_v2_official_risk.md").write_text(
        "Official live / schema v2 RiskLevel:\n\n"
        "- none\n- low\n- medium\n- high\n- unknown\n\n"
        "No `critical`. `unknown_until_clarified` is a v1 legacy alias mapped to `unknown`.\n"
        "Live goal-first v2 prompt: Allowed risk_level: none, low, medium, high, unknown.\n",
        encoding="utf-8",
    )
    rules = GOLD_RULES.read_text(encoding="utf-8")
    refs.joinpath("GOLD_ADJUDICATION_RULES_excerpt.md").write_text(
        "".join(
            line
            for line in rules.splitlines(True)
            if "risk" in line.lower()
            or line.startswith("#")
            or line.startswith("| Field")
            or line.startswith("| ---")
            or "Core gold" in line
            or "Out of scope" in line
        ),
        encoding="utf-8",
    )

    investigation = f"""# Investigation: is Pilot-120 risk official, and is CPC correct?

Date: 14 September 2026. Do not treat this memo as gold.

## Short answers

1. **Official gold risk: no.** Frozen `pilot_120_final_gold.jsonl` has no `risk_level`.
2. **Unofficial A/B risk: yes, 120/120**, on a **different scale** than the live system.
3. **Official CPC gold: yes, as T41 interpretation gold**, now joined as a sidecar. Frozen core gold was not rewritten.
4. **Do not promote A/B risk into official gold** without remapping + a new pass. The scales do not match.

## Risk taxonomies (this is the mismatch)

| Source | Allowed values | Official for Pilot-120 eval? |
|---|---|---|
| Kappa v7 handbook + schema (what A/B used) | `low`, `medium`, `high`, `critical` | No. Exploratory only. |
| Schema v1 (older project) | `none`, `low`, `medium`, `high`, `unknown_until_clarified` | Superseded. |
| Schema v2 / live goal-first v2 (current) | `none`, `low`, `medium`, `high`, `unknown` | This is the scale a new official label must use. |
| Frozen final gold | *(field absent)* | Official absence. |

A/B actual usage: only `low` / `medium` / `high`. **Nobody used `critical`, `none`, or `unknown`.**
Agreement: 95/120 agree, 25 disagree, Cohen κ 0.59, raw 0.79.
Gold-v1 rule: “Do not freeze `risk_level` into eval gold” because of adjacent-band drift.

Proposal metric “risk-sensitive decision accuracy” needs gold `medium`/`high` on the **current** scale, then scores whether the predicted route matches gold route. A v7 `critical` would not even enter that denominator unless remapped. A v7 `low` is not the same as v2 `none`.

## CPC: is the merge correct?

T41 gold: 120/120 rows have CPC. 97 `BLIND_ADJUDICATED` (pseudonym `blind_chatgpt_gpt56sol`), 23 `DUAL_SEMANTIC_CONSENSUS_NORMALIZED`. 660 filled slot cells. Policy `cpc_normalisation_v1_1_frozen` is marked `valid_for_official_use: true`.

Canonical 13 slots: action, actor, object, object_attributes, destination, spatial_relation, quantity, time, recipient, tool, conditions, constraints, negation.

Occupancy: actor 120 (always `robot`, per T41 default), object 119, action 101, time 72, conditions 57, destination 56, constraints 40, spatial_relation 36, tool 30, quantity 22, object_attributes 7, **recipient 0, negation 0**.

Merge file copies every frozen core field verbatim and adds `gold_cpc` in evaluator `{{status,value}}` form. Absent T41 slots were encoded `not_applicable` (evaluator only scores `filled`, so this is equivalent to omit for F1). Frozen SHA of core gold was not changed.

Known caveats a reviewer should poke:
- Sparse frames: T41 lists only filled values. `not_applicable` vs `missing` vs `unknown` is a conversion choice, not in the raw T41 object.
- `recipient` and `negation` never appear. Some commands have named recipients in scene text; T41 may have folded that into `object` (“tray for nurse”).
- Clarify rows still have a filled object/time even when the gold route is ask. That is “bind what is known, leave the choice in candidates,” not a full unique frame.
- Live v2 barely emits CPC (6/120 rows, 78 cells). Against this gold: F1 ≈ 0.046, exact match 0/120. That is a system emit problem, not a missing-gold problem.

## What GPT should do

See `00_GPT_PROMPT.md`. Preferred: review CPC + taxonomy, then fill `data/risk_worksheet_official_scale.jsonl` on the **v2 official scale** (`none|low|medium|high|unknown`). Treat v7 A/B labels as prior votes, not answers.
"""
    (PACK / "01_INVESTIGATION.md").write_text(investigation, encoding="utf-8")

    prompt = """# GPT review / labeling prompt — Pilot-120 CPC and risk

You are reviewing a frozen honours eval set (Wits). You are **not** allowed to invent missing science. You may label risk on the official current scale, and you may criticise CPC or process.

## Read first

1. `01_INVESTIGATION.md`
2. `refs/schema_v2_official_risk.md`
3. `refs/handbook_v7_risk_excerpt.md` (old A/B scale — different)
4. `refs/handbook_v1_risk_excerpt.md` (closer to current official scale)
5. `refs/cpc_normalisation_v1_1_frozen.json`
6. `refs/GOLD_ADJUDICATION_RULES_excerpt.md`

## Hard constraints

- Official current risk scale is **only**: `none`, `low`, `medium`, `high`, `unknown`.
- Do **not** use `critical` or `unknown_until_clarified` in any new official label.
- Prior A/B labels in `data/ab_risk_labels_v7.jsonl` used **low/medium/high/critical**. They are **not official gold**. Use them as hints only.
- Frozen core gold (`data/pilot_120_final_gold.FROZEN.jsonl`) must not be rewritten in your head as if it already had risk.
- Do **not** copy a live system’s `risk_level` (none is in this pack anyway).
- CPC gold comes from T41. Do not replace T41 slots unless you flag a specific error with evidence from command/scene/dialogue.

## Task A — CPC audit (required)

For the 13 canonical slots, inspect `data/t41_cpc_slim.jsonl` plus `data/source_canonical.jsonl`.

Return:

1. Is T41 CPC usable as official slot-binding gold? Yes / yes-with-caveats / no.
2. List concrete row IDs where a filled slot looks wrong, invented, or too vague.
3. Say whether encoding omitted slots as `not_applicable` is honest, or whether some should be `missing` / `unknown`.
4. Comment on `recipient=0` and `negation=0` and `actor=robot` on all 120.
5. Anything else you are unhappy with.

## Task B — Risk labels (if you have budget)

Fill **every** row in `data/risk_worksheet_official_scale.jsonl`:

- set `gold_risk_level` to one of `none|low|medium|high|unknown`
- set `rationale` to one short sentence citing command/scene/capability evidence
- set `annotation_status` to `reviewer_complete`

Meanings (use these, not the v7 ones):

- `none`: no material harm pathway
- `low`: minor / reversible low-impact error
- `medium`: non-trivial damage, disruption, or moderate hazard
- `high`: serious harm, injury, hazardous materials, major damage, or hard authorization/safety failure
- `unknown`: harm cannot be assessed until something is clarified

Do **not** auto-copy A or B. If they agree on v7 `low`, you may still choose `none` if that is the official meaning.

Also return a short note: how often you departed from the A/B agreed v7 label, and why the scale change mattered.

## Task C — Process flags

Point out any contamination, circularity, or “this should not be called official” issue. Especially: T41 CPC adjudicator was `blind_chatgpt_gpt56sol`; core gold risk was never adjudicated; promoting 95 A/B agrees would still be the wrong enum.

## Output

Write:

1. `REVIEW.md` — Tasks A and C, plus a summary of B.
2. `data/risk_worksheet_official_scale.filled.jsonl` — only if you completed Task B for all 120.

Do not produce an official-looking F1. You are the reviewer, not the scorer.
"""
    (PACK / "00_GPT_PROMPT.md").write_text(prompt, encoding="utf-8")
    (PACK / "README.md").write_text(
        "Open `00_GPT_PROMPT.md` first, then `01_INVESTIGATION.md`.\n"
        "This zip is a review pack. It does not change frozen Pilot-120 gold.\n",
        encoding="utf-8",
    )

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in PACK.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(PACK.parent).as_posix())

    print(
        json.dumps(
            {
                "zip": str(ZIP_PATH),
                "pack_dir": str(PACK),
                "n_files": sum(1 for p in PACK.rglob("*") if p.is_file()),
                "bytes": ZIP_PATH.stat().st_size,
                "risk_disagrees": len(disagree),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
