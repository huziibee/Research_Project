# Ticket completion report

## Ticket
- ID: T09
- Title: Weak labelled pool builder

## Preconditions checked
- T00–T08 complete; canonical schema v1.0.0 frozen; 246 tests green before T09.
- All six approved canonical inputs present under `data/interim/{dataset}/`.
- All six conversion summaries present under `outputs/metrics/`.
- SafeAgentBench excluded: no approved canonical converter output.
- Curated configs and T03–T08 converter outputs not modified.

## Files created/changed

### Created
- `src/ambiguity_manager/weak_pool.py`
- `scripts/build_weak_pool.py`
- `tests/test_weak_pool.py`
- `tests/fixtures/weak_pool/tiny_ambik.jsonl`
- `tests/fixtures/weak_pool/tiny_indirect_requests.jsonl`
- `tests/fixtures/weak_pool/tiny_codraw_icr_v2.jsonl`
- `tests/fixtures/weak_pool/tiny_vague.jsonl`
- `tests/fixtures/weak_pool/tiny_clara.jsonl`
- `tests/fixtures/weak_pool/tiny_clariq.jsonl`
- `docs/reports/weak_pool_report.md`
- `docs/reports/ticket_T09_completion_report.md`

### Generated (git-ignored data/outputs)
- `data/processed/weak_pool/weak_pool_canonical.jsonl`
- `data/processed/weak_pool/weak_pool_auxiliary.jsonl`
- `data/processed/weak_pool/weak_pool_membership.jsonl`
- `outputs/manifests/weak_pool_manifest.json`
- `outputs/metrics/weak_pool_summary.json`

### Not modified
- `data/raw/**`
- `src/ambiguity_manager/schema/**`
- `src/ambiguity_manager/converters/**`
- `configs/datasets/*.json`
- T03–T08 canonical converter outputs

## Tests written first, if TDD applies
- Test file: `tests/test_weak_pool.py`
- Red phase: `PYTHONPATH=src python -m unittest tests.test_weak_pool -v`
  -> `ModuleNotFoundError: No module named 'ambiguity_manager.weak_pool'` (errors on import).
- Green phase: 28 weak-pool tests pass; full suite **274** tests pass.

## Commands run
- Red: `PYTHONPATH=src python -m unittest tests.test_weak_pool -v` -> FAILED (ModuleNotFoundError)
- Green (module): `PYTHONPATH=src python -m unittest tests.test_weak_pool -v` -> OK (28 tests)
- Green (full): `PYTHONPATH=src python -m unittest discover -s tests` -> OK (274 tests)
- Build: `PYTHONPATH=src python scripts/build_weak_pool.py` -> success (twice; deterministic)

## Validation results

### Per-dataset verified counts
| Dataset | Input lines | Summary `rows_converted` | Agreement |
| --- | ---: | ---: | --- |
| ambik | 1,000 | 1,000 | yes |
| indirect_requests | 906 | 906 | yes |
| codraw_icr_v2 | 7,034 | 7,034 | yes |
| vague | 1,677 | 1,677 | yes |
| clara | 5,222 | 5,222 | yes |
| clariq | 8,565 | 8,565 | yes |

### Pool accounting
| Metric | Measured |
| --- | ---: |
| Primary pool | 15,839 |
| Auxiliary pool | 8,565 |
| Membership rows | 24,404 |
| Global unique IDs | 24,404 |

### Disjointness and union
- `primary_auxiliary_disjoint`: true
- `membership_equals_union`: true
- Independent primary ∩ auxiliary ID overlap: 0

### Record preservation
- Every output canonical record is field-semantically identical to its input
  (`canonical_record_to_dict` equality per ID).
- No dataset-role fields injected into canonical records.

### Deterministic rerun
All machine artefacts byte-identical across two consecutive builds:

| Artefact | SHA-256 |
| --- | --- |
| Primary pool | `1e51cac046e014a6b890b10a155d22e32e01aa276d4507a10ad4f86abcf9942a` |
| Auxiliary pool | `0f7e34debfbb0638b221faef80d43c5fe8408ce7e2705e031d3ff6960c8ad94f` |
| Membership | `4f8bc0f914ae739b549908b46a194ab0a38983abc41c1edd4ed58e04aaee8162` |
| Manifest | `daed5412fa30a587530cce4c4247ebd40f6106cdc0f7d4f7f333036e9c3bd5f8` |
| Summary | `90d521eb1832fe01c4036c2f6c51fd1495e039bc27a82fd36ce513edb6222d6c` |

### Input SHA-256
| Dataset | SHA-256 |
| --- | --- |
| ambik | `5a37b0dac5f9e2bf293868c680b3d80cc019bcc5866e8055a5297efdf1a7762e` |
| indirect_requests | `796257f026a701a68afe902dbdc97a87a767797ed7156f5aaa8504f74459600e` |
| codraw_icr_v2 | `c8fa4f731518bda7a7b7d4fa4a15611fd9e855ee197bcfcca2726f2f39740a6b` |
| vague | `81a5e82ba2013680c91d4a8ba6c1b81002b0b883fe9fb8bb503b80bfcd680b5d` |
| clara | `80e9b85517db1d5de33fc3c69639e4d4582edd3098665cdeedd5280d305d8507` |
| clariq | `262523b522921f80b5db25024610049cf2789f72c3e6bb89156aaa9c4fb83dc1` |

### Overlap analysis (report-only)
| Metric | Count |
| --- | ---: |
| Integrity duplicate groups | 0 |
| Semantic-payload duplicate groups | 3,226 |
| Exact command duplicate groups | 1,238 |
| Normalized command duplicate groups | 1,212 |
| Command + scene_context duplicate groups | 1,314 |
| Cross-dataset normalized-command overlaps | 0 |
| Repeated non-null group_id values | 1,966 |

## Acceptance criteria status
- [x] All required canonical inputs verified
- [x] Physically separate primary and auxiliary pools
- [x] ClariQ only in auxiliary pool with `core_pool_status=ineligible`
- [x] Conditional-core datasets marked `conditional_pending`
- [x] Core datasets marked `eligible`
- [x] All records schema-valid and field-preserved
- [x] Globally unique IDs
- [x] Deterministic machine artefacts (no timestamp/git in manifest/summary)
- [x] Full provenance manifest with input/output hashes
- [x] Exact row accounting invariants
- [x] Overlap reported, no deduplication
- [x] No split assignment or relabelling
- [x] Guarded writes via `resolve_writable_path()`
- [x] No raw corpus text in machine summaries or reports
- [x] TDD red phase recorded; 274 tests pass

## Row counts / metric outputs, if applicable
- Primary: 15,839
- Auxiliary: 8,565
- Membership: 24,404

## Evidence and traceability
- Builder version: `weak_pool-1.0.0`
- Canonical schema: `1.0.0`
- Git commit at build: `79027cb779b9c49daa31ca22261668e5b7c8b58c`
- Build timestamp (completion report only): 2026-07-10T17:43:24Z (approx.)

## Unresolved TODO_VERIFY / BLOCKED items
- SafeAgentBench `expected_converter_ticket: T09` in curated register remains a stale
  field; not corrected without separate approval.
- SafeAgentBench licence status remains unresolved in licence manifest.

## Stage gate
PASS

Reason: All T09 acceptance criteria met; accounting invariants verified on real
inputs; deterministic artefacts produced; no scope leakage into splits, relabelling,
or SafeAgentBench conversion.
