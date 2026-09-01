# T39 - Pilot-120 v1 reproducibility and evidence atlas

**Status:** APPROVED_EXECUTION_NON_OFFICIAL - ATTEMPT_6_GPU_GATED; R1/R2 VALID, R3 ACTIVE

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
5. Audit R1-R5 raw byte-integrity hashes, replay-content hashes and
   execution-contract identity. The raw hash is forensic artifact identity;
   the replay-content hash normalises only finite numeric `latency_ms` while
   retaining latency presence/validity. Identical replay-content hashes
   establish greedy execution reproducibility. Replay-content, raw-integrity,
   or contract drift is `VERIFY_FAILED` and must not be pooled or selected. A
   drift report lists changed record IDs/fields, component hashes, and runtime
   evidence.

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
execution-contract preflight (`48597`) and completed T40 audit (`48598`), but
its R1 base job `48599` was invalid: its saved runtime provenance records
`torch.cuda.is_available() == false` on an 8-GiB RTX 2060 and it completed zero
prediction rows in 55m09s. It and dependent jobs `48600`-`48606` were
cancelled. No output is scientific evidence. The next immutable attempt adds a
Blackwell/>=90-GiB container-side GPU admission gate, excludes the bad node,
and makes runtime/evidence validation reject CPU fallback before any score can
be emitted.

Attempt 6 uses immutable GPU-gated commit
`6d71affdb77200fdac57f60af71d6797e942b6bd` and output root
`/home-mscluster/mbangie/t28_r5_src/outputs/pilot_120/t39_20260901_6d71aff_gpu`.
Static preflight `48620`, T40 `48621`, and container-side Blackwell GPU
preflight `48622` passed. R1 (`48623`--`48626`) and R2
(`48627`, `48628`, `48630`, `48631`) each have a terminal
`T39_EVIDENCE_ATLAS_COMPLETE` artifact with complete component GPU provenance
under execution contract
`0f414fc37af907a1e123397463646c85c9edf9db44d8308b079b1efd1974743f`.
R3 (`48693`--`48696`) is the active serial replica; R4 and R5 must remain new
roots after their predecessor evidence job is terminal.

R4 (`48701`--`48704`) is dependency-queued after R3 evidence. CPU-only
dispatcher `48708`, recorded in `t39_r5_and_audit_dispatch_submission.tsv`,
is dependency-queued after R3 evidence and carries the R4 evidence handoff.
It will submit the new R5 root after R3 evidence, then submit the final audit
only after R4 evidence is terminal. The dispatcher overlay is hash-verified:
`t39_r5_and_audit_dispatch.sbatch`
`1fb856de4eeb9e7d3a8f94105f919aef3f9b91fffbe36ad6475682b96d73fb6d`,
its submitter
`04236419ab66d0979c13d14ae616b4930d08d7799a64f04644168c4b3a06ae66`,
and its audit submitter
`8f0060971f1f260c986dad194a69732116fc92f8ac1825446e9f0b195215aa5f`.
It changes no inference source, model, prompt, decoding or artifact bytes.

R1/R2 raw prediction-file SHA-256 values differ because every saved row
contains wall-clock `latency_ms`. The tested audit amendment
`docs/reports/T39_REPRODUCIBILITY_AUDIT_AMENDMENT_20260901.md` preserves raw
byte-integrity checking while using a separate replay-content hash for greedy
model-output reproducibility. It changes no inference condition or saved
artifact.

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
