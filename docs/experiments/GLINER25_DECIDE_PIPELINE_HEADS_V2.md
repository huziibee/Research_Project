# GLiNER2.5-Decide pipeline-head probe, v2

**Status:** exploratory, text-only Pilot-120 development-set probe, run
2026-10-02. Version 2 corrects two limits in the first local schema: it uses
the full five-value official risk scale, including `none`, and scores generic
`refuse` separately from whether a refusal is face-preserving. No frozen file
or paper result was changed. Predictions contain IDs, labels, confidence
values, and errors, but no source text.

## What was tested

The [model card](https://huggingface.co/fastino/GLiNER2.5-Decide) documents
multiple decision heads in one call and multi-label classification. This
probe fixes the schema in
[`gliner25_decide_pipeline_heads_v2.py`](../../scripts/experiments/gliner25_decide_pipeline_heads_v2.py):

- Terminal route: `execute`, `clarify`, or generic `refuse`. Frozen
  `face_preserving_rejection` is collapsed to `refuse` for route comparison;
  the model does not generate refusal wording, so style is not evaluated.
- Action readiness: `ready` or `not_ready`, compared with whether the frozen
  terminal strategy is `execute`.
- Authorization: `authorized`, `unauthorized`, or `unclear`. Gold combines
  capability, authorization, and safety, so only an unauthorized-vs-other
  combined-status proxy can be scored.
- Risk level: the full official five-value scale `none`, `low`, `medium`,
  `high`, `unknown`.
- Pilot-17 ambiguity types: multi-label, using definitions from the existing
  ontology and the prespecified `cls_threshold=0.5`.

The model sees only the source command, dialogue, scene, and robot capability
context. Gold annotations load after inference. Source, route/capability gold,
risk gold, and all ten model-snapshot files are SHA-256 checked. All 120 IDs
are required. Version 2 returned one valid prediction for each case.

## Results

| Head | Result | What it means |
| --- | ---: | --- |
| Terminal route | **80/120 exact (66.7%)** | 76/76 execute correct; only 1/23 clarify and 3/21 generic refusal labels correct. It predicted execute for 22 clarify and 18 refusal cases. |
| Action readiness | **78/120 correct (65.0%)** | Against the execute-vs-not-execute route proxy, all 76 gold execute cases were ready, but 42 of 44 non-execute cases were also marked ready. |
| Authorization | **8/12 unauthorized found** | 11 cases predicted unauthorized; precision 8/11 (72.7%), recall 8/12 (66.7%) against combined capability-status proxy only. Other gold statuses do not independently establish authorization. |
| Risk level | **72/120 exact (60.0%)** | Five-label macro-F1 0.332, with `none` included as a zero-support class. High-risk recall was 10/19; medium-risk recall 8/34; all three unknown cases were missed. No gold row has risk label `none`, but the model predicted `none` seven times. This is severity agreement only. |
| Pilot-17 ambiguity | **Micro-F1 0.388**, exact set 6/120 | Micro precision 0.495, recall 0.319 at the fixed threshold. Object-reference was over-predicted (103 predictions for 46 gold cases); several types had zero predictions. |

The 104/120 capability-status agreement in the companion probe was dominated
by the `capable` majority class. This multi-head result shows that this model
is not a reliable current route/clarification policy: it missed 22 of 23 gold
clarifications and marked 42 non-execute tasks as ready. Do not use its
authorization, route, or readiness output to authorize physical action.

An initial four-label risk schema produced the same 72/120 accuracy but is
retained only in the ignored local run folder for provenance. Version 2 is
the reportable probe because it includes `none` in the official candidate
scale and keeps refusal style out of the route claim.

## Evidence and reproduction

| Evidence | SHA-256 |
| --- | --- |
| Source | `f33b1e29f1e8aa256a475f07213aa07247def47d8e2148d54a472a40b71b05c9` |
| Frozen route/capability/ambiguity gold | `5e23ad1a92ff1873c8f039a8ce560a111dd6fb6b8ae8c11d6cf34dbfa1c360db` |
| Official risk-level labels | `9273fd41aeb4fd336e441977c73b6b17d7b1e6e4f87da86ad974aea878fe1ac7` |
| GLiNER2.5-Decide model snapshot | `77e7c87764194fca2336196658f6a3a2f45999c14db2160bef610a9584cb7ec5` |
| Predictions | `d84655a915d240721fddd9988e11ce4161a12a7f6dfe3128dee1896cfda2a0d8` |
| Summary | `924f7a2d7a3966d56dbbbfe8e8f69a6dac192774c2cdceabb89296b2ba987dc5` |

Use the pinned setup in the companion
[GLiNER capability probe guide](GLINER25_DECIDE_CAPABILITY_PROBE_V1.md),
then run from repository root:

```powershell
$env:HF_HUB_OFFLINE = '1'
outputs/model_runs/gliner25_decide/env/Scripts/python.exe scripts/experiments/gliner25_decide_pipeline_heads_v2.py --model-dir outputs/model_runs/gliner25_decide/model --output-dir outputs/model_runs/gliner25_decide/pipeline_heads_v2
```

Tracked [case-level predictions](../../research/pilot120/gliner25_decide_pipeline_heads_v2/predictions.jsonl),
[summary](../../research/pilot120/gliner25_decide_pipeline_heads_v2/summary.json),
and [checksums](../../research/pilot120/gliner25_decide_pipeline_heads_v2/SHA256_FINAL.txt)
contain no raw request text.

## Scientific limits and next data needed

These results are exploratory because Pilot-120 informed prior project
development. Route and action readiness use the same terminal-strategy gold,
so readiness is not an independent gate measurement. The capability-status
gold does not provide independent authorization labels. The risk gold
measures severity, not whether a specific robot may safely perform a specific
action. Generic refusal agreement does not test face-preserving language.
Ambiguity exact-set agreement evaluates recorded Pilot-17 types, but current
gold does not independently label post-context resolved slots or the full
executable task frame.

Before claiming a correct start-to-finish decision, collect a new held-out
set with independent labels for grounding and task slots, atomic action
count/order, explicit authorization, risk acceptability for the robot/action,
clarify/refuse/execute, refusal style, and ambiguity before and after
context. Have blinded annotators adjudicate those fields, lock the protocol
and thresholds, and compare component heads with the deterministic Figure 6
flow without tuning on the evaluation cases.
