# Research Contract v1

**Contract version:** 1.0.0  
**Frozen at ticket:** T11  
**Machine-readable authority:** `configs/research/research_contract_v1.json`  
**Content hash sidecar:** `configs/research/research_contract_v1.sha256`

## Supersession

The proposal dataset section and calendar schedule are superseded. All remaining
non-dataset methodology in the source proposal remains binding unless a later
versioned deviation is approved and recorded.

## Research question

Does a risk-aware ambiguity manager improve routing decisions for compound
ambiguous robot commands compared with direct LLM interpretation and
uniform/degree-based ambiguity-handling policies when evaluated using
interpretation, ambiguity, clarification, routing, and risk-sensitive
correctness?

## Hypothesis

Explicit ambiguity-type, task-risk, capability, context, and uncertainty
coordination will improve routing correctness—especially clarification,
face-preserving rejection, silent-resolution, and multi-step decisions—over
direct interpretation and fixed/degree-only policies.

## Primary outcome

Routing correctness.

## Supporting outcomes

Intent/CPC correctness, ambiguity labels, clarification appropriateness,
risk/capability correctness, safe rejection, unsafe silent resolution,
resolved parameter correctness, and failure decomposition.

## Scope

Text-first natural-language interpretation and routing only. No raw-image/LVLM
processing, perception, motion planning, navigation, grasping, physical
execution, or complete real-world safety classifier.

## Seven mandatory comparison systems

1. `always_execute`
2. `always_clarify`
3. `always_silently_resolve`
4. `direct_base_llm`
5. `degree_based_router`
6. `context_blind_manager`
7. `full_finetuned_type_risk_manager`

## Model and evaluation policy

- Local open-source text LLM with mandatory supervised fine-tuning.
- Direct baseline and proposed manager share the same base model and revision.
- Proposed manager uses the T28 adapter; failure to fine-tune yields `BLOCKED`.
- Context-sampling uncertainty is required.
- Official evaluator is deterministic; a generative LLM is not the primary judge.
- Interpretation metrics remain separate from routing metrics.

## Claim boundaries

May claim improved NLU-layer interpretation/routing under the benchmark. May not
claim safe physical robot execution, general visual grounding, or complete
real-world safety assurance.
