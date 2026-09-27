#!/usr/bin/env bash
# Submit the separately versioned goal-first v2 combined job.
# Reuses the T39 container/model env names if GFV2_* is unset.
set -euo pipefail
umask 077

GFV2_CODE_ROOT="${GFV2_CODE_ROOT:-${T39_CODE_ROOT:?set GFV2_CODE_ROOT or T39_CODE_ROOT}}"
GFV2_TRAINING_SITE_PACKAGES="${GFV2_TRAINING_SITE_PACKAGES:-${T39_TRAINING_SITE_PACKAGES:?}}"
GFV2_HF_HOME="${GFV2_HF_HOME:-${T39_HF_HOME:?}}"
GFV2_CONTAINER="${GFV2_CONTAINER:-${T39_CONTAINER:?}}"
GFV2_OUTPUT="${GFV2_OUTPUT:?set a new output directory, not a T39 path}"

if [[ -e "${GFV2_OUTPUT}" ]]; then
  echo "gf_v2_output_must_be_new:${GFV2_OUTPUT}" >&2
  exit 2
fi
mkdir -p "${GFV2_OUTPUT}" "$(dirname "${GFV2_OUTPUT}")"

export GFV2_CODE_ROOT GFV2_TRAINING_SITE_PACKAGES GFV2_HF_HOME GFV2_CONTAINER GFV2_OUTPUT
if [[ -n "${GFV2_SELECTED_ADAPTER:-${T39_SELECTED_ADAPTER:-}}" ]]; then
  export GFV2_SELECTED_ADAPTER="${GFV2_SELECTED_ADAPTER:-${T39_SELECTED_ADAPTER}}"
  export GFV2_ADAPTER_IDENTITY="${GFV2_ADAPTER_IDENTITY:-${T39_ADAPTER_IDENTITY:?}}"
  export GFV2_ADAPTER_SCALE="${GFV2_ADAPTER_SCALE:-${T39_ADAPTER_SCALE:?}}"
fi

job_id=$(sbatch --parsable --export=ALL "${GFV2_CODE_ROOT}/cluster/goal_first_v2/combined_3day.sbatch")
printf 'job_id\t%s\noutput\t%s\n' "${job_id}" "${GFV2_OUTPUT}" | tee "${GFV2_OUTPUT}/submission.tsv"
echo "submitted ${job_id}"
