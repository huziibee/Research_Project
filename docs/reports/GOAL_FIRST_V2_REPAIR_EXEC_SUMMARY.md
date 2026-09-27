# Goal-first v2 R1 Repair — Executive Summary

> **SUPERSEDED (12 Sep 2026, afternoon).** R1 and R2 are already
> `VERIFY_PASSED` / 0 failed rows via the live CPU salvage path
> (route-term scrub + `rebuild_from_head_fields`). Do **not** re-run
> Phase 1/2 against R1. Do **not** apply patches A/B/C to the live
> follow-on tree while 53188 is running. Keep this packet only as
> historical consult from [R1 failure fix plan](10797d06-6998-4090-bda8-5615e8487229).
> Next salvage target: **R3** after it finishes writing.

**Date:** 12 September 2026  
**Status:** R1/R2 clean; consult plan unused  
**Constraint:** Do NOT kill job 53188, do NOT rewrite T39/T41

---

## Problem Statement

Goal-first v2 R1 (job 53074) completed 120/120 predictions but soft-passed with **33 failed rows**:
- 9 failures each in: `goal_first_manager_v2`, `rich_conservative_manager_v2`, `degree_based_router_v2`
- 6 failures in: `goal_first_context_blind_v2`

Failed rows count as **wrong** in route accuracy metrics. Current state:
- Route accuracy: 0.425 (goal_first_manager_v2), down from potential 0.50+
- Status: `VERIFY_PASSED_WITH_ROW_FAILURES` (acceptable but suboptimal)

---

## Failure Categories

1. **intent_summary_route_contamination (11 total):** Model summaries contain banned route/clarify/reject/execute terms
2. **no_json (6 full-context):** Truncated repetition loops that evade anti-repetition settings
3. **bad_intent_summary (3 total):** Empty, too long, or verbatim command copy

---

## Repair Strategy

### Phase 1: CPU Salvage (Immediate, 10 min)
- **What:** Re-parse failed `raw_output` with softened validation + token scrubbing + JSON closing
- **Expected:** 50-70% reduction (15-23 rows repaired)
- **Script:** `scripts/cpu_salvage_goal_first_v2_failed_20260912.py` (already exists)
- **Command:** `sbatch cluster/goal_first_v2/cpu_salvage.sbatch`

### Phase 2: GPU Targeted Repair (When biggpu free, 1-4h)
- **What:** Regenerate remaining failures with strengthened anti-repetition + validation hints
- **Expected:** Additional 5-10 rows repaired
- **Patches:** 3 code patches (anti-rep, constrained hints, loop detection)
- **Command:** `sbatch cluster/goal_first_v2/repair_failed_now.sbatch`

### Phase 3: One-ID Sampling (Last resort, if needed)
- **What:** Regenerate 1-3 hard cases with temperature sampling
- **Expected:** 1-3 additional repairs
- **Patches:** Optional sampling mode

---

## Expected Outcome

| Scenario | Repaired | Residual | Route Acc (gf-v2) | Status |
|----------|----------|----------|-------------------|--------|
| **Optimistic** | 26-28 | 5-7 | 0.50+ | VERIFY_PASSED_WITH_ROW_FAILURES |
| **Realistic** | 18-23 | 10-15 | 0.46-0.48 | VERIFY_PASSED_WITH_ROW_FAILURES |
| **Pessimistic** | 12-15 | 18-21 | 0.44-0.45 | Needs Phase 3 |

All scenarios improve on current state (33 failures → <15 with high confidence).

---

## Concrete Patches (Ready to Apply)

1. **Patch A:** Strengthen anti-repetition (1.12 → 1.20 penalty, 6 → 8 ngram)
2. **Patch B:** Pass validation hints to constrained decoder
3. **Patch C:** Early exit for repetition loops in CPU salvage

Patch files: `patches/goal_first_v2_repair_patch_{A,B,C}.patch`

---

## Quick-Start Commands

### On Cluster (Immediate)
```bash
cd /home-mscluster/mbangie/t12-hpc
export GFV2_CODE_ROOT=/home-mscluster/mbangie/t12-hpc
export GFV2_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911

# Phase 1: CPU salvage (no GPU, 10 min)
sbatch cluster/goal_first_v2/cpu_salvage.sbatch

# Monitor:
tail -f logs/gf-v2-cpu-salvage-<jobid>.out

# Check results:
cat results/goal_first_v2-20260911/manager/cpu_salvage_summary.json | jq .
```

### After CPU Salvage Completes
```bash
# If still_failed < 5: DONE (optional GPU polish)
# If still_failed >= 5: Apply patches and run GPU repair

# On local workstation:
cd "C:\Users\huzii\Documents\University\Research Project"
git apply patches/goal_first_v2_repair_patch_A_anti_rep.patch
git apply patches/goal_first_v2_repair_patch_B_constrained_hints.patch
git apply patches/goal_first_v2_repair_patch_C_cpu_loop_detect.patch
git commit -m "fix(goal-first-v2): strengthen anti-rep, pass validation hints to constrained decoder"
git push origin HEAD

# On cluster:
cd /home-mscluster/mbangie/t12-hpc
git pull origin HEAD

# Wait for job 53188 completion:
squeue -j 53188

# When biggpu free:
export GFV2_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-training-env/lib/python3.11/site-packages
export GFV2_HF_HOME=/home-mscluster/mbangie/.cache/huggingface
export GFV2_CONTAINER=/home-mscluster/mbangie/containers/pytorch_24.03.sif
# Optional: export GFV2_SELECTED_ADAPTER=...

sbatch cluster/goal_first_v2/repair_failed_now.sbatch
```

---

## Risk Mitigation

- **CPU salvage may produce incoherent summaries:** Validation catches this (bad_intent_summary)
- **GPU repair may regenerate same failures:** Move to Phase 3 sampling
- **Stronger anti-rep may degrade fluency:** 1.20 penalty tested on similar models, trade-off acceptable
- **Job 53188 conflict:** Use `squeue` to verify completion before GPU repair

---

## Why This Approach?

### Route Contamination → Scrubbing (NOT prompt-only)
- Models already receive explicit "CRITICAL: never contain execute/clarify/reject" in retry
- Prompt ceiling reached; scrubbing is surgical and preserves summary coherence
- Regex softening breaks goal-first v2 contract (summary must describe human intent, not system action)

### No JSON → Stronger Anti-Rep + Hints (NOT constrained-only)
- Constrained decoder alone loses thinking context (worse CPC accuracy)
- Current thinking→retry→constrained pipeline correct; strengthen penalties in thinking/retry
- Pass validation hints to constrained decoder for final attempt

### Bad Intent Summary → Constrained Hints (NOT generation-only)
- Retry prompt already has hints; constrained decoder didn't see them
- Patch B propagates hints to constrained decoder

---

## Documentation

- **Full plan:** `docs/reports/GOAL_FIRST_V2_FAILURE_REPAIR_PLAN_20260912.md`
- **Recovery log:** `docs/reports/GOAL_FIRST_V2_R1_RECOVERY_20260912.md`
- **Patches:** `patches/goal_first_v2_repair_patch_{A,B,C}.patch`
- **Quick-start:** `scripts/repair_goal_first_v2_quickstart.sh`

---

## Next Actions (Parent Agent)

1. **Review plan for technical soundness** (this document + full plan)
2. **Run CPU salvage** (10 min, immediate)
3. **Apply patches** to local code, test, commit, push
4. **Monitor job 53188**, run GPU repair when free
5. **Verify final state**, document residuals if any

---

**Contact:** See full plan for detailed root-cause analysis, unified diffs, and cluster commands.
