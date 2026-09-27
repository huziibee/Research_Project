# Paper results: evidence and replay map

This map was checked against the local draft `Research Report/06-results.md`
(SHA-256 `2c5f7ee4963d361a387aaeb4628894a4fd7f23d139276735e50603cd7ab56bf6`).
That manuscript is **outside this repository** and is not a frozen final paper.
The map covers its Results sections 5.1–5.12 and every figure reference found
there. It does not turn an old draft claim into a verified final result. Start
with [setup](SETUP_AND_RECOVERY.md), [datasets](DATASETS.md), and the
[120-case index](../research/pilot120/INDEX.md). Run
`python scripts/release/check_repository.py` before replaying an archive.

## Claims and tables in the inspected draft

| Draft location and claims | Exact repository evidence and replay | Qualification |
| --- | --- | --- |
| 5.1 and 5.3: six-system route/intent scoreboards, T0.7 and T0 | [T0.7 final archive](../research/pilot120/artifacts/t07_matched_baseline_completion_20260927_FINAL.zip), [full-analysis archive](../research/pilot120/artifacts/p120_full_analysis_20260923.zip), [T0.7 replay](experiments/T07_MATCHED_BASELINE.md), [T39/T41 history](experiments/T39_T41_FROZEN.md), and [case index](../research/pilot120/INDEX.md) | Draft T0.7 Goal-First 54/120 and “results incoming” are stale: repaired final is 56/120 with complete 120-row two-judge observations. The judgment is **exploratory**, pending governance, as below. T0 and T0.7 have different inference/protocol histories; do not mix cells. |
| 5.1, 5.3, 5.9: temperature and seed stability, H3/H4 | [Saved temperature replay](experiments/TEMPERATURE_EXPLORATION.md), [full-analysis archive](../research/pilot120/artifacts/p120_full_analysis_20260923.zip), [temperature scorer](../scripts/score_gf_temp_ablation_20260923.py), [coverage audit](experiments/COVERAGE_AUDIT.md) | The single-seed saved streams are 49, 53, 51, 56, 44 /120 at T0.0–T1.0. Draft text also says 42 at T1.0 and mixes repaired/unrepaired snapshots. Five-seed ABLE IX is a separate run; this map makes no completion claim for it. |
| 5.2: intent-box writing, automatic overlap, and route dissociation | [Historical T39/T41 archive](../research/pilot120/artifacts/pilot120_t41_complete_closure.zip), [T0.7 final archive](../research/pilot120/artifacts/t07_matched_baseline_completion_20260927_FINAL.zip), [semantic package audit](reports/PILOT120_SEMANTIC_INTENT_PACKAGE_AUDIT_20260902.md), [T0.7 replay](experiments/T07_MATCHED_BASELINE.md) | Automatic overlap is a screen; two-model semantic judging is not approved official correctness. Intent writing and route selection are different metrics. |
| 5.4: CA-0007 case study | [CA-0007 record](../research/pilot120/cases/CA-0007.json), [case builder](../scripts/release/build_pilot120_cases.py), [frozen source](../data/annotations/pilot_120_v1/source_canonical.jsonl), [gold](../data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl) | The case combines original and inherited predictions with explicit provenance. Inspect the exact system/temperature before quoting a route. |
| 5.5: 62 intent-screen-positive/route-wrong cases, rule breakdown, T0 policy table | [T39/T41 replay guide](experiments/T39_T41_FROZEN.md), [T41 archive](../research/pilot120/artifacts/pilot120_t41_complete_closure.zip), [mechanism report](reports/MECHANISM_DEEP_DIVE_20260911.md), [policy ablation script](../scripts/ablate_goal_and_route_20260913.py) | Historical T0 matched-set diagnosis. The 62 use an automatic intent screen, not approved semantic correctness. Keep separate from the repaired T0.7 intervention. |
| 5.5: capability/risk mechanism and intervention | [Frozen-intent intervention](experiments/CAPABILITY_INTERVENTION.md), [37-case ledger](../research/pilot120/capability_intervention/residual_error_ledger.csv), [ledger checker](../scripts/release/build_capability_residual_ledger.py), [risk sidecar](../data/annotations/pilot_120_v1/pilot_120_gold_risk_official.jsonl) | Repaired T0.7 paired reroute: 56→57→83→87 exact; false refusals 39→26→4→0 of 76. This is a fixed-analysis counterfactual, not a fresh model comparison. |
| 5.6: clarify-label precision/recall, 0/23 wording, later recovery | [T41 archive](../research/pilot120/artifacts/pilot120_t41_complete_closure.zip), [T0.7 final archive](../research/pilot120/artifacts/t07_matched_baseline_completion_20260927_FINAL.zip), [depth-five recovery](experiments/DEPTH_FIVE_CLARIFICATION_RECOVERY.md), [full-analysis archive](../research/pilot120/artifacts/p120_full_analysis_20260923.zip) | The draft's 0/23 is a historical wording measure, not evidence of successful user dialogue. Oracle-consistent recovery is exploratory and uses different interaction depths. |
| 5.7: risk, low-stakes, CPC status | [Gold risk sidecar](../data/annotations/pilot_120_v1/pilot_120_gold_risk_official.jsonl), [T41 archive](../research/pilot120/artifacts/pilot120_t41_complete_closure.zip), [Pilot-120 guide](PILOT120.md), [coverage audit](experiments/COVERAGE_AUDIT.md) | Draft low-risk and risk-sensitive tables are historical T0 diagnostics. CPC source-native evidence remains limited; do not replace unsupported fields with an invented score. |
| 5.8: ambiguity exact-set/micro-F1 and overprediction | [T41 archive](../research/pilot120/artifacts/pilot120_t41_complete_closure.zip), [full-analysis archive](../research/pilot120/artifacts/p120_full_analysis_20260923.zip), [T0.7 replay](experiments/T07_MATCHED_BASELINE.md), [temperature replay](experiments/TEMPERATURE_EXPLORATION.md) | Metric, run, and denominator must travel together; the draft mixes T0 and T0.7. |
| 5.9: confusion/F1 and replica plots | [T0.7 final archive](../research/pilot120/artifacts/t07_matched_baseline_completion_20260927_FINAL.zip), [full-analysis archive](../research/pilot120/artifacts/p120_full_analysis_20260923.zip), [T0.7 scorer](../scripts/score_t07_matched_baseline_20260922.py), [temperature guide](experiments/TEMPERATURE_EXPLORATION.md) | Plotted snapshots were generated before this map and are preserved below as historical draft images; regenerate before using them as final figures. |
| 5.10–5.12: evidence-status, hypotheses, and sufficiency tables | The rows above, [coverage audit](experiments/COVERAGE_AUDIT.md), [governance log](governance/logs/deviation_log.jsonl), [rights audit](PUBLIC_RELEASE_AUDIT.md) | The draft's “settled”, “official”, and pending labels need review against the repaired archive and governance rule. Pilot-120 alone does not prove deployment safety or generalization. |

