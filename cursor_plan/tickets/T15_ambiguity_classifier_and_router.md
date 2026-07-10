# T15 — Ambiguity classifier and route policy

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Implement ambiguity classification and route policy.

## Component responsibilities

Ambiguity classifier answers:

- Is ambiguity present?
- Which ambiguity types are present?
- Which slots are missing?
- Is this compound ambiguity?

Router answers:

- `execute`
- `clarify`
- `silently_resolve`
- `face_preserving_rejection`
- `multi_step`

## Required route rules

Implement as transparent rules first:

- Missing critical referent/location -> `clarify`.
- Low-risk vague temporal/quantitative parameter -> `silently_resolve` only when safe by policy.
- Safety-precondition missing -> `clarify`.
- Multiple ambiguity types requiring order -> `multi_step`.
- All candidates rejected by safety -> `face_preserving_rejection`.
- One clear high-confidence candidate with no blocking ambiguity -> `execute`.

## Required tasks

1. Implement ambiguity classifier interface.
2. Implement rule-assisted router.
3. Add tests for each route.
4. Add tests for compound ambiguity and strategy sequence.
5. Make rules configurable.
6. Do not rely on external safety module yet; use placeholder safety status fields.

## Deliverables

- Ambiguity classifier module.
- Router module.
- Route policy config.
- Tests covering every route.
- Completion report.

## Acceptance criteria

- Every route has at least one test.
- `multi_step` returns explicit `strategy_sequence`.
- Safety-precondition ambiguity routes to clarification, not generic safety rejection.
- No robot planning/execution code appears.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after route tests pass. Do not implement context resolver or safety loop.

## Routing-policy requirements

The full proposed policy must explicitly consume ambiguity type, risk, and capability. Define deterministic precedence and abstention behavior. Include regression tests for:

- high-risk ambiguity never silently resolving without an explicitly justified policy;
- incapable commands routing to face-preserving rejection unless a clarification can genuinely change capability status;
- compound cases producing ordered strategy sequences;
- clear, safe, capable commands routing to execute;
- uncertainty thresholds using dev-only values.
