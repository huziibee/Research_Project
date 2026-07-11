# 06 — Copy/Paste Prompt Template for Cursor

Use this prompt with a fresh Cursor context for each unfinished ticket.

```text
You are executing exactly one ticket in the Risk-Aware Ambiguity Manager research repository.

Read in this order:
1. 01_global_cursor_contract.md
2. 02_context_refresh_protocol.md
3. 11_proposal_alignment_contract.md
4. the current ticket
5. only the additional reference documents named by the ticket
6. relevant prior completion reports and real repository artifacts

T00–T09 are completed. Do not rerun them. If this is T10, migrate their outputs without recreating them.

Before editing:
- inspect the repository;
- list the exact preconditions and whether they pass;
- identify any protected-data or governance restrictions;
- state a short ticket-only implementation plan;
- create failing tests first for deterministic requirements.

During execution:
- do not invent files, fields, labels, counts, licences, model properties, or results;
- do not continue to another ticket;
- preserve raw outputs, manifests, and hashes;
- treat schema v2 from T10 as authoritative;
- use local-only text-model infrastructure;
- never access protected test data before T29;
- stop truthfully if a mandatory gate cannot pass.

At completion:
- run the ticket's tests and validation;
- write docs/reports/ticket_<ID>_completion_report.md using the global template;
- list every changed file and unresolved blocker;
- issue PASS, FAIL, or BLOCKED;
- stop and wait for human approval.
```
