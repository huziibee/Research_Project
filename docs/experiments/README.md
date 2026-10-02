# Experiment recipes and recorded results

Start with [setup and recovery](../SETUP_AND_RECOVERY.md), then choose a study.
Each page names the data, saved evidence, command that was checked on a fresh
extraction, measured result, and the limit of that result. Run commands from
the repository root. These commands **rescore saved predictions**; new model
inference also requires the pinned weights, containers, cluster account, and
experiment protocol. Keep historical artifacts immutable.

| Study | Data and saved result | What can be rerun from this checkout? |
| --- | --- | --- |
| [T0.7 matched baseline](T07_MATCHED_BASELINE.md) | Pilot-120, six systems; final T0.7 archive | Full scoring and final pack from saved predictions and judgments |
| [One-turn recovery](ONE_TURN_RECOVERY.md) | Pilot-120 clarification subset; full-analysis archive | Summary and paired statistics from saved predictions |
| [Frozen-intent capability intervention](CAPABILITY_INTERVENTION.md) | Repaired T0.7 predictions and capability judgments | Recompute 56→57→83→87 and check the 37-case residual ledger |
| [GLiNER2.5-Decide capability-status probe](GLINER25_DECIDE_CAPABILITY_PROBE_V1.md) | Exploratory local five-class Pilot-120 probe | Inspect 104/120 aggregate and rare-class misses; no pipeline claim |
| [GLiNER2.5-Decide pipeline-head probe v2](GLINER25_DECIDE_PIPELINE_HEADS_V2.md) | Local route, readiness, authorization, risk, and Pilot-17 ambiguity heads | Inspect head-specific metrics and gold-label limitations |
| [GLiNER frozen Goal-First semantic router v1](GLINER25_GOALFIRST_SEMANTIC_ROUTER_V1.md) | Exact T0.7 saved interpretations; six routing ablations and action readiness | Rescore text-free predictions, paired comparisons and intent/route dissociation cohorts |
| [GLiNER readiness repair of the 83/120 pipeline](GLINER25_ACTION_READINESS_REPAIR_V1.md) | Frozen semantics with repaired capability; five refusal-preserving readiness hybrids | Reconstruct 83/120, inspect 37 residuals, compare risk and matched gate controls |
| [Depth-five clarification recovery](DEPTH_FIVE_CLARIFICATION_RECOVERY.md) | Two repeats on 22/26-case cohorts | Replay both saved summaries and inspect three invalid routes |
| [Temperature exploration](TEMPERATURE_EXPLORATION.md) | Pilot-120; five existing single-seed streams | Route and automatic intent screening for saved streams |
| [Figure 6 grounded-task flow](FIGURE_SIX_FLOW_V1.md) | Pilot-120 prospective text-only stress test; job 61088 queued | CPU preflight, flow tests, and frozen-gold scorer; new GPU evidence pending |
| [Frozen T39/T41](T39_T41_FROZEN.md) | Pilot-120; historical closure archive | Inspect and audit; preserve the original frozen result |

The [120-case index](../../research/pilot120/INDEX.md) connects individual
source and gold records to T0.7 predictions. The [archive guide](../../research/pilot120/README.md)
lists each ZIP and SHA-256. Data licenses and original providers are in
[DATASETS.md](../DATASETS.md). For the earlier runs and the explicit backup
gaps, read the [full coverage audit](COVERAGE_AUDIT.md). No entry in this index implies independent
validation, new model performance, or permission to redistribute source text.
For a table-by-table paper map and the semantic-judge governance finding, see
[paper reproducibility](../PAPER_REPRODUCIBILITY.md).
