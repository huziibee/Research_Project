# T28 handover

T28 is **BLOCKED** before training.

The T27F-to-T28 human approval is recorded in `docs/reports/ticket_T28_completion_report.md`. T27F and Parent T27 remain PASS, the exact Qwen3-8B base identity remains frozen, and all three preserved T27F artifact verifiers return `VERIFY_PASSED`.

The blocker is concrete: the frozen T15 manifest has IDs and eligibility but the full joined source records required for task-conditioned targets are absent. Only the 192-record T27C smoke subset is available; it cannot be promoted to the mandatory T28 full-data run. No training job, checkpoint selection, adapter package, manager configuration update, protected evaluation, or T29 work was performed.

No protected data was accessed. The working tree’s pre-existing untracked artifacts were preserved. Resume only after the full frozen source-record join is restored and the T28 predeclare/data-integrity gate is re-run with human direction.
