# Ambiguity-manager architecture (T16–T24 foundation)

Model-independent foundation only. Official execution remains blocked pending adjudicated gold (T14/T15), viable model strategy where required, and T29 protocol freeze.

## Manager flow

```mermaid
flowchart TD
  A[command + context] --> B[structured analysis provider]
  B --> C[candidate interpretations]
  C --> D[context resolution]
  D --> E[ambiguity / risk / capability aggregation]
  E --> F[deterministic router]
  F --> G[safety gate]
  G --> H{route}
  H -->|clarify| I[clarification generator]
  H -->|reject| J[rejection generator]
  H -->|execute / silent / multi_step| K[system result envelope]
  I --> K
  J --> K
```

## Seven-system comparison flow

```mermaid
flowchart LR
  IN[shared SystemInput] --> CACHE[optional cached analysis]
  CACHE --> S1[always_execute]
  CACHE --> S2[always_clarify]
  CACHE --> S3[always_silently_resolve]
  CACHE --> S5[degree_based_router]
  IN --> S4[direct_base_llm]
  IN --> S6[context_blind_manager]
  IN --> S7[full_type_risk_aware_manager]
  S1 --> OUT[common SystemResult]
  S2 --> OUT
  S3 --> OUT
  S4 --> OUT
  S5 --> OUT
  S6 --> OUT
  S7 --> OUT
  OUT --> EVAL[deterministic evaluator]
```

## Package layout

- `src/ambiguity_manager/systems/` — contracts, providers, candidates, uncertainty, resolver, classification, router, safety, responses, seven adapters, runner
- `src/ambiguity_manager/evaluation/` — deterministic metrics and eligibility
- `configs/manager/` / `configs/evaluation/` / `configs/experiments/` — versioned unfrozen development configs
- `scripts/run_manager_experiment.py` — synthetic/gated CLI

## Official vs foundation

| Mode | Allowed now |
|---|---|
| `synthetic_smoke` | yes |
| `development` | yes (no protected labels) |
| `official` | blocked until gold + T15 + protocol freeze + model strategy where needed |
