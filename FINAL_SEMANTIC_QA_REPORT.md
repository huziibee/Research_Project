# Final Semantic QA Report — Pilot-120 / Full-1000 gate inspection

**Date:** 2026-08-07  
**Branch:** `cursor/pilot-120-final-protocol-3f89`  
**Protocol:** `final_protocol_v7`  
**Inspection command:** `python3 -m ambiguity_manager.evaluation.pilot_120_cli discover`

## Verdict

| Scope | Status |
| --- | --- |
| **Pilot-120 v1** | **NOT FROZEN** — final-protocol gates are open; required 120-record repaired subset and independent supervisor annotations are absent from this repository |
| **Full-1000** | **NOT READY TO FREEZE** |

This report intentionally does **not** claim:

`Pilot-120 v1: FINAL-PROTOCOL ANNOTATED, ADJUDICATED, FROZEN, HASHED, EVALUATION-ONLY`

because that statement would be false in the current repository state.

## Step 1 — Assumed artifacts vs repository reality

The task assumed these artefacts already existed. Discovery results:

| Assumed artefact | Present at inspection start |
| --- | --- |
| `FINAL_SEMANTIC_QA_REPORT.md` | No (this file creates the report) |
| `docs/DEFERRED_FULL_1000_SEMANTIC_QA_NOTES.md` | No (created by this workstream) |
| `annotations/manual_kappa_v7_final_protocol/README.md` | No (created by this workstream) |
| `tests/test_compound_ambiguity_v7_qa.py` | No (created by this workstream) |
| 120-record repaired evaluation subset | **No** |
| Final-protocol ANN-A / ANN-B submissions for 120 | **No** |
| Adjudicated Pilot-120 gold | **No** |

Related existing programme state (from `feature/t12-cluster-redesign`):

- T13 calibration package: **n=24** candidates, **no official gold**
- Main manual pool: **authored_main_n=0**, remaining_to_author=300
- T14A tooling: ready for synthetic/double-annotation mechanics
- T14B/T14C: human annotation **has not started**
- `ADJ-01` adjudicator identity: **unresolved**
- DEC-20260722-002: future manual protected challenge set **does not exist yet**

No git object, branch tip, or tracked path contained:

- a 1,000-record compound-ambiguity semantic-QA corpus
- a 120-record repaired subset with capability-class D = 0
- `one_path_determinacy` contracts for 120/120
- `manual_kappa_v7` pilot labels
- private owner QA labels

## Claimed prior semantic-QA numbers (unverified here)

The task brief asserted:

- full 1,000-record benchmark is not ready to freeze
- 231 capability-class-D rows remain outside the 120
- one-path contracts complete for only 120/1000
- 120 subset repaired for current use (20/120 capability_context-only factual repairs)
- within 120: capability D=0, 99 class A, 21 class B, one_path_determinacy true for 120/120
- prior agreement must remain labeled only as `pilot_annotation_agreement`

**None of those corpus artefacts are present to verify.** They are recorded as **external/unpushed claims**, not as repository facts. This workstream therefore cannot reannotate, adjudicate, hash, or freeze them.

## Independence / blindness check

Final-protocol machinery added in this branch enforces:

- blind packages contain only permitted evidence fields
- forbidden pilot/private/adjudication label keys are stripped
- evaluation loader refuses training/dev/tuning purposes
- historical pilot agreement is labeled `pilot_annotation_agreement` only

Because no prior pilot/private label files are present, annotators cannot accidentally read them from the repo. The blindness workflow is ready; human supervisor annotations are not.

## Capability / one-path status (Pilot-120)

| Check | Result |
| --- | --- |
| Exactly 120 intended records present | **FAIL** (0 present) |
| Capability D = 0 within 120 | **N/A** (no subset) |
| one_path_determinacy true for 120/120 | **N/A** (no subset) |
| Immutable evidence fields unaltered by latest repair | **N/A** (no repair diff present) |

## Freeze blockers (machine-readable)

See `data/annotations/pilot_120_v1/STATUS.json` after:

```bash
python3 -m ambiguity_manager.evaluation.pilot_120_cli status
```

Typical blockers at this revision:

1. missing `source_canonical.jsonl` (120-record repaired subset)
2. missing independent final-protocol ANN-A/ANN-B submissions
3. final_gold not produced
4. Pilot-120 manifest missing / not frozen
5. `ADJ-01` adjudicator identity unresolved

## What this branch delivers instead

1. `final_protocol_v7` config and blind-package builder
2. Final-protocol agreement metrics (terminal strategy kappa, multilabel ambiguity, capability)
3. Adjudication/export/freeze/hash/eval-handoff pipeline with hard gates
4. Evaluation-only loader guard (refuses train/dev/tuning)
5. Deferred Full-1000 notes
6. Tests for gates, blindness, leakage, hashing, and blocked freeze

## Full-1000

**Full-1000: NOT READY TO FREEZE**

Remaining blockers include (non-exhaustive): authoring/repair of the remaining corpus, 231 deferred class-D repairs outside Pilot-120, completion of one-path contracts beyond 120, independent final-protocol annotation at full scale, adjudication, leakage-safe splits, and T29/T30 protocol freeze. See `docs/DEFERRED_FULL_1000_SEMANTIC_QA_NOTES.md`.

## Honest end-state statements

- **Pilot-120 v1:** NOT FROZEN (pipeline ready; human/final-protocol gates open)
- **Full-1000:** NOT READY TO FREEZE
