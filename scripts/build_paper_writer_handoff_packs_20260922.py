#!/usr/bin/env python3
"""Build two paper-writer handoff packs (evidence + framing).

Pack A = factual evidence only (minimal framing bias).
Pack B = ideas, narrative guardrails, lessons learned.
"""
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
PACK_B = STAGING / "B_FRAMING_AND_IDEAS"
OUT_A = ROOT / "outputs" / "PaperWriter_A_EVIDENCE_COMPLETE_20260922.zip"
OUT_B = ROOT / "outputs" / "PaperWriter_B_FRAMING_IDEAS_20260922.zip"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_tree(src: Path, dst: Path, *, ignore_names: set[str] | None = None) -> int:
    ignore_names = ignore_names or set()
    n = 0
    if not src.exists():
        return 0
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return 1
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        if any(part in ignore_names for part in p.parts):
            continue
        if p.name.endswith(".pyc") or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        n += 1
    return n


def copy_file(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.lstrip("\n") if text.startswith("\n") else text, encoding="utf-8")


def zip_dir(src: Path, out_zip: Path) -> None:
    if out_zip.exists():
        out_zip.unlink()
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                zf.write(p, arcname=str(Path(src.name) / p.relative_to(src)).replace("\\", "/"))


def build_pack_a() -> dict:
    if PACK_A.exists():
        shutil.rmtree(PACK_A)
    PACK_A.mkdir(parents=True)

    counts: dict[str, int] = {}
    missing: list[str] = []

    # --- START HERE (neutral) ---
    write_text(
        PACK_A / "00_START_HERE.md",
        f"""# Pack A — Evidence for research paper writing

**Built:** {datetime.now(timezone.utc).isoformat()}
**Purpose:** Give a paper-writing model *full factual context* for an honours research report on a risk-aware ambiguity manager for compound ambiguous robot commands (Pilot-120).

## How to use this pack
1. Read `01_scope_and_boundaries.md` first.
2. Read methodology in `02_protocol_and_systems/`.
3. Use gold + metrics in `03_gold_and_metrics/` and `07_numbers_json/`.
4. Use results narratives in `04_results_narrative/` and mechanism audits in `05_mechanism_audits/`.
5. Cite cases from `06_cases/` when illustrating.
6. Predictions / emits live in `08_predictions_and_emits/`.
7. Code contracts (router, analysis schema) in `09_code_contracts/`.
8. Temperature + small-model latency in `10_temperature_and_latency/`.
9. For the exhaustive archival dump of *every* project file (~10 GiB, 49 split archives), see pointer file `11_full_archive_pointer.md` (not duplicated inside this zip).

## Neutrality rules for the writer (from this pack)
- Prefer **numbers from JSON/score files** over prose claims.
- Treat rejected hypotheses and negative results as first-class evidence.
- Do **not** invent robot/sim task-success results; planner is out of scope.
- Do **not** rewrite gold labels.
- Grade/mark estimates and cheerleading are **excluded** from this pack on purpose (see Pack B if needed for framing only).

## Project identity
- Student: Mohammed Bangie (2610990)
- Programme: Honours, Wits CSAM
- Core dataset: Pilot-120 compound ambiguous commands
""",
    )

    write_text(
        PACK_A / "01_scope_and_boundaries.md",
        """# Scope and scientific boundaries

## In scope
- Compound ambiguous natural-language robot *commands* (text + scene + dialogue + capability card).
- Write-then-route ambiguity manager (intent_summary → deterministic route: execute / clarify / refuse).
- Evaluation on Pilot-120: intent correctness (two-judge + automatic overlap), routing, risk/capability/CPC/ambiguity/wording sidecars.
- Policy ablations with shared analysis (goal-first / degree / timid / context-blind).
- Capability-calibration interventions on frozen analysis (oracle + LLM patch).
- Small-model latency ablation (Qwen3-1.7B @ T=0.7, thinking-on, matched protocol).

## Out of scope (do not claim)
- Physical robot execution, ROS, simulation task success.
- Planner / action grounding beyond route label + textual capability card.
- Officialising unofficial PEFT fine-tune adapters.
- Rewriting Pilot-120 gold to improve scores.

## Measurement priorities (factual)
- Primary scientific claim area in this project: **intent writing quality** under compound ambiguity, plus characterisation of **intent–policy dissociation** when routing fails despite good intent.
- Routing correctness is measured but often **fails** for goal-first vs historical raw; treat mechanism (capability miscalibration) as the finding when claiming contribution.
""",
    )

    # Protocol / systems
    dest = PACK_A / "02_protocol_and_systems"
    for name in [
        "latest results/05-methodology.md",
        "latest results/04-research-question.md",
        "latest results/03-problem-background.md",
        "latest results/02-introduction.md",
        "latest results/glossary.md",
        "latest results/00-how-to-read.md",
        "results/01-primary-question.md",
        "results/01b-the-six-systems.md",
        "results/02-what-we-are-measuring.md",
        "results/17-experiment-map.md",
        "README.md",
    ]:
        ok = copy_file(ROOT / name, dest / Path(name).name)
        if not ok:
            missing.append(name)
    counts["protocol_files"] = sum(1 for _ in dest.rglob("*") if _.is_file())

    # Gold
    gold_dest = PACK_A / "03_gold_and_metrics" / "pilot_120_v1"
    n = copy_tree(ROOT / "data/annotations/pilot_120_v1", gold_dest, ignore_names={"raw"})
    counts["gold_files"] = n
    # Intent refs
    refs = (
        ROOT
        / "pilot120_intent_evaluation_20260902"
        / "pilot120_intent_evaluation_20260902"
        / "validation"
        / "self_contained_rebuild"
        / "data"
        / "intent_gold_references_120.jsonl"
    )
    if not copy_file(refs, PACK_A / "03_gold_and_metrics" / "intent_gold_references_120.jsonl"):
        alt = ROOT / "data/annotations/pilot_120_v1/intent_gold_references_120.jsonl"
        if not copy_file(alt, PACK_A / "03_gold_and_metrics" / "intent_gold_references_120.jsonl"):
            missing.append("intent_gold_references_120.jsonl")
    copy_file(
        ROOT / "pilot120_t41_complete_closure/final_t41/pilot120_interpretation_gold_final.jsonl",
        PACK_A / "03_gold_and_metrics" / "pilot120_interpretation_gold_final.jsonl",
    )

    # Results narrative (exclude grade-estimate, rubric)
    narr = PACK_A / "04_results_narrative"
    for name in [
        "01-abstract.md",
        "06-results.md",
        "07-conclusion.md",
        "08-references.md",
        "10-cluster-results-status.md",
        "11-temperature-evidence-brief.md",
        "12-capability-rescue-paper-note.md",
        # 13 highlights is framing-ish; still factual numbers — include but writer should treat as summary not cheerleading
        "13-paper-contribution-highlights.md",
        "99-work-state-checkpoint.md",
    ]:
        copy_file(ROOT / "latest results" / name, narr / name)

    # Mechanism audits
    mech = PACK_A / "05_mechanism_audits"
    for name in [
        "00-start-here.md",
        "03-replicas.md",
        "04-the-62-overasks.md",
        "05-who-understood.md",
        "06-the-eight-writing-misses.md",
        "07-secondary-metrics.md",
        "09-verdict.md",
        "10-capability-audit.md",
        "11-ambiguity-why-so-low.md",
        "15-the-10-unsafe.md",
        "16-hole-plugs.md",
        "18-why-wording-and-cpc-look-tiny.md",
        "19-sprint-rescue-capability-ambiguity-20260918.md",
        "20-field-rescue-audit-20260918.md",
        "21-clarify-cpc-latency-20260918.md",
        "22-early-8b-vs-1p7b-T0.7.md",
        "README.md",
    ]:
        if not copy_file(ROOT / "results" / name, mech / name):
            missing.append(f"results/{name}")

    # Cases
    counts["case_files"] = copy_tree(ROOT / "results/cases", PACK_A / "06_cases")

    # Numbers JSON
    num = PACK_A / "07_numbers_json"
    for src in [
        ROOT / "outputs/sprint_rescue_20260918/sprint_rescue_summary.json",
        ROOT / "outputs/sprint_rescue_20260918/repaired_T0.7/sprint_rescue_summary.json",
        ROOT / "outputs/sprint_rescue_20260918/early_8b_vs_1p7b_T0.7.json",
        ROOT / "outputs/sprint_rescue_20260918/ambiguity_audit.json",
        ROOT / "outputs/sprint_rescue_20260918/historical_dissociation_62_ids.json",
        ROOT / "outputs/clarify_cpc_rescue_20260918/clarify_cpc_rescue_summary.json",
        ROOT / "outputs/clarify_cpc_rescue_20260918/wording_row_detail.json",
        ROOT / "outputs/field_rescue_audit_20260918/field_rescue_summary.json",
        ROOT / "outputs/capability_debate_local_oracle_20260918/oracle_gold_summary.json",
        ROOT / "outputs/capability_debate_local_oracle_20260918/llm_capability_summary.json",
        ROOT / "outputs/capability_debate_local_oracle_20260918/capability_judge_summary.json",
        ROOT / "outputs/capability_debate_local_oracle_20260918/ambiguity_debate_summary.json",
    ]:
        if not copy_file(src, num / src.name):
            # keep nested names unique
            if src.exists():
                copy_file(src, num / f"{src.parent.name}__{src.name}")
            else:
                missing.append(str(src.relative_to(ROOT)))
    # unified report numbers if present
    for cand in [
        ROOT / "outputs/cluster_pulls/unified_55670/report_numbers.json",
        ROOT / "outputs/cluster_pulls/unified_55670/EVIDENCE_BRIEF.md",
        ROOT / "outputs/cluster_pulls/unified_55670_repaired_20260918/report_numbers.json",
    ]:
        if cand.exists():
            copy_file(cand, num / cand.name)

    # Predictions / emits
    pred = PACK_A / "08_predictions_and_emits"
    counts["preds_repaired_t07"] = copy_tree(
        ROOT / "outputs/cluster_pulls/unified_55670_repaired_20260918",
        pred / "unified_55670_repaired_20260918",
    )
    counts["preds_unified"] = copy_tree(
        ROOT / "outputs/cluster_pulls/unified_55670",
        pred / "unified_55670",
        ignore_names=set(),
    )
    counts["preds_live_temps"] = copy_tree(
        ROOT / "outputs/cluster_pulls/unified_55670_live_20260918",
        pred / "unified_55670_live_20260918",
    )
    # Note: repaired folder may only contain goal_first predictions; live/unified hold full 4-system emits.
    write_text(
        pred / "README_PREDICTIONS.md",
        """# Predictions layout

- `unified_55670_repaired_20260918/T0.7/predictions/` — repaired goal-first rows used in capability-rescue analyses (may be GF-only).
- `unified_55670/T0.7/` — full four-system emit + evaluations + sidecars at default temperature.
- `unified_55670_live_20260918/` — temperature sweep / unified live tree (T0.0–T1.0 family).
- `clarify_cpc_rescue_20260918/` — wording/CPC CPU rescue preds.
- `capability_debate_local_oracle_20260918/` — capability judge/oracle/reroute artifacts.
- `latency_1p7b_from_paperpack/` — Qwen3-1.7B @ T0.7 latency ablation (from earlier paper pack zip).
""",
    )
    counts["preds_clarify"] = copy_tree(
        ROOT / "outputs/clarify_cpc_rescue_20260918",
        pred / "clarify_cpc_rescue_20260918",
    )
    counts["preds_cap_debate"] = copy_tree(
        ROOT / "outputs/capability_debate_local_oracle_20260918",
        pred / "capability_debate_local_oracle_20260918",
    )
    # 1.7B from existing small paper pack or extract
    zip_1p7 = ROOT / "outputs/Pilot120_PaperPack_1p7b_latency_20260918.zip"
    if zip_1p7.exists():
        extract = pred / "latency_1p7b_from_paperpack"
        extract.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_1p7, "r") as zf:
            zf.extractall(extract)
        counts["preds_1p7b_pack"] = sum(1 for _ in extract.rglob("*") if _.is_file())
    else:
        missing.append("outputs/Pilot120_PaperPack_1p7b_latency_20260918.zip")

    # Code contracts
    code = PACK_A / "09_code_contracts"
    for rel in [
        "src/ambiguity_manager/systems/routing.py",
        "src/ambiguity_manager/systems/goal_first_analysis_v2.py",
        "src/ambiguity_manager/systems/response_generation.py",
        "src/ambiguity_manager/systems/manager.py",
        "src/ambiguity_manager/systems/contracts.py",
        "src/ambiguity_manager/systems/variants.py",
        "configs/annotation/route_precedence_v1.json",
        "configs/evaluation/pilot_120_v1.json",
        "scripts/evaluate_goal_first_manager_v2.py",
        "scripts/reroute_patched_capability_20260918.py",
        "scripts/run_capability_llm_judge_20260918.py",
        "scripts/clarify_cpc_rescue_20260918.py",
        "scripts/sprint_capability_ambiguity_rescue_20260918.py",
        "scripts/field_rescue_audit_20260918.py",
        "scripts/run_early_8b_vs_1p7b_local.py",
    ]:
        if not copy_file(ROOT / rel, code / rel):
            missing.append(rel)

    # Temperature + latency docs already partly in narrative; add cluster pack readme
    temp = PACK_A / "10_temperature_and_latency"
    copy_file(ROOT / "latest results/11-temperature-evidence-brief.md", temp / "11-temperature-evidence-brief.md")
    copy_file(ROOT / "results/22-early-8b-vs-1p7b-T0.7.md", temp / "22-early-8b-vs-1p7b-T0.7.md")
    copy_file(ROOT / "outputs/sprint_rescue_20260918/early_8b_vs_1p7b_T0.7.json", temp / "early_8b_vs_1p7b_T0.7.json")
    copy_tree(ROOT / "cluster/pilot120_latency_small_20260918", temp / "cluster_latency_pack")

    write_text(
        PACK_A / "11_full_archive_pointer.md",
        """# Pointer to exhaustive archive (not embedded)

A separate evidence-preserving transport package already exists:

`research_evidence_package_20260922/`

- ~10.6 GiB across 49 split ZIPs under `archives/` and `transfer/`
- 16k+ source files with SHA-256 inventory
- Read `research_evidence_package_20260922/README.md` and `documentation/STATUS_LEDGER.md` before treating any archived claim as independently verified.

This Pack A is the **paper-writer working set**. Use the full archive only if you need a file not present here.
""",
    )

    # Context checkpoint
    copy_file(
        ROOT / "context/pilot120-stable-checkpoint-20260915.md",
        PACK_A / "12_context_checkpoint/pilot120-stable-checkpoint-20260915.md",
    )

    # Manifest
    files = [p for p in PACK_A.rglob("*") if p.is_file()]
    manifest_rows = []
    for p in sorted(files):
        rel = str(p.relative_to(PACK_A)).replace("\\", "/")
        manifest_rows.append(
            {
                "path": rel,
                "bytes": p.stat().st_size,
                "sha256": sha256_file(p),
            }
        )
    summary = {
        "pack": "A_EVIDENCE_FOR_PAPER",
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "total_bytes": sum(r["bytes"] for r in manifest_rows),
        "counts": counts,
        "missing_sources": missing,
        "excluded_on_purpose": [
            "latest results/grade-estimate.md",
            "latest results/rubric.md",
            "cheerleading / mark forecasting",
        ],
    }
    write_text(PACK_A / "MANIFEST.json", json.dumps({"summary": summary, "files": manifest_rows}, indent=2))
    write_text(PACK_A / "MISSING_SOURCES.json", json.dumps(missing, indent=2))
    return summary


