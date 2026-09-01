# Interim science brief: Pilot-120 v1 early state

**Date:** 2026-08-31
**Status:** Interim only — not the final supervisor results document.
**Current execution:** T39 reproducibility/evidence atlas and T40
interpretation-requirements audit; the final document is gated on the
post-T39 `NOT_COMPUTED` closure programme in
`docs/reports/POST_T39_NONCOMPUTED_CLOSURE_PROGRAM.md`.

## Executive position

The project is on **Pilot-120 v1**: a frozen, hash-bound, evaluation-only
benchmark of 120 compound-ambiguity robot-command records. The early,
non-official T31--T38-named analysis/audit completed and its canonical T38
artifact passed its stated integrity checks. The selected fine-tuned adapter is
technically valid and completed the same 120-record comparison as the base
system, but it did **not** outperform direct base on this benchmark.

The defensible current claim is bounded: the experiment provides early,
non-protected evidence about how the systems behave on this particular
120-record compound benchmark. It does not establish general superiority,
official T28/T29-T38 completion, real-world robot safety, or a reason to tune
the model further. T39 will repeat the exact frozen inference protocol five
times as an execution-reproducibility audit; it is not a five-seed performance
average or a stochastic sampling study.

## Evidence locator

| Evidence | Canonical locator |
|---|---|
| Frozen Pilot source/gold/config | `data/annotations/pilot_120_v1/frozen/FROZEN_MANIFEST.json`, source `f33b1e29f1e8aa256a475f07213aa07247def47d8e2148d54a472a40b71b05c9`, gold `5e23ad1a92ff1873c8f039a8ce560a111dd6fb6b8ae8c11d6cf34dbfa1c360db` |
| Selected-adapter source-dev evidence | `/home-mscluster/mbangie/t12-hpc/runs/t28-recovery/t28-tc-mt-nuclear2500-20260808T164533Z/dev_eval_full_manager_routing_r1/routing_score_r1.json` |
| Early cost/statistics/ablation | `/home-mscluster/mbangie/t28_r5_src/outputs/pilot_120/early_t31_t33_r1/` |
| Early failure/package/audit | `/home-mscluster/mbangie/t28_r5_src/outputs/pilot_120/early_t31_t38_r1/` |
| Cluster execution | T31--T33: 45801--45803; T36--T38: 45826--45828; all `COMPLETED 0:0` |
| Code lineage | Pilot freeze `1214ab5`; T31--T33 `ff3f996`, `0fe35b8`, `fcee192`; T36--T38 `9b41e03`, `f6e2622` |

The early artifact chain contains prediction/config hashes and T38 validates
that chain. It is nonetheless an early audit, not an official T38 completion
report or an official model-selection decision.

## Frozen evaluation dataset

Pilot-120 v1 uses:

- 120 public-input records and 120 pilot-adjudicated gold labels;
- source SHA-256 `f33b1e29...b05c9` and gold SHA-256
  `5e23ad1a...1c360db`;
- 120/120 unique IDs, deterministic order, one-path determinate records, and
  zero overlap with T28 train/dev;
- existing Grok and Claude/GLM annotation with adjudication. It must be called
  **pilot-adjudicated**, not final-protocol human annotation.

Its design is informative but narrow:

| Property | Evidence |
|---|---|
| Gold terminal routes | 76 execute, 23 clarify, 21 face-preserving rejection |
| Compound depth | 46 two-type, 54 three-type, 9 four-type, 11 five-type |
| Context supplied | 120 scene contexts, 120 capability contexts, 44 non-empty dialogue histories |
| Capability labels | 97 capable, 2 conditionally capable, 7 incapable, 12 unauthorised, 2 unsafe |
| Thin ambiguity slices | recipient reference occurs once; several other type/depth slices are small |

There are **no single-ambiguity records** in Pilot-120 v1. It cannot answer
whether any system works well on single ambiguities. There is also no
scene-only or dialogue-only ablation: the context-blind system removes scene,
dialogue, and capability context together.

## Datasets and their roles

| Dataset/artifact | Role in this work | Status |
|---|---|---|
| Pilot-120 v1 | Frozen early evaluation only | Used for the results below; never training, selection, or tuning |
| AmbiK, CLARA, CoDraw-iCR v2, IndirectRequests, VAGUE | T28 source-development train/dev material | Used with field-specific loss masks; source holdout not used here |
| ClariQ | Auxiliary clarification-style pretraining only | No routing, risk, capability, rejection, or compound loss contribution |
| SafeAgentBench | Challenge dataset | Not used by the Pilot/T28 experiment |
| TEACh and teach_tatc | Excluded | Explicitly forbidden from the T28 permitted view |
| Future manual protected challenge set | Protected evaluation | Not accessed by this early experiment |
| Full-1,000 corpus | Deferred workstream | Not authorised; not freeze-ready |

The source-development split has 11,294 source-train and 2,396 source-dev
records across those five core datasets. The frozen T28 full-train contract
used Qwen/Qwen3-8B at revision `b968826d...e91218`, five task schemas, and
9,557 source-train task examples. Its candidate/ambiguity/risk/capability,
intent, CPC, and interpretation supervision uses per-field loss masking;
missing fields are not fabricated as negative labels.

