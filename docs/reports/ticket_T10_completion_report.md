# Ticket T10 Completion Report — Canonical Schema v2 and Completed-Output Migration

**Status:** COMPLETE  
**Verdict:** PASS

## Scope delivered

1. Schema v2 (`2.0.0`) dataclasses, enums, validators, JSONL helpers.
2. Deterministic v1→v2 migration layer with conservative CPC slot mapping.
3. v2 weak pool rebuild from migrated interim outputs.
4. Atomic publication CLI (`scripts/migrate_schema_v2.py`).
5. ADR, migration report, and this completion report.
6. 32 new unit tests (306 total tests pass).

## Red–Green–Refactor evidence

### Red (initial failing tests)

New test modules were written before implementation:

```text
tests/test_schema_v2_enums.py
tests/test_schema_v2_validation.py
tests/test_migration_v1_to_v2.py
tests/test_migration_v2_pools.py
tests/test_migration_v2_manifests.py
tests/test_migration_v2_reports.py
```

Initial run (before v2/migration modules existed) failed with `ModuleNotFoundError: No module named 'ambiguity_manager.schema.v2'` across all new modules — expected Red-phase failure.

### Green

Implemented `src/ambiguity_manager/schema/v2/*`, `src/ambiguity_manager/migration/*`, and `scripts/migrate_schema_v2.py` until all 32 new tests passed.

### Refactor

No unrelated cleanup. Migration orchestration consolidated in `run_migration.py`; pool rebuild isolated in `pool_builder.py`.

## Test results

```text
PYTHONPATH=src python -m unittest tests.test_schema_v2_enums tests.test_schema_v2_validation tests.test_migration_v1_to_v2 tests.test_migration_v2_manifests tests.test_migration_v2_reports tests.test_migration_v2_pools
→ 32 tests OK

PYTHONPATH=src python -m unittest discover -s tests
→ 306 tests OK (before and after migration publish)
```

## Real-data commands

```text
PYTHONPATH=src python scripts/migrate_schema_v2.py --validate-only   → exit 0
PYTHONPATH=src python scripts/migrate_schema_v2.py --publish         → exit 0
PYTHONPATH=src python scripts/migrate_schema_v2.py --validate-only   → exit 0 (post-publish)
PYTHONPATH=src python scripts/migrate_schema_v2.py --publish         → exit 1 (refused overwrite)
```

## Machine publication contract

`--publish` atomically publishes twelve machine paths only (six v2 interim JSONL, three v2 pool files, three JSON manifests/summaries). It does **not** write human markdown reports; those are tracked static deliverables:

```text
docs/decisions/ADR_schema_v2_canonical_record.md
docs/reports/schema_v2_migration_report.md
docs/reports/ticket_T10_completion_report.md
```

## JSON Schema export

Deterministic JSON Schema at `src/ambiguity_manager/schema/v2/schema.json`, derived from Python definitions via `json_schema.py`. Python dataclasses remain authoritative.

## Count reconciliation

| Metric | Expected | Actual |
|---|---:|---:|
| AmbiK | 1,000 | 1,000 |
| IndirectRequests | 906 | 906 |
| CoDraw-iCR v2 | 7,034 | 7,034 |
| VAGUE | 1,677 | 1,677 |
| CLARA | 5,222 | 5,222 |
| ClariQ | 8,565 | 8,565 |
| Primary v2 pool | 15,839 | 15,839 |
| Auxiliary v2 pool | 8,565 | 8,565 |
| Membership | 24,404 | 24,404 |
| Global unique IDs | 24,404 | 24,404 |

## Output artefact SHA-256

| Path | SHA-256 |
|---|---|
| data/interim/schema_v2/ambik/ambik_canonical.jsonl | `91d855fe4dddbe05016baeb3ebd0ba068931047c61e7d30b642b0ab84535abc3` |
| data/interim/schema_v2/indirect_requests/indirect_requests_canonical.jsonl | `c92a88064e2dbed7d951d0a515289695a930a0375b45d737d3c4382fa6134b5a` |
| data/interim/schema_v2/codraw_icr_v2/codraw_icr_v2_canonical.jsonl | `f9cc4711d4ad7ef41253875a685ce005cd493a2a99a79b28417c1cf250782306` |
| data/interim/schema_v2/vague/vague_canonical.jsonl | `6b330ad27cd025d39d5db8efc7bae0860df6db4e85330ca1e113d4315c57da1e` |
| data/interim/schema_v2/clara/clara_canonical.jsonl | `94078669e81a77026c396a3eb4f2d440061d094afd46b95f3d1fa36bf818a5ae` |
| data/interim/schema_v2/clariq/clariq_canonical.jsonl | `44d632c0cff478a938dd3e4acc9c0f5b2bdadf4f75ad78f4e7624c49b31a4bd3` |
| data/processed/schema_v2/weak_pool/weak_pool_canonical.jsonl | `78a62da49ef4bfeca830a25077caf28547efbecddd26ba5b5a0eb713774cca1d` |
| data/processed/schema_v2/weak_pool/weak_pool_auxiliary.jsonl | `813eb391e88afc7b863cb10b4e2846e4452ef3db175750f9fcfaee14b8171bfb` |
| data/processed/schema_v2/weak_pool/weak_pool_membership.jsonl | `01233985f52eb5f4f9d8f71a8df375221188eb6a4459e42c81ae2d1688004bd0` |
| outputs/manifests/schema_v2_migration_manifest.json | `aedf91d769f0c715246e14a1e7fde95c102799b545786a46cc81aaee4c591fd3` |
| outputs/manifests/schema_v2_weak_pool_manifest.json | `a78c11342e7939851f8b956299225fd8aa276544ddaf2d1b5ca90b9baff88b25` |
| outputs/metrics/schema_v2_migration_summary.json | `a556c87a1319062a24ecd27a5c4142c8ec6f04741543283a27f44a9a037e3079` |

