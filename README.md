# Risk-Aware Ambiguity Manager

This repository contains the research code, evaluation contracts, frozen
Pilot-120 cases, case-level outputs, result archives, and provenance for a
language-based robot-command ambiguity manager. It evaluates interpretation,
clarification, refusal, and routing; it does not control robot hardware.

## Start here

| Goal | Go to |
| --- | --- |
| See a case and its outputs | [Pilot-120 case index](research/pilot120/INDEX.md), including [CA-0007](research/pilot120/cases/CA-0007.json) |
| Read the T0.7 and historical result packages | [Pilot-120 research record](research/pilot120/README.md) |
| Set up a new computer and continue the project | [Setup and recovery guide](docs/SETUP_AND_RECOVERY.md) |
| Obtain the upstream datasets | [Dataset guide](docs/DATASETS.md) |
| Understand experiment status and limitations | [Pilot-120 guide](docs/PILOT120.md) and [workflow guide](docs/RESEARCH_WORKFLOWS.md) |
| Check what is in Git and review rights | [Repository audit](docs/PUBLIC_RELEASE_AUDIT.md) and [rights register](configs/licences/dataset_licence_register.json) |
| Find older decisions and reports | [Documentation index](docs/INDEX.md) and [historical execution plan](cursor_plan/README.md) |

**Access and rights:** the case files and preserved ZIPs include text derived
from upstream datasets. Several exact-artifact redistribution permissions are
unresolved in the rights register. The project owner asked for these files to
be preserved in the current repository so that deleting the local checkout
does not lose them. Their presence in Git is not a claim that unrestricted
public redistribution is licensed. Review the rights register before making
the repository public, forking, or mirroring it. Older Git history also
contains upstream payloads.

## Clone and run the code checks

You need Git and Python 3.11. GitHub access is required while the repository
is private. On Windows PowerShell:

```powershell
git clone https://github.com/huziibee/Research_Project.git
Set-Location Research_Project
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe scripts/release/check_repository.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_schema_validation.py
```

On Linux or macOS:

```sh
git clone https://github.com/huziibee/Research_Project.git
cd Research_Project
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python scripts/release/check_repository.py
.venv/bin/python -m pytest -q tests/test_schema_validation.py
```

The repository check verifies tracked-file layout, the 120 case links, ZIP
integrity, and SHA-256 of the central frozen artifacts. The schema test checks
the code without GPU inference. See the [setup guide](docs/SETUP_AND_RECOVERY.md)
for restoring datasets, model dependencies, and cluster work. The full test
suite needs additional model packages and, for some tests, upstream datasets.

## Repository layout

| Folder | Contents |
| --- | --- |
| `research/pilot120/` | Browsable cases, result archives, provenance, and links |
| `data/annotations/pilot_120_v1/` | Canonical frozen source/gold files and official annotation versions used by code |
| `src/ambiguity_manager/` | Core library, schemas, model interfaces, routing, evaluation |
| `scripts/` | Reproducible builders, evaluators, scorers, and release checks; see [script index](scripts/README.md) |
| `cluster/` | Slurm launchers and historical cluster templates; see [cluster guide](cluster/README.md) |
| `configs/` | Versioned contracts, model/environment declarations, and rights records |
| `tests/` | Code and contract tests |
| `docs/` | Setup, datasets, methods, decisions, rights, and historical reports |
| `data/raw/`, `data/development/`, `data/processed/`, `outputs/` | Local workspaces; upstream payloads and generated outputs remain ignored |
| `cursor_plan/` | Frozen historical ticket plan; read as history, not current status |

Pilot-120 v1 remains evaluation-only. Do not train, tune, or choose models on
its 120 cases. T39/T41 evidence is frozen; new experiments need new versioned
protocols. The T0.7 final archive includes failed cases in denominators and
excludes T0.3. ABLE IX was still running at the dated status check in the
[workflow guide](docs/RESEARCH_WORKFLOWS.md), so do not treat it as a final
five-seed result.

Project code should resolve paths through `ambiguity_manager.paths.ProjectPaths`.
Project-owned writes should pass through
`ambiguity_manager.io_guard.resolve_writable_path`, which rejects writes to
`data/raw`; direct writes by other software are outside that guard.
