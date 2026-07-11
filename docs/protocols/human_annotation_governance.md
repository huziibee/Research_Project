# Human Annotation Governance

## Determination record

Machine-readable record:
`configs/governance/human_annotation_governance.json`

## Gate semantics

| Status | T11 verdict | Collection permitted |
| --- | --- | --- |
| `pending` | BLOCKED | false |
| `approval_required` + evidence | PASS | false |
| `approved` | PASS | true |
| `exempt_confirmed` | PASS | true |
| `rejected` | FAIL/BLOCKED | false |
| `blocked` | BLOCKED | false |

Do not manufacture a determination to obtain PASS. Initial state is `pending`
until a responsible authority provides evidence.

## Unresolved human fields

Fields marked `pending_human_confirmation` must remain null until confirmed by
the responsible authority. Do not assume employment status, compensation,
retention, deletion, consent, or personal-data categories.

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
