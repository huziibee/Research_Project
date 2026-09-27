# Agent handover — finish the Pilot-120 T0.7 paper table + clarify recovery

**Your job:** watch the GPU jobs, debug if they fail again, score when they finish, and give the user the paper-ready numbers they asked for. Do **not** invent results. Do **not** ask for a cluster password/passphrase (SSH key only). Do **not** overwrite historical T0 or first-turn 83/120.

Updated: 2026-09-23 ~11:20 SAST after missing-file repair + resubmit.

---

## The goal (why this exists)

The paper’s study default is **temperature 0.7**. Two holes remain:

### 1. T0.7 matched six-system table (main paper request)

At T0 we already have official two-judge intent + exact routing for Raw / Fine-Tune / Goal-First. At T0.7 we only have **manager routing** from frozen emits. We do **not** have:

- Raw Qwen official intent + exact route @ T0.7
- Fine-Tune official intent + exact route @ T0.7
- Official two-judge on repaired Goal-First `intent_summary` @ T0.7
- Official two-judge on Context-Blind `intent_summary` @ T0.7

Degree and Timid **share Goal-First’s written intent** — judge GF once, copy that official intent count. Do not pretend three independent generations.

This is a **matched operating-temperature completion**. Historical T0 (Raw 113 / FT 107 / GF 113) stays the completed matched protocol. **No T0.3 anywhere.**

Frozen manager routing (do not re-emit unless corrupt): GF **56**, Degree **57**, Timid **29**, Blind **21**. First-turn capability-rescue exact routing **83/120** is untouched.

### 2. Clarify recoverability (oracle upper bound, separate experiment)

First-turn eval stops at EXECUTE / CLARIFY / REFUSE. We cannot claim a CLARIFY error is “eventually successful.”

For the 22 cases that went repaired-T0.7 REFUSE → post-capability CLARIFY, gold EXECUTE (plus 4 already-CLARIFY extras = 26):

- Replay first-turn as **control**
- Then answer with oracle `I mean: <reference_A_intent_text>` (not naturalistic)
- If the manager CLARIFYs again, repeat that same oracle answer up to **depth 5** and record each hop
- Report recovery to EXECUTE / still CLARIFY / REFUSE, Wilson CI, McNemar vs control

Keep this claim separate from clarification-quality / wording.

---

## Live jobs (resubmitted after file repair)

Preflight on the login node **passed** (repo root + `verify_freeze` n=120).

| Job | Name | Role | Dependency |
|-----|------|------|------------|
| **58441** | `p120-1turn-rec` | Recovery + multi-depth clarify | none (Priority) |
| **58442** | `p120-t07-match` | Raw/FT T0.7 emit + official two-judge + score | `afterany:58441` |

```bash
squeue -u mbangie
sacct -j 58441,58442 --format=JobID,JobName,State,Elapsed,ExitCode,NodeList
tail -f /home-mscluster/mbangie/t12-hpc/logs/p120-1turn-rec-58441.out
tail -f /home-mscluster/mbangie/t12-hpc/logs/p120-t07-match-58442.out
```

Healthy recovery start: CUDA preflight True → `RUN seed=0 condition=control record_id=CA-0012` **without** `pyproject.toml` / `repo_root` crash.

Healthy T0.7 start: `adapter_ok selected=True official=True` → `phase:raw_intent_box_t07` **without** missing `subset_manifest.json`.

If 58441 fails, 58442 will still start (`afterany`) and may also fail. Fix the first error, then resubmit **both** if needed.

---

## What already failed (do not repeat)

| Job | Why | Fix already applied |
|-----|-----|---------------------|
| 57984 | `cuda_required` on mscluster111 | exclude 111; training-site-packages first on PYTHONPATH |
| 58172 | refused official adapter | accept official+selected; no `--allow-unofficial-adapter` when official |
| 58183 | no `pyproject.toml` at lean recovery root | copied from `final_close-20260913` |
| 58184 | T07 root missing `annotations/.../subset_manifest.json` | symlink `final_close` `annotations/` + `pyproject.toml`; `verify_freeze` OK |

---

## Paths

Windows repo: `C:\Users\huzii\Documents\University\Research Project`  
SSH: `wits-mscluster` / `mbangie@146.141.21.100` / key `C:\Users\huzii\.ssh\id_ed25519_wits`  
Partition: `biggpu`, exclusive. Container: `/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif`  
**Never run inference on the login node.**

| | Recovery | T0.7 matched baseline |
|--|----------|------------------------|
| Code | `/home-mscluster/mbangie/t12-hpc/code/pilot120_one_turn_recovery-20260922/` | `/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922/` |
| Out | `.../results/pilot120_one_turn_recovery-20260922/one_turn_recovery_20260922/` | `.../results/pilot120_t07_matched_baseline-20260922/t07_matched_baseline_completion_20260922/` |
| Local freeze | `outputs/one_turn_recovery_20260922/` | `outputs/t07_matched_baseline_completion_20260922/` |
| Script | `scripts/one_turn_recovery_20260922.py` | `evaluate_pilot_120_intent_box.py` + `build_t07_manager_sgc_packet_20260922.py` + `score_t07_matched_baseline_20260922.py` |
| sbatch | `cluster/pilot120_one_turn_recovery_20260922/one_turn_recovery.sbatch` | `cluster/pilot120_t07_matched_baseline_20260922/t07_matched_baseline.sbatch` |

Adapter: `/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/early_pilot_package_excluding_clara1170_v1` (official+selected, scale 0.18).  
Judges: Gemma Judge_A + GLM Judge_B, same final_close five-boolean AND.  
Manager artifacts (frozen, 120 lines each): `$T07/artifacts_t07/*.predictions.jsonl`.

