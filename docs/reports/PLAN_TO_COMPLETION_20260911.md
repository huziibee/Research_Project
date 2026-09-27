# Plan from here to completion — 11 September 2026

Student-facing, thorough, honest. T39/T41 stay frozen.

## Right now (cluster)

| Job | Partition | Role | Dependency |
|---|---|---|---|
| **53074** | biggpu | Goal-first v2 R1 (live analyses) | running ~1.5h; ~29→120 records |
| **53081** | biggpu | R2+R3 then Gemma/GLM natives | `afterok:53074` |
| **53109** | bigbatch | CPU R1 audit (intent fill + hashes) | `afterok:53074` — **queued tonight** |
| **53110** | bigbatch | CPU score R2/R3 + natives | `afterok:53081` — **queued tonight** |

Also done offline/local (not competing for GPU):

- Base vs adapter **SGC judge packet** built and uploaded  
  `outputs/base_adapter_sgc_packet_20260911/` → cluster  
  `.../results/base_adapter_sgc_packet-20260911/`
- Goal-trace **proxy** evidence (base 68 vs adapter 60 / 120)
- CoDraw-iCR **licence verified** CC BY-NC 4.0

**Do not queue more biggpu work** until 53081 finishes. Extra GPU jobs would fight the follow-on.

---

## What “completion” means (three lanes)

Do not mix these in one number.

### Lane A — Early honours / supervisor packet (target for your report)

Closeable without James/Rosman n=300 annotation and without making the adapter official.

Done when:

1. Goal-first v2 R1–R3 hash-frozen and scored  
2. Native ablations (VAGUE/AmbiK/Indirect; CLARA if finished) scored with majority baselines  
3. Early supervisor brief updated with frozen numbers (not counterfactuals alone)  
4. Adapter still labelled provisional / unofficial  
5. Licence claim = T28-R3 internal academic + CoDraw NC verified; other sources unresolved stated honestly  

### Lane B — Official adapter / official T29–T38

Needs:

1. Author clearances for AmbiK, VAGUE, CLARA, IndirectRequests (or supervisor sign-off that thesis stays internal-only forever)  
2. Selection eligibility under frozen T28 policy (R6 failed; needs a real eligible candidate or `no_adapter` strategy)  
3. `selected_identities_v1.json` flip with attestation  
4. Then official freeze programme  

**Not required for Lane A report.**

### Lane C — Full proposal / thesis stretch

Needs supervisors for T13–T15 n=300, T42 new source, Q41 human coding, SafeAgentBench, TEACh substitute narrative. Can stay “future work.”

---

## Phase-by-phase plan

### Phase 0 — While 53074 runs (now → ~tonight)

| Action | Who | Notes |
|---|---|---|
| Monitor progress | you | `progress.json` + `squeue` |
| Do **not** retune prompts | everyone | Locked before scores |
| Optional: draft report skeleton | you | Use counterfactual + T39 as “what we hope / what froze” |
| Optional: send 4 author licence emails | you | AmbiK/VAGUE/CLARA/Indirect packets already drafted |

Already queued: CPU audit + follow-on score.

ETA: R1 ~3 min/record after load → ~4–5h remaining from ~30/120 (order-of-magnitude).

### Phase 1 — When 53074 exits 0:0 (hours)

Automatic:

- **53081** starts R2 then R3 then natives (up to 3 days)  
- **53109** writes `cpu_r1_audit.json` (intent_summary fill, route eval hashes)

You / agent immediately after audit:

1. Confirm `intent_summary` non-null ≈120/120  
2. Read route accuracy for `goal_first_manager_v2` vs `rich_conservative_manager_v2` vs degree  
3. Record false-execute on gold-refuse (must stay ~0)  
4. Hash-freeze R1 tree (sha256 manifests) **before** deep error reading  
5. Update early supervisor brief with R1 only, marked “one replica”

**Do not** change prompts after seeing R1.

### Phase 2 — While 53081 runs (1–3 days)

| Work | Parallel? |
|---|---|
| Write Methods + T39 findings chapter text | yes |
| Licence email chase | yes |
| Build v2 SGC packet from R1 `intent_summary` (CPU) | yes, after R1 freeze |
| Optional: run **base/adapter SGC judges** on uploaded packet | only if a free GPU after 53081, or use offline two-model judge later |
| Do **not** start T43/T44 GPU factorial | blocks / pollutes |

### Phase 3 — When 53081 exits (or times out cleanly)

Automatic: **53110** scores what finished.

Then:

1. Freeze R2/R3 hashes; check replica stability (same spirit as T39 R1–R5)  
2. Score natives vs majority / modal baselines (`score_vague_*`, `score_ambik_*`, `score_native_context`)  
3. If CLARA skipped for time: say so; do not invent  
4. Blind SGC on v2 `intent_summary` (new packet; not the think-trace leftover SGC)  
5. Optional: score `goal_first_v2_goal_licensed` policy as ablation if still not wired into the live job  

### Phase 4 — Early completion packet (Lane A)

Deliverables:

1. Updated `EARLY_SUPERVISOR_BRIEF` with frozen v2 + native tables  
2. One-page “what failed / what we learned” (over-asking → goal-first)  
3. Licence appendix (CoDraw verified; others unresolved; internal T28-R3)  
4. Adapter status page (hash OK, selection blocked, provisional)  
5. Claim boundaries: no physical success; SGC exploratory; Pilot gold ≠ James/Rosman  

**Stop here for the early supervisor meeting** unless they demand Lane B/C.

### Phase 5 — Only if supervisors want official lane

1. Author replies → update register only for granted rights  
2. Selection re-run or document `no_adapter_final_strategy`  
3. Flip `selected_identities_v1` only with human attestation  
4. Start T13–T15 if they will annotate  

---

## Explicit non-goals / do-not list

- Do not rewrite T39/T41  
- Do not fake `valid_for_official_use=true`  
- Do not invent AmbiK/VAGUE/CLARA/Indirect licences  
- Do not mint task success from route correctness  
- Do not queue competing biggpu jobs before 53081 ends  
- Do not use Pilot-120 to select the adapter  

---

## Success criteria cheat-sheet

| Question | Pass look |
|---|---|
| Did v2 fix over-asking? | Gold-execute → execute recall ≫ 0; route-correct ≫ 33/120 |
| Did we keep safety? | False execute on gold-refuse ≈ 0 |
| Was it the router or the prompt? | Compare `goal_first_manager_v2` vs `rich_conservative_manager_v2` on same analyses |
| Reproducible? | R1–R3 close; hashes frozen |
| Natives insightful? | Beats majority baseline on at least one diagnostic, or honest failure |
| Adapter story? | Provisional; proxy goal+route do not favour SFT |

---

## Commands to watch progress

```powershell
ssh wits-mscluster "squeue -u mbangie; echo; cat /home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911/manager/progress.json"
```

```powershell
ssh wits-mscluster "sacct -j 53074,53081,53109,53110 -o JobID,JobName%22,State,ExitCode,Elapsed,End -P"
```

---

## Bottom line

Tonight we queued everything that **safely accelerates** completion without stealing the GPU: CPU R1 audit and CPU follow-on scoring, plus the base/adapter SGC packet ready for later judges.

The critical path is still **53074 → 53081**. After those exit, Lane A (early report) is a few days of freeze/score/write. Lane B (official adapter) and Lane C (full proposal) stay supervisor-gated and are not required to call the early study complete.
