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

## Authority and claim boundary

The user authorised the fresh T39 submission and the cluster work needed to
unblock it. No other experiment, dataset, model, decoding, or tuning change is
proposed. The final supervisor document remains gated on T39+T40+T41+T42+T43+
T44 terminal artifacts.
