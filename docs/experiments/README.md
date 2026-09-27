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
| [Temperature exploration](TEMPERATURE_EXPLORATION.md) | Pilot-120; five existing single-seed streams | Route and automatic intent screening for saved streams |
| [Frozen T39/T41](T39_T41_FROZEN.md) | Pilot-120; historical closure archive | Inspect and audit; preserve the original frozen result |

The [120-case index](../../research/pilot120/INDEX.md) connects individual
source and gold records to T0.7 predictions. The [archive guide](../../research/pilot120/README.md)
lists each ZIP and SHA-256. Data licenses and original providers are in
[DATASETS.md](../DATASETS.md). For the earlier runs and the explicit backup
gaps, read the [full coverage audit](COVERAGE_AUDIT.md). No entry in this index implies independent
validation, new model performance, or permission to redistribute source text.
