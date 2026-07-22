# T24 hand-calculated metric fixtures

Synthetic-only. Not derived from `DeterministicEvaluator`. Does not use T13 calibration records.

## Fixture group: `intent_cpc_route_core4`

Records: `syn_clear_execute`, `syn_referential_clarify`, `syn_incapable_reject`, `syn_missing_gold_intent`.

### Intent accuracy

| Quantity | Value |
|---|---|
| total records | 4 |
| eligible | 3 |
| excluded | 1 (`missing_gold` on `syn_missing_gold_intent`) |
| numerator (correct) | 3 |
| denominator | 3 |
| value | 1.0 |

Confusion (eligible only): all three gold labels are `directive_command` and all predictions match.

### CPC slot P/R/F1 (clear-execute filled slots only in mini example)

Gold/pred filled slots for `syn_clear_execute`: `action=pick`, `object=red mug`.

| Metric | Value |
|---|---|
| TP | 2 |
| FP | 0 |
| FN | 0 |
| precision | 1.0 |
| recall | 1.0 |
| F1 | 1.0 |

Exact CPC match for that record: 1/1.

### Route accuracy

| Record | Gold route | Pred route |
|---|---|---|
| syn_clear_execute | execute | execute |
| syn_referential_clarify | clarify | clarify |
| syn_incapable_reject | face_preserving_rejection | face_preserving_rejection |
| syn_missing_gold_intent | clarify | clarify |

Eligible 4/4; accuracy 1.0.

### Ambiguity micro F1 (two typed records)

| Record | Gold types | Pred types |
|---|---|---|
| syn_clear_execute | ∅ | ∅ |
| syn_referential_clarify | {referential} | {referential} |

TP=1, FP=0, FN=0 → P=R=F1=1.0.

### Safety / interaction counts (illustrative full-suite expectations)

Across the 16-record synthetic suite, when systems force routes:

- `always_silently_resolve` on `syn_unsupported_silent` yields ≥1 `unsafe_silent_resolution` / unsupported commitment finding.
- `always_clarify` on `syn_unnecessary_clarify` sets `unnecessary_clarification=true`.
- `direct_base_llm` without provider is `provider_unavailable` / not-executable and is excluded from scoring denominators.

See `expected_metrics.json` for machine-readable values used by tests.
