#!/bin/bash
# Admit a T39 GPU node only after proving usable Blackwell CUDA inside container.
#SBATCH --job-name=p120-t39-gpu-preflight
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=00:10:00
#SBATCH --nodelist=mscluster[110,112]
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-t39-gpu-preflight-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-t39-gpu-preflight-%j.err

set -euo pipefail
umask 077
: "${T39_CODE_ROOT:?}"
: "${T39_CONTAINER:?}"
: "${T39_OUTPUT_ROOT:?}"
cd "${T39_CODE_ROOT}"

exec /usr/bin/apptainer exec --nv --cleanenv \
  "${T39_CONTAINER}" \
  python3 scripts/pilot120_t39_gpu_preflight.py \
  --output "${T39_OUTPUT_ROOT}/t39_gpu_runtime_preflight.json"
