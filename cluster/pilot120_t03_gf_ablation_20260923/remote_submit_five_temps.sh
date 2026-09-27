#!/usr/bin/env bash
set -euo pipefail

T03_CODE=/home-mscluster/mbangie/t12-hpc/code/pilot120_t03_gf_ablation-20260923
FC=/home-mscluster/mbangie/t12-hpc/code/final_close-20260913
ABLE_OUT=/home-mscluster/mbangie/t12-hpc/results/able_ix_five_seed-20260923

test -d "${T03_CODE}"
mkdir -p "${T03_CODE}/scripts" "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923" "${ABLE_OUT}"
cp -f /tmp/score_gf_temp_ablation_20260923.py "${T03_CODE}/scripts/score_gf_temp_ablation_20260923.py"
cp -f /tmp/aggregate_able_ix_means_20260923.py "${T03_CODE}/scripts/aggregate_able_ix_means_20260923.py"
cp -f /tmp/able_ix_temp.sbatch "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923/able_ix_temp.sbatch"
cp -f /tmp/submit_five_temps.sh "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923/submit_five_temps.sh"
chmod +x "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923/"*.sh \
         "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923/"*.sbatch

# Official intent-screen refs (fix-emit copy was empty/unusable).
DEST_REFS="${T03_CODE}/pilot120_intent_evaluation_20260902/pilot120_intent_evaluation_20260902/validation/self_contained_rebuild/data"
mkdir -p "${DEST_REFS}"
for src in \
  "${FC}/pilot120_intent_evaluation_20260902/pilot120_intent_evaluation_20260902/validation/self_contained_rebuild/data/intent_gold_references_120.jsonl" \
  "${FC}/pilot120_intent_evaluation_20260902/pilot120_intent_evaluation_20260902/data/intent_gold_references_120.jsonl"
 do
  if [[ -f "${src}" ]]; then
    cp -f "${src}" "${DEST_REFS}/intent_gold_references_120.jsonl"
    echo "refs_from ${src}"
    break
  fi
done
test -s "${DEST_REFS}/intent_gold_references_120.jsonl"
echo "refs_ok $(wc -l < "${DEST_REFS}/intent_gold_references_120.jsonl")"

# 58442 must stay running.
squeue -j 58442 || true

export T03_CODE_ROOT="${T03_CODE}"
export ABLE_OUTPUT="${ABLE_OUT}"
export GFV2_CONTAINER=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif
export GFV2_HF_HOME=/home-mscluster/mbangie/t12-hpc/hf-cache
export GFV2_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-hpc/training-site-packages
export AFTER_FIRST=58442
export ABLE_SEEDS="1 2 3 4"

bash "${T03_CODE}/cluster/pilot120_t03_gf_ablation_20260923/submit_five_temps.sh"
echo FIVE_TEMP_SUBMIT_DONE
