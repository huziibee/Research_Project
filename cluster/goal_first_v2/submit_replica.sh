#!/usr/bin/env bash
# Submit a later locked replica of goal-first v2. Do not change the prompt.
# Do not submit while replica 1 (job 53074 / gf-v2-combined) is still running.
# Usage on cluster:
#   export GFV2_REPLICA=R2
#   export GFV2_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911-${GFV2_REPLICA}
#   bash cluster/goal_first_v2/submit_replica.sh
set -euo pipefail
umask 077

: "${GFV2_REPLICA:?set GFV2_REPLICA to R2 or R3}"
: "${GFV2_CODE_ROOT:?}"
: "${GFV2_OUTPUT:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_CONTAINER:?}"

case "${GFV2_REPLICA}" in
  R2|R3|R4|R5) ;;
  *)
    echo "gf_v2_replica_must_be_R2_R3_R4_or_R5:${GFV2_REPLICA}" >&2
    exit 2
    ;;
esac

if [[ "${GFV2_OUTPUT}" == *t39* ]]; then
  echo "gf_v2_output_must_not_be_a_t39_path:${GFV2_OUTPUT}" >&2
  exit 2
fi
if [[ -e "${GFV2_OUTPUT}" ]]; then
  echo "gf_v2_output_must_be_new:${GFV2_OUTPUT}" >&2
  exit 2
fi

export GFV2_CODE_ROOT GFV2_TRAINING_SITE_PACKAGES GFV2_HF_HOME GFV2_CONTAINER GFV2_OUTPUT
if [[ -n "${GFV2_SELECTED_ADAPTER:-${T39_SELECTED_ADAPTER:-}}" ]]; then
  export GFV2_SELECTED_ADAPTER="${GFV2_SELECTED_ADAPTER:-${T39_SELECTED_ADAPTER}}"
  export GFV2_ADAPTER_IDENTITY="${GFV2_ADAPTER_IDENTITY:-${T39_ADAPTER_IDENTITY:?}}"
  export GFV2_ADAPTER_SCALE="${GFV2_ADAPTER_SCALE:-${T39_ADAPTER_SCALE:?}}"
fi

job_id=$(sbatch --parsable --job-name="gf-v2-${GFV2_REPLICA}" --export=ALL \
  "${GFV2_CODE_ROOT}/cluster/goal_first_v2/combined_3day.sbatch")
mkdir -p "${GFV2_OUTPUT}"
printf 'replica\t%s\njob_id\t%s\noutput\t%s\n' "${GFV2_REPLICA}" "${job_id}" "${GFV2_OUTPUT}" \
  | tee "${GFV2_OUTPUT}/submission.tsv"
echo "submitted replica ${GFV2_REPLICA} as ${job_id}"
