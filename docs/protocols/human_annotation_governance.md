# Human Annotation Governance

## Determination record

Machine-readable record:
`configs/governance/human_annotation_governance.json`

Evidence:
`docs/governance/evidence/ETHGOV-001_supervisor_only_determination.md`

## Gate semantics

| Status | T11 verdict | Collection permitted |
| --- | --- | --- |
| `pending` | BLOCKED | false |
| `not_required` + supervisor-only evidence | PASS | true (supervisor-only scope only) |
| `approval_required` + evidence | PASS | false |
| `approved` | PASS | true |
| `exempt_confirmed` | PASS | true |
| `rejected` | FAIL/BLOCKED | false |
| `blocked` | BLOCKED | false |

### Current determination

- Status: `not_required`
- Basis: `supervisor_only_annotation`
- Ethics clearance required: false
- Ethics waiver required: false
- Annotators: Steven James and Benjamin Rosman (project supervisors only)
- External annotators permitted: false
- Reassessment required if scope changes: true

This is a determination that clearance and waiver are **not required** for the
current supervisor-only scope. It is **not** an ethics approval, exemption, or
waiver.

`collection_permitted: true` means only that the ethics/governance gate permits
annotation by the named project supervisors under the recorded scope. It does
**not** mean T13/T14 are technically ready, that a handbook or sampling freeze
exists, or that annotation collection has begun.

## External-annotator hard guard

Any future change involving an annotator who is not one of the project supervisors
must:

1. set `collection_permitted` to false;
2. block annotation collection;
3. require a fresh institutional determination;
4. prohibit data collection until that determination is recorded.

Leaving `determination_status = not_required` must not bypass this guard.

## Unresolved human fields

Fields marked `pending_human_confirmation` must remain null until confirmed by
the responsible authority. Confirmed supervisor-only fields are marked `recorded`.

## Stable pseudonyms

- Annotator A: `ANN-A`
- Annotator B: `ANN-B`
- Adjudicator: `ADJ-01`
- Author: `AUTHOR-01`
- Supervisor: `SUP-01`

Identity mapping is stored separately under access control.

## Role overlap

- One person cannot be Annotator A and Annotator B.
- An annotator cannot adjudicate their own record.
- An author cannot annotate their own scenario.
- Author/adjudicator overlap requires explicit authority approval per record.
- Supervisor participation must be disclosed per role and record.

Log overlaps in `docs/governance/logs/role_overlap_log.jsonl`.

## Blindness

Annotators must not see model-proposed labels, critiques, or other annotator
responses. Model suggestions cannot become gold without human verification.
