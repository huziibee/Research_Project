# 02 — Context Refresh Protocol for Cursor

Use a fresh Cursor context for every ticket.

## Workflow

```text
Fresh context
  -> attach global contract
  -> attach this protocol
  -> attach current ticket
  -> attach only the reference documents named by that ticket
  -> inspect repository artifacts and prior completion reports
  -> state preconditions and blockers
  -> propose a short ticket-only plan
  -> implement only the current ticket
  -> run ticket-level validation
  -> write completion report
  -> stop for human approval
```

## Always attach

1. `01_global_cursor_contract.md`
2. `02_context_refresh_protocol.md`
3. the current ticket

## Attach when relevant

- `03_dataset_roles_metrics.md` for eligibility, evaluator, runner, and experiment tickets;
- `04_hardware_model_strategy.md` for inference or fine-tuning tickets;
- `08_manual_gold_dataset_program.md` for T13–T15;
- `10_interpretation_evaluation_framework.md` for interpretation scoring and analysis;
- `11_proposal_alignment_contract.md` for architecture, research claim, baseline, and metric decisions;
- `12_core_stretch_policy.md` for final gate behaviour;
- prior ticket completion reports explicitly named by the current ticket.

## Completed-ticket rule

T00–T09 are completed historical specifications. Do not rerun them. T10 is allowed to inspect and migrate their outputs into schema v2 without modifying the original files or pretending those tickets were re-executed.

## Repository-first context

Cursor must inspect files on disk. It must not infer schemas, counts, licences, model configurations, or successful prior outputs from prose alone.

## Transition packet

Every ticket creates:

```text
docs/reports/ticket_<ID>_completion_report.md
```

The next ticket may rely only on committed files, manifests, decision records, and completion reports.

## Approval checklist

Approve only when:

- every mandatory acceptance criterion has evidence;
- no protected-test access occurred prematurely;
- no label, count, licence, model property, or result was invented;
- tests and validation commands actually ran;
- unresolved blockers are explicit;
- the ticket stopped at its boundary.
