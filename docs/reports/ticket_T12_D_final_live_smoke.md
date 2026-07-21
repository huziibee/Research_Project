# T12 Stage D-Final — Live Structured Generation Smoke (BLOCKED)

**Ticket:** T12
**Stage:** D-Final live smoke
**Measurement timestamp:** 2026-07-21T09:13:06Z
**Authority:** DEV-20260721-001 (T11 `PASS` / ethics `not_required`)
**Status:** BLOCKED — bounded regeneration exhausted on all four synthetic records

## 1. Scope

Live D-Final smoke from commit `02f43622b2db90a7e5ed2662a48a0752a9a0e8cc` (`feat(t11): record supervisor-only ethics determination as not required`). Includes committed response-mode transport/semantic separation. Synthetic-only; no protected or research-pool data.

## 2. Source transfer

| Field | Value |
|---|---|
| Commit | `02f43622b2db90a7e5ed2662a48a0752a9a0e8cc` |
| Archive | `t12-02f4362.tar.gz` |
| Archive SHA-256 | `ecedefa30a1e358f9fea55da8105543e1445e1794f4617ec3a94327e5292fe6f` |
| Archive bytes | 228505097 |
| Transfer | `git_archive` |
| Packaging timestamp | 2026-07-21T09:08:58Z |

Packaged source confirmed T11 `not_required` determination and transport-only response-mode probe policy. Cluster recomputed archive hash matched.

## 3. Run identity (job 3974)

| Field | Value |
|---|---|
| Run ID | `stage-d-final-live-20260721T091036Z-02f4362` |
| Prep | `${T12_CLUSTER_ROOT}/runs/stage-d-final/.prep-stage-d-final-live-20260721T091036Z-02f4362` |
| Run dir | `${T12_CLUSTER_ROOT}/runs/stage-d-final/stage-d-final-live-20260721T091036Z-02f4362` |
| Slurm job | 3974 |
| Partition | `biggpu` (exclusive) |
| Node | `mscluster112` (idle Blackwell allowlist; not a permanent pin) |
| GPU | NVIDIA RTX PRO 6000 Blackwell Workstation Edition |
| VRAM | 97887 MiB |
| Compute capability | 12.0 |
| Driver | 595.71.05 |
| Slurm log | `${T12_CLUSTER_ROOT}/logs/t12-d-final-live-3974.out` |

Committed CLI `scripts/t12_run_d_final_smoke.py` executed unchanged. No cluster source patch.

## 4. Gates passed

| Gate | Result |
|---|---|
| SSH BatchMode | pass |
| Archive verification | pass |
| Full SIF SHA-256 | pass (`d404bdf4…`, elapsed 31.568 s) |
| Nested cluster preflight | pass (`status=pass`) |
| Offline snapshot inventory | pass (15 files / 16397461266 bytes; `network_fallback=false`) |
| Runtime settings | matched pinned contract |
| Repository-artefact preload | pass (extracted source root) |
| Structured-output construction | pass (`constructed`) |
| vLLM engine start | pass (exactly once) |
| Response-mode transport selection | pass (`enable_thinking_false`) |

## 5. Response-mode probes

Frozen order: `default` → `enable_thinking_false`. Scope: transport-only; semantic schema diagnostic only.

| Candidate | Transport | Semantic diagnostic |
|---|---|---|
| `default` | **failed** — `finish_reason=length`; prose before/after; direct JSON parse failed | skipped |
| `enable_thinking_false` | **passed** — `finish_reason=stop`; single JSON object; zero repairs; no prose/fences/thinking | **invalid** — empty `supporting_evidence` |

Selected mode: `enable_thinking_false` (`verified_for_run`). Prompt/completion token counts were `null` in probe evidence.

### Generation-call accounting

| Count | Value | Meaning |
|---|---|---|
| `probe_generation_call_count` | 2 | response-mode probe generations |
| `record_generation_call_count` | 12 | D1C1 record attempts (3 × 4) |
| `total_generation_call_count` | 14 | probe + record generations |
| `runner_reported_generation_call_count` | 2 | historical runner field; **probe calls only** |

The committed runner’s `generation_call_count=2` must not be read as the total model-generation count.

## 6. Four-record D1C1 outcome

Infrastructure and response-mode verification succeeded. Record-level model output did not satisfy the strict semantic / canonical contract. All four inputs validated before engine startup. One selected mode reused. Max three attempts each. All raw attempts retained (12).

| Record | Attempts | Final status | Regeneration reasons |
|---|---|---|---|
| `dfinal-001` | 3 | rejected_after_attempts | canonical assembly round-trip mismatch ×3 |
| `dfinal-002` | 3 | rejected_after_attempts | semantic schema invalid (empty supporting_evidence) ×2; assembly mismatch ×1 |
| `dfinal-003` | 3 | rejected_after_attempts | semantic schema invalid ×1; assembly mismatch ×2 |
| `dfinal-004` | 3 | rejected_after_attempts | canonical assembly round-trip mismatch ×3 |

Totals: accepted 0; rejected_after_attempts 4; strict semantic-schema-valid accepted 0; canonical schema-v2-valid accepted 0; unsupported commitments 0; semantic correctness `not_evaluated`.

Schema constraints were not relaxed. The cluster source was not patched. Outputs were not manually edited. **D-Final remains incomplete.**

## 7. Independent manifest verification

Recomputed SHA-256, byte sizes, and JSONL row counts for all listed output artefacts. All matched `run_manifest.json`. Required evidence files present. Caller request IDs preserved (`pred:dfinal-00x`). Engine IDs absent from accepted predictions (empty). Selected response-mode verification bound to the same run ID.

## 8. Historical attempts (not successful generation runs)

| Job | Failure | Engine |
|---|---|---|
| 2008 | Priority wait on busy hard-pinned `mscluster110` | no |
| 2017 | Orchestrator `run_directory_exists` | no |
| 2019 | False-negative `StructuredOutputsParams.__init__` reflection | no |
| 2027 | Cwd-relative `immutable_selection` in probe evaluation | yes (crashed before evidence) |
| 2045 | Transport/semantic conflation blocked mode despite transport pass | yes |
| 3974 | Four records rejected after bounded regeneration (this run) | yes |

## 9. Non-claims

- No four-record pipeline PASS
- No accepted predictions
- No semantic correctness evaluation
- Stage D not complete / D-Final remains incomplete
- `selected_model` remains null
- No T13/T14 annotation, training, or LoRA
- Runner `generation_call_count=2` is not the total generation count
