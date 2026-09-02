# T39/T40 execution log — 2026-08-31

This is a live operational record for the approved, non-protected Pilot-120 v1
T39/T40 protocol. It does not contain a scientific result and must accompany,
not replace, the final evidence atlas and reproducibility audit.

## Attempt 1: invalid archive gate

- Submitted jobs: `48485`–`48494`.
- `48485` (`p120-t39-preflight`) ran on `mscluster72` and ended `FAILED`, exit
  code `1:0`, before any GPU inference.
- Failure: `t39_source_hash_mismatch`. The deployed archive had rewritten the
  byte-frozen Pilot source and gold JSONL files, so preflight correctly stopped
  the study. No T39 result, model prediction, or performance measure was
  produced from this attempt.
- The dependent T40/R1/R2 jobs (`48486`–`48494`) were cancelled before running.
  They must not be treated as valid execution and cannot be reused.

## Attempt 2: incomplete preflight coverage

- Submitted jobs: `48498`–`48507` from immutable code commit
  `56a2fa1573c9ef3a7f87d92f371f577f63f261db`.
- `48498` preflight and `48499` T40 completed. T40's
  `t40_interpretation_requirements_audit.json` is a valid requirements audit.
- Every R1/R2 GPU component failed before inference. The original evaluator
  correctly rejected `GOLD_POLICY.json`: observed
  `c0f18b1b74ce735e820ed9080886b70ce4ab6157f6cebadcf5f77f2323929d30`,
  expected `3c1f0a4d43c29996062a4a2ecd321e4023a38f5fad950801f96e07e23aac4a34`.
  The CPU preflight had checked only source/gold, so it did not catch this
  archive transformation. R1/R2 evidence sentinels are `NOT_COMPUTED`, not
  scientific prediction artifacts.

## Attempt 3: required fresh resubmission

- The repaired preflight now checks the exact five dependencies checked by the
  GPU evaluator: source, gold, `GOLD_POLICY.json`, configuration, and
  `subset_manifest.json`. The missing subset manifest has been restored with
  its authoritative CRLF bytes and expected SHA-256
  `60c8247c867c27ea67c6bb28f1a566df94db839a72df8a1a8e80b85e5d9d6a69`.
- The selective archive will preserve all five dependencies and local archive
  verification must reproduce each hash before upload. A fresh output root is
  mandatory; attempt-2 roots cannot be resumed.
- The account's ten-job submit cap requires scheduler-safe staging: preflight,
  T40, and serial R1/R2 are submitted first; guarded R3–R5 continuation and
  the five-evidence final audit are submitted only as capacity opens. This
  changes scheduling, not systems, data, decoding, or protocol.

## Attempt 3 submission — 2026-09-01

- Immutable code commit: `78ce05d29f0dca2fb816e290b401ad0fd7743678`.
- Immutable runtime root:
  `/home-mscluster/mbangie/t12-hpc/code/pilot120-t39-78ce05d-runtime`.
- Archive SHA-256: `a65be4e2e02f4ca8ed8896a297ab1907e7eb84ba9a7cd2daf4ce54b0b8678a41`.
  Local archive inspection and remote extraction independently reproduced all
  five evaluator hashes before submission.
- Submitted stage: preflight `48572`; T40 `48573`; R1 base/adapter/manager/
  evidence `48574`–`48577`; R2 base/adapter/manager/evidence
  `48578`–`48581`. At submission inspection `48572` was `RUNNING`; every
  downstream job was correctly dependency-pending. These are operational
  statuses only, not result claims.
- Terminal gate verification: `48572` completed `0:0` in 36 seconds with
  `T39_PROVENANCE_PREFLIGHT_PASSED`; its artifact records all five expected
  evaluator hashes, the fixed container, adapter identity and immutable commit.
  `48573` completed `0:0`. R1 direct base (`48574`) then started; no GPU result
  is claimed until its prediction and evidence artifacts pass their own gates.

## Attempt 3 stopped before valid inference evidence

- An independent protocol review found repairable defects before any complete
  evidence atlas existed: only two of the ten all-system disagreement pairs
  would have been emitted; count-only slices could still contain metrics;
  operational failures were discarded before they could be counted; recovery
  did not regenerate an evidence atlas; and the runtime provenance did not
  verify a single immutable execution contract across the five roots.
- The user-authorised stop cancelled `48574`â€“`48581`. Final Slurm accounting:
  `48574` was `CANCELLED` after 4m32s (batch exit `0:15`); `48575`â€“`48581`
  were cancelled before execution. No prediction, partial prediction, or
  sentinel from these cancelled jobs is an input to any result.
- `48572` remains a valid historical five-dependency preflight and `48573`
  remains a valid no-inference T40 inventory, but neither establishes T39
  reproducibility or system performance. A new output root, commit, archive,
  execution-contract preflight, and five fresh replay roots are required.

## Attempt 4 stopped before a memory-safe contract hash