Seed **0**, T=**0.7** for the primary matched table (T0 Raw/FT used seed 20260913 @ T=0.0 — documented mismatch; prompt/schema unchanged). Recovery also runs seed 1 separately (do not pool).

---

## If you must resubmit

```bash
# only if 58441/58442 are not pending/running
bash /tmp/remote_fix_and_resubmit.sh
# or:
#   cluster/pilot120_t07_matched_baseline_20260922/remote_fix_and_resubmit.sh
# (already on cluster as /tmp/remote_fix_and_resubmit.sh)
```

Manual:

```bash
export REC_CODE_ROOT=/home-mscluster/mbangie/t12-hpc/code/pilot120_one_turn_recovery-20260922
export REC_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922
export T07_CODE_ROOT=/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922
export T07_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922
export GFV2_CONTAINER=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif
export GFV2_HF_HOME=/home-mscluster/mbangie/t12-hpc/hf-cache
export GFV2_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-hpc/training-site-packages
export A01_CONTAINER_SIF=/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif
export AFTERANY=0
bash "$REC_CODE_ROOT/cluster/pilot120_one_turn_recovery_20260922/submit.sh"
# then AFTERANY=<new recovery jid>
export AFTERANY=<REC_JID>
export T07_GF_PREDS="$T07_CODE_ROOT/artifacts_t07/goal_first_manager_v2.predictions.jsonl"
export T07_BLIND_PREDS="$T07_CODE_ROOT/artifacts_t07/goal_first_context_blind_v2.predictions.jsonl"
export T07_DEGREE_PREDS="$T07_CODE_ROOT/artifacts_t07/degree_based_router_v2.predictions.jsonl"
export T07_TIMID_PREDS="$T07_CODE_ROOT/artifacts_t07/rich_conservative_manager_v2.predictions.jsonl"
bash "$T07_CODE_ROOT/cluster/pilot120_t07_matched_baseline_20260922/submit.sh"
```

Score if GPU finished but JSON missing:

```bash
python3 "$REC_CODE_ROOT/scripts/one_turn_recovery_20260922.py" score \
  --experiment-dir "$REC_OUTPUT/one_turn_recovery_20260922" --seeds 0 1

python3 "$T07_CODE_ROOT/scripts/score_t07_matched_baseline_20260922.py" \
  --experiment-dir "$T07_OUTPUT/t07_matched_baseline_completion_20260922" \
  --gf-preds "$T07_GF_PREDS" --degree-preds "$T07_DEGREE_PREDS" \
  --timid-preds "$T07_TIMID_PREDS" --blind-preds "$T07_BLIND_PREDS"
```

Package / Windows fetch:

```bash
cd /home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922
tar -czf one_turn_recovery_20260922.tar.gz one_turn_recovery_20260922/
cd /home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922
tar -czf t07_matched_baseline_completion_20260922.tar.gz t07_matched_baseline_completion_20260922/
```

```powershell
scp wits-mscluster:/home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922/one_turn_recovery_20260922.tar.gz "$env:USERPROFILE\Downloads\"
scp wits-mscluster:/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922/t07_matched_baseline_completion_20260922.tar.gz "$env:USERPROFILE\Downloads\"
```

---

## What to return to the user (this is the original ask)

### A. Recovery — from `FINAL_ONE_TURN_RECOVERY_SUMMARY.json`

- Primary 22: recovered EXECUTE / remained CLARIFY / became REFUSE + Wilson 95% CI
- Secondary 26: same
- 3-way transition tables
- Interaction-level one-turn success = `(46 + recovered_among_26) / 76` — **not** routing accuracy
- Seed-0 paired control vs answered + exact McNemar; seed 1 separate
- Depth path: at depth 1…5 where each case landed
- One sentence: oracle upper bound only; not naturalistic; not wording quality

### B. T0.7 table — from `FINAL_T07_MATCHED_BASELINE_SUMMARY.json`

| System | Official intent /120 | Exact routing /120 |
|--------|----------------------|--------------------|
| Raw Qwen | X | X |
| Fine-Tune | X | X |
| Goal-First | X | **56** |
| Degree | X (shared GF intent) | **57** |
| Timid | X (shared GF intent) | **29** |
| Context-Blind | X | **21** |

Paired 2×2 + exact McNemar: Raw vs GF and FT vs GF, for **routing** and **official intent**. Automatic Jaccard is secondary only.

One **descriptive** paragraph only: similar/different vs completed T0 head-to-head; whether GF official intent stays near the direct baselines; whether routing dissociation remains at T0.7. T0 is preserved.

Also give: sbatch paths, job IDs, squeue/sacct, score commands, tar + SCP (above).

---

## Scientific constraints (do not relax)

- Frozen 120 cases, order, context, gold. No gold rewrite, no post-hoc case drop.
- Do not leak gold route / risk / capability / eval labels into model prompts or oracle text.
- Raw/FT stay **direct** intent_box baselines (not Goal-First routed).
- Same official two-judge as `final_close_20260913`. No new judge. No Jaccard as official.
- Failures stay in the /120 denominator.
- Do not pool seeds as new cases.
- No T0.3 in the T0.7 summary.

---

## Read first

1. This file  
2. `scripts/one_turn_recovery_20260922.py`  
3. `scripts/score_t07_matched_baseline_20260922.py`  
4. `cluster/pilot120_one_turn_recovery_20260922/one_turn_recovery.sbatch`  
5. `cluster/pilot120_t07_matched_baseline_20260922/t07_matched_baseline.sbatch`  
6. `outputs/one_turn_recovery_20260922/00_FROZEN_PROTOCOL.md`  
7. `outputs/t07_matched_baseline_completion_20260922/00_PROTOCOL_FREEZE.md`  
8. T0 source of truth: `cluster/final_close_20260913/close.sbatch`  
