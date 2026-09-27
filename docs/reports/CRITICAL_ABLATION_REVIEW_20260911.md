# Critical ablation review — 2026-09-11

## Purpose and claim boundary

This review audits the evidence available before reading any queued dataset-native
full-run results. It distinguishes frozen Pilot-120 T39 observable semantic-goal
trace results from future dataset-native exploratory results. T39/T41 are frozen
and are not modified or rerun.

The T39 semantic measure is **Observable Semantic Goal Trace Correctness**. It
does not establish hidden model intent, faithful internal reasoning, or
intent-summary accuracy.

## Current evidence snapshot

| Frozen T39 system | SGC | SAA | FIC | SGC correct and route wrong |
|---|---:|---:|---:|---:|
| Context-blind manager | 95/120 (79.17%) | 82/120 (68.33%) | 69/120 (57.50%) | 75/120 (62.50%) |
| Degree router | 113/120 (94.17%) | 76/120 (63.33%) | 70/120 (58.33%) | 65/120 (54.17%) |
| Full manager | 113/120 (94.17%) | 76/120 (63.33%) | 70/120 (58.33%) | 83/120 (69.17%) |

The paired full-versus-context-blind SGC contrast is +18/120 (+15.0 percentage
points). The discordant pair count is 23 full-correct/context-blind-wrong versus
5 in the reverse direction (McNemar p=0.000912). This is evidence of a strong
within-record association in this frozen trace evaluation, not evidence that a
particular context component caused the change.

## What the existing ablations support

1. **Goal trace and terminal behaviour are dissociated.** For the full manager,
   83 of 120 records have an SGC-correct observable trace but wrong route. This
   supports the narrow claim that a correct visible goal interpretation can
   coexist with a wrong interaction decision.

2. **Textual context is associated with better visible goal recovery.** The
   full/context-blind comparison is paired and statistically strong at the trace
   layer. It is a useful diagnostic contrast to carry into future work.

3. **Indirect requests expose a different failure surface.** Full-manager SGC
   is 29/29 on the frozen indirect slice while SAA and FIC are 1/29, and only
   5/29 have a correct route conditional on SGC. This is evidence that the
   speech-act/route decision can fail even when the scored visible goal trace
   passes. It is not proof about hidden intent.

## What cannot be identified from those ablations

| Question | Why it is not identified | Required next evidence |
|---|---|---|
| Which context element matters: scene, dialogue, capability, or policy? | The full/context-blind systems remove or alter more than one source of information. | Factorial, frozen-context ablation with one controlled change per condition (T43). |
| Is the final error a router/policy error? | Frozen T39 outputs contain zero CPC candidates, selected interpretations, resolved slots, and resolution evidence. | Future explicit interpretation/CPC output and deterministic evaluator. |
| Does SGC measure internal intent? | T39 has no structured `intent_summary`; SGC judges only observable text. | Future schema V2 with end-to-end preservation tests and blinded evaluation. |
| Is semantic performance general across datasets? | Pilot-120 labels and native datasets use different targets and source-label quality. | Dataset-specific reporting; no pooled accuracy claim. |

The frozen layer counts should therefore be read as: full manager L1 semantic-goal
wrong=4, L2 semantic-goal-correct/speech-act-wrong=33, L3 goal-and-speech-act
correct but downstream route/CPC evidence insufficient=50. Layer 4 is
`NOT_COMPUTED`, rather than a claim that the router is at fault.

## Dataset-native studies: valid questions and limits

| Dataset | Valid queued question | Design strength | Limit that must appear in reporting |
|---|---|---|---|
| VAGUE | Does a textual `meta.caption` improve subject/action/object goal recovery against the command-only condition? | Matched within-record context ablation. | Caption is text, not visual scene evidence; score is source-derived. |
| AmbiK | Can the system recover the dataset's ambiguity-type set? | Native type target and exact-set scorer. | Source mapped labels are not newly adjudicated human gold. This is not a context ablation. |
| CLARA | Does provided source context change the source-defined ambiguity/capability/routing outputs? | Paired condition comparison. | The blind condition removes multiple context dimensions, so effects cannot be assigned to one component. |
| Indirect Requests | Can the system recover source-defined pragmatic ambiguity/missing-slot fields? | Native pragmatic diagnostic. | It does not independently establish semantic-goal correctness. |
| CoDraw / ClariQ | Can a clarification satisfy the source/context goal? | Potentially useful. | Official scoring remains blocked until independent blind semantic review and adjudication are implemented. |

No dataset-native result may be called an official Pilot-120 score, used for
model selection, or pooled with another dataset as a common "intent" accuracy.

## Runtime and protocol confounds to control

1. Compare Gemma and GLM only after both complete the identical input packet,
   prompt, schema, scoring version, and approved GPU runtime. A malformed JSON
   response or a node GPU failure is an infrastructure observation, not a model
   accuracy result.
2. `mscluster111` is quarantined for model inference until a dedicated GPU
   preflight demonstrates a working allocation. The prior vLLM failure was
   `RuntimeError: No CUDA GPUs are available`; `mscluster110` is the proven
   execution node.
3. The structured-output runners were technically repaired after malformed
   canaries by adding a schema-only retry. This is a transport/protocol
   deviation, not a semantic criterion change, but every full result must carry
   the final runner hash and a deviation record. The pre-repair canaries prove
   environment connectivity only; they are not final configuration performance
   evidence.
4. The full outputs must be hash-frozen before scoring, error inspection, or any
   further change to prompt, retry text, parser, or scorer.

## Decisions already baked into the completion plan

- Keep the early report lane separate from the official evidence lane.
- Treat VAGUE as the cleanest immediate context ablation, AmbiK as type
  recovery, and CLARA as a composite context diagnostic.
- Build reviewer packets for CoDraw/ClariQ rather than inventing a lexical or
  self-judged semantic scorer.
- Use recurring failures only to define a future, preregistered stratum; never
  to modify an in-flight system after results are read.
- Preserve T42 as an independent, human-validated, single-unresolved-ambiguity
  study with Pilot-120/T41/T44 exclusion ledgers.

## Immediate gates before reporting a results table

1. Full output coverage, packet fingerprint, exact schema, and manifest pass.
2. Freeze full-output and scorer hashes before inspecting row-level errors.
3. Score only with the matching deterministic source-target scorer.
4. Report denominator, confidence interval, invalid/missing rows, weak-label
   caveat, and `NOT_COMPUTED` fields.
5. Run an independent final audit of mappings, condition blindness, denominators,
   and future-versus-frozen separation.