- Commit `659fb34690b3db3ec407c641529603ca0636b270` added the execution
  contract. Its archive (`4ebb42e694eec08884d883e767cf174d03822d6c8da5246ad21dd87bb668f245`)
  and remote extraction reproduced all five evaluator-frozen bytes.
- Before the preflight could complete, review of the running code identified
  that the model-tree hash loaded an entire model shard with `read_bytes()`.
  That is not safe under the declared 8-GiB preflight allocation. The entire
  chain `48586`â€“`48595` was cancelled rather than treating a memory-unsafe
  provenance check as valid. `48586` ran 3m24s and was cancelled; `48587`â€“`48595`
  never started. No GPU inference or T40 artifact was produced.
- The repair streams SHA-256 in bounded 8-MiB chunks and has a regression test
  that rejects any return to whole-file `read_bytes()` hashing. It requires a
  new commit, archive, code root and output root before another submission.

## Attempt 5: valid execution-contract gate and T40 audit

- Immutable code commit: `7d645d643a3ec3594e116ebede7ab536a964d8b6`.
  The byte-verified archive SHA-256 is
  `57d936324702424e8955eebcffce75b12e6f56449c6f863a222b4c6564af5df5`;
  its remote extraction independently reproduced all five frozen evaluator
  dependencies before submission.
- Output root:
  `/home-mscluster/mbangie/t28_r5_src/outputs/pilot_120/t39_20260901_7d645d6`.
  Submitted jobs: preflight `48597`; T40 `48598`; R1 base/adapter/manager/
  evidence `48599`â€“`48602`; R2 base/adapter/manager/evidence
  `48603`â€“`48606`.
- `48597` completed `0:0` in 1m14s with
  `T39_PROVENANCE_PREFLIGHT_PASSED`. It records one execution-contract SHA
  (`e1d19aa2306375fa1a97e7c44b540a30bfc883fe9b900bf75682beae64b583dc`),
  model snapshot tree SHA, selected-adapter tree SHA, container SHA, immutable
  code commit, and all five evaluator-frozen hashes. `48598` completed `0:0`
  and produced the T40 no-inference requirements audit.
- R1 base `48599` began on 2026-09-01, but this did **not** produce a valid
  GPU replay. Its component runtime provenance records `cuda_available: false`
  under `torch 2.11.0+cu130`; the allocated `mscluster111` host exposed an
  8-GiB RTX 2060 rather than the required high-memory Blackwell device. The
  evaluator consequently made no prediction row after model load and consumed
  CPU only. After 55m09s it and all dependent R1/R2 jobs `48600`-`48606` were
  cancelled. These jobs are diagnostic-only and are excluded from every
  scientific result.
- The replacement must use a fresh archive and output root, admit only
  `mscluster110` or `mscluster112`, and pass a container-side CUDA, small
  allocation, Blackwell, idle-GPU, and >=90,000-MiB VRAM gate before any
  component can load a model. Runtime evidence and the evidence atlas now also
  reject CPU or under-memory component provenance.

## Authority and claim boundary

The user authorised the fresh T39 submission and the cluster work needed to
unblock it. No other experiment, dataset, model, decoding, or tuning change is
proposed. A supervisor dossier may report terminal T39/T40/T45 evidence, but
must carry Q41--Q44 as explicit `NOT_COMPUTED` limitations until their separate
source and human-review prerequisites produce terminal artifacts.

## Attempt 6: terminal GPU-gated five-replay result (2026-09-02)

- Immutable inference code remained
  `6d71affdb77200fdac57f60af71d6797e942b6bd` under output root
  `/home-mscluster/mbangie/t28_r5_src/outputs/pilot_120/t39_20260901_6d71aff_gpu`.
  Static preflight `48620`, T40 `48621`, and GPU admission `48622` were
  accepted before any valid inference.
- R1--R5 component/evidence chains were all `COMPLETED` with exit `0:0`:
  `48623`--`48626`, `48627`/`48628`/`48630`/`48631`, `48693`--`48696`,
  `48701`--`48704`, and `48730`--`48733`. Accepted inference provenance is
  Blackwell/97,249-MiB GPU on `mscluster110`; the former CPU/8-GiB attempt is
  excluded.
- Dispatcher `48708` completed `0:0` and submitted audit `48791` after all
  five evidence jobs. Audit `48791` completed `0:0` in five seconds on
  `mscluster45`, consuming exactly the five R1--R5 evidence artifacts.
- Terminal `t39_reproducibility_audit.json` is `VERIFY_PASSED` (SHA-256
  `b803771c0fcd4a22b3da344e2d0647ebc46fe2a5d6823a8116eb91978630f081`).
  It validates one execution-contract SHA-256
  `0f414fc37af907a1e123397463646c85c9edf9db44d8308b079b1efd1974743f`,
  raw prediction integrity, and replay-content equality across all five
  systems/replicas after normalising finite numeric latency only.
- This is a bounded, non-official reproducibility result. It does not make
  Q41--Q44 measures computed and does not authorise tuning or promotion.
