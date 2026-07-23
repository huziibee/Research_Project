# T27D job-10065 task bottleneck audit

Job 10065 (`t12-qlora-task-conditioned-20260723T185137Z-6419cfc`) contained exactly 120 terminal calls: 60 base and 60 adapter, with 12 records × 5 tasks per mode. Constraint initialisation was 120/120 and unconstrained fallback was zero.

## Task-level result

| Task | Base accepted | Adapter accepted | Base failure | Adapter failure | Decision |
|---|---:|---:|---|---|---|
| `predict_intent_v1` | 3/12 | 10/12 | 9 bounded truncations | 2 bounded truncations | optional; never blocks assembly |
| `predict_cpc_v1` | 12/12 | 12/12 | none | none | retain unchanged |
| `predict_ambiguity_v1` | 0/12 | 0/12 | 12 bounded truncations | 12 bounded truncations | bottleneck; repair only this task |
| `predict_interpretations_v1` | 0/12 | 11/12 | 12 bounded truncations | 1 bounded truncation | optional; missing blocks silent resolution |
| `predict_risk_capability_v1` | 0/12 | 0/12 | 12 bounded truncations | 12 bounded truncations | optional fail-safe UNKNOWN |

No unknown-field, invalid-enum, invalid-nested-type, or empty-output category occurred. The raw attempts for rejected calls were unterminated JSON under the bounded maximum-token contract. Latency and all requested fields are recorded in `configs/model/evidence/t27d_job10065_task_failure_matrix.json`.

## Per-record required-task matrix

The old assembler failed all 24 mode-record assemblies because `predict_ambiguity_v1` failed everywhere; base additionally failed intent on 9 records and adapter on 2. CPC was accepted for all 24. Every record could have produced a production-valid fail-safe partial analysis: missing intent is nullable, missing ambiguity is `null`, missing interpretations is an empty candidate set, and missing risk/capability is UNKNOWN.

| Record | Base failed old requirements | Adapter failed old requirements | Safe partial assembly |
|---|---|---|---|
| `indirect_requests:test:124` | intent, ambiguity | ambiguity | yes |
| `ambik:625` | intent, ambiguity | ambiguity | yes |
| `indirect_requests:validation:169` | intent, ambiguity | intent, ambiguity | yes |
| `ambik:30` | intent, ambiguity | ambiguity | yes |
| `clara:5180` | intent, ambiguity | intent, ambiguity | yes |
| `codraw_icr_v2:8213` | intent, ambiguity | ambiguity | yes |
| `codraw_icr_v2:4720` | intent, ambiguity | ambiguity | yes |
| `codraw_icr_v2:14725` | ambiguity | ambiguity | yes |
| `codraw_icr_v2:9548` | intent, ambiguity | ambiguity | yes |
| `codraw_icr_v2:12748` | ambiguity | ambiguity | yes |
| `vague:3089_XMEN_FIRST_CLASS_00.17.07.819-00.17.11.788@0` | intent, ambiguity | ambiguity | yes |
| `codraw_icr_v2:11414` | ambiguity | ambiguity | yes |

## Supervision and coverage

The training set had 470 examples: ambiguity 68, CPC 124, intent 124, interpretations 124, and risk/capability 30. Intent, interpretations, and risk/capability were weak-label-only; ambiguity and CPC had strong labels. At 36 optimiser steps, only 36/470 = 7.6596% of examples were consumed, although round-robin sampling reached each task. Aggregate loss therefore cannot establish per-task learning.

## Classification and repair decision

- `predict_intent_v1`: retain as optional auxiliary output. No dependable speech-act supervision exists; free-text intent never substitutes for `speech_act`.
- `predict_cpc_v1`: retain unchanged. It is not a bottleneck and is accepted 24/24.
- `predict_ambiguity_v1`: retain as a routing-relevant optional task with fail-safe unknown semantics; repair this task only. Missing ambiguity never becomes `false`.
- `predict_interpretations_v1`: retain optional; missing candidates permit clarify but prohibit `silently_resolve`.
- `predict_risk_capability_v1`: retain optional only; missing values default to UNKNOWN and block execute. No recovery cycle is justified for its weak supervision.

The selected path is eligibility-aware assembly plus a bottleneck-specific ambiguity repair diagnostic. No CPC split was selected, no adapter was selected, and no broad retraining was justified by this audit.
