# T28 completion report

> Historical T28 pre-R3 blocker report. T28-R3 supersedes its governance conclusion: the explicit human internal-use decision is recorded, but T28 remains blocked on the absence of a full-data T28 trainer/profile. See `docs/reports/T28_R3_resume_and_training_report.md`.

## Ticket

- ID: T28
- Title: Mandatory supervised fine-tuning and dev checkpoint selection
- Result: **BLOCKED**

## Preconditions checked

- Approved source commit `72025f8de977f68f7a20a6db15c130d2cc173c95` is an ancestor of the current HEAD.
- Original and final HEAD: `72025f8de977f68f7a20a6db15c130d2cc173c95`.
- Human approval was explicitly supplied for the Parent T27 to T28 transition after reconciliation commit `72025f8de977f68f7a20a6db15c130d2cc173c95`; this approval is recorded here.
- Authoritative reports state T27F PASS and Parent T27 PASS. `docs/reports/T27F_handover.md` exists.
- In preserved `.t27f-submit-worktree`, all required artifact verifiers returned `VERIFY_PASSED` for preflight `t27f-schema-preflight-20260728T181235Z-0a41b35`, canary `t27f-all-task-canary-20260728T181502Z-0a41b35`, and sealed smoke `t27f-sealed-20260728T190852Z-0a41b35`.
- Frozen T15 train/dev manifests are present and group-disjoint: 11,294 `source_train` rows, 2,396 `source_dev` rows, and zero train/dev group intersection.
- The exact immutable base is `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`.
- Canonical T27F task-conditioned schemas resolve through `load_task_registry` and `schema_preflight`; the five-schema remote preflight passed.
- `selected_adapter=null`, `selected_model_strategy=null`, and `valid_for_official_use=false` remain unchanged.
- The working tree was already dirty with unrelated untracked cluster worktrees, archives, and evidence files; these were preserved and not modified.

## Blocking condition

The frozen T15 manifest is only an ID/eligibility manifest in this checkout. The full source-record join required to emit task-conditioned supervision is absent: `data/processed/weak_pool/weak_pool_canonical.jsonl` is missing. The only committed joined training material is the prior 192-record T27C smoke subset (`data/development/qlora_task_conditioned_smoke_v1/`), which is not the full frozen T15 training partition. Rebuilding from raw source data or silently substituting the smoke subset would violate the T28 data and full-data-run contract.

Therefore no T28 training job, checkpoint evaluation, adapter selection, package, manager configuration update, or dev comparison was performed. This is a mandatory BLOCKED outcome, not a failed training result.

## Tests written first

- Added `tests/test_t28_contract.py` before implementation of the T28 contract helpers.
- Initial command: `PYTHONPATH=src python -m unittest tests.test_t28_contract -v`
- Initial failure: `ModuleNotFoundError: No module named 'ambiguity_manager.model.t28'`.
- Final command: same command after implementation.
- Final result: 7 tests passed.
- The broader required T28 test matrix was not claimed because the full T28 runner and source-record join could not be executed safely.

## Files created or changed

- `src/ambiguity_manager/model/t28.py` — deterministic train/dev, frozen-plan, ranking, same-adapter, and package checksum guards.
- `tests/test_t28_contract.py` — first T28 contract tests.
- `docs/reports/ticket_T28_completion_report.md` — this report.
- `docs/reports/T28_handover.md` — blocked handover.

No frozen data, protected data, T27F artifacts, T23 manager configuration, selected-identity configuration, or parallel annotation programme was modified.

## Commands and evidence

- `git rev-parse --show-toplevel; git branch --show-current; git rev-parse HEAD; git status --short`
- Required grounding-file read in the user-specified order.
- `python scripts/t12_cluster_job.py --verify ...` in `.t27f-submit-worktree` for all three T27F runs: all `VERIFY_PASSED`.
- T15 source split accounting script: train/dev group intersection `[]`.
- `PYTHONPATH=src python -m unittest tests.test_t28_contract -v`: `7 passed`.
- Read-only cluster preflight: Wits login reachable; `sbatch`, `squeue`, and `apptainer` available; pinned training SIF and training site packages present under `/home-mscluster/mbangie/t12-hpc`.
- No `sbatch`, training, dev inference, protected evaluation, or T29 command was run.

## Hashes and identities

- Git archive SHA-256 for approved HEAD: `9f04ad12a764f1e3106895392af31e21a626d0fc3125bfe87ab547bb21e0a5ae`.
- T15 record manifest: `5f8e74ed1ae4838a7c44dcfe413e5d4f0b990eb9f2bd04bb4a04949ac11ee42a`.
- T15 group manifest: `6b10750994ed37329122633be249ab0391041f3d3a3e9c36cc79c389da9496c6`.
- T15 manifest: `5506efc4b28d4cc5ca7471c2677b4c00c27c464bb84b8e10255bf52775711d41`.
- T27F schema compatibility config: `86a8c3561bd8a506e7d8915d61b23e91c53c53dc61ba7839f44af6adffef1e5b`.
- T15 training target policy: `c2f73a36aa3450ad83a88f7eb047430d86303aa36050f7f6c23885a0079309fb`.
- Training environment identity: `t12-cluster-training-task-aligned-v1`, SHA-256 `275ea14cc37200a40a2be27b69da5a99cf445571b780b1672168310c68c4cf52`.
- Prompt, target, training-example, run, checkpoint, and package hashes: `NOT_COMPUTED` because the frozen full-data plan could not be submitted.

## Outcomes and acceptance status

- Human approval recorded: yes.
- T27F and Parent T27 remain PASS: yes.
- Protected data accessed: no.
- T15 frozen data modified: no.
- Experiment and selection rules frozen before training: no training plan was frozen because source records were unavailable.
- Train-only adaptation and dev-only selection: not run.
- At least one eligible supervised checkpoint: no.
- Exactly one selected adapter: no; `selected_adapter` remains null.
- Full/context-blind same-adapter configuration: not changed.
- Direct base remains adapter-free: yes.
- `valid_for_official_use=false`: yes.
- T29 or protected evaluation begun: no.

## Stage gate

**T28: BLOCKED.** The missing frozen source-record join prevents a truthful full-data supervised run. The missing artifact must be restored or an explicitly approved, hash-equivalent source-record materialisation must be made available before T28 can resume. T29 and protected evaluation must not begin. A separate human approval is required before any resumed T28 execution and before T29.
