# T28-R1 source-record join recovery

## Ticket

- ID: T28-R1
- Title: Restore the Frozen T15 Source-Record Join
- Scope: source availability and validation only; no training, checkpoint selection, adapter selection, T29, or protected evaluation

## Result

**BLOCKED**. The exact existing canonical artifact was recovered and the permitted T28 train/dev view was materialised. The acceptance gate remains blocked because the authoritative licence register has unresolved or unverified licence identifiers for every included source dataset. The repository licence policy explicitly blocks training while those statuses remain unresolved.

## Preconditions and provenance investigation

- Original HEAD: `72025f8de977f68f7a20a6db15c130d2cc173c95`
- Final HEAD: `72025f8de977f68f7a20a6db15c130d2cc173c95` (working-tree changes are uncommitted)
- Branch: `feature/t12-cluster-redesign`
- Existing artifact history: T09 committed the deterministic builder and documents the canonical output as git-ignored; no canonical JSONL is tracked in Git history.
- Git LFS: only the VAGUE parquet is LFS-managed; the canonical pool is not.
- Existing artifact location: `data/processed/weak_pool/weak_pool_canonical.jsonl`
- Recovery mode: existing artifact recovered; no rebuild or newer download used.
- The artifact is larger than the 192-record T27C smoke subset and its recorded T09 hash matches the file on disk.

## Counts and hashes

| Item | Count | SHA-256 |
|---|---:|---|
| Existing primary canonical pool | 15,839 | `1e51cac046e014a6b890b10a155d22e32e01aa276d4507a10ad4f86abcf9942a` |
| Frozen permitted source_train | 11,294 | included in view |
| Frozen permitted source_dev | 2,396 | included in view |
| T28 permitted train/dev view | 13,690 | `34b551c37c8f97c24c1263a2cc12a9497e65f754924f1404c47055999f04ea22` |
| T15 source_holdout rejected from view | 2,149 | not materialised |

Source-level permitted view counts: AmbiK 850, IndirectRequests 770, CoDraw-iCR v2 5,980, VAGUE 1,426, and CLARA 4,664. ClariQ is auxiliary and is not in the primary T28 view.

Join validation found zero missing IDs, zero duplicate canonical IDs, zero unexpected IDs, zero train/dev group overlap, zero missing command/source content, and 5,498 groups in the view. The 1,998 repeated groups are within-role repetitions, not cross-split leakage.

The T27F schema registry was loaded CPU-only at generation schema `1.0.0`; its five committed schema hashes are recorded in `weak_pool_canonical.manifest.json`. The canary built 13,058 valid structured targets and skipped 632 records with no concrete authorised supervised field. No unknown field was converted to a negative label.

## Licence and provenance gate

The authoritative register `configs/licences/dataset_licence_register.json` reports AmbiK, IndirectRequests, CLARA, VAGUE, and ClariQ as `unresolved`, and CoDraw-iCR v2 as `stated_unverified`. Their licence identifiers are null. The source-version manifest preserves the exact per-input hashes and committed mapping versions, but cannot invent missing licence evidence or upstream revision identifiers.

Therefore the source join is technically recovered, but T28-R1 cannot be marked PASS under the requested “licences and provenance complete” acceptance criterion.

## Files created or changed

- `src/ambiguity_manager/data/t28_r1_join.py`
- `scripts/t28_r1_restore_source_join.py`
- `tests/test_t28_r1_source_join.py`
- `data/processed/weak_pool/weak_pool_canonical.manifest.json`
- `data/processed/weak_pool/t28_permitted_train_dev.jsonl`
- `data/processed/weak_pool/source-version.manifest.json`
- `data/processed/weak_pool/provenance.manifest.json`
- `data/processed/weak_pool/licence.manifest.json`
- `data/processed/weak_pool/exclusion.report.json`
- `data/processed/weak_pool/join-validation.report.json`
- `data/processed/weak_pool/checksums.json`
- `docs/reports/T28_R1_source_record_join_recovery.md`
- `docs/reports/T28_R1_handover.md`

The canonical artifact itself was not rewritten. Frozen T15 manifests, split membership, labels, eligibility, and group assignments were not modified.

## Commands and results

- Required grounding files, T15 reports/manifests, T09 builder, source adapters, licence/provenance records, and duplicate/split validation code: read.
- `git log`, branch/tag/worktree/LFS/ignored-file/history audit: completed.
- Red: `PYTHONPATH=src python -m unittest tests.test_t28_r1_source_join -v` -> failed on missing `ambiguity_manager.data.t28_r1_join`.
- `PYTHONPATH=src python scripts/t28_r1_restore_source_join.py` -> join/canary PASS; licence status explicitly incomplete.
- `PYTHONPATH=src python -m unittest tests.test_t28_r1_source_join -v` -> 8 passed.
- `PYTHONPATH=src python -m unittest tests.test_t15_source_splits tests.test_t28_contract -v` -> 30 passed.
- T27F pytest invocation could not run because this checkout has no pytest executable/environment; existing committed T27F evidence remains unchanged and was not re-run with a new environment.
- No GPU job, model load, training entry point, checkpoint evaluation, adapter selection, or T29 command was run.

## Stage gate

**BLOCKED** on unresolved licence/provenance evidence. T28 may not resume until those source permissions and immutable upstream identities are verified or an explicit institutional decision changes the gate. Following that separate human approval, rerun this recovery command and the T28 predeclare/data-integrity gate. T29 remains unopened.

