# T39 - Pilot-120 v1 reproducibility and evidence atlas

**Status:** APPROVED_EXECUTION_NON_OFFICIAL - ATTEMPT_5_RUNNING_AFTER_VALID_PREFLIGHT

## Goal

Produce a bounded, hash-traceable science package for the frozen Pilot-120 v1
without modifying its data, systems, decoding, model selection, or policy.

## Required work

1. Run a provenance preflight binding the frozen source/gold/policy/base/adapter
   identities, immutable code commit, container SHA-256, model snapshot,
   evaluator/launcher code bytes, and adapter bytes into one execution contract;
   capture and verify that contract with Slurm job/node, software, CUDA/GPU, and
   container provenance for every GPU component.
2. Submit five isolated greedy `do_sample=False` replay roots, each with direct
   base, selected adapter, and degree/full/context-blind manager outputs.
3. Use `afterany` handoffs after the first preflight gate so an incomplete
   replicate is recorded and later independent work continues. Allow one
   same-protocol recovery only inside the failed replicate root; it regenerates
   the whole five-system replay under `recovery_1` and reissues its evidence
   atlas, never mixing an old component prediction with a new one.
4. Produce per-replicate terminal, cost/safety, ambiguity, capability,
   operational, all-ten-pair disagreement, structural slice, context-ablation,
   and error-atlas artifacts. Small structural strata are count-only.
5. Audit R1-R5 prediction hashes and execution-contract identity. Identical
   hashes establish execution reproducibility; prediction or contract drift is
   `VERIFY_FAILED` and must not be pooled or selected. A drift report lists
   changed record IDs/fields, component hashes, and runtime evidence.

## Claim boundary

This is an early, non-protected, evaluation-only study. It cannot tune, select,
or retrain any system. It makes no single-ambiguity, isolated-context,
interpretation/CPC/candidate/writing-quality, robustness, generalisation, or
official-completion claim.

No full-1,000, +80 extension, T34 robustness perturbation, annotation, or
changed decoding condition is part of this ticket.

## Current execution record

Attempt `48485` failed at the CPU frozen-byte gate before any GPU inference;
dependent jobs `48486`-`48494` were cancelled and are not scientific artifacts.
Attempt `48498`-`48507` exposed an incomplete preflight: GPU evaluators rejected
a transformed frozen `GOLD_POLICY.json` before inference. Its T40 audit is
valid, but R1/R2 are `NOT_COMPUTED` sentinels.

Attempt 3 began from commit `78ce05d29f0dca2fb816e290b401ad0fd7743678`:
preflight `48572` passed and no-inference T40 `48573` completed. Before any
complete replay evidence was accepted, an independent protocol review found
evidence-atlas, recovery, and runtime-contract defects. Jobs `48574`-`48581`
were cancelled; no output from them is scientific evidence. The next attempt
must use a fresh output root and repaired immutable archive. The exact
accounting is in `docs/reports/T39_T40_EXECUTION_LOG_20260831.md`.

Attempt 4 from `659fb34690b3db3ec407c641529603ca0636b270` verified its archive
and remote frozen bytes but was stopped before any GPU work: the new model-tree
hasher used whole-file reads that were unsafe for the declared preflight memory
limit. Jobs `48586`-`48595` were cancelled; the streaming-hash correction must
be rearchived and run in another new root. No cancelled output is evidence.

Attempt 5 from `7d645d643a3ec3594e116ebede7ab536a964d8b6` has a passed
execution-contract preflight (`48597`) and completed T40 audit (`48598`);
R1 base `48599` is resource-pending. The fresh root and all job IDs are logged
in `docs/reports/T39_T40_EXECUTION_LOG_20260831.md`. There is still no GPU
prediction result until a replica evidence atlas is terminal.

## Acceptance criteria

- [ ] Preflight validates every evaluator-frozen dependency (source, gold,
  `GOLD_POLICY.json`, configuration, subset manifest), plus policy/base/adapter
  identities and one immutable execution contract.
- [ ] Each valid component has 120 ordered schema-valid, nonfailed rows.
- [ ] A metric family is scored only when its saved field is eligible on all 120
  rows; absent/invalid ambiguity, capability, latency, or terminal fields are
  structured `NOT_COMPUTED`, never treated as an incorrect label.
- [ ] Each invalid component produces an explicit `VERIFY_FAILED` or
  `NOT_COMPUTED` artifact; it is never omitted or silently passed.
- [ ] Slice support below 15 for types or 10 for type pairs is count-only.
- [ ] All ten unordered pairs among the five substantive systems have a saved
  field-level disagreement ledger.
- [ ] Recovery, if used, is a single regenerated five-system root whose
  selected evidence path is recorded in the final reproducibility artifact.
- [ ] Context comparison is labelled all-context descriptive only.
- [ ] Final report records exact job IDs, paths, hashes, and remaining limits.
