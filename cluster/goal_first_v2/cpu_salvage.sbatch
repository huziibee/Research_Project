#!/usr/bin/env bash
# Run CPU salvage of failed R1 rows on bigbatch (no GPU).
#SBATCH --job-name=gf-v2-cpu-salvage
#SBATCH --partition=bigbatch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/gf-v2-cpu-salvage-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/gf-v2-cpu-salvage-%j.err

set -euo pipefail
umask 077
: "${GFV2_CODE_ROOT:?}"
: "${GFV2_OUTPUT:?}"

cd "${GFV2_CODE_ROOT}"
export PYTHONPATH="${GFV2_CODE_ROOT}/src:${GFV2_CODE_ROOT}/scripts:${PYTHONPATH:-}"
python3 scripts/cpu_salvage_goal_first_v2_failed_20260912.py \
  --root "${GFV2_CODE_ROOT}" \
  --manager-dir "${GFV2_OUTPUT}/manager"
