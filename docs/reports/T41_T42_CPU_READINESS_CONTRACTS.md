# T41/T42 CPU readiness contracts

## Status and boundary

This is a readiness-only specification for the two studies that follow the
Pilot-120 T39/T40 early analysis. It creates no source record, annotation,
prediction, model invocation, metric, or science result. It does not modify
Pilot-120, the manager, adapter, prompt, decoder, threshold, model selection,
or frozen data. It is not part of the final supervisor handover.

Both contracts are CPU-only validators. They may verify future supplied files,
but cannot turn absent human evidence into a score. At this point all
interpretation and single-ambiguity performance claims remain
`NOT_COMPUTED`.

## T41: interpretation-quality sidecar

The committed contract is
[`t41_interpretation_sidecar_contract_v1.json`](../../configs/evaluation/t41_interpretation_sidecar_contract_v1.json).
It specifies a new, independently sourced sidecar row with immutable source,
lineage, scenario-family, and input fingerprints. It requires adjudicated gold
for all seven missing target families:

- intent and evidence spans;
- CPC slot map, critical slots, and evidence spans;
- admissible candidate interpretations;
- explicit resolution values, evidence, and safety rationale;
- clarification target and semantic wording criteria;
- rejection target and semantic wording criteria; and
- silent-resolution permission, values, evidence, and safety rationale.

Two distinct reviewer assignments must each be blind to system identity,
system predictions, and the other reviewer's labels. The adjudication record
then records agreement per target family and the final adjudicated gold. The
validator refuses review packets containing `system_id`, a prediction, or raw
model output.

The frozen score contract makes targets explicit. Intent is exact canonical
label equality; CPC reports exact slot map and slot precision/recall/F1;
candidates use one-to-one matching and exact-set accuracy; resolution compares
value, evidence, permission, and safety rationale; clarification and rejection
score decision, target, and semantic wording criteria separately. A terminal
route is never a proxy for any of these. Any missing adjudicated target or
required system field is `NOT_COMPUTED`.

Readiness check (writes a new report and does not annotate):

```powershell
python scripts/pilot120_t41_interpretation_readiness.py contract `
  --contract configs/evaluation/t41_interpretation_sidecar_contract_v1.json `
  --output outputs/t41_readiness_contract.json
```

When independent source material, two blind review JSONLs, and adjudication
exist, the `study` subcommand validates their joint coverage before a separate,
frozen scorer may run. This validator itself deliberately produces no score.

## T42: single-ambiguity study

The committed scaffold is
[`t42_single_ambiguity_study_scaffold_v1.json`](../../configs/evaluation/t42_single_ambiguity_study_scaffold_v1.json).
It is explicitly neither a Pilot-120 subset nor the deferred `+80` records.
Each future record must have exactly one unresolved ambiguity instance, one
non-empty scalar ambiguity type, no secondary ambiguity records, three explicit
eligibility assertions, two distinct blind-review assignments, and final
adjudication. The validator rejects a missing, resolved, multi-instance,
multi-type, or secondary ambiguity record.

Before a future corpus can be marked frozen, its records and source audit must
have hashes, and its exclusion ledger must prove `no_overlap` for every record
against all three comparators: Pilot-120, T41's new sidecar source, and T44's
independent confirmation source. The proof covers record identity, input
fingerprint, source lineage, and scenario family. Because neither the T41 nor
T44 source ledger exists yet, the supplied scaffold cannot pass the future
freeze validator and correctly remains `NOT_COMPUTED`.

Readiness check:

```powershell
python scripts/pilot120_t42_single_ambiguity_readiness.py scaffold `
  --scaffold configs/evaluation/t42_single_ambiguity_study_scaffold_v1.json `
  --output outputs/t42_readiness_scaffold.json
```

The future `validate` command requires a record JSONL, exclusion ledger, and
fully frozen manifest. Passing it establishes eligibility only; a separately
registered fixed-system evaluation and support-qualified reporting are still
required. It does not establish compound-ambiguity, isolated-context, or
generalisation claims.

## Current blockers

1. An independently licensed source corpus and source audit have not been
   supplied for either study.
2. No new sidecar annotations, independent blind reviews, or adjudications
   exist.
3. T41/T42/T44 cross-study lineage and scenario-family ledgers do not exist,
   so a family-disjoint freeze cannot honestly be asserted.
4. No fixed-system output contract for the future studies has been frozen.

These are study prerequisites, not implementation defects. No cluster job is
appropriate until the new-source and human-review prerequisites are supplied
and frozen.
