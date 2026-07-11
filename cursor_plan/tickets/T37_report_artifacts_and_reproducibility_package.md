# T37 — Report artifacts and reproducibility package

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `11_proposal_alignment_contract.md`
- `10_interpretation_evaluation_framework.md`

## Goal

Generate traceable report-ready evidence without manually inventing or copying result values.

## Preconditions

- T30–T36 outputs/statuses exist.

## Required tasks

1. Generate the final architecture diagram showing text inputs, fine-tuned structured analysis, context sampling, deterministic routing, five routes, and evaluation outputs.
2. Generate data/provenance, seven-system, interpretation/CPC, routing, ambiguity, risk/capability, clarification/rejection, silent-resolution, cost, statistics, ablation, and failure tables from saved files.
3. Generate the interpretation-vs-route cross-tab and key confusion matrices.
4. Create a reproducibility checklist and environment/model/adapter/protocol manifest summary.
5. Create proposal-alignment and claim-boundary text for the report methodology/limitations.
6. Generate an AI-use disclosure appendix from the governance log and flag human review before submission.
7. Report stretch tickets/statuses separately from core confirmatory results.
8. Verify every table cell links to a metric artifact and every figure source is recorded.

## Deliverables

- Generated tables/figures.
- Reproducibility package.
- Method/limitations alignment notes.
- AI-use disclosure draft.
- Traceability index.
- T37 completion report.

## Acceptance criteria

- [ ] No result is manually fabricated.
- [ ] All seven systems appear.
- [ ] Mandatory fine-tuning/context-sampling are documented.
- [ ] Interpretation and routing remain separate.
- [ ] Every major result is traceable.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after report artifacts are generated and validated. Do not rewrite experimental outputs.
