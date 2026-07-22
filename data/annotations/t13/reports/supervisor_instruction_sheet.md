# T13 Calibration Supervisor Instruction Sheet

**Package version:** `1.0.0`  
**Handbook version:** `1.0.0`  
**Annotation schema version:** `1.0.0`  
**Partition:** calibration (n=24)

## Annotators

- **ANN-A:** Steven James — package `data/annotations/t13/assignments/ANN-A/t13-calibration-ANN-A-v1.jsonl`
- **ANN-B:** Benjamin Rosman — package `data/annotations/t13/assignments/ANN-B/t13-calibration-ANN-B-v1.jsonl`

## Before you start

1. Read `docs/protocols/annotation_handbook_v1.md`.
2. Read `docs/protocols/annotation_role_policy_v1.md`.
3. Confirm your package hash against `data/annotations/t13/manifests/`.

## Rules

- Annotate independently. Do not discuss labels with the other annotator before submission.
- Use only the visible fields in your package.
- Do not invent unsupported scene details.
- Calibration labels refine the handbook; they do not automatically become official gold.
- Return one submission JSONL with all 24 `record_id` values.

## Out of scope for this package

- Creating main-set records
- Adjudication
- Model-assisted labelling
- Changing handbook rules mid-package

## Contact

Package administration / process clerk: Mohammed Bangie (`AUTHOR-01`).  
Mohammed does not act as ANN-A or ANN-B.
