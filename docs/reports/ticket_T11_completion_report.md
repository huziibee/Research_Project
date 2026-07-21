# Ticket completion report

## Ticket
- ID: T11
- Title: Research contract, AI governance, ethics, and licensing

## Preconditions checked
- T10 PASS and schema v2 (`2.0.0`) present — verified via `docs/reports/ticket_T10_completion_report.md`
- Proposal alignment and core/stretch policy available in `cursor_plan/`
- T02 licence manifest and inclusion register present and left as historical evidence
- No protected data, annotations, or model selection artefacts present

## Files created/changed

### Created — governance package
- `src/ambiguity_manager/governance/__init__.py`
- `src/ambiguity_manager/governance/errors.py`
- `src/ambiguity_manager/governance/hashing.py`
- `src/ambiguity_manager/governance/paths.py`
- `src/ambiguity_manager/governance/research_contract.py`
- `src/ambiguity_manager/governance/ai_use.py`
- `src/ambiguity_manager/governance/ethics.py`
- `src/ambiguity_manager/governance/dataset_licence.py`
- `src/ambiguity_manager/governance/model_licence.py`
- `src/ambiguity_manager/governance/core_stretch.py`
- `src/ambiguity_manager/governance/role_overlap.py`
- `src/ambiguity_manager/governance/protected_data.py`
- `src/ambiguity_manager/governance/validation.py`

### Created — configs and contract
- `configs/research/research_contract_v1.json`
- `configs/research/research_contract_v1.sha256`
- `configs/governance/core_stretch_policy.json`
- `configs/governance/ai_use_log_schema.json`
- `configs/governance/human_annotation_governance_schema.json`
- `configs/governance/human_annotation_governance.json`
- `configs/governance/protected_data_policy.json`
- `configs/licences/dataset_licence_register.json`
- `configs/licences/model_licence_register.json`

### Created — protocols and docs
- `docs/protocols/research_contract_v1.md`
- `docs/protocols/ai_use_log_instructions.md`
- `docs/protocols/human_annotation_governance.md`
- `docs/protocols/protected_data_policy.md`
- `docs/decisions/decision_record_template.md`
- `docs/decisions/deviation_record_template.md`
- `docs/dataset_cards/dataset_licence_register.md`

### Created — tracked governance logs
- `docs/governance/logs/generative_ai_use_log.jsonl`
- `docs/governance/logs/decision_log.jsonl`
- `docs/governance/logs/deviation_log.jsonl`
- `docs/governance/logs/protected_access_log.jsonl`
- `docs/governance/logs/role_overlap_log.jsonl`

### Created — scripts and tests
- `scripts/validate_governance.py`
- `tests/test_governance_hashing.py`
- `tests/test_governance_research_contract.py`
- `tests/test_governance_ai_use_log.py`
- `tests/test_governance_ethics.py`
- `tests/test_governance_dataset_licence.py`
- `tests/test_governance_core_stretch.py`
- `tests/test_governance_repo_smoke.py`

### Ethics resolution (2026-07-21)
- `docs/governance/evidence/ETHGOV-001_supervisor_only_determination.md`
- `docs/decisions/DEV-20260721-001_closure_of_DEV-20260711-001.md`
- Updated ethics schema/config/validators for `not_required` supervisor-only determination
- Append-only closure entry `DEV-20260721-001` in `docs/governance/logs/deviation_log.jsonl`

### Not modified by the ethics-resolution update
- Historical T12 measurement evidence that recorded `t11_status: BLOCKED` at measurement time
- D-Final technical implementation and response-mode probe code
- All T00–T10 data, schema, converter, and migration artefacts

## Tests written first, if applicable
- Test files: `tests/test_governance_*.py`
- Initial failing behaviour: `ModuleNotFoundError: No module named 'ambiguity_manager.governance'` across all new governance modules (Red phase)
- Ethics-resolution tests cover `not_required` PASS, evidence requirements, external-annotator hard guard, and deviation closure

