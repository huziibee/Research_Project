# T39 — Pilot-120 v1 reproducibility and evidence atlas

**Status:** APPROVED_EXECUTION_NON_OFFICIAL

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

## Acceptance criteria

- [ ] Preflight validates the frozen source/gold/policy/base/adapter hashes.
- [ ] Each valid component has 120 ordered schema-valid, nonfailed rows.
- [ ] A metric family is scored only when its saved field is eligible on all 120
  rows; absent/invalid ambiguity, capability, latency, or terminal fields are
  structured `NOT_COMPUTED`, never treated as an incorrect label.
- [ ] Each invalid component produces an explicit `VERIFY_FAILED` or
  `NOT_COMPUTED` artifact; it is never omitted or silently passed.
- [ ] Slice support below 15 for types or 10 for type pairs is count-only.
- [ ] Context comparison is labelled all-context descriptive only.
- [ ] Final report records exact job IDs, paths, hashes, and remaining limits.
