# Schema v2 Migration Report (T10)

Aggregate evidence only. No raw corpus commands, dialogue, scene text, or candidate interpretation text appear in this report.

## Migration identity

| Field | Value |
|---|---|
| Migration version | `v1_to_v2-1.0.0` |
| Canonical schema version | `2.0.0` |
| Records migrated | 24,404 |
| Protected v1 artefacts | unchanged (hashes verified before and after) |

## Per-dataset row reconciliation

| Dataset | v1 input rows | v2 migrated rows | Delta |
|---|---:|---:|---|
| ambik | 1,000 | 1,000 | 0 |
| indirect_requests | 906 | 906 | 0 |
| codraw_icr_v2 | 7,034 | 7,034 | 0 |
| vague | 1,677 | 1,677 | 0 |
| clara | 5,222 | 5,222 | 0 |
| clariq | 8,565 | 8,565 | 0 |

## Weak pool reconciliation

| Pool | Rows | Unique IDs |
|---|---:|---:|
| Primary v2 | 15,839 | 15,839 |
| Auxiliary v2 | 8,565 | 8,565 |
| Membership index | 24,404 | 24,404 |
| Global unique logical IDs | — | 24,404 |

Primary datasets (in order): ambik, indirect_requests, codraw_icr_v2, vague, clara.  
Auxiliary: clariq only.  
SafeAgentBench: excluded (not converted, not migrated).

## Legacy enum mapping counts

| Mapping | Count |
|---|---:|
| `unknown_until_clarified → unknown` | 0 |
| `partially_capable → conditional` | 0 |
| Rejected legacy values | 0 |

## Unmapped legacy slot accounting

| Dataset | Unique unmapped keys | Total preserved instances | Reason |
|---|---:|---:|---|
| ambik | 0 | 0 | empty v1 slots |
| codraw_icr_v2 | 0 | 0 | empty v1 slots |
| vague | 0 | 0 | all keys mapped to CPC |
| clara | 0 | 0 | empty v1 slots |
| clariq | 0 | 0 | empty v1 slots |
| indirect_requests | 37 | 744 | dynamic slot_description keys — no proven CPC mapping |

All unmapped values preserved under `v1_legacy.slots`.

## Unmappable v2 field reasons (per migrated record)

Each of 24,404 records records unavailability for: `selected_interpretation`, `supporting_evidence`, `context_sampling_uncertainty`, `resolved_slots`, `resolution_method`, `resolution_evidence`, `rejection_reason`, `speech_act`.

## Output paths (repository-relative)

```text
data/interim/schema_v2/{dataset}/{dataset}_canonical.jsonl
data/processed/schema_v2/weak_pool/weak_pool_canonical.jsonl
data/processed/schema_v2/weak_pool/weak_pool_auxiliary.jsonl
data/processed/schema_v2/weak_pool/weak_pool_membership.jsonl
outputs/manifests/schema_v2_migration_manifest.json
outputs/manifests/schema_v2_weak_pool_manifest.json
outputs/metrics/schema_v2_migration_summary.json
```

## Protected v1 hash preservation

Before and after hashes identical for all nine protected paths (six interim canonical files + three v1 weak-pool files). See `outputs/manifests/schema_v2_migration_manifest.json` → `protected_v1_hashes_before`.

## Conditional dataset status

codraw_icr_v2, vague, and clara retain `conditional_core` / `conditional_pending` membership roles. Clariq remains auxiliary / ineligible for core pool metrics.

## Skipped / quarantine sources

v1 quarantine and excluded files (clara excluded, clariq excluded/quarantine, codraw quarantine) were not migration inputs — consistent with T07–T09 policy.

## Publication boundary

Human markdown reports (`docs/decisions/`, `docs/reports/schema_v2_migration_report.md`, `docs/reports/ticket_T10_completion_report.md`) are static tracked deliverables. The migration CLI publishes machine JSON/JSONL outputs only.
