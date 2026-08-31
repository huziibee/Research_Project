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
- The dependent T40/R1/R2 jobs (`48486`–`48494`) remain Slurm pending with
  failed-dependency states. They must not be treated as valid execution and
  cannot be reused for the corrected protocol.

## Corrected immutable deployment, ready but not submitted

- Code commit: `56a2fa1573c9ef3a7f87d92f371f577f63f261db` on branch
  `science/pilot120-t38`.
- Immutable runtime root:
  `/home-mscluster/mbangie/t12-hpc/code/pilot120-t39-56a2fa1573c9ef3a7f87d92f371f577f63f261db-runtime`.
- Archive SHA-256:
  `b9ee3138d49e186f6dc933a7cab9ca8a0498b8cb859f3d7a0354612baa477a72`.
- The archive was locally checked to reproduce source hash
  `f33b1e29f1e8aa256a475f07213aa07247def47d8e2148d54a472a40b71b05c9`
  and gold hash
  `5e23ad1a92ff1873c8f039a8ce560a111dd6fb6b8ae8c11d6cf34dbfa1c360db`.
- All deployed Slurm shell files pass `bash -n`; preflight now writes an
  explicit `VERIFY_FAILED` artifact if future container or frozen-provenance
  validation fails.

## Required authority before corrected submission

The previous pending jobs occupy the cluster submission allowance. Cancel only
`48486`–`48494` (all are dependency-blocked and have never run), then submit
the unchanged approved T39/T40 protocol from the corrected immutable root. No
other experiment, dataset, model, decoding, or tuning change is proposed.
