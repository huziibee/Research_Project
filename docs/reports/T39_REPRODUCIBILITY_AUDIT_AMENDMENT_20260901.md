# T39 reproducibility audit amendment — timing telemetry

Status: `PENDING_APPLY_AFTER_R5`  
Scope: post-inference audit correction only; Pilot-120 v1 remains evaluation-only and non-official.

## Trigger and diagnosis

The first two valid GPU replicas, R1 and R2, each passed their individual
evidence-atlas and runtime-provenance gates under the same execution-contract
SHA-256 (`0f414fc37af907a1e123397463646c85c9edf9db44d8308b079b1efd1974743f`).
Their raw prediction-file SHA-256 values differed for every system. Inspection
showed that the prediction records include measured `latency_ms`; this is a
wall-clock observation and necessarily differs between otherwise identical
greedy executions.

For all five systems, R1 and R2 have identical ordered JSONL content when the
finite numeric latency value alone is normalised. This check did not change or
rewrite either raw artifact.

The original audit incorrectly treated the raw file SHA-256 as a greedy
model-output identity, which would force a false reproducibility failure when
only timing telemetry changes.

## Corrected, frozen audit rule

The terminal audit will report two separate identities for every prediction
artifact:

1. `prediction_sha256`: exact raw bytes, retained for artifact integrity. The
   audit recomputes it and fails if it differs from the recorded evidence
   atlas.
2. `prediction_replay_content_sha256`: ordered, canonical JSONL content. Every
   field is retained except that a finite numeric `latency_ms` is replaced by a
   fixed `finite_numeric` marker. Missing latency and invalid latency values
   remain distinct and therefore fail equivalence.

`VERIFY_PASSED` requires five valid evidence atlases, raw-byte integrity for
each saved prediction file, one shared execution contract, and identical
replay-content hashes. Raw-byte differences are reported separately as
timing-metadata-only only when the replay-content hashes agree. No averages or
best-replica selection are permitted.

## Boundaries

This amendment changes no model, adapter, prompt, decoder, threshold, frozen
Pilot source/gold/policy, or inference artifact. It is an audit-method repair
identified before R3--R5 results are examined. The amended audit source and its
tests are versioned separately from the immutable inference code root used by
R1--R5.

The final supervisor dossier must cite both raw-byte integrity and this
replay-content reproducibility result. It must not state reproducibility until
the five-replica audit is terminal.