The source of each cited case is the [case index](../research/pilot120/INDEX.md);
the [case builder](../scripts/release/build_pilot120_cases.py) records the
archive join. The [archive index](../research/pilot120/README.md) gives SHA-256
for every preserved ZIP. The intervention guide gives member-level hashes and
its checker recomputes the 37-row ledger.

## Figure inventory from that draft

Exact local draft PNG bytes have been preserved under
[`research/paper/figures/`](../research/paper/figures/) with a
[`SHA256.tsv`](../research/paper/figures/SHA256.tsv). This is **image
preservation**, not figure/result validation. The draft's `figures/` path is
relative to the external manuscript, so a future paper checkout should copy
these files to its own `figures/` folder only after updating and reviewing
the plots. The generator scripts read local `results/` or `latest results/`
snapshots that are not all tracked; running them from a clean clone is not a
verified full regeneration path.

| Draft section | Figure files in `research/paper/figures/` | Generator script and source family |
| --- | --- | --- |
| 5.1 | `intent-primary-wide.png`, `intent-vs-route-wide.png`, `routing-correct-wide.png` | [`build_intent_primary_obsidian_20260913.py`](../scripts/build_intent_primary_obsidian_20260913.py), [`rebuild_aligned_report_figures_20260918.py`](../scripts/rebuild_aligned_report_figures_20260918.py); T0/T0.7 archives above |
| 5.3 | `intent-routing-heatmap-wide.png` | [`rebuild_report_intent_figures_20260915.py`](../scripts/rebuild_report_intent_figures_20260915.py); T0/T0.7 intent and route snapshots |
| 5.5 | `the-62-rules-wide.png`, `overask-breakdown-wide.png`, `capability-accuracy-wide.png`, `capability-vs-refuse-wide.png` | [`build_live_six_figures_20260913.py`](../scripts/build_live_six_figures_20260913.py), [`build_intent_primary_obsidian_20260913.py`](../scripts/build_intent_primary_obsidian_20260913.py); historical T0 mechanism and T0.7 diagnostics |
| 5.6 | `clarification-pr-wide.png` | [`build_live_six_figures_20260913.py`](../scripts/build_live_six_figures_20260913.py); route/wording archives |
| 5.8 | `ambiguity-overpredict-wide.png` | [`build_live_six_figures_20260913.py`](../scripts/build_live_six_figures_20260913.py); T0.7 ambiguity diagnostics |
| 5.9 | `replica-stability-wide.png`, `routing-confusion-heatmaps.png`, `route-f1-wide.png`, `temperature-intent-routing-line.png` | [`build_intent_primary_obsidian_20260913.py`](../scripts/build_intent_primary_obsidian_20260913.py), [`build_live_six_figures_20260913.py`](../scripts/build_live_six_figures_20260913.py), [`rebuild_aligned_report_figures_20260918.py`](../scripts/rebuild_aligned_report_figures_20260918.py); temperature and route snapshots |

The extra `text-layer-pipeline.png` is not embedded in the inspected Results
draft; its generator is [`_make_text_layer_figure.py`](../scripts/_make_text_layer_figure.py).
No final manuscript table numbers or final figure versions were supplied in
this repository, so this is the complete mapping of the **inspected draft**,
not a certification of a later paper.

## Semantic-judge governance finding

The [evaluator policy](../configs/evaluation/evaluator_policy_v1.json) says
“No LLM judge may determine official correctness.” The
[research contract](../configs/research/research_contract_v1.json) requires a
deterministic primary evaluator. The earlier [semantic-package audit](reports/PILOT120_SEMANTIC_INTENT_PACKAGE_AUDIT_20260902.md)
explicitly classified two blind judges as an exploratory addendum unless an
approved protocol deviation and required adjudication authority exist. The
tracked [deviation log](governance/logs/deviation_log.jsonl) contains only
`DEV-20260711-001` (T12 execution order) and `DEV-20260721-001` (its closure).
Neither authorizes Gemma+GLM semantic intent as “official correctness.” **No
approved deviation was found in the tracked governance records.** Historical
archive fields and report titles using “official” are preserved as recorded
names, but the paper must not present the two-model verdict as official
correctness under the current policy.
