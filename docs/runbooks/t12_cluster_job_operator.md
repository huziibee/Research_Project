# T12 Cluster Job Operator Runbook

Local Windows operator for packaging exact Git HEAD, submitting a Slurm profile,
polling status, pulling results, and verifying manifests.

**Default SSH alias:** `wits-mscluster`
**Local state root:** `outputs/t12_cluster_jobs/` (untracked runtime data)
**Profiles:** `configs/cluster/t12_job_profiles.json` (initially `canary` only)

D-Final is terminally closed. Do not add an enabled D-Final profile.

## Examples

Submit:

```powershell
python scripts/t12_cluster_job.py --run canary
```

Submit, wait and pull:

```powershell
python scripts/t12_cluster_job.py --run canary --poll --pull
```

Check latest:

```powershell
python scripts/t12_cluster_job.py --status latest
```

Poll and pull:

```powershell
python scripts/t12_cluster_job.py --poll latest --pull
```

Pull later:

```powershell
python scripts/t12_cluster_job.py --pull latest
```

Verify:

```powershell
python scripts/t12_cluster_job.py --verify latest
```

List runs:

```powershell
python scripts/t12_cluster_job.py --list
```

Dry-run (no SSH/submit):

```powershell
python scripts/t12_cluster_job.py --run canary --dry-run
```

## Local layout

```text
outputs/t12_cluster_jobs/state.json
outputs/t12_cluster_jobs/<run-id>/remote_metadata.json
outputs/t12_cluster_jobs/<run-id>/source_identity_manifest.json
outputs/t12_cluster_jobs/<run-id>/submit.sbatch
outputs/t12_cluster_jobs/<run-id>/pulled/
outputs/t12_cluster_jobs/<run-id>/verification.json
```

## Behaviour notes

- Requires OpenSSH client and BatchMode access via the configured alias.
- `--run` packages exact `HEAD`, refuses staged/unexpected tracked dirty trees,
  and permits known unrelated untracked runtime files.
- `--status` queries `squeue` first, then `sacct`. Leaving the queue is not success.
- Terminal states include: PENDING/RUNNING/COMPLETING and COMPLETED/FAILED/
  CANCELLED/TIMEOUT/OUT_OF_MEMORY/NODE_FAIL/PREEMPTED.
- `--poll` prints state changes, stops on terminal state, and never auto-cancels
  on local timeout.
- `--pull` works for COMPLETED and failed jobs; refuses silent overwrite; never
  deletes remote runs; never auto-promotes evidence into Git.
- `--verify` recomputes SHA-256, sizes, and JSONL row counts without importing
  torch/transformers/vLLM.

## Troubleshooting (non-destructive)

1. Confirm SSH: `ssh -o BatchMode=yes wits-mscluster -- printf ok`
2. Inspect state: `python scripts/t12_cluster_job.py --list`
3. Re-check status: `python scripts/t12_cluster_job.py --status latest`
4. Pull after terminal failure if results exist: `--pull latest`
5. Do not use `rm -rf`, `scancel` from this operator, or interactive SSH blocks
   that could terminate a login session.
