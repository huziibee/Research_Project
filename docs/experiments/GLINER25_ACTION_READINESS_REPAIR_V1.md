# GLiNER action-readiness repair of the frozen 83/120 pipeline

## Research question and boundaries

Can `fastino/GLiNER2.5-Decide` improve the EXECUTE/CLARIFY boundary of the
capability-repaired Goal-First pipeline while preserving its refusal gate?
This experiment does not replace the full pipeline, regenerate semantics,
classify a raw source packet, change frozen evidence, or edit the paper.
It is separate from the [original semantic-router probe](GLINER25_GOALFIRST_SEMANTIC_ROUTER_V1.md).

Pilot-120 has informed development, including the previous negative GLiNER
experiment. This is an exploratory frozen development-set diagnostic. The
best of five hybrid ablations is selected on this same set; its accuracy and
unadjusted paired p value are not a held-out or confirmatory result.

## Exact reconstruction of 83/120

The historical release does not contain a separate complete 120-row prediction
stream for the repaired condition. Its evidence consists of saved Goal-First
analyses, frozen per-case capability judgments, saved per-case correctness
maps, and the 37-row residual ledger. The script reconstructs routes using the
recorded capability patch and deterministic router, then verifies every case
against those saved outputs before permitting inference.

| Frozen evidence | SHA-256 |
| --- | --- |
| `research/pilot120/artifacts/p120_full_analysis_20260923.zip` | `0305b1e9ab062876ee6ee89778cc6028d2eaf01718b7dd0295944e7d9cb81a01` |
| Member `temperature_ablation_existing/T0.7/predictions/goal_first_manager_v2.predictions.jsonl` | `e6cb2070aa56c566f955ce064775ffaac489a82962135ee69445b6e53182f258` |
| `research/pilot120/capability_intervention/capability_judgments_cluster.jsonl` | `e4706a5e061b6f0da90801365fc58787db102027681e83de0209622a04f649b1` |
| `research/pilot120/capability_intervention/sprint_rescue_summary.json` | `af2acdb8fb87f2005159504d074ba94fb79b681f88d9f9c0aa7534112a7a8588` |
| Residual CSV, with LF line endings | `e54368560eb4cd3aba178b667c2b9f27ff50037ea86daaaab72b73ac34b00224` |
| Frozen Pilot-120 gold | `5e23ad1a92ff1873c8f039a8ce560a111dd6fb6b8ae8c11d6cf34dbfa1c360db` |

The capability evidence was preserved at commit
`4929fd0f525fae3989fc74223de0ab7c4b967b55`. Router source is the version at
`0f59fd1ef5186dbee6d69a258f348e9fb2baa33c`, observed SHA-256
`77327493cca48bb02fca462180d4e2f0c80da94b07c0aa3aba0f3d4c275d64ab`.
The patch helper's observed CRLF hash is
`240fda26d17237a35e2ee7f9810b227ee1ce43f03d4f40770b7a3c48c73778c2`;
the experiment records LF-normalized dependency hashes for portable replay.

Goal-First is the frozen T0.7, seed-0, version-2.0.0 interpretation from
`Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`.
Its run-manifest member is `temperature_ablation_existing/T0.7/run_manifest.json`,
SHA-256 `5d7873e6d18bbd1016b9d541557c26e4d0fef4c6717bdba04c6fcfbe5a3470e4`.
Capability judgment rows record Qwen3-8B and temperature 0.0, but do not record
an exact capability-model revision. The Goal-First revision is not assigned
to those judgments without evidence.

`patch_capability_in_analysis` replaces only canonical `capability_status`
and the `pilot_capability_status:` finding. Canonical mappings are capable →
capable, conditionally_capable → conditional, incapable → incapable,
unauthorized/unsafe → unknown. The five-way finding retains the repaired
distinction between authorization and safety. Intent, speech act, 13 CPC
slots, unresolved/resolved slots, ambiguity, uncertainty, risk and every other
saved analysis field are unchanged. Judgment reason/raw output/gold fields
are not passed to GLiNER.

The deterministic policy is `goal_first_v2`:

1. Refuse for existing prohibited/unsafe findings, unsafe capability, or
   unauthorized capability with elevated/unknown risk.
2. Refuse for incapability, or unknown capability with elevated/unknown risk.
3. Execute capable/conditional, low/none-risk, actionable speech acts.
4. Otherwise clarify.

The checker reproduces **56/57/83/87**, matches all 120 saved correctness
flags in each condition, and matches all 37 residual IDs and routes. The
derived [baseline stream](../../research/pilot120/gliner25_action_readiness_repair_v1/baseline83.predictions.jsonl)
and [audit](../../research/pilot120/gliner25_action_readiness_repair_v1/baseline_audit.json)
record exact IDs, repaired status, rule, semantic-state hash and route.

