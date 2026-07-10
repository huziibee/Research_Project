# Risk-Aware Ambiguity Manager

This repository implements and evaluates a natural-language coordination layer
for ambiguous robot/user commands. Given a command plus optional scene context,
dialogue history, and capability context, the system produces either a
non-ambiguous interpretation or a routing decision (`execute`, `clarify`,
`silently_resolve`, `face_preserving_rejection`, `multi_step`).

## Scope boundary

In scope: the natural-language ambiguity, clarification, risk, capability, and
routing layer, plus its evaluation.

Out of scope: robot planning, robot execution, navigation, grasping, and a full
embodied safety system.

## Repository layout

```
src/ambiguity_manager/   Python package (paths + write guard scaffold)
tests/                   Test suite (run with: python -m unittest)
scripts/                 Operational and audit scripts (added by later tickets)
configs/                 Configuration, including configs/datasets/ manifests
docs/                    Reports, decisions, and dataset cards
data/raw/                Immutable external dataset payloads (never written to)
data/interim/            Derived intermediate data (generated; git-ignored)
data/processed/          Processed data (generated; git-ignored)
data/annotations/        Project-owned manual annotations
data/splits/             Frozen split manifests
outputs/                 Generated experiment outputs (git-ignored)
```

## Path and write-safety policy

- Do not hard-code absolute paths. Import
  `ambiguity_manager.paths.ProjectPaths` and derive locations from the
  repository root (located by searching upward for `pyproject.toml`).
- All project-owned writes MUST route their target path through
  `ambiguity_manager.io_guard.resolve_writable_path`, which rejects any write
  into `data/raw`. This guard protects writes that use the API; it cannot stop
  arbitrary third-party tools or direct filesystem writes.

## Running tests

```
python -m unittest discover -s tests
```

`pytest` configuration is also provided in `pyproject.toml` for environments
where it is installed (`pip install -e .[dev]`), but the suite runs on the
standard library alone.

## Status

Ticket T00 (scaffold and repository safety) complete. Schema, converters,
models, routing, and evaluation are introduced in later tickets.
