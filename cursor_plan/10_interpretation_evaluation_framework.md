# 10 — Interpretation, CPC, and Routing Evaluation Framework

This document governs T14, T15, T24, T25, T29, T30, and T36.

## Core principle

The official evaluator compares the original command/context, human/source gold, and system output. Route correctness alone is insufficient.

## Official deterministic layers

### 1. Intent / speech act

Measure whether the requested communicative action is recovered.

### 2. Core Propositional Content

Compare canonical action arguments:

- action and actor;
- object and attributes;
- destination and spatial relation;
- quantity and time;
- recipient and tool;
- conditions, negation, and constraints.

Report CPC slot precision/recall/F1, critical-slot correctness, and exact CPC match.

### 3. Candidate interpretation sets

Use one-to-one assignment between predicted and gold candidates. Report candidate precision, recall, F1, exact set match, missing candidates, and extra candidates.

### 4. Evidence faithfulness

Detect unsupported details, contradictions, context conflicts, and capability/safety assumptions not supported by the input.

### 5. Ambiguity, risk, and capability

Report multi-label ambiguity metrics, unresolved-slot metrics, risk classification/underestimation, and capability classification/violation.

### 6. Silent-resolution correctness

When the route is `silently_resolve`, compare actual `resolved_slots`, resolution method eligibility, evidence/default policy, and uncertainty. Merely choosing the route is not sufficient.

### 7. Routing and response

Report exact route correctness, route macro-F1, route confusion, multi-step sequence, clarification decision/target, rejection decision/reason, and safety-sensitive rates.

## Multiple valid interpretations

Gold may contain zero, one, or many materially valid interpretations. A system may select one only when:

- the command is unambiguous; or
- supplied context uniquely resolves it.

Penalise unsupported commitment, missing candidates, invalid candidates, and invented specificity.

## Human relation taxonomy

Use for meta-evaluation and failure analysis:

```text
exact_match
paraphrase
added_info
missing_info
partially_correct
contradicted
irrelevant
```

Critical changes include action, actor, object, destination, relation, time, quantity, condition, negation, safety constraint, and capability assumption.

## Official metric names

The final protocol must freeze at least:

- routing correctness;
- route macro-F1 and per-route precision/recall/F1;
- ambiguity micro-F1 and macro-F1;
- exact ambiguity-set match;
- clarification precision, recall, and F1;
- intent correctness;
- CPC/slot precision, recall, F1, and exact match;
- candidate-set precision, recall, and F1;
- selected-interpretation accuracy;
- unresolved-slot F1;
- unsupported-commitment rate;
- hallucinated-detail and context-contradiction rates;
- risk-sensitive decision accuracy and risk-underestimation rate;
- capability accuracy and capability-violation rate;
- safe rejection rate and rejection-reason correctness;
- unsafe silent-resolution rate;
- silent-resolution value correctness;
- multi-step exact sequence match;
- invalid JSON/repair rate, latency, token usage, and compute estimate.

Every formula and denominator is frozen in T29.

## Secondary semantic verifier

T25 may build a triadic verifier using normalisation/fuzzy checks, embeddings, reranking, NLI, optional QA, and a calibrated combiner. It may influence official secondary scores only if it matches adjudicated human comparisons at predefined thresholds. It never replaces structured official metrics.

## Four-way outcome table

Every system report must separate:

| Interpretation | Route | Meaning |
|---|---|---|
| correct | correct | full success |
| correct | wrong | language understanding succeeded; policy failed |
| wrong | correct | route happened to be right for the wrong reason |
| wrong | wrong | complete failure |
