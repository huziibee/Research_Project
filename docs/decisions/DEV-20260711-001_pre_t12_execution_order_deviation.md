# Deviation Record — Pre-T12 execution-order exception

**Deviation ID:** `DEV-20260711-001`  
**Date:** 2026-07-11  
**Status:** accepted  
**Change type:** execution_order_exception  
**Approver:** Mohammed Bangie / AUTHOR-01, project owner  
**Approval basis:** Explicit human approval in the project execution workflow  
**Protocol version before:** research contract `1.0.0`; T11 governance infrastructure complete  
**Protocol version after:** unchanged (execution-order exception only; no protocol amendment)  
**Affected tickets:** T11, T12  
**Affected artefacts:**  
- `docs/governance/logs/deviation_log.jsonl`  
- `docs/decisions/DEV-20260711-001_pre_t12_execution_order_deviation.md`  
- `cursor_plan/tickets/T12_local_text_model_and_training_stack_setup.md`  
- `cursor_plan/05_master_execution_plan.md`  
- `docs/reports/ticket_T11_completion_report.md`  

## Ethics disclaimer

The institutional ethics determination remains pending. This deviation does not constitute or imply institutional ethics approval.

## Summary

Authorise T12 local hardware measurement, model/runtime evaluation, schema-v2 inference on synthetic or existing non-protected fixtures, licence review, and a minimal adapter-load feasibility probe **while T11 remains BLOCKED** on the pending supervisor/institutional ethics determination for future human annotation.

This is a narrow execution-order deviation. It does not change the T11 stage gate, lift annotation-collection blocks, or satisfy the T11 ethics precondition for human-gold work. T12 must still satisfy its own ticket acceptance criteria; completion requires a selected base model/revision that meets licence and schema-v2 gates, not an indefinitely provisional placeholder.

## Rationale

1. **T11 remains BLOCKED.** Its verdict must not be changed to PASS. T11 governance infrastructure is complete and committed, but `determination_status: "pending"` with `collection_permitted: false` continues to block all human-annotation activity.

2. **The pending determination continues to block:**
   - external human recruitment;
   - annotation collection;
   - Annotator A/B activity;
   - adjudication;
   - semantic-relation human judgement;
   - any release of human annotation data.

3. **T12 is authorised** because its permitted scope is limited to:
   - recording actual RTX 3070 hardware and environment facts;
   - configuring local inference and training environments;
   - verifying model cards and model licences;
   - testing candidate models on synthetic or existing non-protected schema-v2 fixtures;
   - measuring schema validity, latency, VRAM, and repeatability;
   - performing a minimal adapter-load feasibility probe without research-data training;
   - selecting the T12 base model/revision for the later experimental path, with any later replacement requiring a recorded decision or deviation.

4. **T12 must not:**
   - use protected data;
   - generate benchmark scenarios;
   - collect annotations;
   - fine-tune on research datasets;
   - use external datasets whose training/evaluation permissions remain unresolved;
   - must not begin T13;
   - must not begin T14;
   - weaken any licence gate.

5. **T12 completion does not satisfy or erase the T11 ethics blocker.**

6. **Before T13 human-review activities or T14 annotation collection**, the governance state must be reassessed against the documented determination.

T12 work is preparatory local infrastructure and does not require human annotation, gold data, protected records, or research-dataset training. Deferring it until T11 PASS would idle hardware and model-stack validation without reducing ethics risk.

## Evidence

- T11 completion report: `docs/reports/ticket_T11_completion_report.md` — infrastructure complete; stage gate **BLOCKED** (`determination_status: "pending"`).
- Ethics gate: `configs/governance/human_annotation_governance.json` — `collection_permitted: false`.
- T12 ticket scope: `cursor_plan/tickets/T12_local_text_model_and_training_stack_setup.md` — local model stack only; stop before benchmark authoring or fine-tuning on research data.
- Research contract supersession: `binding_unless_deviation` (`configs/research/research_contract_v1.json`).

## Risk

- **Scope creep:** T12 work could drift into annotation, benchmark authoring, or research-dataset training. Mitigation: explicit prohibited activities in this deviation and T12 stop condition.
- **False unblock:** T12 progress could be misread as T11 PASS. Mitigation: T11 verdict remains BLOCKED; this deviation is recorded separately and referenced in T12 preconditions.
- **Licence bypass:** Base model selection before full verification. Mitigation: licence gates unchanged; unresolved permissions remain blocking for training/evaluation on external datasets; T12 acceptance criteria still apply.

## Required reruns

None. T11 governance validators and ethics state are unchanged. Reassess governance before T13/T14.

## Protected-test implications

None. T12 must not access protected test data (protected access remains gated until T29). No protected-test protocol change.

## Preservation of prior outputs

All T00–T11 artefacts, the T11 BLOCKED verdict, ethics pending state with `collection_permitted: false`, and licence null-permission gates remain authoritative and unchanged.
