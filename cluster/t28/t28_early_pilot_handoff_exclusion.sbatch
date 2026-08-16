#!/bin/bash
# Package and clean-load a T28 adapter for Pilot-only evaluation with one disclosed exclusion.
#SBATCH --job-name=t28-early-pilot-handoff
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=04:00:00
#SBATCH --nodelist=mscluster111
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/t28-early-pilot-handoff-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/t28-early-pilot-handoff-%j.err

set -euo pipefail
umask 077
: "${T28_CODE_ROOT:?}"
: "${T28_TRAINING_SITE_PACKAGES:?}"
: "${T28_HF_HOME:?}"
: "${T28_CONTAINER:?}"
: "${T28_ADAPTER:?}"
: "${T28_REPAIR_EVALUATION_DIR:?}"
: "${T28_EARLY_IDENTITY:?}"
: "${T28_EARLY_PACKAGE:?}"
: "${T28_EARLY_CLEAN_LOAD:?}"
cd "${T28_CODE_ROOT}"
run_container() {
  /usr/bin/apptainer exec --nv --cleanenv --env "PYTHONPATH=${T28_TRAINING_SITE_PACKAGES}:${T28_CODE_ROOT}/src,HF_HOME=${T28_HF_HOME},HUGGINGFACE_HUB_CACHE=${T28_HF_HOME}/hub,TRANSFORMERS_CACHE=${T28_HF_HOME}/hub" "${T28_CONTAINER}" "$@"
}
run_container python scripts/create_t28_early_pilot_identity.py --adapter-identity "${T28_ADAPTER}/adapter_identity.json" --repair-evaluation-dir "${T28_REPAIR_EVALUATION_DIR}" --excluded-call-id clara:1170::predict_cpc_v1 --output "${T28_EARLY_IDENTITY}"
run_container python scripts/t28_package_adapter.py --checkpoint "${T28_ADAPTER}" --destination "${T28_EARLY_PACKAGE}" --identity-json "${T28_EARLY_IDENTITY}"
run_container python scripts/t28_clean_load_verify.py --package "${T28_EARLY_PACKAGE}" --output "${T28_EARLY_CLEAN_LOAD}" --base-revision b968826d9c46dd6066d109eabc6255188de91218 --schema-registry "${T28_CODE_ROOT}/configs/model/evidence/t27f_schema_preflight_live.json" --perform-model-load
