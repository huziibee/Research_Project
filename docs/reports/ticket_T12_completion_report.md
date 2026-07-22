# T12 Completion Report — Cluster Model Stack

**Ticket:** T12
**Branch:** `feature/t12-cluster-redesign`
**Terminal ADR:** `docs/decisions/ADR_T12_terminal_zero_shot_candidate_rejection.md`
**Final D-Final evidence:** `configs/model/evidence/t12_d_final_live_smoke_final.json`
**Operator canary evidence:** `configs/cluster/evidence/t12_cluster_operator_canary.json`

## Verified technical outcomes

- Immutable source packaging (`git archive` + source-identity manifest)
- SSH BatchMode transfer and remote archive hash verification
- Slurm submission (`sbatch --parsable`)
- Scheduler monitoring (`squeue` → `sacct` fallback)
- Result polling without automatic cancellation
- Result retrieval into `outputs/t12_cluster_jobs/<run-id>/pulled/`
- Independent manifest verification (SHA-256, sizes, JSONL counts)
- Offline model snapshot and pinned Apptainer container (historical Stages B–C)
- Persistent vLLM engine and structured-output transport (Stage D path)
- Strict semantic and safety rejection with complete negative evidence retention
- Local Slurm operator (`run` / `status` / `poll` / `pull` / `verify`) proven by
  CPU canary job **4122**

## Terminal candidate outcome

- Qwen3-8B is unsuitable as the zero-shot candidate under the frozen T12
  structured-output and safety contract
- Final D-Final job **3998**: **3/4** accepted; `dfinal-004` failed three times
  on `unsupported_silent_commitment`
- Stop rule triggered; no further D-Final corrections authorised
- `selected_model` remains `null`
- Terminal outcome: `candidate_rejected` / `NO_SELECTION`
- Do **not** call the D-Final correctness gate a PASS

## Deferred work

- **E-Minimal:** deferred until a viable future model/prompt strategy exists
- **LoRA feasibility:** deferred to a later model/training strategy ticket
- **Performance benchmarking:** deferred until a viable candidate is selected
- **Publication automation:** deferred as non-essential engineering

## T12 final state

| Field | Value |
|---|---|
| `ticket_status` | COMPLETE |
| `technical_stack_status` | PASS |
| `candidate_selection_status` | NO_SELECTION |
| `terminal_candidate_outcome` | candidate_rejected |
| `selected_model` | null |
| `next_active_ticket` | T13 |

T13 may begin preparation (handbook, sampling freeze, pilot tooling). T14 tooling
may be implemented while supervisors are unavailable. No T13/T14 human annotation
or adjudication was executed under this close-out.
