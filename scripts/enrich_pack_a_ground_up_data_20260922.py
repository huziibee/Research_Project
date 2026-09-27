#!/usr/bin/env python3
"""Enrich Pack A with ground-up data + necessary-vs-optional load guide; rezip."""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "outputs" / "paper_writer_handoff_20260922"
PACK_A = STAGING / "A_EVIDENCE_FOR_PAPER"
OUT_A = ROOT / "outputs" / "PaperWriter_A_EVIDENCE_COMPLETE_20260922.zip"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_tree(src: Path, dst: Path) -> int:
    if not src.exists():
        return 0
    n = 0
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return 1
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        if "__pycache__" in p.parts or p.suffix == ".pyc":
            continue
        rel = p.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        n += 1
    return n


def load_jsonl(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rid = str(row.get("record_id") or row.get("id") or "")
        if rid:
            out[rid] = row
    return out


def build_joined_ground_truth() -> Path:
    """One row per Pilot-120 id: source inputs + gold route/capability + intent refs."""
    gold_dir = PACK_A / "03_gold_and_metrics" / "pilot_120_v1"
    source = load_jsonl(gold_dir / "source_canonical.jsonl")
    final_gold = load_jsonl(gold_dir / "pilot_120_final_gold.jsonl")
    risk = load_jsonl(gold_dir / "pilot_120_gold_risk_official.jsonl")
    cpc = load_jsonl(gold_dir / "pilot_120_gold_cpc_official.jsonl")
    wording = load_jsonl(gold_dir / "pilot_120_gold_wording_official.jsonl")
    intent_refs = load_jsonl(PACK_A / "03_gold_and_metrics" / "intent_gold_references_120.jsonl")

    # per-record gold json overrides/complements
    per_rec: dict[str, dict] = {}
    for p in (gold_dir / "gold").glob("CA-*.json"):
        per_rec[p.stem] = json.loads(p.read_text(encoding="utf-8"))

    ids = sorted(set(source) | set(final_gold) | set(per_rec))
    out_path = PACK_A / "03_gold_and_metrics" / "pilot120_joined_ground_truth.jsonl"
    rows_out = []
    for rid in ids:
        g = dict(final_gold.get(rid) or {})
        g.update(per_rec.get(rid) or {})
        s = source.get(rid) or {}
        ir = intent_refs.get(rid) or {}
        rk = risk.get(rid) or {}
        ck = cpc.get(rid) or {}
        wk = wording.get(rid) or {}
        row = {
            "record_id": rid,
            "command": s.get("command"),
            "scene_context": s.get("scene_context"),
            "dialogue_history": s.get("dialogue_history"),
            "capability_context": s.get("capability_context"),
            "gold_terminal_strategy": g.get("terminal_strategy") or g.get("gold_route"),
            "gold_capability_status": g.get("capability_status"),
            "gold_ambiguity_types": g.get("ambiguity_types"),
            "gold_strategy_sequence": g.get("strategy_sequence"),
            "gold_risk": rk.get("risk_level") or rk.get("gold_risk") or rk.get("risk"),
            "gold_cpc_present": bool(ck),
            "gold_wording_present": bool(wk),
            "reference_A_intent_text": ir.get("reference_A_intent_text"),
            "reference_B_intent_text": ir.get("reference_B_intent_text"),
        }
        # keep compact CPC/wording blobs if small enough
        if ck:
            row["gold_cpc"] = ck
        if wk:
            row["gold_wording"] = wk
        rows_out.append(row)

    out_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows_out) + "\n",
        encoding="utf-8",
    )
    # also a tiny index without long scene text for context-light loading
    slim_path = PACK_A / "03_gold_and_metrics" / "pilot120_joined_ground_truth_SLIM.jsonl"
    slim = []
    for r in rows_out:
        slim.append(
            {
                "record_id": r["record_id"],
                "command": r.get("command"),
                "gold_terminal_strategy": r.get("gold_terminal_strategy"),
                "gold_capability_status": r.get("gold_capability_status"),
                "gold_ambiguity_types": r.get("gold_ambiguity_types"),
                "gold_risk": r.get("gold_risk"),
                "reference_A_intent_text": r.get("reference_A_intent_text"),
                "reference_B_intent_text": r.get("reference_B_intent_text"),
                "has_scene": bool(r.get("scene_context")),
                "has_capability_card": bool(r.get("capability_context")),
            }
        )
    slim_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in slim) + "\n",
        encoding="utf-8",
    )
    return out_path


