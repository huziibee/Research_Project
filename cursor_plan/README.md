# Cursor Optimal Execution Plan — Risk-Aware Ambiguity Manager

This pack is a **standalone, stage-gated Cursor execution system** for completing the actual experiment before report writing. It uses fresh context per ticket, evidence-based stopping criteria, and TDD for deterministic components.

## Approved data strategy

- Keep AmbiK and IndirectRequests.
- Use CLARA only after label verification.
- Use CoDraw-iCR and VAGUE if acquired and verified.
- Use ClariQ only as auxiliary clarification data.
- TEACh is not core unless a later recorded decision adds it.
- SafeAgentBench is optional and remains a separate safety/challenge integration.
- Build and adjudicate the required manual compound-ambiguity extension.

## How to use

For each ticket:

1. Start a fresh Cursor context.
2. Attach `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the current ticket.
3. Require repository inspection and a short plan before edits.
4. Require Red–Green–Refactor where the ticket is TDD-required.
5. Require the completion report and human approval.
6. Stop; do not let Cursor continue to the next ticket.

## Ticket groups

| Phase | Tickets | Outcome |
|---|---|---|
| Foundation | T00–T02 | scaffold, schema, data/licence audit |
| Conversion | T03–T09 | validated source converters and weak pool |
| Gold benchmark | T10–T12 | manual data, agreement, frozen leakage-safe splits |
| Systems | T13–T19 | proposed manager and all required baselines |
| Evaluation infrastructure | T20–T24 | metrics, runner, local model, optional fine-tuning |
| Protocol and complete experiment | T27–T32 | freeze, cost, statistics, ablations, robustness, stability |
| Analysis and final gate | T25, T26, T33 | failure analysis, evidence package, readiness audit |

## Mandatory comparisons

- always execute;
- always clarify;
- always silently resolve;
- direct structured LLM;
- degree-based routing;
- context-blind ablation;
- full type-and-risk-aware manager;
- optional fine-tuned condition if actually run.

## Completion definition

The experiment is complete only when `T33_final_experiment_readiness_audit.md` issues a global PASS or the human records an explicit, justified deviation. Report writing must not be used to conceal missing experiments.
