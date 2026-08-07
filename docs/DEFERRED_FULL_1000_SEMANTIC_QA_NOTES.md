# Deferred Full-1000 Semantic QA Notes

**Status:** Full-1000 **NOT READY TO FREEZE**  
**Date:** 2026-08-07  
**Related:** `FINAL_SEMANTIC_QA_REPORT.md`, `configs/annotation/final_protocol_v7.json`

## Scope boundary

This note records why the full ~1,000-record compound-ambiguity benchmark must remain deferred.  
**Do not** mass-rewrite the 1,000, repair remaining class-D rows outside Pilot-120, complete the other 880 one-path contracts, or start a full-1,000 freeze in the Pilot-120 workstream.

## Why Full-1000 is blocked

1. **Corpus absent in repository.** No tracked 1,000-record semantic-QA benchmark exists on `main` or `feature/t12-cluster-redesign`.
2. **Manual programme incomplete.** T13 main authoring remaining = 300; T14B/T14C supervisor annotation has not started; ADJ-01 unresolved.
3. **Task-brief external claims unverified.** Assertions about 231 class-D rows outside a 120 subset, and partial one-path coverage (120/1000), cannot be audited without the missing corpus.
4. **Pilot-120 itself is not frozen yet.** Full-1000 freeze cannot precede a completed, hashed Pilot-120 evaluation slice and the broader T15/T29 gates.

## Deferred workstreams (later)

| Workstream | Notes |
| --- | --- |
| Repair remaining class-D rows | Outside Pilot-120 only after Pilot-120 freeze |
| Complete one-path contracts for remaining records | Not in this task |
| Full-1000 final-protocol annotation | Requires supervisor ANN-A/ANN-B capacity |
| Full-1000 freeze + hashes | After T14C/T15/T29 |
| Training on evaluation gold | Forbidden |

## Allowed near-term focus

- Close Pilot-120 final-protocol human gates when the repaired 120 subset is supplied
- Keep Full-1000 explicitly deferred and evaluation-protected

## Statement

**Full-1000: NOT READY TO FREEZE**