def write_load_guide() -> None:
    text = f"""# Necessary vs optional — what to load into context

**Built:** {datetime.now(timezone.utc).isoformat()}

This pack is intentionally **dense on disk** so you can verify claims from the ground up.
It is **not** meant to be fully pasted into a model context window.

Use tiers. Keep most files closed until needed.

---

## TIER 0 — Always load first (necessary for any paper draft)

| Path | Why |
|---|---|
| `00_START_HERE.md` | Navigation |
| `01_scope_and_boundaries.md` | In/out of scope |
| `DATA_NECESSARY_VS_OPTIONAL.md` | This file |
| `02_protocol_and_systems/04-research-question.md` | RQs / H1–H4 |
| `02_protocol_and_systems/05-methodology.md` | Protocol + metrics |
| `02_protocol_and_systems/01b-the-six-systems.md` | Systems |
| `04_results_narrative/06-results.md` | Results chapter |
| `04_results_narrative/12-capability-rescue-paper-note.md` | Capability mechanism |
| `07_numbers_json/sprint_rescue_summary.json` | Capability patch numbers |
| `07_numbers_json/early_8b_vs_1p7b_T0.7.json` | Size/latency Pareto |
| `07_numbers_json/report_numbers.json` | Headline scoreboard |
| `13_intent_judging_and_comparators/final_close_20260913/gfv2_sgc_summary.json` | Official two-judge 113 |
| `13_intent_judging_and_comparators/final_close_20260913/intent_box_sgc_summary.json` | Raw/FT two-judge |
| `03_gold_and_metrics/pilot120_joined_ground_truth_SLIM.jsonl` | Compact gold+intent index (120 rows) |

**Approx intent:** enough to draft Abstract–Discussion without drowning context.

---

## TIER 1 — Load when verifying a claim (necessary on demand)

| Path | When |
|---|---|
| `03_gold_and_metrics/pilot120_joined_ground_truth.jsonl` | Need full scene/command/capability card for a case |
| `03_gold_and_metrics/pilot_120_v1/source_canonical.jsonl` | Rebuild inputs from scratch |
| `03_gold_and_metrics/pilot_120_v1/gold/*.json` | Per-id gold route/capability/ambiguity |
| `03_gold_and_metrics/pilot_120_v1/pilot_120_gold_*_official.jsonl` | CPC / risk / wording gold |
| `03_gold_and_metrics/intent_gold_references_120.jsonl` | Intent auto-screen refs |
| `05_mechanism_audits/04-the-62-overasks.md` + `07_numbers_json/historical_dissociation_62_ids.json` | Dissociation slab |
| `05_mechanism_audits/10-capability-audit.md`, `15-the-10-unsafe.md` | Capability/unauthorized mechanism |
| `05_mechanism_audits/19-*.md` … `22-*.md` | Sprint rescue / field / latency write-ups |
| `08_predictions_and_emits/unified_55670/T0.7/predictions/*.jsonl` | Live system outputs |
| `08_predictions_and_emits/unified_55670_repaired_20260918/` | Repaired GF emit used in capability rescue |
| `08_predictions_and_emits/capability_debate_local_oracle_20260918/` | Oracle/LLM capability patches |
| `08_predictions_and_emits/clarify_cpc_rescue_20260918/` | Wording/CPC rescue preds |
| `08_predictions_and_emits/latency_1p7b_from_paperpack/` | 1.7B ablation |
| `09_code_contracts/src/.../routing.py` | Prove refuse-first / unauthorized rules |
| `06_cases/CA-0007.md` (and selected cases) | Illustrative narrative |

---

## TIER 2 — Keep on disk (optional / deep verification only)

Do **not** load into context unless chasing a specific dispute.

| Path | Why optional |
|---|---|
| `03_gold_and_metrics/pilot_120_v1/gold_v2_officialization_20260914/**` | Annotator adjudication intermediates (already have official jsonl) |
| `03_gold_and_metrics/pilot_120_v1/cpc_risk_review_20260914/**` | Review scratch |
| `13_intent_judging_and_comparators/gfv2_intent_summary_sgc_packet_20260913/**` | Packet scaffolding; prefer `final_close_20260913` summaries |
| `13_intent_judging_and_comparators/pilot120_semantic_intent_judging_20260908/**` | Historical semantic judging (pre-final-close) |
| `13_intent_judging_and_comparators/base_adapter_sgc_packet_20260911/**` | Older comparator packet |
| `08_predictions_and_emits/unified_55670_live_20260918/**` full tree | All temps; load only the T you discuss |
| `08_predictions_and_emits/unified_55670/mega_*` | Raw/FT mega comparator dumps |
| `06_cases/**` entire folder | 125 cases; sample 3–8, don’t ingest all |
| `10_temperature_and_latency/cluster_latency_pack/**` | Job scripts, not results |
| `11_full_archive_pointer.md` → `research_evidence_package_20260922/` | ~10.6 GiB exhaustive archive outside this zip |

---

## Explicitly NOT necessary for the paper argument

| Item | Reason |
|---|---|
| Grade estimates / rubric | Bias; excluded from Pack A (Pack B only, do-not-cite) |
| Physical robot / ROS / sim success logs | Out of scope; none claimed |
| Rewriting gold | Integrity violation |
| Full raw `data/raw` corpora | Not Pilot-120 evaluation surface |
| Unofficial PEFT adapter weights | Not official comparator |
| Every temperature’s full 4-system preds at once | Pick default T0.7 + cite ablation tables |
| Entire 10 GiB evidence package | Use only if a cited file is missing here |

---

## Ground-up rebuild recipe (if challenged)

1. Inputs: `source_canonical.jsonl` (command, scene, dialogue, capability card).
2. Gold route/capability/ambiguity: `gold/CA-****.json` or `pilot_120_final_gold.jsonl`.
3. Intent refs: `intent_gold_references_120.jsonl`.
4. Sidecars: official CPC / risk / wording jsonl.
5. Predictions: unified T0.7 `goal_first_manager_v2.predictions.jsonl`.
6. Scores: `report_numbers.json` + `sprint_rescue_summary.json` + final-close `*_sgc_summary.json`.
7. Or use the joined file: `pilot120_joined_ground_truth.jsonl` (full) / `_SLIM.jsonl` (context-light).

---

## Size philosophy

- **Zip = warehouse** (have it all handy).
- **Context = workbench** (Tier 0, then open Tier 1 files surgically).
- Prefer JSON numbers over long markdown when space is tight.
"""
    (PACK_A / "DATA_NECESSARY_VS_OPTIONAL.md").write_text(text, encoding="utf-8")


