# T42 — Single-ambiguity frozen study

**Status:** CPU_READINESS_VERIFIED; NEW-CORPUS STUDY NOT QUEUED; RESULTS NOT COMPUTED

Produce a new, independently frozen corpus in which every row has exactly one
adjudicated unresolved ambiguity instance of exactly one type, with no secondary
ambiguity. It is not a Pilot subset and not the deferred `+80` expansion. Pre-register source audit,
stratification, sample-size/precision, annotation/adjudication, cost policy,
and fixed inference configuration. Its exclusion ledger must prove no record,
paraphrase lineage, or scenario-family overlap with Pilot-120, T44, or any
future T41 new source material.

**Acceptance:** immutable source/gold/protocol manifests; freeze validator proves
exactly one unresolved ambiguity instance/type and zero secondary ambiguities;
support-qualified and count-only slices; fixed-system metrics and
uncertainty limited to this corpus and its eligible strata; explicit safety
limitations.

## CPU-only readiness record (2026-09-01)

`configs/evaluation/t42_single_ambiguity_study_scaffold_v1.json` and
`scripts/pilot120_t42_single_ambiguity_readiness.py` now reject multi-instance,
multi-type, resolved or secondary-ambiguity records and require three-axis
cross-study exclusion evidence before a future freeze can pass. The scaffold
reports `T42_READINESS_SCAFFOLD_PASSED` only as an implementation check; it is
not a corpus, metric, or single-ambiguity claim.

An independent licensable source, source audit, blinded annotation and
adjudication, frozen exclusion ledger and fixed-system evaluation remain
required. Pilot-120 is still ineligible and is not relabelled or extended.
