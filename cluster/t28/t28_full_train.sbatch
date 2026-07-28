#!/bin/bash
# T28 production profile: one whole Blackwell node, no Slurm GPU GRES.
#SBATCH --job-name=t28-full-train
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=24:00:00
#SBATCH --output=%x-%j.out
#SBATCH --error=%x-%j.err

set -euo pipefail
umask 077
: "${T28_RUN_ID:?T28_RUN_ID is required}"
: "${T28_OUTPUT_DIR:?T28_OUTPUT_DIR is required}"

module purge || true
module load apptainer || true
command -v nvidia-smi
nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader
python - <<'PY'
import os, shutil
ram = shutil.disk_usage('/').free
print({'node': os.uname().nodename, 'python': os.sys.version, 'free_root_bytes': ram})
PY

test "$(hostname)" != ""
test -d "${T28_OUTPUT_DIR}"
test "$(df -Pk "${T28_OUTPUT_DIR}" | awk 'NR==2 {print $4}')" -ge 524288000

# The frozen environment/container is supplied by the submission wrapper.
if [[ -n "${T28_CONTAINER:-}" ]]; then
  exec apptainer exec --nv --cleanenv "${T28_CONTAINER}" \
    python scripts/train_t28_full.py "${T28_TRAIN_ARGS[@]}"
fi
exec python scripts/train_t28_full.py "${T28_TRAIN_ARGS[@]}"