Baseline confusion, gold rows and predicted columns in E/C/R order:
`[[46,26,4],[5,16,2],[0,0,21]]`. Residual composition is exactly
26 E→C, four E→R, five C→E and two C→R.

## Locked hybrid policy

The gate preserves all **27 baseline REFUSE outcomes**. Every one uses
`known_unsafe_or_prohibited`: 21 repaired unauthorized and six repaired unsafe
statuses. They include all 21 gold refusals and six false refusals. This is
**baseline refusal preservation**, not independently verified hard safety.

| Situation | Hybrid output |
| --- | --- |
| Baseline refusal gate fires | REFUSE, regardless of GLiNER label; disagreement recorded |
| Nongated ACTION_READY | EXECUTE |
| Nongated ACTION_BLOCKING_AMBIGUITY | CLARIFY |
| Nongated HARD_BLOCKED | Retain baseline E/C; flag unsupported hard-block claim |
| Nongated inference failure | FAILED, counted wrong |
| Gated inference failure | Preserve baseline REFUSE; retain/report classifier failure |

This intentionally replaces the old low-risk readiness requirement for the
93 nongated cases. Copying that execute requirement unchanged would leave the
26 over-clarifications unrepaired. Hard refusal rules still use the original
frozen risk field in **every** input ablation. Removing risk from classifier
text does not remove risk from the gate.

The six frozen false refusals are CA-0042, CA-0203, CA-0259, CA-0369 (gold E)
and CA-0552, CA-0727 (gold C). They cannot be repaired by this hybrid version.
All GLiNER disagreement with a preserved refusal is explicitly recorded;
there is no gold-derived gate, exception list, or confidence threshold.

## Fixed inputs, labels and controls

Inputs are deterministic projections of the frozen analysis after the exact
capability patch. CPC values/statuses and literal missing-value strings are
preserved. No new context, inferred default, or case-specific answer hint is
added. Candidate/supporting/resolution evidence remains the frozen value.

| Condition | Model input |
| --- | --- |
| A | Intent summary only |
| B | Intent, unresolved slots, ambiguity types |
| C | Intent, speech act, 13 CPC cells, unresolved slots; no risk/capability |
| D — primary | Full semantic allowlist plus repaired capability, without risk fields |
| E | D plus risk level and risk relevance |
| F — secondary direct route | Exactly E's input text, direct EXECUTE/CLARIFY/REFUSE labels |

The [pinned prior renderer](../../scripts/experiments/gliner25_goalfirst_semantic_router_v1.py)
provides deterministic field ordering and leakage exclusions. The new script
adds only frozen exact `prohibited`/`unsafe_action` findings if present. Never
rendered: route, router trace/validation, rejection reasons, clarification
recommendations, provenance notes, gold, correctness, capability-match flags,
capability reason/raw output, original source packet, or case ID.

The readiness descriptions are the user's fixed definitions of one concrete
action, unresolved action-changing choices, and evidence-backed hard blocking.
They are saved verbatim in [protocol.json](../../research/pilot120/gliner25_action_readiness_repair_v1/protocol.json).
Single-label argmax is used; labels and confidence thresholds are not tuned.
Raw readiness predictions are separately mapped to E/C/R for evaluation.
Readiness has no independent physical-grounding gold; mapped route agreement
does not establish complete robot-task understanding.

Two prespecified controls require no extra inference: always ACTION_READY
behind the same gate, and secondary direct labels passed through that same
gate. They distinguish the effect of refusal preservation from readiness
classification. The always-ready gated reference is **93/120**, but misses
all 23 gold clarifications; beating 83 alone is insufficient evidence of
useful clarification-boundary repair.

## Operational ambiguity diagnostics

The seven gold-CLARIFY residuals are CA-0215, CA-0225, CA-0552, CA-0608,
CA-0727, CA-0762, and CA-0889. Existing case-record scene evidence identifies
these choices:

| Cases | Missing operational variable | Evidence |
| --- | --- | --- |
| CA-0215, CA-0225, CA-0762 | Physical versus digital filing medium | `frozen_source.scene_context` in each existing case record |
| CA-0552 | Which archive cage unit among two authorized empty units | Same case-record field |
| CA-0727 | Which storage bay unit; returned asset already resolved | Same case-record field |
| CA-0608, CA-0889 | 20 mL versus 60 mL, with neither default | Same case-record field |

These source-evidence diagnostic categories are evaluation annotations only.
They do **not** enter GLiNER inputs or the hybrid gate. The seven-row ledger
links to each existing case record and records every readiness label/route.
Linguistic slot filling is compared with this operational choice; a filled
string is not treated as independently validated grounding.

