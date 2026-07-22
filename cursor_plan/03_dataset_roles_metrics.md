# 03 — Dataset Roles, Gold Fields, and Machine-Enforced Eligibility

The dataset details in the original proposal are superseded. This document reflects the current repository and must be converted into a versioned machine-readable manifest in T15.

## Current source roles

| Source | Intended role | Status rule |
|---|---|---|
| AmbiK | ambiguity, clarification, embodied command cases | use only verified native/mapped fields |
| IndirectRequests | pragmatic/indirect intent recovery | use only verified intent fields |
| CoDraw-iCR v2 | dialogue and scene-grounded clarification | conditional on acquired schema/licence evidence |
| VAGUE | context-dependent interpretation | conditional on verified textual context and targets |
| CLARA/SaGC-derived source | clear/ambiguous/infeasible and routing signals | conditional on verified label semantics |
| ClariQ | auxiliary clarification development/style | not robot gold unless a written protocol decision says otherwise |
| Manual compound benchmark | interpretation sets, compound ambiguity, risk, capability, route, strategy sequence | required human-adjudicated gold |
| Optional safety challenge data | stress testing only | separate manifest and separately reported |

T15 must inspect actual files and completion reports rather than assume every listed source is available or eligible.

## Development versus protected partitions (`DEC-20260722-002`)

| Partition | Role | Development use | Protected / official use |
|---|---|---|---|
| Existing source datasets (AmbiK, IndirectRequests, CLARA/SaGC-derived, etc.) | verified native/mapped labels where available | permitted for model selection, training, prompts, thresholds, and ablations with explicit metric eligibility per record | eligible only where T15 manifest assigns the metric and split |
| Synthetic fixtures | interface, evaluator, and smoke validation | permitted; hand-authored; must not derive from T13 calibration | not official gold |
| T13 calibration (n=24) | annotation-process calibration only | **forbidden** — not development gold, not bake-off, not training, not synthetic evaluator input | **forbidden** |
| Future `manual_protected_challenge_set` (~300 adjudicated records) | planned supervisor-double-annotated protected challenge set | **forbidden** — does not exist yet; must not influence model selection, training, adapter choice, prompts, thresholds, or policy editing | unlocked only after T29 protocol freeze for T30 execution |

Weak or unavailable labels must not be invented. Missing gold stays `null` and excludes the record from that metric.

## Gold-field policy

A record is eligible only when required gold is verified. Canonical gold may include:

- `gold_intent` / speech act;
- `gold_cpc_frame` and canonical slots;
- `gold_valid_interpretations`;
- `gold_intended_interpretation` when known;
- `gold_uniquely_resolvable`;
- `gold_unresolved_slots`;
- `gold_supporting_evidence`;
- `gold_ambiguity_types`;
- `gold_risk_level`;
- `gold_capability_status`;
- `gold_route`;
- `gold_strategy_sequence`;
- `gold_clarification_targets`;
- `gold_rejection_reason`;
- `gold_resolved_slots` for silent resolution.

Missing gold stays `null` and excludes the record from that metric.

## Interpretation and CPC eligibility

| Metric family | Required gold |
|---|---|
| Intent/speech-act accuracy | `gold_intent` |
| CPC slot precision/recall/F1 | `gold_cpc_frame` with applicable slots |
| CPC exact match | complete required CPC fields |
| Candidate-set precision/recall/F1 | `gold_valid_interpretations` |
| Selected-interpretation accuracy | unique/context-resolved gold interpretation |
| Unsupported commitment | unresolved/ non-unique gold plus valid candidates |
| Hallucinated detail | evidence-bearing command/context and canonical slots |
| Context consistency | evidence links or resolvable contextual target |
| Unresolved-slot F1 | `gold_unresolved_slots` |
| Silent-resolution correctness | `gold_resolved_slots` and route eligibility |

## Routing/classification eligibility

| Metric family | Required gold |
|---|---|
| Routing correctness / route F1 | `gold_route` |
| Ambiguity micro/macro F1 | `gold_ambiguity_types` |
| Exact ambiguity-set match | complete ambiguity set |
| Risk metrics | `gold_risk_level` |
| Capability metrics | `gold_capability_status` |
| Clarification precision/recall/F1 | `gold_route` and clarification eligibility |
| Clarification-target correctness | `gold_clarification_targets` |
| Safe rejection / rejection reason | rejection eligibility and reason |
| Unsafe silent-resolution rate | risk/safety gold and route gold |
| Multi-step exact sequence | `gold_strategy_sequence` |
| Context benefit | paired context/no-context eligibility |

## Machine-readable manifest

T15 must produce a schema-validated manifest consumed by T24, T26, T29, and T30. It must include:

```yaml
metrics:
  cpc_exact_match:
    required_fields: [gold_cpc_frame]
    eligible_sources: [manual_compound]
  route_correctness:
    required_fields: [gold_route]
    eligible_sources: [manual_compound, ambik, clara, codraw_icr_v2]
  silent_resolution_value_f1:
    required_fields: [gold_resolved_slots]
    eligible_sources: [manual_compound]
```

The manifest must be generated from verified repository evidence, not copied blindly from this example.

## Split and leakage rules

Keep together all related:

- paraphrases and generated siblings;
- template/seed families;
- dialogue/scene families;
- source pairs and counterfactual variants;
- context-present/context-removed pairs;
- manually authored derivatives.

Run exact, normalised, fuzzy, and semantic near-duplicate checks. Freeze train/dev/test and a separate optional challenge set. Every reported metric includes eligible `N`, included sources, and excluded-count reasons.
