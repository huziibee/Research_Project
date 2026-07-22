# Annotation Role and Blindness Policy v1

**Version:** `1.0.0`  
**Effective date:** `2026-07-22`  
**Status:** frozen for T13 calibration  
**Machine config:** `configs/annotation/annotation_roles_v1.json`  
**Ethics basis:** `ETHGOV-001` (`not_required`, supervisor-only)

## Roles

| Pseudonym | Person | Official annotation role |
|---|---|---|
| `AUTHOR-01` | Mohammed Bangie | Dataset author and quality reviewer |
| `ANN-A` | Steven James | Official Annotator A |
| `ANN-B` | Benjamin Rosman | Official Annotator B |
| `ADJ-01` | unresolved | Deferred to T14 adjudication policy |

## Author policy (`AUTHOR-01`)

- May create scenarios and review data quality.
- May label handbook examples and synthetic interface tests.
- Handbook and synthetic labels are **excluded** from official evaluation gold.
- **Must not** be assigned as `ANN-A` or `ANN-B` on official records.
- May act as process clerk for package administration only.
- Must not cast an automatic adjudication label vote.

## Official annotator policy

- Only Steven James (`ANN-A`) and Benjamin Rosman (`ANN-B`) may annotate official calibration and main records.
- External annotators are forbidden without ethics reassessment.
- One person cannot be both `ANN-A` and `ANN-B`.
- Both annotators receive the **same official record set**.
- Record order differs deterministically between packages.
- Neither annotator may see the other’s answers before independent submission.

## Blindness controls

Hidden from annotator packages:

- intended design-cell labels;
- author notes and review codes;
- intended answers / author expectations;
- model outputs and critiques;
- peer annotations;
- adjudication drafts.

Visible to annotators:

- command;
- dialogue history;
- scene context;
- capability context;
- visible provenance category;
- handbook / schema / package version stamps.

## Immutability and gold formation

- Raw `ANN-A` and `ANN-B` submissions are immutable after acceptance.
- Adjudication must retain both originals.
- No single annotation may silently become gold.
- Final gold export requires completed adjudication under the T14 policy.
- Calibration records do not automatically enter the main gold set.

## Conflict-of-interest disclosure

Supervisor participation as annotators must be disclosed per record in
`docs/governance/logs/role_overlap_log.jsonl` when collection begins.
Adjudicator identity remains unresolved until T14 approval.