The tracked [37-case ledger](../../research/pilot120/gliner25_action_readiness_repair_v1/residual37.jsonl)
contains IDs, routes, repaired capability, risk, unresolved-slot names,
ambiguity labels, condition predictions, and exact semantic/case references.
To avoid duplicating derived source text in the new tracked predictions,
`score` also writes a local full-detail JSON containing the actual intent,
full unresolved slots and repaired semantic representation for all 37 cases:
`outputs/model_runs/gliner25_decide/action_readiness_repair_v1/residual37_full_details.json`.
This ignored file is regenerable from the tracked frozen archives and script.
The existing repository remains the controlled full-evidence archive; upstream
redistribution permissions are not newly granted by this experiment.

## Reproduce

Run from repository root. Python 3.11 is required. The local observed package
versions are pinned in
[gliner25_decide_windows_py311_requirements_v1.txt](../../configs/experiments/gliner25_decide_windows_py311_requirements_v1.txt).

```powershell
py -3.11 -m venv outputs/model_runs/gliner25_decide/env
outputs/model_runs/gliner25_decide/env/Scripts/python.exe -m pip install -r configs/experiments/gliner25_decide_windows_py311_requirements_v1.txt
outputs/model_runs/gliner25_decide/env/Scripts/python.exe -c "from huggingface_hub import snapshot_download; snapshot_download('fastino/GLiNER2.5-Decide', revision='5a7adf72a23b4d311abae6ce050d7f0012bb3416', local_dir='outputs/model_runs/gliner25_decide/model')"
$env:HF_HUB_OFFLINE = '1'
outputs/model_runs/gliner25_decide/env/Scripts/python.exe scripts/experiments/gliner25_action_readiness_repair_v1.py prepare
outputs/model_runs/gliner25_decide/env/Scripts/python.exe scripts/experiments/gliner25_action_readiness_repair_v1.py run
outputs/model_runs/gliner25_decide/env/Scripts/python.exe scripts/experiments/gliner25_action_readiness_repair_v1.py score
outputs/model_runs/gliner25_decide/env/Scripts/python.exe scripts/experiments/gliner25_action_readiness_repair_v1.py hash
```

For reviewing committed results, run only `score`; it validates all prediction
and protocol identities and writes the full-detail local ledger. `run` records
the current runtime, even when resuming/skipping existing rows, so use it only
in a separate replay clone. To repeat inference, retain the frozen archives and
locked protocol in that clone, and remove only this experiment's six prediction
streams and derived runtime/scoring files. Do not replace committed evidence.
A changed label schema, renderer, or hybrid policy requires a new version.

Verify original output hashes without regenerating them:

```powershell
py -3.11 -c "import hashlib,json,pathlib; m=json.load(open('research/pilot120/gliner25_action_readiness_repair_v1/SHA256_FINAL.json')); assert all(hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==h for p,h in m.items()); print('OUTPUT_HASHES_OK')"
```

The pinned model revision is `5a7adf72a23b4d311abae6ce050d7f0012bb3416`;
weights SHA-256 is
`40a5a23ff860dc3dff426cecd1048cacdd29c648c96db209dad818e9686dc997`.
All ten model files are verified against the prior snapshot manifest before
loading. No new model download or generation is needed for saved-result scoring.
`runtime.json` records observed versions, CPU, thread count and platform.
The protocol records exact renderer/analysis/router dependency hashes, input
hashes for all 720 condition/case pairs, labels, exclusions and gate semantics.

Independent preprocessing checks confirmed all 360 D/E/F full inputs were
consumed without truncation and E/F retained risk. Encoder input lengths were
D 602–1,102, E 610–1,110, F 572–1,072 subwords. All exceed nominal 512 positions;
complete input coverage does not establish long-input classification quality.
See `tokenization_audit.json` for per-case counts and installed-source evidence.

All conditions require exactly 120 unique matching Pilot-120 IDs. Classifier
failures remain in raw mapped-label denominators. A failed nongated case is
also wrong in hybrid scoring; a failed gated case retains its independent
baseline refusal and is explicitly reported as classifier failure.
Refusal style is not tested: frozen `face_preserving_rejection` maps to REFUSE.
Fresh timings vary, so replay output byte hashes need not match original
predictions; compare labels, input/protocol identity and pinned model hashes.

## Results and claim limits

Primary D reached **88/120**, repairing 17 errors and introducing 12 regressions. With-risk E reached **84/120**. Best accuracy A reached **93/120**, but predicted ACTION_READY on every case and exactly matched the always-ready gated control. No condition met the no-regression/new-CLARIFY-to-EXECUTE objective. All hybrids retained all 21 required refusals.

See the [result README](../../research/pilot120/gliner25_action_readiness_repair_v1/README.md)
and `metrics.json` for complete accuracy, per-class precision/recall/F1,
confusion matrices, 37/26/7-case cohorts, gate disagreements, changed-case
analysis, risk comparison and exact paired McNemar tests. Both raw readiness
and hybrid results are reported. Any apparent accuracy gain must be checked
against regressions on correct clarification cases and the 93/120 gated
always-ready control. The paper is not modified by this experiment.
