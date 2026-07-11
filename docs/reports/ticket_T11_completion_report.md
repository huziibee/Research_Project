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

### Not modified
- `src/ambiguity_manager/paths.py`
- `configs/datasets/licence_provenance_manifest.json`
- `configs/datasets/dataset_inclusion_register.json`
- All T00–T10 data, schema, converter, and migration artefacts

## Tests written first, if applicable
- Test files: `tests/test_governance_*.py`
- Initial failing behaviour: `ModuleNotFoundError: No module named 'ambiguity_manager.governance'` across all new governance modules (Red phase)

## Commands run
- Red: `PYTHONPATH=src python -m unittest discover -s tests -p "test_governance*.py"` → FAILED (`ModuleNotFoundError`)
- Green: `PYTHONPATH=src python -m unittest discover -s tests` → OK (371 tests)
- Governance CLI: `PYTHONPATH=src python scripts/validate_governance.py` → exit 0

## Validation results
- 371 tests pass (322 pre-existing + 49 new governance tests)
- Research contract sidecar verifies against canonical UTF-8 JSON bytes
- Sidecar format: `<64-char lowercase sha256>  configs/research/research_contract_v1.json\n`
- Contract SHA-256: `224f1c0c315858bfe6c8e9a44f82f283735d127d386c902a9ee9e73ae6d29103`
- AI-use log contains three evidence-backed aggregate backfill entries with Cursor and OpenAI tools; model revisions not recorded
- Ethics determination initial state: `pending`, `collection_permitted: false`
- Dataset licence register v2 authoritative; all unresolved/stated_unverified sources block training, evaluation, and redistribution via null permission gates
- Model register present with `selected_model: null`

## Acceptance criteria status
- [x] All seven systems are mandatory in the contract
- [x] Fine-tuning is mandatory for the proposed manager
- [x] No LVLM/raw-image scope remains
- [x] Human judgement collection cannot begin without a recorded determination (`collection_permitted: false` while pending)
- [x] Licence status exists for every model/source intended for use (honest unresolved/null statuses)
- [ ] Ethics/governance determination completed with supervisor/institutional evidence — **BLOCKED: still `pending`**

## Counts / metric outputs
- Governance test modules: 6
- New governance tests: 49
- AI-use backfill entries: 3
- Dataset licence register entries: 8
- Model licence register entries: 0

## Evidence and traceability
- Input hashes/versions:
  - `configs/research/research_contract_v1.sha256` → `224f1c0c315858bfe6c8e9a44f82f283735d127d386c902a9ee9e73ae6d29103`
  - T02 historical manifest: `configs/datasets/licence_provenance_manifest.json` (unchanged)
- Output paths:
  - `configs/research/research_contract_v1.json`
  - `configs/governance/human_annotation_governance.json`
  - `configs/licences/dataset_licence_register.json`
  - `docs/governance/logs/generative_ai_use_log.jsonl`
- Config/prompt/model versions: research contract `1.0.0`; ethics schema `1.0.0`; dataset licence register `2.0.0`

## Unresolved TODO_VERIFY / BLOCKED items
- **Single remaining blocker:** supervisor/institutional ethics determination evidence is not yet available
  - `determination_status: "pending"`
  - `determination_status_evidence: null`
  - Human fields remain `pending_human_confirmation`
- Dataset licence permissions remain `null` for all external sources; training and official evaluation are gated off until verification or institutional/legal decision
- No model selected (deferred to T12)

## Stage gate
**PASS/FAIL/BLOCKED:** BLOCKED

**Reason:** All deterministic T11 governance infrastructure is implemented and validated, but the ethics determination remains `pending` with no responsible-authority evidence. Per approved gate semantics, T11 cannot PASS while the determination itself is pending. Human annotation collection (T13/T14) remains blocked.

**Infrastructure complete:** research contract, AI-use log, licence registers, core/stretch policy, decision/deviation templates, protected-data policy, validators, and tests.

**Unblock path:** Record supervisor/institutional determination with evidence (`approved`, `exempt_confirmed`, or `approval_required` with evidence reference) and confirm pending human-governance fields.
