# Science restart plan and evidence state (2026-08-31)

## Decision

Continue from the frozen Pilot-120/T31-T38 early-analysis line. Do not spend
the next iteration improving the manager. Treat the existing fine-tuned
adapter and manager configurations as fixed experimental conditions. The
purpose of the next phase is explanation, error analysis, and a defensible
decision about whether a later intervention is warranted.

The active branch is `science/pilot120-t38`, rooted at `1214ab5`.
Current manager/Compound-120 work is preserved separately on
`archive/manager-compound120-20260831` at `8e430ab`.

## What is established

- Pilot-120 v1 is frozen, evaluation-only, hash-verified, 120/120 one-path
  deterministic, and has no T28 train/dev overlap. It must not be used for
  training, threshold selection, prompt tuning, or adapter selection.
- The T28 fine-tuning lineage has working development evidence, but the
  resulting adapter is not evidence of a general performance improvement.
- Cluster jobs 45826 (T36), 45827 (T37), and 45828 (T38) completed with exit
  `0:0`. The canonical T38 audit reports `audit_passed=true` for the early
  120-record chain and explicitly says it is not valid for official use,
  full-1000 closure, tuning, training, or selection.

## Current early result table

Canonical source: `early_t31_t38_r1` on the cluster. These are descriptive,
non-protected Pilot-120 results, not final system claims.

| System | Correct terminal routes / 120 | Safety-weighted cost | Unsafe execute when gold is clarify | Interpretation |
|---|---:|---:|---:|---|
| Direct base | 88 | 0.1354 | 6 | Current best early cost and accuracy |
| Selected adapter | 87 | 0.1604 | 5 | One fewer correct route and worse cost than base |
| Degree router | 51 | 0.2813 | 1 | Lower accuracy, fewer unsafe executes |
| Full type/risk manager | 33 | 0.2563 | 0 | Safer on this metric, but much lower route accuracy |
| Context-blind manager | 23 | 0.3396 | 0 | Context removal is strongly harmful to route accuracy |

The base-versus-adapter difference is one record and the adapter has higher
cost. It is not evidence that fine-tuning improved this benchmark. Any claim
of improvement would require a separately frozen confirmation set.

## Sample-size decision

Use the frozen 120 now. Do not jump directly to the current 1,000-record
artifact: its semantic QA is not ready to freeze, including 231
capability-evidence-D records and incomplete one-path contracts.

The recommended next expansion, if authorised, is a separately frozen,
stratified 80-record extension (total 200). It should repair known coverage
gaps rather than add more common execute cases: aim for at least about 40
clarify cases, 40 rejection cases, 40 depth-4/5 cases, and meaningful counts
of safety/capability/type phenomena. Preserve family isolation from the
original 120 and publish independent sampling, gold, hash, and protocol
records.

At a proportion near 50%, a 95% interval is roughly plus/minus 8.8 percentage
points with 120, 6.9 with 200, and 3.1 with 1,000. Thus 120 supports large
paired effects and qualitative failure analysis; 200 is a useful precision
and coverage improvement; 1,000 becomes valuable only after its underlying
QA is genuinely complete.

## Required analysis table

Build one denominator-preserving table from the frozen predictions, with raw
counts and confidence intervals. Pre-specify the following rows before looking
for a preferred result:

1. Overall system comparison and paired base-versus-adapter comparison.
2. Context available versus context removed (the full versus context-blind
   matched manager condition).
3. Gold terminal route: execute, clarify, reject.
4. Ambiguity depth: 2, 3, 4, and 5 types; optionally 2-3 versus 4-5 only if
   declared before analysis.
5. Risk/capability status and unsafe-execute/silent-resolution safety errors.
6. Ambiguity type only where the denominator is adequate; otherwise report
   the count and `NOT_COMPUTED`, not an unstable p-value.
7. A case review of every base/adapter disagreement and every safety error,
   with record IDs and the raw evidence link.

Pilot-120 has compound ambiguities (depth 2-5), not a single-ambiguity stratum.
It cannot answer whether the manager works well on single ambiguities. That
requires a separately frozen single-ambiguity evaluation set and must be
reported as a distinct study, not a retrospective slice of this benchmark.

## Operational next steps

1. Retrieve and hash-verify the canonical T31-T38 artifacts; do not recreate
   them from local status files.
2. Produce the above analysis table and a short error atlas, preserving all
   120 records in each denominator.
3. Write a results report that labels every outcome `EARLY`, `NON-PROTECTED`,
   and `NOT FOR TUNING OR SELECTION`.
4. Decide from that report whether an 80-record extension is justified. If
   yes, obtain approval and freeze its protocol before sampling or annotation.
5. Leave manager changes, adapter changes, and the current Compound-120 v2
   work on the archive branch unless a later scientific finding justifies a
   separate authorised intervention.

## Scope boundary

This plan does not close official T28/T29-T38, does not validate the current
full-1,000 corpus, and does not authorise tuning. It closes the early
Pilot-120 analysis chain only: its integrity is verified, while its scientific
claims remain bounded to the frozen 120-record benchmark.
