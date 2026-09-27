# Depth-five seed-0 analysis failure: technical rerun v1

**Status:** Slurm **60920** failed because its staged code omitted
`pyproject.toml`. The corrected separate staging and output, Slurm **60943**,
completed on 2026-09-27 with exit `0:0`. The frozen experiment and its
original 26-row scores remain unchanged. This versioned run is a technical
sensitivity check, not a replacement for the primary 13/22 and 16/26 seed-0
recovery counts or a matched-depth causal comparison.

## Exact diagnosis

The saved [full-analysis ZIP](../../research/pilot120/artifacts/p120_full_analysis_20260923.zip)
has SHA-256 `0305b1e9ab062876ee6ee89778cc6028d2eaf01718b7dd0295944e7d9cb81a01`.
The relevant members are `one_turn_recovery_20260922/06_answered_predictions_seed0.jsonl`,
`12_answered_predictions_seed1.jsonl`, `04_oracle_responses.jsonl`, and
`01_frozen_manifest.json`. The seed-0 answered member has SHA-256
`ca1b80b46af38fc7faec8dc64fbfcde9904be35afde422169efebd971b260d23`.
The saved final `raw_generations.goal_first` SHA matches the recorded final
attempt SHA for each case. All three final attempts report
`transport_status=constrained_generated`, `termination_reason=maximum_token`,
and `max_new_tokens=1024`. The top-level JSON begins with a valid
`intent_summary` but enters a long repeated string inside `cpc`; it ends
before the string and outer object close. `json.loads` reports an unterminated
string. [`extract_analysis_json`](../../src/ambiguity_manager/systems/goal_first_analysis_v2.py)
then selects a valid nested `value/status` object, which lacks
`intent_summary`; validation returns `bad_intent_summary`. That is the
correct response to incomplete top-level JSON, not evidence of a parser
defect or a valid out-of-schema terminal decision. Capability judging is
skipped after failed analysis, so the route stays empty. There is no
recorded transport/runtime error. Earlier raw analysis attempts are not
retained; only their hashes and validation codes are available.

| Case | Seed-0 failure depth | Attempts 1 / 2 / constrained 3 | Final raw SHA-256 | Classification |
| --- | ---: | --- | --- | --- |
| [CA-0702](../../research/pilot120/cases/CA-0702.json) | 1 | `bad_intent_summary` / `bad_intent_summary` / `bad_intent_summary`; third hit 1024 tokens | `535439ba4d50d018c604f56bb3db7779e941d913e2ac6d55f7f3b3fbea0d725f` | Incomplete repetitive constrained generation; validator correctly rejects nested fragment. |
| [CA-0733](../../research/pilot120/cases/CA-0733.json) | 2, after valid CLARIFY at depth 1 | `bad_intent_summary` / `bad_intent_summary` / `bad_intent_summary`; third hit 1024 tokens | `21e7a2af042d79ca08443c50515c04feac8d7f6c2ee02168ca2e9144b1037402` | Same failure at second answered depth. |
| [CA-0778](../../research/pilot120/cases/CA-0778.json) | 2, after valid CLARIFY at depth 1 | `bad_intent_summary` / `bad_pilot_ambiguity_types` / `bad_intent_summary`; third hit 1024 tokens | `7f7875260dc42c747c01901d03e2c76875ce9a7c3e06d6acd01fcf7bcfad1f66` | Attempt 2 also violated the ambiguity-type schema; final failure is the same incomplete constrained generation. |

Seed 1 independently produced valid routes for all three (CA-0702 EXECUTE
at depth 2, CA-0733 EXECUTE at depth 4, CA-0778 EXECUTE at depth 1). Thus
there is no evidence of an intrinsically impossible case. Increasing the
constrained-final cap is a technically justified sensitivity rerun. A
successful rerun cannot be attributed **only** to that cap, because fresh
stochastic generation may succeed on an earlier retry. Keep the original
failures in every primary denominator.

## Versioned job and safeguards

[`recovery_technical_rerun_v1.py`](../../scripts/recovery_technical_rerun_v1.py)
checks hashes of the frozen manifest, oracle responses, and 26-row seed-0
answered stream before loading a GPU. It requires the three exact failed
row hashes and depths, resumes each at its frozen failed command and
dialogue history, and carries forward only its earlier valid path. It runs
**answered only**, with independent recorded rerun seeds, the same model
revision and 0.7 temperature, and a 4096-token constrained-final cap. It
does not run the control, seed 1, or the other 23 answered rows. Its output
contains `original_failed_rows.jsonl`, `answered_failed_step_reruns.jsonl`,
`technical_rerun_report.json`, and `SHA256_FINAL.txt`. No code splices new
routes into the frozen `06_answered_predictions_seed0.jsonl` or rewrites a
primary summary.

For a local CPU preflight, extract the ZIP's three named members into an
ignored `outputs/recovery_original/one_turn_recovery_20260922/` directory,
then run:

```sh
python scripts/recovery_technical_rerun_v1.py \
  --original-exp outputs/recovery_original/one_turn_recovery_20260922 \
  --out outputs/recovery_technical_rerun_v1_20260927
```

The preflight returns `PREFLIGHT_OK original=26 affected=CA-0702,CA-0733,CA-0778
answered_seed0_only cap=4096` without GPU inference. The checked cluster
launcher is
[`technical_rerun.sbatch`](../../cluster/pilot120_recovery_technical_rerun_v1/technical_rerun.sbatch).
Stage a separate immutable code checkout on the cluster and verify these
paths before submission:

