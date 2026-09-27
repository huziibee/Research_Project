# Set up or recover this project on a new computer

This guide starts from an empty computer. The repository carries the frozen
Pilot-120 cases, code, and the result archives listed below. GPU models and
upstream datasets for *new* experiments are separate dependencies.

## 1. Clone and verify

Install Git and Python 3.11, then clone the repository. GitHub credentials are
needed while `huziibee/Research_Project` is private.

```sh
git clone https://github.com/huziibee/Research_Project.git
cd Research_Project
git switch main
git pull --ff-only
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python scripts/release/check_repository.py
.venv/bin/python -m pytest -q tests/test_schema_validation.py
```

On Windows PowerShell, replace the Python lines with:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe scripts/release/check_repository.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_schema_validation.py
```

`REPOSITORY_TREE=PASS` checks that all 120 case records match the frozen source,
gold, and archived outputs; it also verifies central file hashes and ZIP CRCs.
It checks recorded identity and packaging, not scientific correctness or
redistribution permission. If the checkout was
downloaded as a GitHub ZIP instead of cloned, the script cannot inspect the
Git index; use `git clone` for this check.

## 2. Find cases and recorded results

- [All Pilot-120 cases](../research/pilot120/INDEX.md) and
  [CA-0007](../research/pilot120/cases/CA-0007.json) can be browsed directly.
- [Pilot-120 artifact guide](../research/pilot120/README.md) links the exact
  T0.7, T41, annotation, intent, and full-analysis ZIPs with hashes.
- `data/annotations/pilot_120_v1/source_canonical.jsonl` and
  `pilot_120_final_gold.jsonl` are the canonical inputs used by evaluators.
  `scripts/release/build_pilot120_cases.py` regenerates the browsable files
  after checking the frozen input and archive hashes.
- [Pilot-120 guide](PILOT120.md) explains which results are final, inherited,
  incomplete, or outside the official T0.7 package.

No local transfer folder is needed to inspect these saved cases and outputs.
GitHub `main` is the recovery source for these exact files.

## 3. Obtain external datasets for new work

The upstream AmbiK, IndirectRequests, CLARA, CoDraw-iCR v2, VAGUE, ClariQ,
and SafeAgentBench payloads are not in the latest tree. Follow
[DATASETS.md](DATASETS.md) for provider links, exact study pins, expected
`data/raw/` paths, and checksum commands. Do not silently substitute a newer
provider version. The `data/raw/` directory is ignored by Git. The rights
register is `configs/licences/dataset_licence_register.json`.

The historical Git objects contain some older upstream bytes, but the
documented provider acquisition path is the reproducible route for new work.

## 4. Set up model inference or resume cluster work

The code-only install does not provide PyTorch, Transformers, PEFT, vLLM,
CUDA, the multi-gigabyte container images, the Qwen checkpoint, or the T28
adapter. Their recorded identities and environment contracts are under
`configs/model/`, `configs/environments/`, and `requirements/`. For the actual
T0.7 selected adapter identity, read its run manifest in the final T0.7 ZIP;
the older `configs/model/selected_identities_v1.json` still marks its adapter
selection incomplete. The active
Slurm templates are indexed in [cluster/README.md](../cluster/README.md).

For the original Wits account, configure an SSH alias named `wits-mscluster`
using credentials issued by the cluster administrator. Do not commit private
keys or passwords. The historical code and results root is
`/home-mscluster/mbangie/t12-hpc/`. Check the current cluster state with
`squeue -u mbangie` and `sacct` before resubmitting anything. The ABLE IX
five-temperature jobs 60861-60865 were still running/dependency-queued at
the 2026-09-27 check; a queued job is not a saved final result. Retrieve and
verify final outputs when the jobs finish.

The cluster scripts preserve exact historical paths and container assumptions.
On a different account, copy a versioned experiment directory, set its code,
result, model, adapter, cache, and container paths to the new account, then run
its preflight before any Slurm submission. Do not rerun T39/T41 or use
Pilot-120 for training/model selection. [RESEARCH_WORKFLOWS.md](RESEARCH_WORKFLOWS.md)
explains the metric and denominator rules.

## 5. Continue research safely

Create a new branch and a new versioned protocol for future experiments.
Keep `data/annotations/pilot_120_v1/` and the archived result ZIPs immutable.
Generated outputs belong in ignored `outputs/` until they are complete,
hash-verified, reviewed for rights, and deliberately promoted into
`research/pilot120/artifacts/` or another named research record. Update the
case index and its provenance only through the release builder.

The repository audit at [PUBLIC_RELEASE_AUDIT.md](PUBLIC_RELEASE_AUDIT.md)
records the inclusion and rights boundary. A successful clone or hash check
does not grant permission to publicly redistribute upstream-derived text.
