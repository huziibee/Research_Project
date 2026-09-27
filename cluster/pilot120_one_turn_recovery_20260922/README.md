# Pilot-120 one-turn recovery (oracle upper bound) — cluster pack

## What

GPU follow-up experiment: matched control vs oracle-answered second turn for the
26 post-capability CLARIFY ∩ gold-EXECUTE cases (primary 22 = REFUSE→CLARIFY).

Does **not** alter first-turn 83/120 routing.

## Paths

- Code: `/home-mscluster/mbangie/t12-hpc/code/pilot120_one_turn_recovery-20260922/`
- Out: `/home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922/one_turn_recovery_20260922/`

## Submit

From a machine with `rsync` + SSH `wits-mscluster`:

```bash
bash cluster/pilot120_one_turn_recovery_20260922/sync_and_submit.sh
```

Or on the cluster after sync:

```bash
export REC_CODE_ROOT=/home-mscluster/mbangie/t12-hpc/code/pilot120_one_turn_recovery-20260922
export REC_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922
bash "${REC_CODE_ROOT}/cluster/pilot120_one_turn_recovery_20260922/submit.sh"
```

## Status / package / fetch

```bash
squeue -u mbangie
sacct -j <JOBID> --format=JobID,State,Elapsed,ExitCode
cd /home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922
tar -czf one_turn_recovery_20260922.tar.gz one_turn_recovery_20260922/
```

```powershell
scp wits-mscluster:/home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922/one_turn_recovery_20260922.tar.gz .
```