def enrich_protocol_and_freeze() -> dict:
    added = {}
    dest = PACK_A / "03_gold_and_metrics" / "protocol_and_freeze"
    dest.mkdir(parents=True, exist_ok=True)
    # subset manifest + freeze
    pairs = [
        (
            ROOT / "annotations/manual_kappa_v7_final_protocol/subset_manifest.json",
            dest / "subset_manifest.json",
        ),
        (
            ROOT / "data/annotations/pilot_120_v1/frozen/FROZEN_MANIFEST.json",
            dest / "FROZEN_MANIFEST.json",
        ),
        (
            ROOT / "configs/evaluation/pilot_120_v1.json",
            dest / "pilot_120_v1_eval_config.json",
        ),
        (
            ROOT / "configs/annotation/route_precedence_v1.json",
            dest / "route_precedence_v1.json",
        ),
    ]
    # handbook if present
    handbook_candidates = list(
        (ROOT / "annotations/manual_kappa_v7_final_protocol").rglob("handbook*.md")
    ) if (ROOT / "annotations/manual_kappa_v7_final_protocol").exists() else []
    for h in handbook_candidates[:5]:
        pairs.append((h, dest / "briefs" / h.name))

    for src, dst in pairs:
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            added[str(dst.relative_to(PACK_A))] = src.stat().st_size

    # copy key configs tree (small)
    added["configs_evaluation_files"] = copy_tree(
        ROOT / "configs/evaluation", PACK_A / "09_code_contracts" / "configs" / "evaluation"
    )
    added["configs_annotation_files"] = copy_tree(
        ROOT / "configs/annotation", PACK_A / "09_code_contracts" / "configs" / "annotation"
    )
    return added


