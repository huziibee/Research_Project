#!/bin/bash
# Run the three missing non-protected Pilot-120 manager systems together.
#SBATCH --job-name=p120-manager-matrix
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=18:00:00
#SBATCH --nodelist=mscluster111
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-manager-matrix-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-manager-matrix-%j.err

set -euo pipefail
umask 077
: "${P120_CODE_ROOT:?}"
: "${P120_TRAINING_SITE_PACKAGES:?}"
: "${P120_HF_HOME:?}"
: "${P120_CONTAINER:?}"
: "${P120_MANAGER_OUTPUT:?}"
: "${P120_SELECTED_ADAPTER:?}"
: "${P120_SELECTED_ADAPTER_IDENTITY:?}"
: "${P120_ADAPTER_SCALE:?}"
cd "${P120_CODE_ROOT}"

exec /usr/bin/apptainer exec --nv --cleanenv \
  --env "PYTHONPATH=${P120_TRAINING_SITE_PACKAGES}:${P120_CODE_ROOT}/src,HF_HOME=${P120_HF_HOME},HUGGINGFACE_HUB_CACHE=${P120_HF_HOME}/hub,TRANSFORMERS_CACHE=${P120_HF_HOME}/hub" \
  "${P120_CONTAINER}" \
  python scripts/evaluate_pilot_120_manager_systems.py \
  --root "${P120_CODE_ROOT}" \
  --output-dir "${P120_MANAGER_OUTPUT}" \
  --adapter "${P120_SELECTED_ADAPTER}" \
  --adapter-identity "${P120_SELECTED_ADAPTER_IDENTITY}" \
  --adapter-scale "${P120_ADAPTER_SCALE}"