## Systems actually evaluated

All five substantive systems completed with 120/120 ordered prediction rows,
schema-valid rate 1.0, and failure-error rate 0.0. Three constant policies
also completed as calibration baselines. These are development-only results.

| System | Terminal correct / 120 | Mean safety-weighted cost | Key failure pattern |
|---|---:|---:|---|
| Direct base LLM | 88 | 0.1354 | 6 gold-clarify cases executed; all 21 gold rejections correctly rejected |
| Selected fine-tuned adapter | 87 | 0.1604 | 5 gold-clarify cases executed; 5 gold rejections downgraded to clarify |
| Degree-based router | 51 | 0.2813 | 47 gold-execute cases over-clarified; all 21 gold rejections clarified |
| Full type/risk-aware manager | 33 | 0.2563 | 75 gold-execute cases clarified; 11 gold rejections clarified |
| Context-blind manager | 23 | 0.3396 | 75 gold-execute and all 21 gold-rejection cases clarified |
| Always execute | 76 | 1.0667 | Executes all 23 gold-clarify and 21 gold-rejection cases |
| Always clarify | 23 | 0.3333 | Clarifies every case; correct only on the 23 gold-clarify cases |
| Always silently resolve | 0 | 2.0000 | Emits a terminal outside the Pilot label set for every record |

The primary cost matrix imposes its largest penalty (5) for executing a
gold-rejection case. This is why route accuracy alone is insufficient.

## What the fine-tune result means

The selected recovery adapter passed its source-development routing gate with
501 complete assemblies and 296/296 fully safe eligible assemblies. This is
evidence that the adapter can be run and evaluated under the intended manager
contract. It was selected exclusively from pre-Pilot source-development
evidence; Pilot-120 did not select it and may not retrospectively justify that
selection. It is not evidence that it improves Pilot-120.

Against direct base, the adapter has a paired terminal-accuracy difference of
-0.83 percentage points (87/120 versus 88/120), 95% bootstrap interval
[-9.17, +7.50] percentage points, and exact paired sign-test p=1.0 (13
adapter-only versus 14 base-only correct records). Its mean cost is higher by
0.025 (19.25 versus 16.25 total cost). The data are compatible with a modest
advantage for either system and do not support a superiority claim.

The route confusions expose the behavioural trade-off:

| Gold route | Direct base: execute / clarify / reject | Adapter: execute / clarify / reject |
|---|---|---|
| Execute (76) | 50 / 21 / 5 | 54 / 18 / 4 |
| Clarify (23) | 6 / 17 / 0 | 5 / 17 / 1 |
| Reject (21) | 0 / 0 / 21 | 0 / 5 / 16 |

The adapter correctly executes four more gold-execute cases and has one fewer
unsafe execute on gold-clarify cases, but it loses five gold rejections by
clarifying instead. This is a substantive failure pattern to report, not a
reason to retune on the same 120 records.

**Cost reconciliation completed.** The direct-base total exactly reproduces
the frozen policy: six gold-clarify executions cost `6 × 1.00`, 21
gold-execute clarifications cost `21 × 0.25`, and five gold-execute rejections
cost `5 × 1.00`, for `16.25`. The prior 15.00 note used the wrong directional
cost for an execute-to-rejection error and is withdrawn. The adapter's 19.25
total is likewise consistent with its displayed confusion.

## Context: what is and is not shown

The context-blind manager is an all-context-removal comparison: it rebuilds
analysis after removing dialogue, scene, and capability context; it cannot reuse
a full-context analysis cache. Its 23/120 route correctness and 0.3396 cost are
worse than the full type/risk-aware manager's 33/120 and 0.2563. This observed
difference is compatible with value in the combined context bundle, not a
component-specific or causal estimate.

However, this is not a clean estimate of the separate value of scene versus
dialogue versus capability: all three were removed simultaneously, only 44
records contain dialogue, and the completed T32 paired analysis did not
predeclare or calculate the full-manager versus context-blind contrast. It is
proper to call this a descriptive context-ablation finding, not a statistically
confirmed per-context-component effect.

## Which metrics are evidence-backed now

| Metric family | Current state |
|---|---|
| Denominator, order, hashes, model/prediction identities, schema and failure rate | Complete and audited by T38 |
| Terminal routing accuracy, confusion, per-route errors | Complete for all eight systems |
| Safety-weighted terminal cost and safety errors | Complete for all eight systems |
| Paired terminal-accuracy statistics versus direct base | Complete; bootstrap 5,000, fixed seed, exact sign test |
| Predeclared cost ablations | Complete; descriptive only |
| Ambiguity type F1 and capability F1 | `NOT_COMPUTED` in the early T31--T38 package; T39 will recompute them from saved frozen predictions and existing gold without new inference |
| Interpretation/CPC exactness and candidate-set quality | `NOT_COMPUTED`: current gold has no intent/CPC/candidate targets |
| Clarification wording/target correctness, rejection wording, silent-resolution value | `NOT_COMPUTED` for this early Pilot-120 artifact |
| Single-ambiguity performance | `NOT_COMPUTED`: no eligible records |
| Scene-only, dialogue-only, and capability-only effect | `NOT_COMPUTED`: only all-context removal exists |
| Generalisation beyond Pilot-120 | `NOT_COMPUTED`: no independent confirmation set |

