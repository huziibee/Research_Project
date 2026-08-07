# Pilot-120 Final-Protocol Workstream Report

**Date:** 2026-08-07  
**Branch:** `cursor/pilot-120-final-protocol-3f89`  
**Base:** `feature/t12-cluster-redesign`

## Honest end-state

| Statement | Truth in this revision |
| --- | --- |
| Pilot-120 v1: FINAL-PROTOCOL ANNOTATED, ADJUDICATED, FROZEN, HASHED, EVALUATION-ONLY | **False — not claimed** |
| Pilot-120 v1: pipeline ready; gates open; NOT FROZEN | **True** |
| Full-1000: NOT READY TO FREEZE | **True** |

## Why freeze did not complete

Assumed prior artefacts (1,000-record semantic QA corpus, repaired 120 subset, pilot labels, private QA, capability D repairs, one-path contracts) are **not present** in the GitHub repository on `main` or `feature/t12-cluster-redesign`. Fabricating supervisor gold would violate annotation governance.

Machine blockers (`python3 -m ambiguity_manager.evaluation.pilot_120_cli blockers`):

1. missing `source_canonical.jsonl` (120-record repaired subset)
2. missing independent final-protocol ANN-A/ANN-B submissions
3. final_gold not produced
4. Pilot-120 manifest missing
5. ADJ-01 adjudicator identity unresolved

## Delivered

- `configs/annotation/final_protocol_v7.json` — blindness + gate contracts
- `configs/evaluation/pilot_120_v1.json` — evaluation-only config
- `src/ambiguity_manager/annotation/final_protocol_v7.py`
- `src/ambiguity_manager/evaluation/pilot_120.py` + `pilot_120_cli.py`
- `annotations/manual_kappa_v7_final_protocol/README.md`
- `FINAL_SEMANTIC_QA_REPORT.md`
- `docs/DEFERRED_FULL_1000_SEMANTIC_QA_NOTES.md`
- Tests: `tests/test_compound_ambiguity_v7_qa.py`, `tests/test_pilot_120_freeze_guards.py`
- Synthetic end-to-end freeze covered in tmp_path only (not written as official gold)

## Tests executed

```bash
python3 -m pytest tests/test_compound_ambiguity_v7_qa.py -q
python3 -m pytest tests/test_compound_ambiguity_v7_qa.py tests/test_pilot_120_freeze_guards.py -q
```

Result: **passed** (9 + 3 = 12 tests in the combined run).

## Evaluation command (after a real freeze)

```bash
python3 -m ambiguity_manager.evaluation.pilot_120_cli evaluate \
  --config configs/evaluation/pilot_120_v1.json \
  --predictions <PREDICTIONS.jsonl>
```

## Next human actions to close Pilot-120

1. Supply the repaired 120-record `source_canonical.jsonl` (D=0, one_path true, unique IDs).
2. Resolve ADJ-01 identity in `annotation_roles_v1.json`.
3. Run blind packages; supervisors ANN-A/ANN-B annotate independently.
4. Adjudicate disagreements; run `freeze`.
5. Keep Full-1000 deferred.
