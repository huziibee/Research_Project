# T11 — Research contract, AI governance, ethics, and licensing

**Status:** COMPLETE
**Stage gate:** PASS
**Determination:** `not_required` (supervisor-only annotation)

## Shared context

T00–T10 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment.

## Required reference documents

- `11_proposal_alignment_contract.md`
- `12_core_stretch_policy.md`
- `docs/governance/evidence/ETHGOV-001_supervisor_only_determination.md`
- `docs/reports/ticket_T11_completion_report.md`

## Goal

Freeze the research claim and governance requirements before new data, model, or human-annotation work.

## Preconditions

- T10 passed and schema v2 exists.

## Required tasks

1. Create a versioned research contract containing the final research question, hypothesis, primary outcome, secondary outcomes, seven mandatory systems, claim boundaries, mandatory fine-tuning, and text-only scope.
2. Record that proposal dataset details and schedule are superseded while all other methodology remains binding.
3. Create the generative-AI use log schema and initial entries for planning/code assistance.
4. Obtain and record the supervisor/institutional determination for annotation/meta-evaluation ethics, consent, role overlap, personal data, compensation if any, pseudonymisation, storage, and deletion.
5. Create dataset and model licence registers with verified source links/references and permitted uses.
6. Define core versus stretch gate semantics exactly as in `12_core_stretch_policy.md`.
7. Create deviation and decision-log templates so later changes are explicit.

## Deliverables

- Frozen research-contract document.
- AI-use log and instructions.
- Human-annotation governance/ethics determination.
- Dataset/model licence registers.
- Decision/deviation templates.
- T11 completion report.

## Acceptance criteria

- [x] All seven systems are mandatory in the contract.
- [x] Fine-tuning is mandatory for the proposed manager.
- [x] No LVLM/raw-image scope remains.
- [x] Human judgement collection cannot begin without a recorded determination.
- [x] Licence status exists for every model/source intended for use.
- [x] Institutional determination recorded: clearance and waiver **not required** for supervisor-only annotation (`ETHGOV-001`).

## Determination summary

- Annotators: Steven James and Benjamin Rosman (project supervisors only)
- `determination_status`: `not_required`
- Ethics clearance required: false
- Ethics waiver required: false
- External annotators permitted: false
- Reassessment required if scope changes: true
- This is **not** an ethics approval, exemption, or waiver

## Stop condition

Governance documents and the ethics determination are recorded. Do not treat T13/T14 as started. Model selection remains a T12 Stage I concern (`selected_model` remains null until then).