The project has a fuller evaluator specification (intent/CPC, candidates,
ambiguity type, risk/capability, clarification/rejection structure, and
safety/interaction metrics), but those fields were not all scored in the
completed early T31-T38 artifact. They must not be presented as completed
results.

## Observed system patterns, not causal explanations

- **Direct base** has the best observed terminal-routing and cost score in this
  early artifact. It correctly routes every gold rejection in the saved matrix,
  while executing six gold-clarification cases. This does not prove the internal
  reasoning mechanism.
- **Fine-tuned adapter** differs from direct base on some execute/clarify and
  rejection decisions. In the saved early matrix its paired comparison is not
  decisive and its frozen cost is higher. T39 will publish a disagreement ledger
  rather than attribute those changes to fine-tuning.
- **Degree router** has an observed clarification-heavy route distribution and
  weak rejection performance in the saved matrix. This fixed-pipeline result
  does not identify the responsible stage.
- **Full type/risk manager** has no saved schema or missing-row failure. In the
  finite 120-row matrix, it has zero safety-critical execute-on-gold-rejection
  errors among the 21 gold-rejection rows, while executing only 1 of 76
  gold-execute records. The evidence establishes an output distribution, not an
  inferred explanation such as “conservatism” or a real-world safety claim.
- **Context-blind manager** has the most clarification-heavy observed output.
  The full-versus-blind contrast removes dialogue, scene, and capability context
  together, so it cannot identify a source-specific or causal context effect.

Historical technical failures are preserved separately. An earlier unselected
R6 adapter produced unbounded/repetitive `predict_interpretations_v1` output
and was ineligible; decoder bounds (candidate count/text and CPC bounds) fixed
the generation-contract issue for the later recovery path. The final five-system
matrix itself has no saved schema or missing-row failure. That supports
evaluating its output patterns, but does not itself identify the mechanism
behind any performance difference; T39 adds fresh runtime provenance and
reproducibility checks before drawing even that bounded conclusion.

## What is incomplete before report writing

The early result package may be used only as an internal working draft for a
bounded results/methods/limitations chapter. No final supervisor results
document or table is produced until the T39+T40+T41+T42+T43+T44 closure gate in
`docs/reports/POST_T39_NONCOMPUTED_CLOSURE_PROGRAM.md` is terminal. Before
quoting a comprehensive manager evaluation, the following remains incomplete:

1. `NOT_COMPUTED` — **T39**: a no-new-inference, evidence-only slice report: depth,
   ambiguity type,
   capability, natural dialogue presence, and all base/adapter disagreements.
2. `NOT_COMPUTED` — **T39/T43**: a paired full-context versus context-blind analysis if a
   formal context claim is desired; the present contrast is descriptive.
3. `NOT_COMPUTED` — **T40/T41**: an interpretation evaluation dataset/artifact with gold intent, CPC,
   candidates, resolution values, and clarification/rejection targets. Pilot
   terminal gold alone cannot prove interpretive quality.
4. `NOT_COMPUTED` — **T42**: any single-ambiguity claim requires a separate
   frozen study and is limited to its pre-registered corpus/eligible strata.
5. `NOT_COMPUTED` — **T43**: scene-only, dialogue-only, and capability-only
   estimates require the separately frozen factorial study.
6. `NOT_COMPUTED` — **T44**: only narrow held-out-corpus generalisation may be
   assessed; official/protected generalisation remains blocked by its separate
   protocol and is outside this early report.

## Recommended next decision

**Approved now:** run the frozen T39 queue (five isolated greedy replays plus
CPU-only scoring and error/slice reports) and T40's no-annotation field audit.
Include null/adverse adapter findings and label every result early,
non-protected, and not-for-tuning/selection. Do not launch full-1,000 work,
dataset expansion, perturbation tests, or a changed inference condition.

**Included in approved T39:** CPU-only scoring and slice analysis over
hash-bound predictions will create the descriptive error atlas, with
`NOT_COMPUTED` for unavailable fields and count-only reporting for thin
denominators. This requires no model/gold change, protected data, or tuning.

**No 200/+80 or 1,000-record extension is part of this programme.** The former
discussion of a possible 200-record extension is historical and not an
alternative route to closing the T39–T44 evidence gaps or to producing the
final supervisor document.

## Boundaries for approval

- **Currently running:** only the fixed Pilot-120 T39/T40 batch, including its
  CPU-only evidence work. **Approved after the T39/T40 terminal gate:** T41–T44
  protocol and execution, each only after its own immutable-input and claim
  gates pass. Their status is not a claim that their results already exist.
- No Pilot-120 result may select, tune, retrain, or change the adapter.
- No full-1,000 or deferred +80 activity is part of the approved closure
  programme.
- Every T41–T44 cluster job must use its frozen input manifest and
  pre-registered claim boundary; it must write `NOT_COMPUTED` rather than a
  proxy if its own gates fail.