def patch_start_here() -> None:
    p = PACK_A / "00_START_HERE.md"
    t = p.read_text(encoding="utf-8")
    needle = "## How to use this pack"
    insert = """## Context-window rule (important)
This zip is a **warehouse**. Do **not** load everything into the model context.
1. Read `DATA_NECESSARY_VS_OPTIONAL.md` (Tier 0 / 1 / 2).
2. Prefer `03_gold_and_metrics/pilot120_joined_ground_truth_SLIM.jsonl` for gold lookups.
3. Open full scenes / prediction JSONL only for the specific record_ids you discuss.

"""
    if "DATA_NECESSARY_VS_OPTIONAL.md" not in t:
        if needle in t:
            t = t.replace(needle, insert + needle)
        else:
            t = insert + t
        p.write_text(t, encoding="utf-8")


def refresh_manifest_and_zip() -> dict:
    files = [p for p in PACK_A.rglob("*") if p.is_file() and p.name != "MANIFEST.json"]
    rows = [
        {
            "path": str(p.relative_to(PACK_A)).replace("\\", "/"),
            "bytes": p.stat().st_size,
            "sha256": sha256_file(p),
        }
        for p in sorted(files)
    ]
    summary = {
        "pack": "A_EVIDENCE_FOR_PAPER",
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "total_bytes": sum(r["bytes"] for r in rows),
        "note": "Includes joined ground-truth + necessary-vs-optional load guide",
    }
    (PACK_A / "MANIFEST.json").write_text(
        json.dumps({"summary": summary, "files": rows}, indent=2), encoding="utf-8"
    )
    if OUT_A.exists():
        OUT_A.unlink()
    with zipfile.ZipFile(OUT_A, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(PACK_A.rglob("*")):
            if p.is_file():
                zf.write(p, arcname=str(Path(PACK_A.name) / p.relative_to(PACK_A)).replace("\\", "/"))
        rev = STAGING / "REVIEW_A_EVIDENCE.md"
        if rev.exists():
            zf.write(rev, arcname=f"{PACK_A.name}/_REVIEW/REVIEW_A_EVIDENCE.md")
        guide = PACK_A / "DATA_NECESSARY_VS_OPTIONAL.md"
        # already included via walk
    summary["zip_bytes"] = OUT_A.stat().st_size
    summary["zip_path"] = str(OUT_A)
    (STAGING / "BUILD_SUMMARY_A_DATA_ENRICHED.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main() -> int:
    print("Building joined ground truth...")
    joined = build_joined_ground_truth()
    print("wrote", joined, "bytes", joined.stat().st_size)
    print("Writing load guide...")
    write_load_guide()
    print("Enriching protocol/freeze/configs...")
    added = enrich_protocol_and_freeze()
    print(json.dumps(added, indent=2))
    patch_start_here()
    print("Rezipping Pack A...")
    summary = refresh_manifest_and_zip()
    print(json.dumps(summary, indent=2))
    # mirror guide next to zip for humans
    shutil.copy2(
        PACK_A / "DATA_NECESSARY_VS_OPTIONAL.md",
        ROOT / "outputs" / "PaperWriter_A_DATA_NECESSARY_VS_OPTIONAL_20260922.md",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
