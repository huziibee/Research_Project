#!/usr/bin/env bash
# One isolated 24h job: goal-first manager v2 on frozen Pilot-120.
# Does not rerun or overwrite T39/T41. Later optional tasks are skipped if time is low.
#SBATCH --job-name=gf-v2-combined
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=24:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/gf-v2-combined-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/gf-v2-combined-%j.err

set -u
umask 077
: "${GFV2_CODE_ROOT:?}"
: "${GFV2_OUTPUT:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_CONTAINER:?}"

cd "${GFV2_CODE_ROOT}"
mkdir -p "${GFV2_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs

GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
if [[ "${GPU_USED}" -gt 1000 ]]; then
  echo "busy_gpu:${GPU_USED}" >&2
  exit 42
fi

python3 - <<'PY'
import json
import os
from pathlib import Path

out = Path(os.environ["GFV2_OUTPUT"])
out.mkdir(parents=True, exist_ok=True)
argv = [
    "python3",
    "scripts/evaluate_goal_first_manager_v2.py",
    "--root",
    os.environ["GFV2_CODE_ROOT"],
    "--output-dir",
    str(out / "manager"),
]
adapter = os.environ.get("GFV2_SELECTED_ADAPTER")
if adapter:
    argv.extend(
        [
            "--adapter",
            adapter,
            "--adapter-identity",
            os.environ["GFV2_ADAPTER_IDENTITY"],
            "--adapter-scale",
            os.environ["GFV2_ADAPTER_SCALE"],
        ]
    )
tasks = [
    {
        "id": "manager_v2",
        "required": True,
        "min_remaining_seconds": 1800,
        "argv": argv,
    }
]
# Native full Gemma/GLM runs are a different model load and can consume the
# remaining wall clock. Keep them off unless GFV2_ENABLE_NATIVE=1.
if os.environ.get("GFV2_ENABLE_NATIVE") == "1":
    tasks.append(
        {
            "id": "native_note",
            "required": False,
            "min_remaining_seconds": 21600,
            "argv": ["python3", "-c", "raise SystemExit('native_full_not_wired_in_this_job_use_cluster_canaries')"],
        }
    )
(out / "tasks.json").write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out / 'tasks.json'} n_tasks={len(tasks)}")
PY

exec /usr/bin/apptainer exec --nv --cleanenv \
  --env "PYTHONPATH=${GFV2_TRAINING_SITE_PACKAGES}:${GFV2_CODE_ROOT}/src,HF_HOME=${GFV2_HF_HOME},HUGGINGFACE_HUB_CACHE=${GFV2_HF_HOME}/hub,TRANSFORMERS_CACHE=${GFV2_HF_HOME}/hub" \
  "${GFV2_CONTAINER}" \
  python3 scripts/cluster_isolated_task_runner.py \
  --tasks "${GFV2_OUTPUT}/tasks.json" \
  --output-dir "${GFV2_OUTPUT}"
