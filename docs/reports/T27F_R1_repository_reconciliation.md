# T27F-R1 repository reconciliation

## Scope

This was a repository-state recovery only. No T28 work, training rerun, protected-data access, or new cluster evaluation was performed.

## Repository lineage

- Original current-branch HEAD: `be67e93909b5321293186cd60bb4dcfea462e3d0` on `feature/t12-cluster-redesign`.
- T27F worktree: `.t27f-submit-worktree`, branch `feature/t12-cluster-redesign`, HEAD `becb79e863655309d981e5be8da2f4613a907f4b`; clean before its final evidence commit.
- Recovered commits, in order: `2d6c0f264b11bbad50632dfd40be57dbae5cb609`, `e4c6e5a8be1e2a5913533732aa4e5de9b364d734`, `0a41b3547c23da7d0afd7eff7104f93a4edafc1e`, `becb79e863655309d981e5be8da2f4613a907f4b`.
- Transfer method: the exact four-commit patch series was generated from the T27F clone and applied with `git am --3way` because the main clone did not contain those object IDs. Equivalent current-branch commits are `8685fdc`, `ca3bcdc`, `3d02b10`, and `0f7194e`.

## Reconciled files

The recovered implementation/evidence sequence reconciled:

- `configs/model/evidence/t27f_canary_evidence.json`
- `configs/model/evidence/t27f_sealed_evidence.json`
- `scripts/t27f_all_task_canary.py`
- `scripts/t27f_schema_preflight.py`
- `scripts/t27f_sealed.py`
- `src/ambiguity_manager/systems/structured_analysis_assembler.py`
- `tests/test_t27f_canonical_schema_recovery.py`
- `docs/reports/T27F_handover.md`
- `docs/reports/ticket_T27F_completion_report.md`
- `docs/reports/ticket_T27_parent_T27F_stage_gate_addendum.md`

This report is the new reconciliation artifact. The preflight evidence JSON, schema configuration, frozen sealed dataset, and earlier T27F implementation files were already present on the current branch and were verified against the recovered evidence.

## Evidence verification

Existing pulled artifacts were verified directly from the T27F worktree:

- `python scripts/t12_cluster_job.py --verify t27f-schema-preflight-20260728T181235Z-0a41b35` -> `VERIFY_PASSED`.
- `python scripts/t12_cluster_job.py --verify t27f-all-task-canary-20260728T181502Z-0a41b35` -> `VERIFY_PASSED`.
- `python scripts/t12_cluster_job.py --verify t27f-sealed-20260728T190852Z-0a41b35` -> `VERIFY_PASSED`.

The preflight artifact records LMFE `0.10.12`, five passing schemas, valid minimal/omission instances, and no unconstrained fallback. The canary artifact records `160/160` terminal calls and zero fallbacks. The sealed artifact records exit `0:0`, 60 calls per mode, 12 assembly attempts per mode, 12 production-schema-valid assemblies per mode, 12 safe assemblies per mode, and zero fallbacks.

Sealed acceptance is `12/12` CPC-plus-ambiguity, `12/12` complete valid assemblies, and `12/12` safe routes in both modes. Unsafe execute, unsafe silent-resolution, fabricated-field, and unsupported-commitment counts are zero. The pulled run includes raw outputs, append-only journals, `run_manifest.json`, `verification.json`, assembly results, and task prediction results.

## Provenance and hashes

- Run source commit: `0a41b3547c23da7d0afd7eff7104f93a4edafc1e`.
- Source archive SHA-256: `44d96ca7369505e1c573963402a46b391f912f4a130621f9d35d737b09cd9645`.
- Sealed manifest hash: `4961a41179e672af6e1e84e76d3d26610b0a0b857b7916d2a7e7599b9b31f6de`.
- Records-manifest hash: `3c04b298c363c0a65d3bef7cd5983a66eb007709b21d47b3256a99e248a023e9`.
- Task-matrix hash: `7789cacb2beb6fa8b69465b79c9d847d5f37f78531bae28ae1282291e3e6d131`.
- Constraint config hash: `0077dd8165f25ae89b269d7700aded86fd259abfb6b3a0e7bdf3bbe5e50bcd7c`.
- Evidence-file SHA-256: preflight `EDF74D21A5957D47147CDFE2332BD1134C1036C6836E1305EF3A32A52FAA2A91`; canary `747A0CF58381D11374B380D7F720CBFF301A20849055DB31DF2E36DEE1D80917`; sealed `2B885C410C88FF42A92F61F4634F2EF5C7CCE35ABBF9CC128786439B6AFBEE5A`.

The frozen identity remains base model `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`, `selected_adapter=null`, `selected_model_strategy=null`, and `valid_for_official_use=false`.

## Validation

- Focused T27F/T27C/T27D/T27E regression selection: 39 passed; 2 tests were blocked by the known managed Windows temporary-directory permission harness.
- Evidence regression suite: 18 passed.
- Cluster operator evidence tests: 7 passed.
- Governance validation: `governance validation OK`.
- Report consistency scan: passed; no authoritative T27F report contains stale `BLOCKED`, `BLOCKED_NOT_RUN`, or pending-run stage-gate text.
- All three recovered run IDs returned `VERIFY_PASSED`.

The separate `test_t12_cluster_snapshot_verify` suite was not treated as a product failure: its seven setup/teardown failures were the same managed temporary-directory permission issue, with no code assertion failure.

## Final gate

T27F is **PASS**. Parent T27 is **PASS**, pending human approval. T28 may begin only after that approval is explicitly recorded. No new sealed run occurred during T27F-R1.
