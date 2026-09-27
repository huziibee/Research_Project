# Goal-first v2 R1 Repair Checklist

**Date:** 12 September 2026  
**Operator:** _______________  
**Start time:** _______________  
**End time:** _______________

---

## Pre-Flight Checks

- [ ] Job 53188 (follow-on) status checked: `squeue -j 53188`
  - Status: _______________
- [ ] Current failed count verified: 33 rows (9+9+9+6)
- [ ] Code in sync: `git status` clean on cluster
- [ ] Environment variables set (see Quick-Start section)
- [ ] Cluster login successful: `ssh mscluster-login`

---

## Phase 1: CPU Salvage (Immediate)

**Duration:** ~10 minutes  
**Partition:** bigbatch (CPU only)  
**Risk:** None (read-only model operations)

### Tasks

- [ ] Export environment variables:
  ```bash
  export GFV2_CODE_ROOT=/home-mscluster/mbangie/t12-hpc
  export GFV2_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911
  ```

- [ ] Submit CPU salvage job:
  ```bash
  cd /home-mscluster/mbangie/t12-hpc
  sbatch cluster/goal_first_v2/cpu_salvage.sbatch
  ```
  - Job ID: _______________

- [ ] Monitor job:
  ```bash
  tail -f logs/gf-v2-cpu-salvage-<jobid>.out
  ```
  - Started at: _______________
  - Completed at: _______________
  - Exit code: _______________

- [ ] Check salvage results:
  ```bash
  cat results/goal_first_v2-20260911/manager/cpu_salvage_summary.json | jq .
  ```
  - Repaired counts: _______________
  - Still failed counts: _______________
  - Total residual: _______________

### Decision Point

- [ ] If residual < 5: **SUCCESS** — GPU repair optional, go to Phase 4 (Verify)
- [ ] If residual 5-15: **GOOD** — Proceed to Phase 2 (GPU repair)
- [ ] If residual > 15: **PARTIAL** — Review salvage logs before Phase 2

**Decision:** _______________

---

## Phase 2: Apply GPU Patches (Local Workstation)

**Duration:** ~15 minutes  
**Risk:** Low (patches tested, can revert)

### Tasks

- [ ] Switch to local workstation
- [ ] Pull latest code:
  ```bash
  cd "C:\Users\huzii\Documents\University\Research Project"
  git pull origin main
  ```

- [ ] Apply Patch A (anti-repetition):
  ```bash
  git apply patches/goal_first_v2_repair_patch_A_anti_rep.patch
  ```
  - Status: _______________

- [ ] Apply Patch B (constrained hints):
  ```bash
  git apply patches/goal_first_v2_repair_patch_B_constrained_hints.patch
  ```
  - Status: _______________

- [ ] Apply Patch C (CPU loop detection):
  ```bash
  git apply patches/goal_first_v2_repair_patch_C_cpu_loop_detect.patch
  ```
  - Status: _______________

- [ ] Review changes:
  ```bash
  git diff
  ```
  - Changes look correct: [ ] Yes [ ] No

- [ ] Commit and push:
  ```bash
  git add scripts/evaluate_goal_first_manager_v2.py scripts/cpu_salvage_goal_first_v2_failed_20260912.py
  git commit -m "fix(goal-first-v2): strengthen anti-rep, pass validation hints to constrained decoder"
  git push origin HEAD
  ```
  - Commit SHA: _______________

- [ ] Sync to cluster:
  ```bash
  ssh mscluster-login
  cd /home-mscluster/mbangie/t12-hpc
  git pull origin HEAD
  ```
  - Synced successfully: [ ] Yes [ ] No

---

## Phase 3: GPU Repair (When biggpu Available)

**Duration:** 1-4 hours  
**Partition:** biggpu (exclusive)  
**Risk:** Medium (GPU required, longer runtime)

### Pre-Flight

- [ ] Verify job 53188 complete:
  ```bash
  squeue -j 53188
  ```
  - Status: _______________

- [ ] Check biggpu availability:
  ```bash
  squeue -p biggpu
  ```
  - Available: [ ] Yes [ ] No
  - If no, estimated wait: _______________

### Tasks

- [ ] Set GPU environment variables:
  ```bash
  export GFV2_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-training-env/lib/python3.11/site-packages
  export GFV2_HF_HOME=/home-mscluster/mbangie/.cache/huggingface
  export GFV2_CONTAINER=/home-mscluster/mbangie/containers/pytorch_24.03.sif
  ```

- [ ] Optional: Set adapter if used in original run:
  ```bash
  export GFV2_SELECTED_ADAPTER=...
  export GFV2_ADAPTER_IDENTITY=...
  export GFV2_ADAPTER_SCALE=0.18
  ```
  - Adapter used: [ ] Yes [ ] No
  - Adapter path: _______________

- [ ] Submit GPU repair job:
  ```bash
  sbatch cluster/goal_first_v2/repair_failed_now.sbatch
  ```
  - Job ID: _______________

