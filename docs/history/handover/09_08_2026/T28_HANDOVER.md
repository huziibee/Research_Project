# T28 full handover — 09 Aug 2026 (refreshed 08 Sep 2026)

**Branch context:** workspace may be on `science/pilot120-t38`; this note covers the
T28 recovery → selection lane and points at later Pilot work.  
**Cluster user / SSH:** `mbangie` via `wits-mscluster`.  
**Preferred nodes:** `mscluster110`, `mscluster111`.  
**Exclude:** `mscluster106,107,108,109` (Apptainer `setgroups` / weak nodes).

---

## Verdict

| Gate | State |
|------|--------|
| Nuclear recovery train (MT 2500) | Done — job **36417** |
| Nuclear full task-conditioned eval | Done — **2234/2234** `VERIFY_PASSED` (job **38789** tail after **36474** SIGKILL) |
| Beats collapsed primary on ambiguity True | Yes (~174 vs 0) |
| Beats base on `ambiguity_present` | **No** (matrix still Clara-heavy `(True,False)=612`) |
| Nuclear adapter promotable | **No** — `technical_smoke_only=true` |
| T28 formally closed (selection + package + clean-load) | **No** |
| T29 | **Do not start** without separate human approval |

Later work (see `T28_PROGRESS_20260809.md`) opened a formal **T28-R6** selectable-candidate train path. R6 routing score beats base on the compatible subset but remains **`adapter_eligible_for_selection=false`** (incomplete safe assemblies on `predict_interpretations_v1`). Early Pilot-120 T31–T38 artifacts exist; they are descriptive only and do not close T28.

---

## 1. Nuclear recovery track (this chat’s closure bar)

### Root cause of primary collapse

Train used `build_inference_time_prompt` + full structured targets; eval used
`build_task_prompt` + compact task JSON (prompt hashes differ). Not a PEFT wiring bug.

### Key jobs

| Job | Name | Result |
|-----|------|--------|
| 30609 / 30610 | early task-cond eval | FAILED ≤1s on `mscluster108` (setgroups) |
| 34267 → 36120 | primary task-cond eval | 2234 `VERIFY_PASSED`; ambiguity True=**0** (collapsed) |
| 36357 / 36366 | amb-only recovery + smoke | smoke **48/48** hard `(True,True)` |
| 36417 | MT nuclear 2500 train | `COMPLETED` on `mscluster111` |
| 36474 | nuclear full eval | `FAILED 0:9` at **2224/2234** |
| **38789** | nuclear eval tail resume | **`COMPLETED`**, **2234/2234**, `VERIFY_PASSED` |

### Canonical paths

```text
Adapter:
  /home-mscluster/mbangie/t12-hpc/runs/t28-recovery/t28-tc-mt-nuclear2500-20260808T164533Z/adapter
  adapter_id: t28-tc-recovery-mt-2500
  technical_smoke_only: true
  selected_adapter: false
  valid_for_official_use: false

Full eval:
  .../t28-tc-mt-nuclear2500-20260808T164533Z/dev_eval_task_conditioned_full_r1/
  status: VERIFY_PASSED
  completed: 2234
  adapter_schema_valid_rate: 1.0
  base_schema_valid_rate: ~0.989
  results_sha256: ae34fbfa493becd3a0aa0346cbf9f7d5d63585b13a18a108edd5df031c1aa395

Ambiguity matrix (base, adapter):
  (False,False)=188  (False,True)=74  (True,False)=612  (True,True)=100
  → adapter True ≈ 174; base True ≈ 712
```

### Success bars (agreed)

1. Beat collapsed primary first → **met**.  
2. Beat base to promote → **not met** on `ambiguity_present`.  
3. Provenance must allow selection → nuclear recovery is **smoke-only / experimental** → **blocked**.

Do **not** promote this nuclear adapter or the original collapsed primary as official.

---

## 2. Ops notes that still matter

- Long evals often die with Slurm **`ExitCode=0:9` (SIGKILL)** with no Python traceback. JSONL is resume-safe: resubmit the **same `--output-dir`**. Progress JSON can stay stale `RUNNING` after the job is dead — trust `sacct` + row counts.
- Eval knobs: `T28_EVAL_EXTRA_ARGS` (`--task-ids`, `--call-ids-file`, `--adapter-scale`, `--max-new-tokens-multiplier`).
- Source sync path used for submissions: `/home-mscluster/mbangie/t28_r5_src`.
- Prefer PowerShell-safe SSH (temp `.sh` / `.py` + `scp`), not bash heredocs.

Quick health check:

```bash
squeue -u mbangie
sacct -j 38789,36417,36474 -o JobID,JobName%22,State,ExitCode,Elapsed,NodeList,End -P
```

---

## 3. What happened after nuclear (selection lane)

Authoritative narrative: `handover/09_08_2026/T28_PROGRESS_20260809.md`.

Short form:

| Item | State |
|------|--------|
| Smoke recovery scored better than base on routing | Provenance blocked (`technical_smoke_only`) → `T28_SELECTION_BLOCKED_PROVENANCE` |
| T28-R6 train config | `configs/model/t28_task_conditioned_full_train_v1.json` (formal candidate path) |
| R6 train | Job **42331** completed |
| R6 full routing eval | Resume **43219** → **2505/2505** `VERIFY_PASSED` |
| R6 hardened score | `.../t28-r6/t28-tc-full-20260811/dev_eval_full_manager_routing_r1/routing_score_r1.json` — `VERIFY_PASSED`, **beats base**, **`adapter_eligible_for_selection=false`** (190/296 full safe assemblies; 146 interpretations `no_json` / max-token digit loops) |
| Decoder-bound v3 smokes | Later diagnostics; selection still not cleared in the progress ledger |
| Pilot-120 direct-base | `direct_base_r4` clean baseline exists (evaluation-only) |
| Early Pilot T31–T33 | Complete under `.../outputs/pilot_120/early_t31_t33_r1/` |
| Early Pilot T36–T38 | Artifacts present under `.../outputs/pilot_120/early_t31_t38_r1/` (`T36_*` / `T37_*` / `T38_*_COMPLETE`) |

