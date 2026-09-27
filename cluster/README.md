# Cluster jobs

These scripts document Wits Slurm runs. They are versioned experiment
templates, not a single generic launcher. Keep old completed jobs and their
result archives frozen.

| Experiment | Launcher | State and result location |
| --- | --- | --- |
| T0.7 matched baseline | `pilot120_t07_matched_baseline_20260922/submit.sh` | Completed; frozen ZIP in `research/pilot120/artifacts/` |
| One-turn clarify recovery | `pilot120_one_turn_recovery_20260922/submit.sh` | Historical results in the full-analysis ZIP; inspect protocol and failed rows |
| ABLE IX temperatures | `pilot120_t03_gf_ablation_20260923/submit_five_temps.sh` | Five jobs queued 2026-09-27; check live Slurm and final artifacts |
| Earlier T12/T28/T39/T41 jobs | Other versioned directories | Historical; do not submit without a new protocol and preflight |

The launchers use account-specific paths under
`/home-mscluster/mbangie/t12-hpc/` and need existing container images,
checkpoint/adapter files, and a configured Slurm account. The core Python
package alone does not install these dependencies. Inspect the launcher and
`configs/environments/` before copying a job to a new account. Keep job
submissions, logs, and results outside Git until verified and archived.

For a running study, use `squeue -u mbangie`, then `sacct -j JOBID` for final
state and exit code. Also check the declared number of output rows, unique
record IDs, final summary, ZIP integrity, and SHA-256. A `RUN` log line or
Slurm `.extern COMPLETED` step is not proof of a completed experiment.
