# Risk-Aware Ambiguity Manager

This project studies how a language-based robot assistant should interpret an
ambiguous command and choose among execution, clarification, and refusal. It
contains the manager implementation, evaluation code, frozen research protocols,
and provenance records. It does not implement robot motion or hardware control.

## Start here

| If you need to... | Read |
| --- | --- |
| Understand the system and run code-only checks | This README, then `docs/RESEARCH_WORKFLOWS.md` |
| Obtain the upstream datasets | `docs/DATASETS.md` |
| Understand or verify Pilot-120 | `docs/PILOT120.md` |
| Check what can enter a public release | `docs/PUBLIC_RELEASE_AUDIT.md` and `configs/licences/dataset_licence_register.json` |
| Find historical execution decisions | `cursor_plan/README.md` and `handover/` |

The current Git history includes upstream dataset payloads and derived
Pilot-120 text. The latest tree keeps those local inputs out of the tracked
release files, but a fresh clone still receives the older Git objects. See the
release audit for the exact boundary before mirroring the repository.

## Install and check the code

Use Python 3.10 or newer. Python 3.11 is the most relevant local and cluster
baseline for this project. In PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q tests/test_schema_validation.py
```

On Linux or macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q tests/test_schema_validation.py
```

These are code and schema checks. The full suite includes tests that require
locally acquired datasets, frozen Pilot-120 files, or optional model packages.
Run `python -m pytest -q` only after those inputs are present and report any
skips or unavailable dependencies separately. `pyproject.toml` declares the
core package and development extras; GPU inference uses additional pinned
cluster/container dependencies described in `docs/RESEARCH_WORKFLOWS.md`.

## Repository map

| Path | Purpose |
| --- | --- |
| `src/ambiguity_manager/` | Schemas, data handling, systems, and evaluation library |
| `tests/` | Unit, contract, and frozen-evidence checks |
| `scripts/` | Builders, evaluators, scorers, and audits |
| `cluster/` | Slurm jobs and launch scripts; inspect before submission |
| `configs/` | Evaluation contracts, model settings, dataset and rights registers |
| `docs/` | Research workflow, dataset, licence, and result explanations |
| `data/raw/` | Locally obtained upstream material; no new payloads should be committed |
| `data/annotations/` | Project annotation and frozen evaluation work; release rights vary |
| `outputs/` | Generated results and large archives, normally ignored by Git |
| `cursor_plan/`, `handover/` | Historical decisions and operational handovers |

External data is acquired from its original provider. Exact source versions,
local paths, hashes, and rights status are in `docs/DATASETS.md`.

## Running research workflows

First verify the dataset and model inputs, then select the versioned protocol in
`docs/RESEARCH_WORKFLOWS.md`. CPU scorers and schema checks run locally; model
inference needs a separately provisioned GPU environment. Do not run an old
Slurm script merely because it is present: many scripts preserve historical
jobs and fixed inputs. Pilot-120 v1 is frozen and evaluation-only; do not train,
tune, or select a model on its 120 cases.

The most recent T0.7 result is described in `docs/PILOT120.md`. The ABLE IX
temperature jobs are a separate exploratory study, with an automatic intent
screen rather than the official two-judge metric. No T0.3 result is part of the
T0.7 official package.

## Data and release boundary

Project code, schemas, hashes, and aggregate results can be reviewed without
copying upstream records. Dataset access and publication depend on the exact
source rights recorded in `configs/licences/dataset_licence_register.json`.
The internal academic-use decision does **not** grant public redistribution of
source text, transformed records, or adapter weights. A public release must use
a separately reviewed, clean Git history; the current history is not suitable
for publication as-is.

Project code should resolve paths through `ambiguity_manager.paths.ProjectPaths`.
Project-owned writes should pass through
`ambiguity_manager.io_guard.resolve_writable_path`, which rejects writes to
`data/raw`. This guard cannot stop a direct write by other software.
