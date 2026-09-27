# Temperature sweep 2026-09-13

One Slurm job that reruns **generation-only** live experiments at four temperatures and three replicas.

Logical grid is still `idx = temp_i * 3 + replica_i` for `idx` in `0..11`. A Slurm `--array=0-11` is rejected on `mss_biggpu` (`MaxSubmitJobsPerUser=6`) and would not run in parallel anyway (`MaxJobsPerUser=1`). This job walks all 12 slices with skip-if-exists so a requeue can continue.

- Code: `/home-mscluster/mbangie/t12-hpc/code/temp_sweep-20260913`
- Native pack: `/home-mscluster/mbangie/t12-hpc/code/temp_sweep-native-20260913`
- Results: `/home-mscluster/mbangie/t12-hpc/results/temp_sweep-20260913/T{temp}/R{n}/`

## Mapping

`idx = temp_i * 3 + replica_i`

| idx | T | replica | seed = `20260913 + replica_i * 1000 + int(T*100)` |
|---|---|---|---|
| 0–2 | 0.0 | R1–R3 | 20260913, 20261913, 20262913 |
| 3–5 | 0.3 | R1–R3 | 20260943, 20261943, 20262943 |
| 6–8 | 0.7 | R1–R3 | 20260983, 20261983, 20262983 |
| 9–11 | 1.0 | R1–R3 | 20261013, 20262013, 20263013 |

`T==0` is greedy (`do_sample=False`). `T>0` samples. Native per-row seed is `slice_seed + row_index`.

## What it does not overwrite

Does **not** write into T39/T41, `goal_first_v2-20260911`, or `goal_first_followon-20260912b`. Adapter stays unofficial. Skip-if-exists on requeue.

## Not in this job

Official two-judge SGC (different study). No competing judge job.
