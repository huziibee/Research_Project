# T13 Foundation and Calibration Report

**Date:** 2026-07-22  
**Branch:** `feature/t12-cluster-redesign`  
**Decision:** `DEC-20260722-001`

## Ticket amendment

- `selected_model` is not a T13 prerequisite.
- T13 is human-programme / dataset preparation.
- Local-LLM authoring is optional future tooling.
- Calibration n=24; main target n=300; expansion to 400 conditional.
- No official gold in T13.
- Roles: Mohammed Bangie (`AUTHOR-01`); Steven James (`ANN-A`); Benjamin Rosman (`ANN-B`).
- T14A tooling may proceed; T14B/T14C pending.
- T16–T24 interface/synthetic work may proceed while annotation is pending.

## Roles and blindness

See `docs/protocols/annotation_role_policy_v1.md` and
`configs/annotation/annotation_roles_v1.json`.

## Handbook / schema versions

| Artefact | Version |
|---|---|
| Handbook | `1.0.0` (`docs/protocols/annotation_handbook_v1.md`) |
| Annotation schema | `1.0.0` (`configs/annotation/annotation_schema_v1.json`) |
| Intent taxonomy | `1.0.0` |
| Route precedence | `1.0.0` |
| Design cells | `1.0.0` |
| Package version | `1.0.0` |

## Intent taxonomy

`directive_command`, `indirect_request`, `information_question`,
`permission_request`, `prohibition`, `conditional_directive`, `multi_intent`,
`other_non_actionable`.

## Design-cell plan

Stratified 300-record target in `configs/annotation/design_cells_v1.json`
(not a full Cartesian product).

## Calibration coverage

Exactly 24 human-authored calibration candidates were frozen.

Coverage gates (from tooling):

- all five routes present
- all risk levels present
- all capability statuses present
- all schema-v2 ambiguity types present
- clear, single, and compound cases present
- direct and indirect proxies present
- context-rich and minimal-context present
- safety-sensitive cases present

Machine report: `data/annotations/t13/reports/calibration_quality.json`  
Hashes: `data/annotations/t13/reports/calibration_package_hashes.json`

## Duplicate / contamination

Deterministic exact, normalised, and context-command duplicate checks are
implemented. Calibration source package reports are written under
`data/annotations/t13/reports/`. No official gold fields are present.

## Confirmation

- No official gold labels were created.
- No real supervisor annotation occurred in this delivery.
- Main 300 package was **not** frozen.
- Main-pool templates and remaining-count artefacts exist under
  `data/annotations/t13/main_pool_readiness/`.

## Open supervisor-review questions

1. Approve handbook v1 and intent taxonomy for calibration annotation?
2. Confirm adjudication policy direction for T14C (ADJ-01 still unresolved)?
3. After calibration, approve proceeding to main-package authoring toward n=300?
4. Any calibration records to quarantine/replace before T14B?

## Next step after calibration review

Begin T14B calibration annotation by ANN-A and ANN-B using the frozen packages,
then revise handbook only if agreement gates fail, before freezing the main 300
package.