## Commands run
- Red: `PYTHONPATH=src python -m unittest discover -s tests -p "test_governance*.py"` → FAILED (`ModuleNotFoundError`)
- Green: `PYTHONPATH=src python -m unittest discover -s tests` → OK (371 tests at infrastructure close-out)
- Governance CLI: `PYTHONPATH=src python scripts/validate_governance.py` → exit 0
- Ethics resolution: governance and T12 suites re-run after `not_required` update

## Validation results
- Research contract sidecar verifies against canonical UTF-8 JSON bytes
- Sidecar format: `<64-char lowercase sha256>  configs/research/research_contract_v1.json\n`
- Contract SHA-256: `224f1c0c315858bfe6c8e9a44f82f283735d127d386c902a9ee9e73ae6d29103`
- AI-use log contains evidence-backed aggregate backfill entries with Cursor and OpenAI tools; model revisions not recorded
- Ethics determination: `not_required`, basis `supervisor_only_annotation`, `collection_permitted: true` (supervisor-only scope)
- Dataset licence register v2 authoritative; unresolved/stated_unverified sources block training, evaluation, and redistribution via null permission gates
- Model register present with `selected_model: null`

## Acceptance criteria status
- [x] All seven systems are mandatory in the contract
- [x] Fine-tuning is mandatory for the proposed manager
- [x] No LVLM/raw-image scope remains
- [x] Human judgement collection cannot begin without a recorded determination
- [x] Licence status exists for every model/source intended for use (honest unresolved/null statuses)
- [x] Ethics/governance determination completed with institutional evidence — `not_required` for supervisor-only annotation (`ETHGOV-001`)

## Counts / metric outputs
- Governance test modules: under `tests/test_governance_*.py`
- AI-use backfill entries: 3
- Dataset licence register entries: 8
- Model licence register `selected_model`: null

## Evidence and traceability
- Input hashes/versions:
  - `configs/research/research_contract_v1.sha256` → `224f1c0c315858bfe6c8e9a44f82f283735d127d386c902a9ee9e73ae6d29103`
  - T02 historical manifest: `configs/datasets/licence_provenance_manifest.json` (unchanged)
  - ETHGOV-001 evidence SHA-256: `5ce312681b8faa1a9c74d88697558813a4062c0c03c546d9c270e931f66b6678`
- Output paths:
  - `configs/research/research_contract_v1.json`
  - `configs/governance/human_annotation_governance.json`
  - `configs/licences/dataset_licence_register.json`
  - `docs/governance/logs/generative_ai_use_log.jsonl`
  - `docs/governance/evidence/ETHGOV-001_supervisor_only_determination.md`
- Config/prompt/model versions: research contract `1.0.0`; ethics schema `1.0.0`; dataset licence register `2.0.0`

## Unresolved TODO_VERIFY / BLOCKED items
- None for the T11 ethics determination gate
- Dataset licence permissions remain `null` for unresolved external sources; training and official evaluation remain gated until verification or institutional/legal decision
- No model selected (`selected_model: null`; deferred to T12 Stage I)
- T13/T14 remain technically not ready (handbook, sampling freeze, annotation package, T12 model stability, supervisor role-separation protocol)

## Stage gate
**PASS/FAIL/BLOCKED:** PASS

**Reason:** Governance infrastructure is complete and the institutional determination is recorded as `not_required` for supervisor-only annotation. Ethics clearance is not required. An ethics waiver is not required. External annotators are not permitted. Scope change requires reassessment. This is **not** an ethics approval or exemption.

**Still active controls:** research contract, AI-use log, licence registers, core/stretch policy, decision/deviation templates, protected-data policy, validators, and tests.

**Annotation start rule:** `collection_permitted: true` does not authorise starting T13/T14 until their technical and protocol gates are satisfied.

## Related execution-order deviation

**DEV-20260711-001** historically authorised T12 preparatory work while T11 was BLOCKED on a pending ethics determination. That pending-ethics rationale is **closed / superseded** by **DEV-20260721-001** on the basis of **ETHGOV-001**. Completed work under DEV-20260711-001 remains valid. Historical T12 evidence that recorded T11 as BLOCKED at measurement time is preserved.
