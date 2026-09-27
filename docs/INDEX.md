# Documentation index

## Read first

- [Setup and recovery](SETUP_AND_RECOVERY.md): clone, verify, find cases,
  obtain datasets, and continue work on a new machine.
- [Datasets](DATASETS.md): original providers, exact pins, layout, and rights.
- [Pilot-120](PILOT120.md): frozen identity, result families, and limitations.
- [Research workflows](RESEARCH_WORKFLOWS.md): code checks, GPU prerequisites,
  current experiment paths, and status semantics.
- [Experiment recipes and results](experiments/README.md): exact data,
  replay commands, saved outputs, measured numbers, and claim limits.
- [Experiment coverage and gaps](experiments/COVERAGE_AUDIT.md): earlier
  studies and what a fresh clone still cannot recover.
- [Repository audit](PUBLIC_RELEASE_AUDIT.md): tracked content, provenance,
  credential check, visibility, and redistribution caveat.

## Methods and evidence

- `protocols/` contains versioned experiment methods; the current intent
  judging prompt and schema are under `configs/evaluation/pilot120_intent_v1/`.
- `dataset_cards/`, `mapping/`, and `architecture/` explain source roles and
  the implemented design.
- `licences/` and `configs/licences/` record rights evidence. Use the latter
  register for the current decision, not an old report.
- `decisions/` and `governance/` preserve formal decisions and deviations.
- `reports/` is historical evidence. Reports describe what was observed at
  their date; they are not live job status or a substitute for final ZIPs.
- `cursor_plan/` at the repository root is a frozen execution-plan archive.
  Its old “current status” text is historical. Use the guides above for the
  current state.

The [research record](../research/pilot120/README.md) connects browsable
cases to the exact archives and their hashes.
