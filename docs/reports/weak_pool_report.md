# Weak Pool Report (T09)

This report describes the weak labelled pools built from approved T03–T08 canonical
converter outputs. These pools are for prompting, training, and exploration. They
are **not** the final gold evaluation benchmark.

## Physical layout

| Artefact | Path | Records |
| --- | --- | ---: |
| Primary robot weak pool | `data/processed/weak_pool/weak_pool_canonical.jsonl` | 15,839 |
| Auxiliary clarification pool | `data/processed/weak_pool/weak_pool_auxiliary.jsonl` | 8,565 |
| Membership index | `data/processed/weak_pool/weak_pool_membership.jsonl` | 24,404 |
| Machine manifest | `outputs/manifests/weak_pool_manifest.json` | — |
| Count summary | `outputs/metrics/weak_pool_summary.json` | — |

## Dataset inclusion

| Dataset | Role | Physical pool | Core pool status | Records |
| --- | --- | --- | --- | ---: |
| ambik | core | primary | eligible | 1,000 |
| indirect_requests | core | primary | eligible | 906 |
| codraw_icr_v2 | conditional_core | primary | conditional_pending | 7,034 |
| vague | conditional_core | primary | conditional_pending | 1,677 |
| clara | conditional_core | primary | conditional_pending | 5,222 |
| clariq | auxiliary | auxiliary | ineligible | 8,565 |
| safe_agent_bench | challenge | excluded | — | 0 |

SafeAgentBench is excluded because no approved canonical converter output exists.

## Accounting invariants

- Primary pool IDs are disjoint from auxiliary pool IDs.
- Membership rows equal the union of both pools (24,404).
- Global canonical IDs are unique across all included inputs.
- Every source-converted input record is represented exactly once in membership.

## Overlap analysis (report-only)

Counts are factual overlap indicators for T12 leakage work. No records were removed
or merged in T09.

| Overlap type | Groups |
| --- | ---: |
| Integrity duplicate (full canonical record hash) | 0 |
| Semantic-payload duplicate | 3,226 |
| Exact command duplicate | 1,238 |
| Normalized command duplicate | 1,212 |
| Command + scene_context duplicate | 1,314 |
| Cross-dataset normalized-command overlap | 0 |
| Repeated non-null group_id values | 1,966 |

Normalization for audit: strip, lowercase, collapse internal whitespace on command text.

## Provenance hashes

### Canonical inputs

| Dataset | SHA-256 |
| --- | --- |
| ambik | `5a37b0dac5f9e2bf293868c680b3d80cc019bcc5866e8055a5297efdf1a7762e` |
| indirect_requests | `796257f026a701a68afe902dbdc97a87a767797ed7156f5aaa8504f74459600e` |
| codraw_icr_v2 | `c8fa4f731518bda7a7b7d4fa4a15611fd9e855ee197bcfcca2726f2f39740a6b` |
| vague | `81a5e82ba2013680c91d4a8ba6c1b81002b0b883fe9fb8bb503b80bfcd680b5d` |
| clara | `80e9b85517db1d5de33fc3c69639e4d4582edd3098665cdeedd5280d305d8507` |
| clariq | `262523b522921f80b5db25024610049cf2789f72c3e6bb89156aaa9c4fb83dc1` |

### Outputs

| Artefact | SHA-256 |
| --- | --- |
| Primary pool | `1e51cac046e014a6b890b10a155d22e32e01aa276d4507a10ad4f86abcf9942a` |
| Auxiliary pool | `0f7e34debfbb0638b221faef80d43c5fe8408ce7e2705e031d3ff6960c8ad94f` |
| Membership | `4f8bc0f914ae739b549908b46a194ab0a38983abc41c1edd4ed58e04aaee8162` |

## Determinism

Machine artefacts are deterministic for unchanged inputs. Rebuild produced
byte-identical primary pool, auxiliary pool, membership, manifest, and summary files.

## Deferred work

- Final train/dev/test/gold split assignment (T12)
- Leakage removal and group-aware split freezing (T12)
- SafeAgentBench conversion (not approved)
- Model training or evaluation
