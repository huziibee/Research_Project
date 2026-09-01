# T44 independent confirmation: readiness-only protocol

## Scope and boundary

This package prepares the family-disjointness, source-rights and blinded-review
controls for T44. It creates no corpus, labels, model outputs or inference
jobs, and it does not change Pilot-120, a model, an adapter, prompts, decoding
or thresholds. A successful readiness check is not a held-out result and does
not permit an official or real-world generalisation claim.

## Required immutable inputs

Before any T44 label review, create and freeze all of the following:

1. A source licence/provenance ledger copied from
   `configs/evaluation/pilot120_t44_source_provenance_template.json`. It must
   identify the acquired source/version, retrieval manifest hash, usable
   licence evidence and a named approval for this study. It contains only
   record hashes and upstream identifiers, not labels or model output.
2. A hash-only Pilot comparison reference generated from
   `configs/evaluation/pilot120_t44_pilot_provenance_recovery_template.json`.
   It binds the comparison index to the current immutable Pilot source and
   frozen manifest. Its normalised fingerprint is only an exact/near-text aid;
   it cannot prove paraphrase lineage or scenario-family separation.
3. A three-axis ledger copied from
   `configs/evaluation/pilot120_t44_three_axis_exclusion_template.json`.
   Every future candidate must be checked against all of `pilot_120_v1`,
   `t41_new_source` and `t42_single_ambiguity` on every axis:
   `exact_record`, `paraphrase_or_derivation`, and `scenario_family`.
   A missing or future reference corpus is `NOT_COMPUTED`, not `NO_MATCH`.
   Paraphrase/derivation and scenario-family decisions require named human
   review plus an evidence reference; hash similarity is insufficient.
4. A blinded review packet copied from
   `configs/evaluation/pilot120_t44_review_packet_template.json`. It locks two
   different annotators, mutual/system-identity blinding, adjudication,
   denominator/eligibility rule, evaluator identity, and each T41
   interpretation field as `IN_SCOPE` or `NOT_COMPUTED` before label review.

The ledger only passes when candidate identifiers and source-record hashes are
identical across the source, exclusion and review artifacts. All three
comparison corpora must already have a frozen reference manifest. This strict
rule prevents an absent future T41/T42 corpus from being silently treated as
family-disjoint.

## CPU-only commands

```powershell
python scripts/pilot120_t44_readiness.py recover-pilot-reference `
  --output outputs/t44/pilot120_reference_recovery.json

python scripts/pilot120_t44_readiness.py validate `
  --provenance outputs/t44/source_provenance.json `
  --exclusion outputs/t44/three_axis_exclusion.json `
  --review-packet outputs/t44/review_packet.json `
  --pilot-reference outputs/t44/pilot120_reference_recovery.json `
  --output outputs/t44/readiness_validation.json
```

The commands refuse to overwrite an existing artifact. `T44_READINESS_VERIFY_PASSED`
means the supplied evidence is structurally complete; `NOT_COMPUTED` lists the
missing field, ledger axis or manifest. Neither status runs an evaluation.

## What remains after readiness passes

T44 still requires a new licensable corpus, frozen source/gold/protocol
manifests, double annotation/adjudication, pre-registered field eligibility
and denominators, the unchanged system/evaluator bundle, and terminal
evaluation artifacts. Only then may the result describe this specific
held-out, family-disjoint corpus; it never proves general superiority,
real-world robot safety or protected/official completion.