- [ ] Monitor job:
  ```bash
  tail -f logs/gf-v2-repair-now-<jobid>.out
  ```
  - Started at: _______________
  - GPU memory check passed: [ ] Yes [ ] No
  - Predictions regenerated: _______________
  - Completed at: _______________
  - Exit code: _______________

- [ ] Check repair results:
  ```bash
  cat results/goal_first_v2-20260911/manager/run_manifest.json | jq '{status, row_failure_total}'
  ```
  - Final status: _______________
  - Final failure count: _______________

---

## Phase 4: Verify Final State

**Duration:** ~5 minutes

### Tasks

- [ ] Run verification script:
  ```bash
  python3 scripts/verify_repair_completion.py results/goal_first_v2-20260911/manager
  ```
  - Overall verdict: _______________

- [ ] Review route accuracy per system:
  - goal_first_manager_v2: _______________
  - rich_conservative_manager_v2: _______________
  - degree_based_router_v2: _______________
  - goal_first_context_blind_v2: _______________

- [ ] Compare to initial metrics:
  - Initial route acc (gf-v2): 0.425
  - Final route acc (gf-v2): _______________
  - Improvement: _______________

- [ ] Check manifest status:
  - Status: _______________
  - Row failure total: _______________
  - Acceptable: [ ] Yes [ ] No

### Decision Point

- [ ] If row_failure_total == 0: **COMPLETE** — Mark as VERIFY_PASSED
- [ ] If row_failure_total < 5: **EXCELLENT** — Mark as VERIFY_PASSED_WITH_ROW_FAILURES, document residuals
- [ ] If row_failure_total 5-15: **GOOD** — Mark as VERIFY_PASSED_WITH_ROW_FAILURES, consider Phase 5
- [ ] If row_failure_total > 15: **NEEDS_WORK** — Proceed to Phase 5

**Decision:** _______________

---

## Phase 5: One-ID Sampling (Last Resort, Optional)

**Duration:** 1-2 hours  
**When:** If 1-5 hard cases remain after Phase 3

### Tasks

- [ ] Identify remaining failed IDs:
  ```bash
  cat results/goal_first_v2-20260911/manager/run_manifest.json | \
    jq -r '.row_failures | to_entries[] | "\(.key): \(.value | join(","))"'
  ```
  - Failed IDs: _______________

- [ ] Review failed raws to confirm sampling needed:
  ```bash
  # Check specific prediction file for raw_output field
  cat results/goal_first_v2-20260911/manager/predictions/goal_first_manager_v2.predictions.jsonl | \
    jq -r 'select(.record_id == "CA-XXXX") | .raw_output' | head -200
  ```
  - Review complete: [ ] Yes [ ] No
  - Sampling justified: [ ] Yes [ ] No

- [ ] Apply Phase 3 patches (sampling mode) — see full plan

- [ ] Submit targeted repair:
  ```bash
  export TARGET_IDS="CA-XXXX,CA-YYYY"
  sbatch cluster/goal_first_v2/repair_failed_now.sbatch
  ```
  - Job ID: _______________

- [ ] Verify final state (repeat Phase 4)

---

## Post-Completion

### Documentation

- [ ] Update GOAL_FIRST_V2_R1_RECOVERY_20260912.md with final metrics
- [ ] Save verification output to file:
  ```bash
  python3 scripts/verify_repair_completion.py results/goal_first_v2-20260911/manager > \
    docs/reports/GOAL_FIRST_V2_R1_FINAL_VERIFICATION.txt
  ```

- [ ] Document residual failures (if any) in manifest claim_boundary field
- [ ] Commit final state:
  ```bash
  git add docs/reports/
  git commit -m "docs(goal-first-v2): R1 repair completion — final failure count: <N>"
  git push origin HEAD
  ```

### Notification

- [ ] Notify team of completion
  - Status: _______________
  - Final failure count: _______________
  - Route accuracy improvement: _______________

- [ ] Update project board / ticket status

---

## Rollback Procedure (If Needed)

**Use only if GPU repair produces worse results than CPU salvage.**

- [ ] Restore CPU salvage state:
  ```bash
  cd results/goal_first_v2-20260911/manager
  # Backup current state
  cp run_manifest.json run_manifest.json.gpu_attempt
  for f in predictions/*.jsonl; do cp "$f" "$f.gpu_attempt"; done
  
  # Restore from CPU salvage backup (if created)
  # Or re-run CPU salvage with --diagnose-only flag first
  ```

- [ ] Verify rollback:
  ```bash
  python3 scripts/verify_repair_completion.py results/goal_first_v2-20260911/manager
  ```

- [ ] Document rollback reason in recovery log

---

## Notes / Issues Encountered

_______________________________________________________________________________

_______________________________________________________________________________

_______________________________________________________________________________

_______________________________________________________________________________

---

## Sign-Off

- [ ] Repair complete and verified
- [ ] Documentation updated
- [ ] Final metrics acceptable for claim boundary
- [ ] No outstanding issues

**Operator signature:** _______________  
**Date:** _______________
