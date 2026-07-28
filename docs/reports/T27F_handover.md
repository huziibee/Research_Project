# T27F Handover

## Context & Goal

T27F repairs the LMFE 0.10.12 generation-schema incompatibility exposed by T27E, promotes the proven two-field ambiguity contract, preserves production-schema/fail-safe assembly semantics, and validates the runtime through exact-container preflight, an all-task non-sealed canary, and exactly one fresh 12-record sealed smoke. T28 remains prohibited.

Completed in the clean isolated worktree at commit `0a41b35`:

- Canonical generation layer: `src/ambiguity_manager/model/generation_schema.py`.
- Exact-runtime preflight: `src/ambiguity_manager/model/schema_preflight.py` and `scripts/t27f_schema_preflight.py`.
- Verifiable preflight manifest repair: commit `2d6c0f2`.
- Standard operator-argument compatibility: commit `e4c6e5a`.
- Optional-interpretation fail-safe assembly repair and regression test: commit `0a41b35`.
- Cluster failure propagation and durable failure artifacts are exercised by the existing operator tests.

## Current State

Worktree: `.t27f-submit-worktree` (clean before the sealed submission), branch `feature/t12-cluster-redesign`, based on the immutable base `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`. `selected_adapter`, `selected_model_strategy`, and official-use validity remain null/null/false.

Verified artifacts:

- [Exact preflight evidence](../../configs/model/evidence/t27f_schema_preflight.json): all five effective schemas passed LMFE 0.10.12; no nullable enums; no unconstrained fallback.
- Exact-container preflight job 22628: exit `0:0`, operator `VERIFY_PASSED`.
- [Canary evidence](../../outputs/t12_cluster_jobs/t27f-all-task-canary-20260728T181502Z-0a41b35/pulled/t27f_canary_evidence.json): job 22632, 160/160 terminal calls, 0 fallbacks, all 32 assemblies production-schema-valid, raw outputs and journal pulled, operator `VERIFY_PASSED`.
- [Fresh sealed manifest](../../data/development/t27f_final_smoke_v1/manifest.json): 12 source_dev records, leakage report passed, manifest hash `4961a41179e672af6e1e84e76d3d26610b0a0b857b7916d2a7e7599b9b31f6de`.

Active task:

- Exactly one sealed smoke is submitted as job `22660`, run `t27f-sealed-20260728T190852Z-0a41b35`.
- Current Slurm state: `PENDING` for resources; no sealed model calls or acceptance counts are available yet.
- Local run record reports `pulled=False`.
- Do not submit another sealed run. Do not cancel the active run merely because it is pending.

## Next Steps

1. Poll the existing run until terminal:
   `python scripts/t12_cluster_job.py --poll t27f-sealed-20260728T190852Z-0a41b35 --pull`
2. Pull and verify the exact run; require Slurm exit `0:0`, completion marker, run manifest, expected artifacts, raw outputs, journal reconciliation, and no failure markers:
   `python scripts/t12_cluster_job.py --verify t27f-sealed-20260728T190852Z-0a41b35`
3. Reconcile `t27f_sealed_evidence.json`, per-task/per-record acceptance, CPC-plus-ambiguity count, assembly counts, route-safety counts, and all frozen hashes. Use `NOT_COMPUTED` for any unavailable evidence.
4. Update [ticket_T27F_completion_report.md](ticket_T27F_completion_report.md) and [the parent T27 stage-gate addendum](ticket_T27_parent_T27F_stage_gate_addendum.md) with the sealed result and explicit T27F/parent-T27 PASS or BLOCKED decision.
5. Preserve the identity rules: no adapter selection, no model-strategy selection, and `valid_for_official_use=false`. Stop immediately after the reports. T28 requires a PASS gate and human approval.
