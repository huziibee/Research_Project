# T27C-R1 — Job 9479 forensic diagnosis

Status: diagnosed; runtime recovery required

## Evidence inspected

- Local run metadata: `outputs/t12_cluster_jobs/t12-qlora-task-conditioned-20260723T171913Z-f3fdf91/remote_metadata.json`.
- Local submit script: `outputs/t12_cluster_jobs/t12-qlora-task-conditioned-20260723T171913Z-f3fdf91/submit.sbatch`.
- Pulled adapter and checkpoint manifests under the same run's `pulled/` directory.
- Remote Slurm accounting for job `9479`.
- Remote stdout/stderr:
  `/home-mscluster/mbangie/t12-hpc/logs/t12-qlora-task-conditioned-9479.out` and
  `/home-mscluster/mbangie/t12-hpc/logs/t12-qlora-task-conditioned-9479.err`.
- Remote result directory:
  `/home-mscluster/mbangie/t12-hpc/runs/qlora-task-conditioned-smoke/t12-qlora-task-conditioned-20260723T171913Z-f3fdf91`.
- Runner source at the submitted source commit `f3fdf91b0be26e446f15c7caa7129cf59d1339fb`.

## Direct observations

Slurm accounting returned:

```text
9479|CANCELLED by 328600030|0:0|00:27:52|mscluster109|None
9479.batch|CANCELLED|0:15|00:27:52|mscluster109|
9479.extern|COMPLETED|0:0|00:27:52|mscluster109|
```

The stdout file is zero bytes. The stderr file ends with a completed
`Loading weights ... 100%` progress sequence, warnings from PEFT/bitsandbytes,
and:

```text
[2026-07-23T17:49:10.390] error: *** JOB 9479 ON mscluster109 CANCELLED AT 2026-07-23T17:49:10 DUE to SIGNAL Terminated ***
```

There is no application progress line, record ID, task ID, constraint-compilation
line, generation-return line, validation line, heartbeat, journal, partial task
prediction, or final result JSON in the remote result directory. The remote
directory contains the adapter, adapter identity, training state, and full
checkpoint only.

## Stage map

1. Source verification: completed; the submitted archive and source identity
   manifest identify `f3fdf91b0be26e446f15c7caa7129cf59d1339fb`.
2. Environment verification: entered; the training SIF and site packages ran.
3. Base-model load: completed at least once; training reached checkpoint and
   adapter artefacts were written.
4. Adapter training/loading: training completed sufficiently to write the
   adapter and checkpoint; no inference adapter-load marker exists.
5. Checkpoint verification: training artefacts were written and pulled.
6. Base prediction: not reached; the runner first constructs evaluation model
   instances before the first task call.
7. Adapter prediction: not reached.
8. Constrained-decoder initialisation: not reached.
9. Task-specific generation: not reached.
10. Task validation: not reached.
11. Deterministic assembly: not reached.
12. Evidence finalisation: not reached.
13. Operator pull: completed later from the partial artefact directory.
14. Local verification: verified the pulled artefacts, not a sealed result.

The exact stopping region is therefore evaluation model construction/loading,
after training artefact creation and before the first prediction. The logs do
not contain a program-owned marker that distinguishes the final base evaluation
load from the adapter-base evaluation load; that sub-stage must not be guessed.

## Classification

Primary failure classification: **insufficient observability**.

The process was alive in a model-weight loading path when it was cancelled by
Slurm signal termination. The evidence does not establish a deadlock,
constrained-schema compilation hang, generation hang, EOS failure, or time-limit
expiry. It also does not establish useful inference progress. The correct
conclusion is **unobservable slow/pre-generation evaluation followed by operator
cancellation**, not a genuine generation hang.

The implementation defect is material: the runner creates separate base and
adapter evaluation model instances, performs all 120 task calls serially, and
has no heartbeat, per-task bound, durable task journal, or resumable result
matrix. Job 9479 therefore could not distinguish model loading from inference
progress and could not finalise a blocked run.

## Adapter reuse decision at this checkpoint

The adapter safetensors, adapter config, identity, and checkpoint blob exist and
the immutable base identity, data manifest hash, task registry hash, and field
registry hash are present. However, the checkpoint manifest records
`source_commit: unknown`, and there is no runtime inference result or base-frozen
verification for this adapter. It must remain technical-smoke-only until the
new explicit reuse verifier confirms every frozen identity. It is never written
to `selected_adapter`.
