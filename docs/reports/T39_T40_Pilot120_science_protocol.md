# T39/T40 Pilot-120 v1 science protocol and report boundary

## Purpose

T39 provides an execution-reproducibility and evidence atlas for the frozen
120-record Pilot-120 v1. T40 records the missing gold required for an
interpretation-quality evaluation. Both are early, non-protected
(outside the protected confirmation protocol), evaluation-only work; neither
alters the frozen source/gold/system nor informs training, tuning, threshold
choice, or selection.

## Method

The provenance gate verifies the frozen source and gold SHA-256 values,
the early cost policy, T39 evidence-policy SHA-256, Qwen/Qwen3-8B revision,
selected-adapter identity/hash, immutable code commit, container image, and
runtime environment. Five
fresh, isolated replay roots run the direct base, selected adapter, degree
router, full type/risk manager, and all-context-blind manager under existing
greedy decoding (`do_sample=False`). The three constant policies are not
re-inferred. Replicates are serialised to stay within the approved 72-hour
window: each root has a two-hour base job, two-hour adapter job, and eight-hour
manager job (60 hours total), reserving 12 hours for at most one
same-protocol recovery. The preflight is `afterok`; the adapter, manager,
per-replay sentinel, and subsequent independent root continue `afterany`.
Every sentinel emits `VERIFY_PASSED`, `VERIFY_FAILED`, or `NOT_COMPUTED`.

For every valid replay, T39 re-scores terminal accuracy/macro-F1/confusion,
asymmetric terminal cost and safety errors, ambiguity micro/macro F1 and exact
set accuracy, capability accuracy/macro-F1/per-class outcomes, and operational
validity/latency. It produces paired base/adapter disagreement ledgers, a
descriptive full-context versus all-context-blind comparison, structural slices,
and a traceable route-error atlas. Type slices below 15 and type-pair slices
below 10 are count-only.

Metric eligibility is explicit per system: terminal metrics require a valid
terminal on all 120 rows; ambiguity and capability metrics require their saved
prediction fields on all 120 rows; latency requires recorded numeric latency.
An unavailable field is `NOT_COMPUTED`, never a zero-filled or synthesized
score. The paired adapter-minus-base comparison uses the frozen T39 policy:
10,000 paired record bootstrap draws, seed 20260831, 95% percentile intervals,
and an exact two-sided sign test. Replicates are never pooled.

The full slice inventory is: depth 2, 3, and 4–5; gold route; capability;
ambiguity types with support at least 15; co-occurring type pairs with support
at least 10; gold/adjudication status; dialogue present/absent; scene and
capability-context length bins; and disagreements among the five substantive
systems. The error atlas covers false clarification, missed clarification
unsafe execution, missed rejection unsafe execution, missed rejection, false
rejection, the superordinate incorrect-execution flag, analysis-label error,
deterministic-router error given the available labels are correct, schema/retry
issues, and context-sensitive full-versus-blind disagreement. Every route error
receives two independent deterministic code passes; this is explicitly not a
human semantic-adjudication claim.

## Interpretation rules

Equal R1--R5 hashes mean reproducible execution, not five independent
performance samples. Hash drift is a runtime/reproducibility failure and will
not be averaged, pooled, or used to choose a best run. The all-context ablation
removes dialogue, scene, and capability together: it cannot prove an isolated
context-source or causal effect. Natural dialogue-present versus absent is
descriptive and confounded.

Any drift report must list changed record IDs and components, per-component
prediction hashes, Slurm job/node identifiers, container/software/runtime
provenance, and the invalid/valid component status. No performance comparison
is emitted from a failed or incomplete component.

## Required `NOT_COMPUTED` statements

- Interpretation/CPC exactness and candidate-set quality: no corresponding
  frozen gold targets.
- Clarification/rejection wording or target correctness and silent-resolution
  quality: no target/value references.
- Single-ambiguity performance: zero eligible records.
- Scene-only, dialogue-only, and capability-only effects: no such ablations.
- Generalisation: no independent confirmation set.

## Artifact locator and report completion

Before supervisor delivery, populate this document with the T39 preflight,
R1--R5 evidence-atlas, reproducibility-audit, and T40 artifact paths, hashes,
job IDs, and terminal statuses. The current early T31--T38 evidence is located
in `docs/SUPERVISOR_SCIENCE_HANDOVER_20260831.md`; it remains non-official.
T40's machine-readable deliverable is
`t40_interpretation_requirements_audit.json`, containing the missing-field
inventory and future data dictionary. Its future study requires blinded
annotators to each other's labels and system identity, per-field agreement and
adjudication, and family-disjoint data: no record, paraphrase lineage, or
shared scenario family may occur in both development and confirmation sets.
