# T28-R3 resume and training report

## Result

**BLOCKED before training.** The explicit human governance decision was recorded and the internal T28 training gate is permitted. The technical/data preconditions that were available passed, but the checkout contains no bounded full-data T28 training entry point or cluster profile. The only available QLoRA cluster profiles are T27 smoke profiles and cannot be used as the full T28 run.

## Governance decision

Machine-readable record: `docs/governance/decisions/T28-R3_internal_use_decision.json`.

- Decision type: `human_internal_academic_use_authorisation`.
- Decision date: `2026-07-28`.
- Internal training, internal dev evaluation, and aggregate research publication are permitted.
- Raw-data redistribution, transformed-text redistribution, commercial use, and public adapter release remain prohibited.
- Dataset licence statuses remain unresolved/unchanged.
- No institutional signature or author permission was fabricated.

## Preconditions

- Required commits `72025f8`, `b61dbf5`, `38f551d`, and `c8e464b` are ancestors of HEAD `c8e464be0b97bd1d138ff2a59e97c849c643c1a2`.
- T27F and parent T27 are PASS in the authoritative reports.
- All three preserved T27F verifiers returned `VERIFY_PASSED`.
- Canonical SHA-256: `1e51cac046e014a6b890b10a155d22e32e01aa276d4507a10ad4f86abcf9942a`.
- Permitted-view SHA-256: `34b551c37c8f97c24c1263a2cc12a9497e65f754924f1404c47055999f04ea22`.
- Counts: train `11,294`, dev `2,396`, valid targets `13,058`, skipped `632`.
- Source holdout loaded: `0`; protected records loaded: `0`; train/dev group overlap: `0`.
- Base: `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`.
- `selected_adapter=null`, `selected_model_strategy=null`, `valid_for_official_use=false`.

## Frozen artifacts

- Plan: `configs/model/t28_training_plan_v1.json`.
- Run matrix: `configs/model/t28_frozen_run_matrix_v1.json`.
- Selection policy: `configs/model/t28_frozen_selection_policy_v1.json`.
- Train manifest SHA-256: `eb73488a19eb98770ea8ac18986c91d02cd8ca418608340da65394ac66582407`.
- Dev manifest SHA-256: `6b2b3b3ac1f3682636e1a5bd4ac0bd635660827febfc4c4230cdd5a537a4e2a4`.
- Effective schema registry hash: `3d84474d5f0db49ee3689dc68336a0b51ac72231a0591b606a15a0de0fe6998c`.

## Runtime preflight

The local preflight could not import LMFE. The approved cluster preflight job `22704` installed LMFE `0.10.12`, compiled all five schemas, reported no unconstrained fallback, and returned `VERIFY_PASSED`. Evidence is in `configs/model/evidence/t28_r3_preflight.json`.

## Training and selection outcome

No GPU training job was submitted. No checkpoint, dev prediction, T24 evaluation, selected adapter, package, clean-load verification, or manager configuration update exists. Submitting the available T27 smoke profile would violate the full-data requirement and smoke-substitution prohibition. Therefore no supervised checkpoint is eligible and T28-R3 cannot pass.

## Protected/public boundaries

No protected evaluation data was accessed. No public dataset, transformed source text, or adapter was released. T29 did not begin.

## Stage gate

**T28-R3: BLOCKED.** Add and independently validate a bounded full-data T28 cluster trainer/profile that consumes the frozen train manifest and evaluates only the frozen dev manifest, then resume from these immutable plan/manifests under separate human direction. T29 must not begin.
