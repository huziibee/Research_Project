# Frozen Goal-First semantics to GLiNER routing v1

## Question and scope

Can `fastino/GLiNER2.5-Decide` convert the saved study-default T0.7
Goal-First interpretation into the correct EXECUTE / CLARIFY / REFUSE route?
This is a new semantic-to-action experiment, separate from the
[raw-source multi-head probe](GLINER25_DECIDE_PIPELINE_HEADS_V2.md).
No Goal-First generation, source-packet inference, paper edit, or frozen
evidence replacement is part of this experiment.

Pilot-120 already informed development. All comparisons and selection of the
best ablation are exploratory development-set diagnostics. The 117/120 intent
figure is the final matched two-judge semantic-intent screening result; no
approved protocol deviation was found authorizing it as independently validated
official correctness. See [paper reproducibility](../PAPER_REPRODUCIBILITY.md).
Intent-positive does not guarantee grounded, authorized, safe robot action.

## Exact frozen interpretation

Archive: [p120_full_analysis_20260923.zip](../../research/pilot120/artifacts/p120_full_analysis_20260923.zip).
Member: `temperature_ablation_existing/T0.7/predictions/goal_first_manager_v2.predictions.jsonl`.
The script reads this exact member, never another run or regenerated output.

| Evidence | SHA-256 |
| --- | --- |
| Full-analysis archive | `0305b1e9ab062876ee6ee89778cc6028d2eaf01718b7dd0295944e7d9cb81a01` |
| Frozen Goal-First member | `e6cb2070aa56c566f955ce064775ffaac489a82962135ee69445b6e53182f258` |
| Frozen gold | `5e23ad1a92ff1873c8f039a8ce560a111dd6fb6b8ae8c11d6cf34dbfa1c360db` |
| Final matched-baseline archive | `34ca50e034ca37b617068bb50c734d12fa26282fb5eec563c11ead700163e491` |
| Final comparison CSV member | `f1e013cc6a6f70b9b58da390d704c48ee41f05c57b12b6dec23affbc8c9c3ddc` |

There are exactly 120 unique IDs matching frozen Pilot-120 gold. Goal-First
system version is `2.0.0`; the study-default manifest specifies temperature
0.7 and seed 0. Its model is
`Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`.
The exact run-manifest member is
`temperature_ablation_existing/T0.7/run_manifest.json`, SHA-256
`5d7873e6d18bbd1016b9d541557c26e4d0fef4c6717bdba04c6fcfbe5a3470e4`.

The semantic input is `row.parsed.analysis`. Every record has intent summary,
speech act, all 13 CPC cells, ambiguity fields, capability, risk, unresolved
and resolved slots, and context-sampling uncertainty. CPC cells preserve their
saved `status` and `value`; literal `not specified` values are preserved
exactly and are not replaced with invented values.
Uncertainty is `context_sampling_uncertainty` with `score`, `agreement`, and
`variant_count`; there is no invented `uncertainty_score` field. Empty/null
saved semantic fields remain empty/null. The complete 28-field coverage audit
is in [input_audit.json](../../research/pilot120/gliner25_goalfirst_semantic_router_v1/input_audit.json).

The CPC slots are action, actor, object, object attributes, destination,
spatial relation, quantity, time, recipient, tool, conditions, constraints,
and negation. All 120 saved analyses mark ambiguity present; this alone does
not establish action-blocking ambiguity. The general capability field is
unknown for 60, capable for 43, and incapable for 17 cases. It disagrees with
the saved `pilot_capability_status` semantic finding on 60 cases. The renderer
preserves both rather than replacing either with gold or a repaired capability.

## Fixed renderer and leakage controls

The [script](../../scripts/experiments/gliner25_goalfirst_semantic_router_v1.py)
contains one deterministic renderer. Field labels have a fixed order;
structured values use compact JSON with sorted keys. A receives exactly the
intent summary. No case ID is included in the model text.

Never rendered: outer prediction fields, raw output, original source packet,
gold, correctness, router trace, recommended strategy, rejection reason,
strategy sequence, provenance notes, generated clarification question or
clarification targets. Free-form findings are excluded except the individually
allowlisted semantic prefixes below. `router_validation` findings are always
excluded. An independent pre-inference review checked all 840 inputs and found
no route-field, gold-field, rejection-reason, or router-validation leakage.