```sh
export REC_TECH_CODE=/home-mscluster/mbangie/t12-hpc/code/pilot120_recovery_technical_rerun_v1-20260927
export REC_TECH_ORIGINAL_EXP=/home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922/one_turn_recovery_20260922
export REC_TECH_OUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_recovery_technical_rerun_v1-20260927
export GFV2_CONTAINER=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif
export GFV2_HF_HOME=/home-mscluster/mbangie/t12-hpc/hf-cache
export GFV2_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-hpc/training-site-packages
python3 "$REC_TECH_CODE/scripts/recovery_technical_rerun_v1.py" \
  --original-exp "$REC_TECH_ORIGINAL_EXP" --out "$REC_TECH_OUT"
sbatch --export=ALL "$REC_TECH_CODE/cluster/pilot120_recovery_technical_rerun_v1/technical_rerun.sbatch"
```

The staged code archive at
`/home-mscluster/mbangie/t12-hpc/code/pilot120_recovery_technical_rerun_v1_20260927.tar`
was verified SHA-256
`b34b1c1444b3f43cdd2357c86ada01f8e7114da47d30ec54d70b657dcabd1f5f`
before extraction to the separate `REC_TECH_CODE` directory. The original
cluster manifest, oracle, and seed-0 answered stream matched the three
expected hashes; the cluster preflight printed `PREFLIGHT_OK`.

The host preflight needs the same Python dependencies as the original runner;
the Slurm script repeats it inside the pinned container before loading the
model. Confirm the original input hashes, model/cache availability, and an
empty new output directory first. If there are running jobs, inspect their
checkpoint/resume contract before changing priority or cancelling anything.
After submission, use `squeue` and `sacct` for state/exit code, verify all
three new JSONL rows and the four listed artifacts, and compare SHA-256 to
`SHA256_FINAL.txt`. Report these outcomes separately from the frozen result.

At the live queue check, ABLE IX **60861** was RUNNING on `mscluster112` and
its T0.0 seed-1 checkpoint was 79/120; it was **not stopped**. Jobs 60862–60865
were dependency queued. To make 60920 the next eligible user job while
preserving automatic continuation, only job 60862's dependency was changed
from `afterany:60861` to `afterany:60861,afterany:60920`. Its verified Slurm
state is `PENDING Dependency` with both conditions unfulfilled; 60863–60865
retain their original downstream chain. If 60920 fails, `afterany` still
releases 60862 once 60861 has ended, so the other experiment is not stranded.
The preceding queue note records the state at submission time. Its pending
status was superseded by the completion record below.

## Completed technical sensitivity rerun

Job 60920 passed the frozen-input and GPU preflights but failed before any
case completed. Its staged code lacked `pyproject.toml`, which
`ProjectPaths.from_repo_root()` requires before loading the routing config.
The failed output directory contains only `original_failed_rows.jsonl`; its
Slurm log and directory are retained. The launcher now checks the repository
marker and both needed configs and instantiates the router before GPU loading.

The corrected job used separate code and output directories:

```text
/home-mscluster/mbangie/t12-hpc/code/pilot120_recovery_technical_rerun_v2-20260927
/home-mscluster/mbangie/t12-hpc/results/pilot120_recovery_technical_rerun_v2-20260927
/home-mscluster/mbangie/t12-hpc/logs/p120-rec-tech-v1-60943.out
```

The staged `pyproject.toml` SHA-256 is
`66c58d0d027e5e7e7c9f328e5bd21379047cfdf0dda7954185548565cabdefc0`;
the corrected `technical_rerun.sbatch` SHA-256 is
`88898d51927cb8d7ab5f4e0e2542faa7cb2a889b3531c394999f672072369227`.
The exact-hash original-input preflight and router/constraint-config preflight
passed. Slurm job **60943** completed in 00:08:55 with exit `0:0`.

| Record | Rerun terminal route | Clarify depth | Failed |
| --- | --- | ---: | --- |
| CA-0702 | execute | 1 | false |
| CA-0733 | execute | 3 | false |
| CA-0778 | execute | 3 | false |

`answered_failed_step_reruns.jsonl` has exactly three rows, with SHA-256
`59fe378fc253627ab014cef7177071e7e7c42392362a467b00665e76ddfc692a`.
`technical_rerun_report.json` has SHA-256
`4f58647960b8f9f9dc681405e4ba5b787406ce99d29640f41560b1b4f11dd1c2`.
`original_failed_rows.jsonl` has SHA-256
`d93f35c0e847e0cbb23359795102c19ca220f3e1bd487a03f2cbcc965dc04f1a`.
The user ran `sha256sum -c SHA256_FINAL.txt` in the completed output directory;
all three files returned `OK`. To repeat that verification:

```sh
cd /home-mscluster/mbangie/t12-hpc/results/pilot120_recovery_technical_rerun_v2-20260927
wc -l answered_failed_step_reruns.jsonl
sha256sum -c SHA256_FINAL.txt
```

These three fresh-seed paths reached a valid terminal route after increasing
the constrained-final cap from 1024 to 4096. They do not prove that the cap
alone caused the change, because stochastic generation could succeed on an
earlier retry. Keep the original failed rows in all primary denominators.
The other ABLE IX jobs (60862-60865) were subsequently cancelled at the
user's direction to prioritize this run; they are not completed results.
