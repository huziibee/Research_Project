# 02 — Context Refresh Protocol for Cursor

Use this to keep Cursor efficient and avoid context pollution.

## Why this protocol exists

Cursor can lose track of requirements when too many files, previous decisions, or partial attempts stay in context. The safest approach is ticket isolation.

## Per-ticket workflow

For every ticket:

```text
Fresh Cursor context
  ↓
Attach/paste global contract
  ↓
Attach/paste current ticket only
  ↓
Cursor scans relevant repo files
  ↓
Cursor proposes implementation plan
  ↓
Cursor implements only that ticket
  ↓
Cursor runs ticket-level validation
  ↓
Cursor produces completion report
  ↓
Human approves or rejects
  ↓
Next ticket starts with refreshed context
```

## What to paste into Cursor

Always provide:

1. `01_global_cursor_contract.md`
2. This file, `02_context_refresh_protocol.md`
3. The one current ticket file

Do not paste older tickets unless the current ticket explicitly says it depends on a concrete artifact from them.

## What Cursor should inspect instead of remembering

Cursor should inspect files on disk, not rely on memory.

Examples:

- Use `ls`, `find`, or IDE file tree for repo layout.
- Use Python/pandas scripts for CSV columns and row counts.
- Use schema files from `src/ambiguity_manager/schema/`.
- Use reports from `docs/reports/`.
- Use split manifests from `data/splits/`.

## Ticket transition packet

At the end of each ticket, Cursor must create:

```text
docs/reports/ticket_<ID>_completion_report.md
```

The next ticket may use that report as a compact context artifact.

## Human approval checkpoint

The human should approve only when:

- all acceptance criteria are checked,
- no fake or guessed labels/results exist,
- test/validation commands pass,
- unresolved `TODO_VERIFY` items are acceptable or intentionally deferred.

## Required carry-over artifacts

The next ticket may rely only on:

- files committed or saved in the repository;
- the previous completion report;
- versioned schema/config/split manifests;
- explicit human decisions recorded in `docs/decisions/`.

Do not carry undocumented assumptions between Cursor contexts.

## Test-first reminder

When the current ticket is marked TDD-required, Cursor must show the failing test before implementation in its completion report. A ticket is not approved merely because tests pass at the end if no behavior-focused test was created.
