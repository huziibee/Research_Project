#!/bin/bash
# Submit exactly one same-protocol resume for one incomplete T39 component.
set -euo pipefail
umask 077
: "${T39_CODE_ROOT:?}"
: "${T39_OUTPUT_ROOT:?}"
: "${T39_REPLICATE:?}"
: "${T39_COMPONENT:?}"
: "${T39_AFTER_JOB:?}"
: "${T39_TRAINING_SITE_PACKAGES:?}"
: "${T39_HF_HOME:?}"
: "${T39_CONTAINER:?}"
: "${T39_SELECTED_ADAPTER:?}"
: "${T39_ADAPTER_IDENTITY:?}"
: "${T39_ADAPTER_SCALE:?}"
: "${T39_CODE_COMMIT:?}"

case "${T39_REPLICATE}" in R1|R2|R3|R4|R5) ;; *) echo "invalid_replicate:${T39_REPLICATE}" >&2; exit 2 ;; esac
case "${T39_COMPONENT}" in direct_base|selected_adapter|manager) ;; *) echo "invalid_component:${T39_COMPONENT}" >&2; exit 2 ;; esac

replicate_root="${T39_OUTPUT_ROOT}/${T39_REPLICATE}"
marker="${replicate_root}/t39_same_protocol_recovery.tsv"
if [[ -e "${marker}" ]]; then
  echo "t39_recovery_already_submitted:${marker}" >&2
  exit 2
fi
mkdir -p "${replicate_root}"
container_sha256=$(sha256sum "${T39_CONTAINER}" | awk '{print $1}')
if [[ ! "${T39_CODE_COMMIT}" =~ ^[0-9a-fA-F]{40}$ || ! "${container_sha256}" =~ ^[0-9a-fA-F]{64}$ ]]; then
  echo "t39_immutable_code_or_container_hash_invalid" >&2
  exit 2
fi

policy="${T39_CODE_ROOT}/configs/evaluation/pilot120_early_analysis_policy_v1.json"
analysis_policy="${T39_CODE_ROOT}/configs/evaluation/pilot120_t39_evidence_policy_v1.json"
common_export="ALL,T39_CODE_ROOT=${T39_CODE_ROOT},T39_OUTPUT_ROOT=${T39_OUTPUT_ROOT},T39_TRAINING_SITE_PACKAGES=${T39_TRAINING_SITE_PACKAGES},T39_HF_HOME=${T39_HF_HOME},T39_CONTAINER=${T39_CONTAINER},T39_CONTAINER_SHA256=${container_sha256},T39_CODE_COMMIT=${T39_CODE_COMMIT},T39_SELECTED_ADAPTER=${T39_SELECTED_ADAPTER},T39_ADAPTER_IDENTITY=${T39_ADAPTER_IDENTITY},T39_ADAPTER_SCALE=${T39_ADAPTER_SCALE},T39_EARLY_POLICY=${policy},T39_ANALYSIS_POLICY=${analysis_policy}"
case "${T39_COMPONENT}" in
  direct_base)
    output="${replicate_root}/direct_base"
    script="${T39_CODE_ROOT}/cluster/pilot120/t39_direct_base.sbatch"
    ;;
  selected_adapter)
    output="${replicate_root}/selected_adapter"
    script="${T39_CODE_ROOT}/cluster/pilot120/t39_selected_adapter.sbatch"
    ;;
  manager)
    output="${replicate_root}/manager"
    script="${T39_CODE_ROOT}/cluster/pilot120/t39_manager_bundle.sbatch"
    ;;
esac

job=$(sbatch --parsable --dependency="afterany:${T39_AFTER_JOB}" --export="${common_export},T39_REPLICATE=${T39_REPLICATE},T39_COMPONENT_OUTPUT=${output}" "${script}")
printf 'replicate\tcomponent\tjob_id\tafter_job\n%s\t%s\t%s\t%s\n' "${T39_REPLICATE}" "${T39_COMPONENT}" "${job}" "${T39_AFTER_JOB}" > "${marker}"
printf 'recovery_job=%s marker=%s\n' "${job}" "${marker}"
