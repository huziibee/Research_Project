# Research workflows

This page separates checks that work from a code checkout from experiments
that require controlled data, model weights, and a GPU environment.

## Code and schema checks

Install the package and development extras as shown in the root README. Run:

```sh
python -m pytest -q tests/test_schema_validation.py
```

These checks do not reproduce a model score. The complete suite is
`python -m pytest -q` after the exact local inputs and optional dependencies
are provisioned. Tests that require restricted Pilot-120 text cannot be run
from a metadata-only public release.

## Before evaluating

1. Read `docs/DATASETS.md` and obtain the exact dataset version from its
   original provider under the applicable terms.
2. Read `docs/PILOT120.md`; verify the frozen source, gold, and manifest hashes
   if you have authorised access. Keep Pilot-120 evaluation-only.
3. Read `configs/evaluation/pilot_120_v1.json` for labels, denominator policy,
   and gold paths. Use the specific experiment's protocol and run manifest for
   model identity, decoding, temperature, and seed.
4. Verify the model and adapter files separately. The core Python package does
   not install PyTorch, Transformers, PEFT, vLLM, CUDA, or cluster containers.
   Historical cluster environment records are under `configs/environments/`,
   `requirements/`, and the relevant `cluster/` job directory.

Use `python scripts/<chosen-script>.py --help` to inspect inputs. CPU scorers
may work locally; GPU evaluators require the pinned inference environment.
Do not execute the historical `cluster/pilot120/submit_t39_*.sh` scripts as a
fresh run. They preserve frozen evidence and job-specific paths. Copy the
versioned contract to a **new** experiment directory for future work.

## Current analysis paths

- Core manager and local evaluation: `src/ambiguity_manager/`,
  `scripts/evaluate_pilot_120_manager_systems.py`, and the matching tests.
- T0.7 official intent: `cluster/pilot120_t07_matched_baseline_20260922/`,
  `scripts/evaluate_pilot_120_intent_box.py`, the SGC packet builders,
  `scripts/semantic_intent/run_blind_semantic_judge.py`,
  `scripts/score_t07_matched_baseline_20260922.py`, and
  `scripts/finalize_t07_paper_pack_20260923.py`.
- One-turn clarification recovery:
  `cluster/pilot120_one_turn_recovery_20260922/` and
  `scripts/one_turn_recovery_20260922.py`.
- ABLE IX exploratory temperatures:
  `cluster/pilot120_t03_gf_ablation_20260923/`,
  `scripts/score_gf_temp_ablation_20260923.py`, and
  `scripts/aggregate_able_ix_means_20260923.py`.

The last two are separate from the T0.7 official two-judge result. ABLE IX's
intent measure is an automatic screening metric, not official intent gold.
Do not pool deterministic replays as independent samples or drop failed rows.

## Artifacts and status

Generated files live under `outputs/` locally or a versioned cluster result
root. A Slurm `COMPLETED` state alone is insufficient: verify the declared
number of JSONL rows, unique IDs, final summaries, archive integrity, and
SHA-256. A `RUN` log line or `.extern COMPLETED` step is not a finished study.
Use `docs/PILOT120.md` for the completed T0.7 aggregate table and archive
hash. The `handover/` folder and `cursor_plan/` retain historical decisions;
their dates and job IDs are not a current queue snapshot.
