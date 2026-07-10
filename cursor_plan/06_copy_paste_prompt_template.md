# 06 — Copy/Paste Prompt Template for Cursor

```text
You are working on the Risk-Aware Ambiguity Manager project.

Implement exactly one ticket and then stop.

Attached context:
1. 01_global_cursor_contract.md
2. 02_context_refresh_protocol.md
3. tickets/TXX_<ticket_name>.md

Required behavior:
- Follow the global contract strictly.
- Inspect the repository and summarize only relevant files.
- State the ticket preconditions and whether they are satisfied.
- Propose a short implementation plan.
- If deterministic behavior is involved, use Red–Green–Refactor: write focused failing tests first, show the initial failure, implement the minimum change, then refactor.
- Do not hallucinate fields, labels, licences, files, examples, or results.
- Do not use the protected test set unless the frozen protocol explicitly permits it.
- Run only the ticket's validation/tests.
- Create docs/reports/ticket_TXX_completion_report.md in the required format.
- Stop after the completion report.

If any prerequisite is missing, mark BLOCKED_TODO_VERIFY or TODO_VERIFY_LABEL_MAPPING and stop. Do not fake progress.
```

After Cursor finishes, request only:

```text
1. changed files
2. tests created and initial failing result
3. final validation output
4. completion report
5. unresolved TODO/BLOCKED items
```