R6 score snapshot (cluster, 2026-09-08):

```text
status: VERIFY_PASSED
adapter_beats_base: true
adapter_eligible_for_selection: false
contract_compatible_routing_n: 296
expected_calls / observed_calls: 2505 / 2505
evaluation_results_sha256: caa3c06aaf9cbbfd6f2974b9ae5bf66e997071c26d0cb09d381a397ee830a1df
adapter full_safe_assemblies: 190
base full_safe_assemblies: 6
```

Promotion still requires: full accounting/safety eligibility, package checksum, real clean model load, identical adapter identities in required manager configs, and an evidence ledger. Pilot-120 must not be used to train, tune, or select.

---

## 4. Live cluster snapshot (2026-09-08 ~11:00 UTC+2)

- `squeue -u mbangie`: **empty**
- Nuclear + R6 score artifacts: present as above
- Recent failed jobs (today): `p120-semjudge` **50861** / **50863** (exit **42:0**, ~1–2s; 50863 on excluded-class **mscluster107**), **50868** / **50874** (exit **1:0**, ~7 min on `mscluster112`)
- Last known good semjudge in the recent window: **49107** `COMPLETED` (2026-09-03)
- No T28 nuclear/R6 jobs currently running

---

## 5. Do-not list

1. Do not promote nuclear recovery (`technical_smoke_only`) or collapsed primary.  
2. Do not treat R6 “beats base” alone as selection.  
3. Do not start T29 without separate approval.  
4. Do not train/tune/select from Pilot-120 or early T31–T38 outputs.  
5. Do not schedule long GPU work on `mscluster106–109`.  
6. Do not assume a stale `evaluation_progress.json` means the job is alive.

---

## 6. Recommended next steps (pick one lane)

**Lane A — T28 closeout (selection science)**  
1. Re-read frozen policy `configs/model/t28_frozen_selection_policy_v1.json` against the latest eligible candidate (R6 + decoder-bound path if cleared).  
2. Only if `adapter_eligible_for_selection=true` (or explicit `no_adapter_final_strategy`): package → clean-load → identity attestation → T28 completion note.  
3. Otherwise keep T28 open with a written disqualification / no-adapter decision.

**Lane B — Nuclear evidence packaging (non-promotional)**  
Formal nuclear vs primary vs base metrics packet for the thesis appendix only; do not feed into official selection.

**Lane C — Current Pilot / semjudge firefight**  
Diagnose today’s `p120-semjudge` 50861–50874 failures (node exclude + exit 42/1), then resume that Pilot lane on `110/111`. This does not close T28.

---

## 7. Formal metrics packet (nuclear vs primary vs base)

Non-promotional evidence only. Nuclear adapter remains `technical_smoke_only`.

### Schema-valid rates (2234 calls each)

| Task | n | Primary base | Primary adp | Nuclear base | Nuclear adp |
|------|---|--------------|-------------|--------------|-------------|
| All tasks | 2234 | 0.897 | 0.845 | 0.989 | **1.000** |
| predict_ambiguity_v1 | 974 | 974/974 | 974/974 | 974/974 | 974/974 |
| predict_intent_v1 | 253 | 252/253 | **89/253** (164 `no_json`) | 252/253 | **253/253** |
| predict_interpretations_v1 | 253 | 25/253 (228 `no_json`) | 70/253 (183 `no_json`) | 230/253 | **253/253** |
| predict_cpc_v1 | 253 | 253/253 | 253/253 | 253/253 | 253/253 |
| predict_risk_capability_v1 | 501 | 501/501 | 501/501 | 501/501 | 501/501 |

### `ambiguity_present` True counts (974 ambiguity calls)

| System | True | False | Notes |
|--------|------|-------|-------|
| Base (shared label on nuclear matrix) | **712** | 262 | Reference |
| Collapsed primary adapter | **0** | 974 | Mode collapse; matrix `(True,False)=712`, `(False,False)=262` |
| Nuclear recovery adapter | **174** | 800 | Matrix FF=188, FT=74, TF=612, TT=100 |

Bars: nuclear **beats primary** on ambiguity True (174 ≫ 0) and on schema validity; nuclear **does not beat base** on ambiguity True (174 ≪ 712).

### Artifact digests

```text
Primary eval results_sha256:
  9c1f569392eff377189db6e5f91c1ce57e11800347e323eee995df85bce4fee8
Nuclear eval results_sha256:
  ae34fbfa493becd3a0aa0346cbf9f7d5d63585b13a18a108edd5df031c1aa395
```

---

## Related local docs

- `handover/09_08_2026/T28_PROGRESS_20260809.md` — day-by-day post-nuclear ledger through T36–T38 queue  
- `configs/model/t28_frozen_selection_policy_v1.json`  
- `configs/model/t28_task_conditioned_full_train_v1.json`  
- `scripts/train_t28_task_conditioned_recovery.py`  
- `cluster/t28/t28_task_conditioned_*.sbatch`
