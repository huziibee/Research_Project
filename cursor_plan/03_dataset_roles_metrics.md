# 03 — Dataset Roles and Metric Alignment

This document records the approved dataset strategy. It is reference context, not a ticket.

## Approved dataset policy

The final experiment may use the following sources, subject to real-file, schema, licence, and label verification:

| Dataset | Intended role | Core/auxiliary status | Final-use condition |
|---|---|---|---|
| AmbiK | embodied ambiguity, clarification, ambiguity labels | core | real fields and mappings verified |
| IndirectRequests | pragmatic/indirect intent recovery | core | real fields and mappings verified |
| CLARA/SaGC | clear/ambiguous/infeasible and risk/capability routing | conditional core | label meanings verified from source documentation |
| CoDraw-iCR v2 | dialogue and scene-grounded clarification | conditional core | acquired and schema verified |
| VAGUE | context-dependent disambiguation | conditional core | acquired and schema verified; text/caption path allowed |
| ClariQ | clarification style/auxiliary training | auxiliary only | never treated as robot gold without explicit decision |
| SafeAgentBench | safety/rejection stress test | optional integration/challenge | included only through a documented mapping and separate results |
| Manual compound extension | compound ambiguity, risk, strategy sequence | required gold contribution | target size and coverage matrix frozen before annotation |
| TEACh/TEACh-DA | broader embodied dialogue | dropped unless later justified | requires a recorded change decision |

CoDraw-iCR, VAGUE, and ClariQ are approved additions. Dropping TEACh from the core benchmark is approved. SafeAgentBench remains optional and must never be silently mixed into core gold results.

## Mandatory dataset decision register

Before final splits, create `docs/decisions/dataset_inclusion_register.md` with one row per candidate source:

- included, excluded, auxiliary, or challenge-only;
- verified file/version;
- licence status;
- actual row count;
- supported labels;
- unsupported labels;
- mapping confidence;
- role in train/dev/test/challenge;
- reason for final decision.

## Metric-to-dataset alignment

| Metric | What is compared | Strongest eligible sources |
|---|---|---|
| Routing correctness | predicted route vs adjudicated gold route | manual compound, AmbiK, verified CLARA, verified CoDraw-iCR |
| Ambiguity classification | predicted label set vs gold label set | manual compound, AmbiK, verified context datasets |
| Risk classification | predicted low/medium/high vs gold | manual compound, verified CLARA, optional safety challenge |
| Capability classification | predicted capability status vs gold | manual compound, verified CLARA |
| Clarification decision | clarify vs not clarify | AmbiK, CoDraw-iCR, verified CLARA |
| Clarification target | predicted missing fields/target vs gold | AmbiK, CoDraw-iCR, manual compound |
| Intent/slot correctness | predicted interpretation vs gold | IndirectRequests, VAGUE, CoDraw-iCR, AmbiK where supported |
| Rejection behavior | correct rejection and explanation target | manual compound, verified CLARA, SafeAgentBench challenge if included |
| Compound sequence correctness | complete strategy sequence vs gold | manual compound |
| Context benefit | paired with-context vs without-context change | VAGUE, CoDraw-iCR, manual paired examples |

## Gold versus weak labels

- Source-native, verified labels may be gold for the exact field they support.
- Project-inferred labels are weak until manually reviewed or adjudicated.
- Missing fields remain `null`; they are not inferred merely to make a record complete.
- Auxiliary datasets may support training or prompt development but do not automatically enter final gold evaluation.
- Final metrics must state the eligible denominator per metric because not every dataset supports every label.

## Data integrity requirements

- Preserve source IDs and source split.
- Add `group_id` for paraphrases, dialogue episodes, scene variants, and generated siblings.
- Run exact and near-duplicate detection before splitting.
- Group-related records into a single split.
- Maintain a licence manifest and dataset card.
- Freeze a protected final test set and a separate robustness/challenge set.
