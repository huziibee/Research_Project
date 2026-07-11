# T12 Slice 4 — Synthetic evaluation report

- Ticket: T12
- Slice: 4
- Candidate: t12-cand-001
- Model: Qwen/Qwen2.5-1.5B-Instruct
- Revision: 989aa7980e4cf806f80c7fef2b1adb7bc71aa306
- Fixture file SHA-256: `a3c502312a2be7eb5fc414dbc122273c9c1725a64faeca10b2219b103584c931`
- Run status: completed
- Outcome classification: threshold_not_frozen
- Fallback probe recommended: True

## Aggregate metrics

```json
{
  "authorised_fixture_count": 10,
  "attempted_count": 10,
  "completed_generation_count": 10,
  "completed_generation_rate": 1.0,
  "non_empty_raw_output_count": 10,
  "non_empty_raw_output_rate": 1.0,
  "parse_success_count": 10,
  "parse_success_rate": 1.0,
  "schema_valid_count": 0,
  "schema_valid_rate": 0.0,
  "schema_invalid_count": 10,
  "parser_failure_count": 0,
  "repair_attempt_distribution": {
    "1": 10
  },
  "repair_success_count": 10,
  "timeout_count": 0,
  "oom_count": 0,
  "backend_error_count": 0,
  "unsupported_commitment_total": 0,
  "fixtures_with_unsupported_commitments": 0,
  "false_silent_resolution_eligibility_count": 0,
  "route_accuracy": {
    "annotated_count": 10,
    "exact_match_count": 0,
    "exact_match_rate": 0.0
  },
  "ambiguity_type_accuracy": null,
  "risk_accuracy": null,
  "unresolved_slot_accuracy": null,
  "latency_ms_distribution": {
    "count": 10,
    "min": 38452.879,
    "max": 60714.579,
    "mean": 46798.578,
    "median": 44545.207
  },
  "prompt_token_distribution": {
    "count": 10,
    "min": 213.0,
    "max": 249.0,
    "mean": 235.5,
    "median": 237.0
  },
  "completion_token_distribution": {
    "count": 10,
    "min": 142.0,
    "max": 202.0,
    "mean": 173.2,
    "median": 178.0
  },
  "peak_vram_mib_distribution": {
    "count": 10,
    "min": 1151.754,
    "max": 1154.518,
    "mean": 1153.835,
    "median": 1154.023
  },
  "context_overflow_count": 0,
  "worker_cleanup_failures": 0
}
```

## Per-fixture summary

| Fixture | Generation | Parse | Schema | Route match | Unsupported | Silent gate | Latency ms |
|---|---|---|---|---|---:|---|---:|
| syn-001 | completed | parse_success | schema_invalid | False | 0 | False | 60714.6 |
| syn-002 | completed | parse_success | schema_invalid | False | 0 | False | 59642.8 |
| syn-003 | completed | parse_success | schema_invalid | False | 0 | False | 44666.6 |
| syn-004 | completed | parse_success | schema_invalid | False | 0 | False | 45951.3 |
| syn-005 | completed | parse_success | schema_invalid | False | 0 | False | 43680.5 |
| syn-006 | completed | parse_success | schema_invalid | False | 0 | False | 44243.4 |
| syn-007 | completed | parse_success | schema_invalid | False | 0 | False | 44423.8 |
| syn-008 | completed | parse_success | schema_invalid | False | 0 | False | 46715.4 |
| syn-009 | completed | parse_success | schema_invalid | False | 0 | False | 39494.5 |
| syn-010 | completed | parse_success | schema_invalid | False | 0 | False | 38452.9 |

## Governance confirmations

- selected_model: None
- no_model_selection: True
- no_adapter_attached: True
- no_optimiser_step: True
- no_research_data_access: True
- no_fallback_download: True

