#!/usr/bin/env bash
# Submit CPU jobs that unlock scoring without fighting GPU 53074/53081.
set -euo pipefail
umask 077

: "${GFV2_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911}"
: "${FOLLOWON_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260911}"
: "${FOLLOWON_SCORE_OUT:=/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260911-cpu-scores}"
: "${GFV2_R1_MANAGER_DIR:=/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911/manager}"
: "${GFV2_R1_AUDIT_OUT:=/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911/cpu_r1_audit.json}"
: "${PACKET_OUT:=/home-mscluster/mbangie/t12-hpc/results/base_adapter_sgc_packet-20260911}"
: "${PACKET_GOLD:=/home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911/pilot120_intent_evaluation_20260902/pilot120_intent_evaluation_20260902/data/intent_gold_references_120.jsonl}"
: "${PACKET_BASE_PRED:=/home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911/review_bundles/pilot120_t39_20260902/cluster_outputs/R1/direct_base/direct_base_llm.predictions.jsonl}"
: "${PACKET_ADAPTER_PRED:=/home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911/review_bundles/pilot120_t39_20260902/cluster_outputs/R1/selected_adapter/t28_selected_adapter_llm.predictions.jsonl}"
: "${PACKET_CODE_ROOT:=${GFV2_CODE_ROOT}}"

# Fallbacks if intent pack / review bundle were not synced into the v2 code root.
if [[ ! -f "${PACKET_GOLD}" ]]; then
  PACKET_GOLD=/home-mscluster/mbangie/t28_r5_src/pilot120_intent_evaluation_20260902/pilot120_intent_evaluation_20260902/data/intent_gold_references_120.jsonl
fi
if [[ ! -f "${PACKET_BASE_PRED}" ]]; then
  PACKET_BASE_PRED=/home-mscluster/mbangie/t28_r5_src/outputs/pilot_120/t39_20260901_6d71aff_gpu/cluster_outputs/R1/direct_base/direct_base_llm.predictions.jsonl
fi
if [[ ! -f "${PACKET_ADAPTER_PRED}" ]]; then
  PACKET_ADAPTER_PRED=/home-mscluster/mbangie/t28_r5_src/outputs/pilot_120/t39_20260901_6d71aff_gpu/cluster_outputs/R1/selected_adapter/t28_selected_adapter_llm.predictions.jsonl
fi

export GFV2_CODE_ROOT FOLLOWON_OUTPUT FOLLOWON_SCORE_OUT
export GFV2_R1_MANAGER_DIR GFV2_R1_AUDIT_OUT
export PACKET_CODE_ROOT PACKET_OUT PACKET_GOLD PACKET_BASE_PRED PACKET_ADAPTER_PRED

mkdir -p "$(dirname "${GFV2_R1_AUDIT_OUT}")" "${FOLLOWON_SCORE_OUT}" "${PACKET_OUT}" \
  /home-mscluster/mbangie/t12-hpc/logs

echo "=== locating gold/preds ==="
ls -la "${PACKET_GOLD}" "${PACKET_BASE_PRED}" "${PACKET_ADAPTER_PRED}" || true

# 1) NOW: build base/adapter SGC packets (CPU)
j1=$(sbatch --parsable --export=ALL \
  "${GFV2_CODE_ROOT}/cluster/goal_first_v2/build_base_adapter_sgc_packet.sbatch")
echo "submitted ba-sgc-packet ${j1}"

# 2) afterok:53074: R1 CPU audit while GPU follow-on starts
j2=$(sbatch --parsable --dependency=afterok:53074 --export=ALL \
  "${GFV2_CODE_ROOT}/cluster/goal_first_v2/post_r1_cpu_audit.sbatch")
echo "submitted gf-v2-r1-audit ${j2} afterok:53074"

# 3) afterok:53081: score R2/R3 + natives when follow-on finishes
j3=$(sbatch --parsable --dependency=afterok:53081 --export=ALL \
  "${GFV2_CODE_ROOT}/cluster/goal_first_v2/post_followon_cpu_score.sbatch")
echo "submitted gf-followon-score ${j3} afterok:53081"

printf 'ba_sgc_packet\t%s\ngf_v2_r1_audit\t%s\tafterok:53074\ngf_followon_score\t%s\tafterok:53081\n' \
  "${j1}" "${j2}" "${j3}" | tee /home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911/cpu_jobs_submission.tsv

squeue -u mbangie -o '%.18i %.9P %.20j %.2t %.10M %.20R %.30E'
