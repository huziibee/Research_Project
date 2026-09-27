#!/usr/bin/env bash
# CPU reparse of failed v2 rows (improved JSON pick). No GPU.
#SBATCH --job-name=gf-v2-reparse
#SBATCH --partition=bigbatch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/gf-v2-reparse-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/gf-v2-reparse-%j.err

set -euo pipefail
umask 077
: "${GFV2_CODE_ROOT:?}"
: "${GFV2_R1_MANAGER_DIR:?}"

cd "${GFV2_CODE_ROOT}"
python3 scripts/reparse_goal_first_v2_failed_raws.py \
  --root "${GFV2_CODE_ROOT}" \
  --manager-dir "${GFV2_R1_MANAGER_DIR}"