## Protected v1 hashes (before = after)

| Path | SHA-256 |
|---|---|
| data/interim/ambik/ambik_canonical.jsonl | `5a37b0dac5f9e2bf293868c680b3d80cc019bcc5866e8055a5297efdf1a7762e` |
| data/interim/indirect_requests/indirect_requests_canonical.jsonl | `796257f026a701a68afe902dbdc97a87a767797ed7156f5aaa8504f74459600e` |
| data/interim/codraw_icr_v2/codraw_icr_v2_canonical.jsonl | `c8fa4f731518bda7a7b7d4fa4a15611fd9e855ee197bcfcca2726f2f39740a6b` |
| data/interim/vague/vague_canonical.jsonl | `81a5e82ba2013680c91d4a8ba6c1b81002b0b883fe9fb8bb503b80bfcd680b5d` |
| data/interim/clara/clara_canonical.jsonl | `80e9b85517db1d5de33fc3c69639e4d4582edd3098665cdeedd5280d305d8507` |
| data/interim/clariq/clariq_canonical.jsonl | `262523b522921f80b5db25024610049cf2789f72c3e6bb89156aaa9c4fb83dc1` |
| data/processed/weak_pool/weak_pool_canonical.jsonl | `1e51cac046e014a6b890b10a155d22e32e01aa276d4507a10ad4f86abcf9942a` |
| data/processed/weak_pool/weak_pool_auxiliary.jsonl | `0f7e34debfbb0638b221faef80d43c5fe8408ce7e2705e031d3ff6960c8ad94f` |
| data/processed/weak_pool/weak_pool_membership.jsonl | `4f8bc0f914ae739b549908b46a194ab0a38983abc41c1edd4ed58e04aaee8162` |

## Acceptance criteria

| Criterion | Met |
|---|---|
| No T00–T09 converter or builder rerun | Yes |
| Legacy schema conflicts resolved by v2 authority | Yes (ADR) |
| Every completed row accounted for | Yes (24,404 = 24,404) |
| Original v1 artefacts unchanged | Yes (hash proof) |
| v2 validators reject legacy ambiguity | Yes (tests + enum mapping) |
| No overwrite of prior T10 outputs | Yes (second `--publish` refused) |
| ClariQ auxiliary only | Yes |
| SafeAgentBench absent | Yes |

## Files created

```text
docs/decisions/ADR_schema_v2_canonical_record.md
docs/reports/schema_v2_migration_report.md
docs/reports/ticket_T10_completion_report.md
scripts/migrate_schema_v2.py
src/ambiguity_manager/migration/__init__.py
src/ambiguity_manager/migration/pool_builder.py
src/ambiguity_manager/migration/run_migration.py
src/ambiguity_manager/migration/slot_mapping.py
src/ambiguity_manager/migration/v1_to_v2.py
src/ambiguity_manager/schema/v2/__init__.py
src/ambiguity_manager/schema/v2/errors.py
src/ambiguity_manager/schema/v2/jsonl.py
src/ambiguity_manager/schema/v2/records.py
src/ambiguity_manager/schema/v2/taxonomies.py
src/ambiguity_manager/schema/v2/validation.py
src/ambiguity_manager/schema/v2/json_schema.py
src/ambiguity_manager/schema/v2/schema.json
tests/fixtures/migration/*.json
tests/test_schema_v2_enums.py
tests/test_schema_v2_validation.py
tests/test_migration_v1_to_v2.py
tests/test_migration_v2_pools.py
tests/test_migration_v2_manifests.py
tests/test_migration_v2_reports.py
tests/test_schema_v2_json_schema.py
tests/test_migration_v2_publication_failure.py
```

Plus published machine outputs under `data/interim/schema_v2/`, `data/processed/schema_v2/`, and `outputs/`.

## Files modified

None of the protected v1 modules or T00–T09 artefacts were modified.

## Explicitly untouched

```text
data/raw/**
src/ambiguity_manager/converters/**
src/ambiguity_manager/weak_pool.py
src/ambiguity_manager/schema/{version,taxonomies,records,validation,jsonl,errors}.py
data/interim/{dataset}/{dataset}_canonical.jsonl (v1 paths)
data/processed/weak_pool/**
outputs/manifests/weak_pool_manifest.json
outputs/metrics/weak_pool_summary.json
configs/datasets/**
docs/reports/ticket_T00_completion_report.md … ticket_T09_completion_report.md
```

## Unresolved issues

None blocking T10. SafeAgentBench register stale reference intentionally not corrected per ticket scope.

## Stop condition

Schema v2 and migrated artefacts pass reconciliation. No model or annotation work started.
