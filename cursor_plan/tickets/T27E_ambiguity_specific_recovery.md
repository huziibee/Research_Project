# T27E - Ambiguity-Specific Structured Prediction Recovery

## Scope and stop condition

This ticket repairs and evaluates `predict_ambiguity_v1` only. CPC, intent,
interpretations, risk/capability, deterministic routing, and the T27D assembly
policy remain unchanged. T28 is prohibited until this ticket is explicitly
marked PASS by a human-approved stage gate.

## Verified starting preconditions

- T27D is blocked and T28 is prohibited.
- Immutable base: `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`.
- `selected_adapter`, `selected_model_strategy`, and official-use validity remain
  `null`, `null`, and `false`.
- T27D sealed ambiguity acceptance was 0/12 for base and adapter; all failures
  were bounded maximum-token unterminated JSON.
- CPC was accepted 12/12 in both modes; it is not modified here.
- Ambiguity has 68 strong training examples; the prior 36-step smoke consumed
  36/470 total task examples.
- Missing ambiguity remains `null`/unknown and blocks `execute` and
  `silently_resolve`; the deterministic router remains authoritative.

## Data exclusions

Only source-native `source_train` ambiguity labels may be used for adaptation.
The fresh diagnostic and sealed sets are source_dev-only and are disjoint by
source ID and group key from all T27/T27B/T27C/T27C-R1/T27D sets, model-selection
fixtures, source_holdout, T13 calibration, supervisor annotations, and the
future manual protected challenge namespace. No protected data is permitted.

## Frozen execution contract

`configs/model/t27e_ambiguity_recovery_v1.json` is frozen before any sealed
output is inspected. The diagnostic compares the existing ambiguity schema with
a constrained minimal schema containing only `ambiguity_present` and
`ambiguity_types`. Optional fields are omitted, never fabricated, and never
deterministically inferred.

The initial structural bound is 96 tokens: current ambiguity targets have
48-203 serialized target tokens (median 97), while minimal targets have
48-68 serialized character/token units (95th percentile 60). The live report
must replace these preliminary local measurements with tokenizer measurements.

## Decision paths

- Path A: constrained decoding is mechanically sound but the current contract
  expands or mismatches generation; apply only the minimal contract/decoder fix.
- Path B: constrained generation is mechanically sound and the minimal contract
  does not recover the task; train only ambiguity, traversing every eligible
  strong example at least once.
- Path C: apply the smallest structural correction first, then one bounded
  ambiguity-only adaptation if diagnostic evidence proves both defects.

No unconstrained fallback may count as model success. A deterministic fallback,
if retained, is only an unavailability fail-safe and cannot satisfy the gate.

## Live order

1. Run deterministic and focused tests.
2. Run the fresh 16-record current-vs-minimal diagnostic.
3. Inspect diagnostic evidence and freeze the selected repair path.
4. Freeze all sealed identities, hashes, thresholds, timeout, and rerun policy.
5. Run exactly one fresh 12-record sealed smoke.
6. Run unchanged assembly and verification.
7. Write the completion report and stop at the stage gate.
