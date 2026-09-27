# Mega close 2026-09-13

One Slurm job that:

1. Smokes unofficial adapter path on **5 rows** (goal-first managers + PEFT direct) at T=0
2. Runs the full final-close (raw/FT intent boxes, speech-act, two-judge SGC)
3. Walks the full temperature sweep (12 slices, skip-if-exists) with `--allow-unofficial-adapter`

Does **not** flip `selected_adapter` / `valid_for_official_use`. Does **not** overwrite T39/T41.

Submit on the cluster:

```bash
bash /home-mscluster/mbangie/t12-hpc/code/mega_close-20260913/cluster/mega_close_20260913/submit.sh
```
