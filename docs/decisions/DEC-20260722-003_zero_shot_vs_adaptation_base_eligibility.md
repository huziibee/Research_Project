# Decision Record — Separate zero-shot eligibility from adaptation-base eligibility

**Decision ID:** `DEC-20260722-003`  
**Date:** `2026-07-22`  
**Status:** accepted  
**Approver:** project author (Mohammed Bangie); supervisors to review  
**Affected tickets:** T12 close-out, T27–T28 (QLoRA development), T29–T30  
**Affected artefacts:** `configs/model/selected_identities_v1.json`, `configs/model/adaptation_base_selection_policy_v1.json`, `configs/model/base_model_selection_policy_v1.json` (unchanged zero-shot semantics), `src/ambiguity_manager/systems/model_identities.py`, `src/ambiguity_manager/model/base_model_selection.py`

## Summary

Zero-shot candidate eligibility and QLoRA adaptation-base eligibility are formally separate decisions. The frozen zero-shot bake-off under `base_model_selection_policy_v1.json` requires 4/4 Stage-1 transport acceptance and produced `zero_shot_candidate_status = rejected`. That rejection is immutable. A checkpoint may still be assessed and selected as an immutable development base under `adaptation_base_selection_policy_v1.json`, which does not require zero-shot Stage-1 pass and ranks candidates on structured-output reliability, severity-weighted safety, and related development criteria.

## Rationale

T12 demonstrated that none of the three shortlist candidates passed the strict zero-shot structured-output and safety gate. Erasing or superseding that evidence would contaminate the research record. QLoRA development nonetheless requires a technically viable immutable base checkpoint. Conflating zero-shot success with adaptation-base suitability would either force a false zero-shot acceptance or block all QLoRA work despite partial structured-output success on some candidates.

## Zero-shot status layer

| Field | Current value | Semantics |
|---|---|---|
| `zero_shot_candidate_status` | `rejected` | No candidate passed 4/4 Stage-1 hard gate; immutable |
| Policy | `base_model_selection_policy_v1.json` | Requires Stage-1 transport pass; unchanged |

Failed zero-shot evidence remains in `selected_identities_v1.json → bakeoff_outcome` and `configs/model/evidence/model_selection_bakeoff_v1/`.

## Adaptation-base status layer

| Field | Current value | Semantics |
|---|---|---|
| `adaptation_base_status` | `null` | Not yet assessed under adaptation-base policy (Phase D) |
| `selected_base_model` | `null` | Set only after frozen adaptation-base policy application |
| Policy | `adaptation_base_selection_policy_v1.json` | Does not require 4/4 zero-shot pass; frozen before application |

Adaptation-base selection is development-only. It does not set `selected_adapter`, `selected_model_strategy`, or `valid_for_official_use`.

## Legacy migration

The licence register field `selected_model` remains deprecated and must stay `null`. Official identity uses the three-part contract (`selected_base_model`, `selected_adapter`, `selected_model_strategy`) in `selected_identities_v1.json`. Loaders infer `zero_shot_candidate_status = rejected` from legacy `status = no_viable_base_candidate` when the explicit field is absent.

## Evidence

- `docs/decisions/ADR_T12_terminal_zero_shot_candidate_rejection.md`
- `docs/decisions/DEC-20260722-002_development_on_source_data_delayed_manual_protected_challenge.md`
- `docs/reports/base_model_shortlist_and_bakeoff.md`
- `configs/model/selected_identities_v1.json`
- `configs/model/adaptation_base_selection_policy_v1.json`

## Risk

- Selecting an adaptation base that failed zero-shot must be clearly documented as development-only, not official safety approval.
- Engineers must not rewrite `zero_shot_candidate_status` when a base is chosen for QLoRA.
- Two policies must remain separate files so zero-shot hard-gate semantics are not weakened retroactively.

## Required reruns

None for this decision record alone. Phase D adaptation-base application may require additional cluster evidence after Mistral diagnosis.