| Condition | Rendered information |
| --- | --- |
| A intent only | Intent summary only |
| B intent + grounding | Intent, unresolved slots, ambiguity types |
| C intent + task slots | Intent, speech act, 13 CPC cells |
| D grounding + capability | C, unresolved slots, ambiguity types, capability status, saved `pilot_capability_status` finding |
| E full without risk | D, ambiguity presence/primary/compound fields, resolved slots, context-sampling uncertainty, candidate/selected interpretations, supporting/resolution evidence and method, unsupported specificity, saved `pilot_ambiguity_types` finding |
| F full (primary) | E plus risk level and risk relevance |
| G action readiness | Identical text to F, separate three-label readiness task mapped to routes |

Candidate interpretations, selected interpretation, supporting/resolution
evidence/method, and unsupported specificity are empty/null across all 120
records. They add no original source packet. E and F differ only in risk
fields; D and E differ in additional semantic fields and uncertainty.
Removing the named risk fields does not erase safety-related words already
present in the frozen intent, CPC constraints, or capability representation.

Direct labels use the user-requested definitions: EXECUTE requires one grounded
admissible concrete action; CLARIFY means unresolved decision-relevant values
could produce different concrete actions; REFUSE means a sufficiently specified
job is blocked by capability, authorization, prohibition, or unacceptable safety.
Readiness labels are ACTION_READY, ACTION_BLOCKING_AMBIGUITY, and HARD_BLOCKED,
mapped respectively to EXECUTE, CLARIFY, and REFUSE. Exact descriptions are in
[protocol.json](../../research/pilot120/gliner25_goalfirst_semantic_router_v1/protocol.json).
Single-label argmax is used without threshold tuning. Label wording is fixed
before inference and is not revised in response to Pilot-120 performance.
Readiness is scored through its mapping to frozen route gold, not against
independently annotated action-grounding, authorization, or physical-safety gold.

## Baselines and cohort provenance

The final archive member
`t07_matched_baseline_completion_20260922/17_t07_case_level_comparison.csv`
provides routes and final two-judge intent screening per case. It verifies
Goal-First 56/120, Raw Qwen 96/120, Fine-Tune 92/120, 117 intent-positive cases,
and the 63 intent-positive/route-wrong cohort. Each original Goal-First route
is crosschecked against the same artifact used for semantic input.

The saved [capability-intervention summary](../../research/pilot120/capability_intervention/sprint_rescue_summary.json)
contains exact per-case correctness maps verifying post-capability 83/120 and
capability oracle 87/120. These saved maps are used for paired accuracy; no
historical model or router is rerun to fabricate baseline results. An
independent audit also reconstructed routes with the existing intervention
checker and matched all 120 saved correctness flags.

**Cohort discrepancy:** the older capability sprint's 63-ID dissociation list
substitutes CA-0878 for CA-0845. This experiment uses the final matched study's
cohort, not that stale list. The three final intent-negative cases are
CA-0149, CA-0460, and CA-0878. Original false refusals comprise 57 cases:
39 gold EXECUTE and 18 gold CLARIFY.

## Reproduce and audit

Run from repository root. Saved-result scoring requires only Python's standard
library; inference requires the pinned GLiNER environment and model snapshot.
See [the original installation recipe](GLINER25_DECIDE_CAPABILITY_PROBE_V1.md)
and [pinned requirements](../../configs/experiments/gliner25_decide_windows_py311_requirements_v1.txt).

```powershell
py -3.11 -m venv outputs/model_runs/gliner25_decide/env
outputs/model_runs/gliner25_decide/env/Scripts/python.exe -m pip install -r configs/experiments/gliner25_decide_windows_py311_requirements_v1.txt
outputs/model_runs/gliner25_decide/env/Scripts/python.exe -c "from huggingface_hub import snapshot_download; snapshot_download('fastino/GLiNER2.5-Decide', revision='5a7adf72a23b4d311abae6ce050d7f0012bb3416', local_dir='outputs/model_runs/gliner25_decide/model')"
$env:HF_HUB_OFFLINE = '1'
outputs/model_runs/gliner25_decide/env/Scripts/python.exe scripts/experiments/gliner25_goalfirst_semantic_router_v1.py prepare
outputs/model_runs/gliner25_decide/env/Scripts/python.exe scripts/experiments/gliner25_goalfirst_semantic_router_v1.py run
outputs/model_runs/gliner25_decide/env/Scripts/python.exe scripts/experiments/gliner25_goalfirst_semantic_router_v1.py score
outputs/model_runs/gliner25_decide/env/Scripts/python.exe scripts/experiments/gliner25_goalfirst_semantic_router_v1.py hash
```

