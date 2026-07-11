# T11 — Research contract, AI governance, ethics, and licensing

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `11_proposal_alignment_contract.md`
- `12_core_stretch_policy.md`

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

- [ ] All seven systems are mandatory in the contract.
- [ ] Fine-tuning is mandatory for the proposed manager.
- [ ] No LVLM/raw-image scope remains.
- [ ] Human judgement collection cannot begin without a recorded determination.
- [ ] Licence status exists for every model/source intended for use.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after governance documents are approved. Do not install or select a model.
