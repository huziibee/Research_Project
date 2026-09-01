# T39 — Pilot-120 v1 reproducibility and evidence atlas

**Status:** APPROVED_EXECUTION_NON_OFFICIAL — ATTEMPT_3_RUNNING

## Goal

Produce a bounded, hash-traceable science package for the frozen Pilot-120 v1
without modifying its data, systems, decoding, model selection, or policy.

## Required work

1. Run a provenance preflight binding the frozen source/gold/policy/base/adapter
   identities, immutable code commit, and container SHA-256; capture Slurm
   job/node, software, CUDA/GPU, and container provenance for every GPU component.
2. Submit five isolated greedy `do_sample=False` replay roots, each with direct
   base, selected adapter, and degree/full/context-blind manager outputs.
3. Use `afterany` handoffs after the first preflight gate so an incomplete
   replicate is recorded and later independent work continues. Allow one
   same-protocol resume only inside the failed replicate root.
4. Produce per-replicate terminal, cost/safety, ambiguity, capability,
   operational, pairwise disagreement, structural slice, context-ablation, and
   error-atlas artifacts.
5. Audit R1--R5 prediction hashes. Identical hashes are expected and establish
   execution reproducibility; drift is `VERIFY_FAILED` and must not be pooled
   or selected. A drift report lists changed record IDs/fields, component hashes,
   and the runtime evidence for both roots.

## Claim boundary

This is an early, non-protected, evaluation-only study. It cannot tune, select,
or retrain any system. It makes no single-ambiguity, isolated-context,
interpretation/CPC/candidate/writing-quality, robustness, generalisation, or
official-completion claim.

No full-1,000, +80 extension, T34 robustness perturbation, annotation, or
changed decoding condition is part of this ticket.

## Current execution record

Attempt `48485` failed at the CPU frozen-byte gate before any GPU inference;
dependent jobs `48486`–`48494` were cancelled and are not scientific artifacts.
Attempt `48498`–`48507` exposed an incomplete preflight: GPU evaluators rejected
a transformed frozen `GOLD_POLICY.json` before inference. Its T40 audit is
valid, but R1/R2 are `NOT_COMPUTED` sentinels. Attempt 3 uses a new output root,
a five-dependency preflight, byte-preserving archive, and scheduler-safe
R1/R2-then-R3–R5 staging. The exact record is in
`docs/reports/T39_T40_EXECUTION_LOG_20260831.md`.

Attempt 3 is now running from commit
`78ce05d29f0dca2fb816e290b401ad0fd7743678`: preflight `48572` passed and
R1 base `48574` started. This changes no acceptance criterion; it is not a
scientific result until all five replica artifacts and the final audit are
terminal.

## Acceptance criteria

- [ ] Preflight validates every evaluator-frozen dependency (source, gold,
  `GOLD_POLICY.json`, configuration, subset manifest), plus policy/base/adapter
  identities.
- [ ] Each valid component has 120 ordered schema-valid, nonfailed rows.
- [ ] A metric family is scored only when its saved field is eligible on all 120
  rows; absent/invalid ambiguity, capability, latency, or terminal fields are
  structured `NOT_COMPUTED`, never treated as an incorrect label.
- [ ] Each invalid component produces an explicit `VERIFY_FAILED` or
  `NOT_COMPUTED` artifact; it is never omitted or silently passed.
- [ ] Slice support below 15 for types or 10 for type pairs is count-only.
- [ ] Context comparison is labelled all-context descriptive only.
- [ ] Final report records exact job IDs, paths, hashes, and remaining limits.