Use `score` to audit the committed result without loading weights. `run`
validates and skips existing rows but records the current runtime, so run
inference only in a separate replay clone. For a new inference replay, preserve
its downloaded model/environment while removing only the new experiment's
seven prediction streams and derived scoring/runtime files; retain the locked
protocol and frozen input archives. Do not replace the committed result with
a replay. A changed schema or renderer requires a new experiment version.

```powershell
py -3.11 scripts/experiments/gliner25_goalfirst_semantic_router_v1.py score
py -3.11 -c "import hashlib,json,pathlib; m=json.load(open('research/pilot120/gliner25_goalfirst_semantic_router_v1/SHA256_FINAL.json')); assert all(hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==h for p,h in m.items()); print('OUTPUT_HASHES_OK')"
```

Model revision is `5a7adf72a23b4d311abae6ce050d7f0012bb3416`; weights SHA-256 is
`40a5a23ff860dc3dff426cecd1048cacdd29c648c96db209dad818e9686dc997`.
All ten snapshot files are verified before loading. The model and its
classification API are described in the
[official model card](https://huggingface.co/fastino/GLiNER2.5-Decide).
Observed package versions, CPU device, thread count and model-file hashes are
saved in `runtime.json`. The locked protocol records the renderer code hash,
input hashes for every case/condition, labels, exclusions, and selection rule.
Byte-preserving Git attributes prevent line-ending changes from breaking replay.
An independent tokenization audit verified all 120 full inputs were consumed
without truncation, including risk and the appended semantic findings. The
installed API and collator use `max_len=None`; combined encoder inputs contain
572–1,072 subwords with the direct-route schema. This audit uses preprocessing
only, not additional model inference. See `tokenization_audit.json`.
The encoder config records `max_position_embeddings=512`, relative attention,
and no position-biased input; the installed implementation accepts these longer
inputs. Full consumption does not establish classification quality beyond that
nominal length. This is an additional limitation of the full-field conditions.

All seven conditions require exactly the same 120 unique gold-matching IDs.
Failed inference rows are retained and counted wrong; confidence is recorded,
not calibrated or used to tune decisions. Gold is loaded for scoring only
after all seven inference streams are complete. Generic REFUSE is compared
to frozen `face_preserving_rejection`; refusal style is not evaluated.
Text-free predictions, paired case ledger, metrics, failure ledger, and final
checksums are in the [versioned result folder](../../research/pilot120/gliner25_goalfirst_semantic_router_v1/).
Fresh inference records new elapsed times, so its files need not reproduce the
observed output byte hashes. Compare case-level labels and verified input/model/
protocol identity; the recorded checksums identify the original observed run.

## Results

Best direct accuracy is **C: 77/120**, macro F1 **0.3170**, versus original
Goal-First 56/120 and capability-repaired 83/120. C sends **19/21 required
refusals** and **23/23 clarification cases** to EXECUTE; it is only one case
above the all-EXECUTE majority reference (76/120). It repairs 42 of the final
63 intent-positive/route-wrong cases but destroys refusal preservation.

The primary full condition F scores **43/120**. It correctly clarifies 10/23
and has zero refusal-to-execute errors, but correctly executes only 21/76 and
refuses only 12/21. Adding risk improves E 25/120 to F 43/120; readiness G
scores 29/120. This supports an **exploratory negative/diagnostic result**,
not successful or safe end-to-end routing. The independent metric review passed.

See the [result README](../../research/pilot120/gliner25_goalfirst_semantic_router_v1/README.md)
and `metrics.json` for the completed scores,
per-class precision/recall/F1, confusion matrices, cohort breakdowns, and exact
paired McNemar comparisons. Required-refusal false EXECUTE is reported separately
because aggregate route accuracy does not establish safe refusal preservation.
