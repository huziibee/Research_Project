# 11 — Non-Dataset Proposal Alignment Contract

The source proposal remains authoritative except for its dataset section and calendar schedule. This document translates the remaining methodology into execution constraints.

## Research question

Does a risk-aware ambiguity manager improve routing decisions for compound ambiguous robot commands compared with direct LLM interpretation and uniform/degree-based ambiguity-handling policies when evaluated using interpretation, ambiguity, clarification, routing, and risk-sensitive correctness?

## Hypothesis

Explicit ambiguity-type, task-risk, capability, context, and uncertainty coordination will improve routing correctness—especially clarification, face-preserving rejection, silent-resolution, and multi-step decisions—over direct interpretation and fixed/degree-only policies.

## Scope

- Text-first NLU coordination layer only.
- No embodied execution or perception evaluation.
- Scene/dialogue/capability context is textual or structured.
- No LVLM condition.

## Proposed method

- Local open-source text LLM.
- Mandatory supervised fine-tuning.
- Schema-constrained structured output.
- Explicit intent/CPC, ambiguity, risk, capability, and uncertainty signals.
- Context-sampling output variance.
- Deterministic risk-aware router selecting one of five routes.

## Seven mandatory systems

1. always execute;
2. always clarify;
3. always silently resolve;
4. direct base LLM;
5. degree-based router;
6. context-blind manager;
7. full fine-tuned type/risk-aware manager.

The first five include the proposal's central comparators; the extra two remain mandatory controls by explicit project decision.

## Primary and supporting outcomes

Primary outcome: routing correctness.

Supporting outcomes: intent/CPC correctness, ambiguity labels, clarification appropriateness, risk/capability correctness, safe rejection, unsafe silent resolution, actual resolved parameter correctness, and failure decomposition.

## Claim boundary

The project may claim improved NLU-layer interpretation/routing under the benchmark. It may not claim safe physical robot execution, general visual grounding, or complete real-world safety assurance.
