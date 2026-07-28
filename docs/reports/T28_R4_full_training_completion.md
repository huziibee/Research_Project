# T28-R4 Full-Data Training Completion Report

## Result

**T28-R4: BLOCKED at the pre-training data-integrity gate.** The trainer, production profile, orchestration, checkpoint/package utilities, tests, and exact frozen preflight evidence were implemented. The single frozen training run was submitted three times only as bounded recovery: the first failed on run-ID mapping, and the two subsequent attempts failed before model loading because the remote canonical-corpus bytes did not match the authoritative SHA-256. No checkpoint or dev evaluation was produced.

The blocker is explicitly enumerated in the ticket: canonical/permitted/train/dev hashes do not match authoritative values in the execution environment after bounded recovery. T29 did not begin.

## Preservation and commits

- Required ancestors verified: `72025f8`, `b61dbf5`, `38f551d`, `c8e464b`.
- T28-R3 preservation commit: `67fddf5`.
- R4 implementation: `ab21ebe`.
- Run-identity correction: `488f8bd`.
- Frozen-byte archive correction: `dbc704a`, `7dcb1a3`.
- Final HEAD: `7dcb1a373d296779e268704579f5f7f4d5de9c23`.
- Unrelated dirty/untracked paths were preserved and not committed.

## Frozen evidence

- Canonical SHA-256: `1e51cac046e014a6b890b10a155d22e32e01aa276d4507a10ad4f86abcf9942a`.
- Permitted-view SHA-256: `34b551c37c8f97c24c1263a2cc12a9497e65f754924f1404c47055999f04ea22`.
- Train manifest SHA-256: `eb73488a19eb98770ea8ac18986c91d02cd8ca418608340da65394ac66582407`.
- Dev manifest SHA-256: `6b2b3b3ac1f3682636e1a5bd4ac0bd635660827febfc4c4230cdd5a537a4e2a4`.
- Effective schema registry SHA-256: `3d84474d5f0db49ee3689dc68336a0b51ac72231a0591b606a15a0de0fe6998c`.
- Counts reproduced: 11,294 source-train, 2,396 source-dev, 13,058 valid targets, 632 skipped, zero holdout, zero protected, zero group overlap.
- Exact recorded T27F LMFE preflight: `VERIFY_PASSED`, job `22704`; local Windows preflight remains unavailable because LMFE is not installed.

## Implementation and validation

Added bounded lazy loading and identity gates in `src/ambiguity_manager/model/t28_trainer.py`; `scripts/train_t28_full.py`; `scripts/orchestrate_t28.py`; `scripts/evaluate_t28_dev.py`; checkpoint manifest, ranking, packaging, and clean-load scripts; `cluster/t28/t28_full_train.sbatch`; and the production profile in `configs/cluster/t12_job_profiles.json`. The profile uses `biggpu`, one exclusive node, 110,000 MB, 16 CPUs, and no GPU GRES flag.

Focused T28/R1/R2 tests: **35 passed**. Governance validation: **passed**. The local R3 freeze reproduced both manifest hashes and all counts. No adapter package, checkpoint, dev output, T24 comparison, identity propagation, or clean-load verification exists.

## Slurm execution

| Job | Run ID | Result | Evidence |
|---|---|---|---|
| 22708 | `t28-full-train-20260728T210930Z-ab21ebe` | FAILED, 2 s | run identity not in frozen matrix |
| 22710 | `t28-full-train-20260728T211250Z-488f8bd` | FAILED, 3 s | `canonical_hash_mismatch` |
| 22715 | `t28-full-train-20260728T212157Z-7dcb1a3` | FAILED, 2 s | `canonical_hash_mismatch` |

The locally extracted committed archive reproduces the authoritative canonical hash, but both remote hash-gate attempts failed. Therefore no model was loaded, no protected path was accessed, and no training result can be claimed.

## Governance boundary

Internal academic training was permitted by the preserved R3 decision. Dataset licence metadata remains unresolved and unchanged. Raw or transformed data, checkpoints, and adapters were not publicly released. `selected_adapter` and `selected_model_strategy` remain null; `valid_for_official_use=false`; `public_release_allowed=false`; `protected_evaluation_completed=false`.

## Final decision

T28-R4: **BLOCKED**. Parent T28: **BLOCKED**. The next action is to repair and independently verify the remote archive/extraction byte-preservation path, then open a new authorized recovery ticket. T29 may not begin without separate human approval.