def build_pack_b() -> dict:
    if PACK_B.exists():
        shutil.rmtree(PACK_B)
    PACK_B.mkdir(parents=True)

    write_text(
        PACK_B / "00_START_HERE.md",
        f"""# Pack B — Framing, ideas, and path-correction context

**Built:** {datetime.now(timezone.utc).isoformat()}
**Purpose:** Help a paper-writing model stay on the *scientifically correct narrative path*. This pack is opinionated by design. Prefer Pack A numbers if Pack B prose conflicts.

## When to open this pack
- Choosing research questions / contribution claims
- Deciding what is primary vs secondary vs limitation
- Avoiding wrong emphases (e.g. “we beat raw on routing”)
- Speeding recovery if the draft drifts

## Pack relationship
- **Pack A** = evidence (prefer for all numeric claims)
- **Pack B** = guidance (prefer for structure and anti-patterns)
""",
    )

    write_text(
        PACK_B / "01_core_contribution_claim.md",
        """# Core contribution claim (defendable)

**One-sentence claim:**
Under compound ambiguity, high-quality intent writing is not enough for correct robot handling decisions; correcting capability calibration — holding intent fixed — recovers most of the routing gap, establishing **intent–policy dissociation** as a central issue for risk-aware ambiguity managers.

## What “good enough for honours” looks like
- Strong absolute intent performance + honest negative routing results + mechanism ablation
- Not SOTA robot autonomy
- Not “our manager beats raw on understanding” as the lead (H1 was a tie at official T0 two-judge)

## Primary vs secondary story
1. **Primary:** write-then-route intent quality + dissociation + capability mechanism (56→83 LLM / 87 oracle; false refuse 39→4)
2. **Secondary:** ambiguity soft-F1 lift under constrained Pilot-17; clarification wording after scene harvest; CPC coerce; temperature line; 8B vs 1.7B latency–accuracy
3. **Limitations:** wording residual, CPC still weak, no embodied planner, ~70–116 s/cmd latency class
""",
    )

    write_text(
        PACK_B / "02_metric_priority_and_wrong_paths.md",
        """# Metric priority and wrong paths

## Prioritize (in order)
1. Intent correctness (two-judge where available; automatic overlap screen otherwise)
2. Intent–policy dissociation characterisation (intent-yes ∩ route-no slab)
3. Capability / unauthorized mechanism + frozen-intent patch ablations
4. Shared-analysis policy ablations (goal-first / degree / timid)
5. Risk stratification (honest: risk-oracle alone does not rescue routing)
6. Temperature sensitivity (intent high; refuse-first routing flat / worse at high T)
7. Latency vs size (8B ~116s vs 1.7B ~73s; intent 118→113; routing 56→26)
8. Ambiguity tagging (in-vocab; soft F1; exact-set hard)
9. Clarification wording / CPC (improved but still limited)

## Do NOT make these the lead claim
- “We win on routing vs raw” (data rejects for goal-first emit)
- “Ambiguity exact-set solved”
- “Clarification wording solved” without pairing with ask-route coverage
- “Deployable real robot stack”
- “Risk-aware routing works” without the capability caveat
- Treating H1/H2 rejects as project failure — they are findings if mechanism is clear

## Common draft drift → correction
| Drift | Correction |
|---|---|
| Focus on routing correctness as success metric | Focus on intent + dissociation + capability calibration |
| Hide negative results | Lead with honest negatives + mechanism |
| Overclaim embodiment | Explicitly defer planner/robot |
| Sell 1.7B as better overall | Sell Pareto: faster, intent mostly holds, policy collapses |
| Claim risk fix | Show risk-oracle can hurt; capability is the bottleneck |
""",
    )

    write_text(
        PACK_B / "03_suggested_paper_spine.md",
        """# Suggested paper spine (honours)

1. **Introduction:** compound ambiguous commands; robots need job understanding *and* handling decision.
2. **Background:** ambiguity in HRI / instruction following; gap = decision layer under risk/capability.
3. **RQ:**
   - RQ1: Does write-then-route improve / achieve strong intent correctness?
   - RQ2: Holding analysis fixed, does risk/capability-aware policy improve handling path?
   - RQ3: Where do residual errors concentrate?
4. **Method:** Pilot-120; six systems; metrics; shared-analysis ablations; capability patch protocol; latency ablation.
5. **Results:** intent strong; routing weak; dissociation slab; capability patch deltas; temperature; 1.7B Pareto; wording/CPC secondary.
6. **Discussion:** dissociation; implications for robot handoff gates; limitations.
7. **Conclusion:** contribution + future work (planner, better capability module, latency).

Paste-ready factual paragraphs live in Pack A under `04_results_narrative/12-capability-rescue-paper-note.md` — verify numbers against Pack A JSON before finalising.
""",
    )

    write_text(
        PACK_B / "04_ideas_and_nuances.md",
        """# Ideas and nuances worth using

- **Intent–policy dissociation** as named phenomenon (62-slab historically; recomputed on repaired emits).
- **Same writing, different buttons:** degree/timid/goal-first share analysis JSON.
- **Unauthorized-at-low-risk** refuse gate as concrete bug class (10 rows).
- **False refuse vs false execute** safety trade-off table across systems.
- **Ask ≠ ask well:** route can be ask while wording templates fail; scene harvest rescues wording when asks happen.
- **Ambiguity in-vocab ≠ correct set:** soft F1 story; action_order binge then prompt fix.
- **Small model:** understanding vs decision calibration diverge further at 1.7B.
- **Future robot path:** improve capability labelling module before planner; do not pretend planner exists.
""",
    )

    write_text(
        PACK_B / "05_key_numbers_cheat_sheet.md",
        """# Key numbers cheat-sheet (verify in Pack A JSON before citing)

## 8B goal-first (repaired / study T0.7 family)
- Intent auto ~117–118/120; official two-judge at T0 historically 113/120 (tie with raw)
- Routing emit ~54–56/120; historical raw routing higher (~88 at T0) — do not claim GF routing win
- Capability patch: routing 56→83 (LLM) / 87 (oracle); false refuse 39→4→0; dissociation 63→37→33
- Wording with LLM-cap + scene harvest: 0→16/23
- CPC F1: ~0.113→0.180 after status coerce
- Latency 8B: ~116 s/cmd mean

## 1.7B @ T0.7 (thinking-on, repaired)
- Intent auto: 113/120
- Routing: 26/120
- Executes: 0
- Latency: ~73 s/cmd mean
- Remaining GF schema fails after repair: 1

If Pack A JSON disagrees with this sheet, **trust Pack A JSON**.
""",
    )

    # Include framing docs from project
    for name in [
        "latest results/13-paper-contribution-highlights.md",
        "latest results/12-capability-rescue-paper-note.md",
        "latest results/grade-estimate.md",
        "latest results/rubric.md",
        "results/09-verdict.md",
        "results/12-proposal-metrics.md",
    ]:
        copy_file(ROOT / name, PACK_B / "06_source_framing_docs" / Path(name).name)

    write_text(
        PACK_B / "07_anti_bias_note.md",
        """# Anti-bias note

Pack B contains grade estimates and contribution framing that can bias a writer toward overclaiming.

**Rule:** Any evaluative claim in Pack B must be checked against Pack A numeric artifacts. If uncertain, write the more conservative claim and put ambition in Future Work.
""",
    )

    files = [p for p in PACK_B.rglob("*") if p.is_file()]
    manifest_rows = [
        {"path": str(p.relative_to(PACK_B)).replace("\\", "/"), "bytes": p.stat().st_size, "sha256": sha256_file(p)}
        for p in sorted(files)
    ]
    summary = {
        "pack": "B_FRAMING_AND_IDEAS",
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "total_bytes": sum(r["bytes"] for r in manifest_rows),
    }
    write_text(PACK_B / "MANIFEST.json", json.dumps({"summary": summary, "files": manifest_rows}, indent=2))
    return summary


def main() -> int:
    STAGING.mkdir(parents=True, exist_ok=True)
    print("Building Pack A...")
    sa = build_pack_a()
    print(json.dumps(sa, indent=2))
    print("Building Pack B...")
    sb = build_pack_b()
    print(json.dumps(sb, indent=2))
    print("Zipping...")
    zip_dir(PACK_A, OUT_A)
    zip_dir(PACK_B, OUT_B)
    write_text(
        STAGING / "BUILD_SUMMARY.json",
        json.dumps(
            {
                "pack_a_zip": str(OUT_A),
                "pack_b_zip": str(OUT_B),
                "pack_a": sa,
                "pack_b": sb,
                "pack_a_zip_bytes": OUT_A.stat().st_size,
                "pack_b_zip_bytes": OUT_B.stat().st_size,
            },
            indent=2,
        ),
    )
    print("DONE", OUT_A, OUT_A.stat().st_size, OUT_B, OUT_B.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
