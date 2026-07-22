# Ticket report — T16–T24 model-independent foundation

**Author:** Mohammed Bangie — 2610990  
**Decision:** `DEC-20260722-001`  
**Branch:** `feature/t12-cluster-redesign`  
**Scope:** shared contracts, deterministic components, seven-system adapters, evaluator, gated runner, synthetic fixtures  
**Not in scope:** model selection/inference, QLoRA, supervisor annotation, adjudicated gold, official metrics, T25 LLM judge, T27–T31 execution

## Ticket-to-implementation mapping

| Ticket | Mapping | Status note |
|---|---|---|
| T16 | interface only now for model path; synthetic adapter + provider contract implemented | `direct_base_llm` → `provider_unavailable` without provider |
| T17 | implement now (deterministic candidate service + fixtures) | synthetic validation complete |
| T18 | implement now over supplied samples (no model sampling) | thresholds unfrozen / development_only |
| T19 | implement now (aggregation + deterministic router) | model classifier remains provider-gated |
| T20 | implement now (deterministic resolver) | official scoring blocked on gold |
| T21 | implement now (safety enforcement findings) | external live safety provider not required |
| T22 | implement now (template generators); provider wording interface-only | synthetic validation complete |
| T23 | implement now (seven adapters + registry + synthetic smoke) | not empirically complete |
| T24 | implement now (deterministic evaluator + eligibility on synthetic gold) | official execution blocked |

## Components completed

- Shared `SystemInput` / `StructuredAnalysis` / `SystemResult` contracts
- Provider protocols + deterministic doubles + honest `ProviderUnavailableError`
- Candidate interpretation validation/fingerprints
- Context-sampling uncertainty diagnostics over supplied analyses
- Context resolver with evidence/rule IDs
- Ambiguity/risk/capability aggregation
- Deterministic route precedence router with rule traces
- Safety enforcement (fail-closed critical findings)
- Clarification/rejection template generators
- All seven comparison systems
- Experiment runner modes: `synthetic_smoke`, `development`, `official` (gated)
- Deterministic evaluator metrics + denominator reporting
- Synthetic fixture suite (16 records) + hand-calculated expected metrics doc

## Components interface-only

- Model-backed structured analysis / direct LLM / future clarification-rejection LLM wording
- Bounded regeneration after safety rejection
- External live safety provider loop beyond deterministic findings

## Blocked on model strategy

- Real T16 direct-base predictions
- Provider-backed full-manager semantic analysis without deterministic fixtures
- Official model-backed system runs

## Blocked on adjudicated gold / T15 / T29

- Official scoring and research performance claims
- Threshold freeze
- Train/dev/protected-test split freeze
- Official experiment evidence under non-synthetic paths

## Seven systems

1. `always_execute` — shared cached analysis; force execute; retain safety findings  
2. `always_clarify` — force clarify; record unnecessary clarification when no target  
3. `always_silently_resolve` — force silent; preserve unsupported resolution honestly  
4. `direct_base_llm` — provider-driven; not executable without provider  
5. `degree_based_router` — scalar uncertainty only; routes ∈ {execute, silently_resolve, clarify}  
6. `context_blind_manager` — ablates dialogue/scene/capability without mutating input  
7. `full_type_risk_aware_manager` — full deterministic pipeline; awaits T28 adapter; not empirically complete  

## Safety invariants

- Unsupported selected interpretation / silent resolve without evidence recorded  
- Execute with unresolved critical slots recorded  
- Capability overcommitment recorded  
- Invalid clarify/reject/strategy sequences recorded  
- No silent repair without findings  

## Evaluator metrics

Intent, CPC (P/R/F1, exact, critical, joint), candidate-set, ambiguity (micro/macro/exact/compound), risk, capability, routing (accuracy, per-route F1, four-way decomposition, risk-sensitive), safety/interaction rates, structural clarification/rejection checks. Every metric reports total/eligible/excluded/reasons/numerator/denominator/value.

## Runner gates

Official mode refuses start without adjudicated gold, T15 split manifest, protocol-freeze ID, handbook version, and (for model-backed systems) approved model strategy + configured provider. Protected-label leakage is an explicit blocking gate.

## Confirmation

- No official experiment was executed.
- T13 calibration packages were not used as gold.
- No human annotations or adjudicated gold were created.
- No model inference/training occurred.
- No torch/transformers/vllm imports in systems/evaluation foundation path.

## Synthetic smoke

```text
python scripts/run_manager_experiment.py --run-synthetic configs/experiments/synthetic_smoke_v1.json
```

Outputs under `outputs/manager_experiments/synthetic/` are labelled `synthetic_only: true`, `official_result: false`.
