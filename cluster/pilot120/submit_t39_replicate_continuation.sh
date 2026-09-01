#!/bin/bash
# Submit one fresh R3--R5 replica after a terminal predecessor evidence job.
set -euo pipefail
umask 077
: "${T39_CODE_ROOT:?}"
: "${T39_OUTPUT_ROOT:?}"
: "${T39_REPLICATE:?}"
: "${T39_AFTER_EVIDENCE_JOB:?}"
: "${T39_TRAINING_SITE_PACKAGES:?}"
: "${T39_HF_HOME:?}"
: "${T39_CONTAINER:?}"
: "${T39_SELECTED_ADAPTER:?}"
: "${T39_ADAPTER_IDENTITY:?}"
: "${T39_ADAPTER_SCALE:?}"
: "${T39_CODE_COMMIT:?}"
: "${T39_CONTAINER_SHA256:?}"
: "${T39_MODEL_SNAPSHOT:?}"

case "${T39_REPLICATE}" in R3|R4|R5) ;; *) echo "t39_continuation_replicate_must_be_R3_R4_or_R5" >&2; exit 2 ;; esac
if [[ ! "${T39_AFTER_EVIDENCE_JOB}" =~ ^[0-9]+$ ]]; then
  echo "t39_after_evidence_job_invalid" >&2
  exit 2
fi
if [[ ! -d "${T39_OUTPUT_ROOT}" || ! -f "${T39_OUTPUT_ROOT}/t39_submission_jobs.tsv" ]]; then
  echo "t39_initial_staging_manifest_missing" >&2
  exit 2
fi
if ! grep -q '"status": "T39_PROVENANCE_PREFLIGHT_PASSED"' "${T39_OUTPUT_ROOT}/t39_provenance_preflight.json"; then
  echo "t39_preflight_not_passed_for_continuation" >&2
  exit 2
fi
replicate_root="${T39_OUTPUT_ROOT}/${T39_REPLICATE}"
if [[ -e "${replicate_root}" ]]; then
  echo "t39_replicate_root_must_be_new:${replicate_root}" >&2
  exit 2
fi
if [[ ! "${T39_CODE_COMMIT}" =~ ^[0-9a-fA-F]{40}$ || ! "${T39_CONTAINER_SHA256}" =~ ^[0-9a-fA-F]{64}$ ]]; then
  echo "t39_immutable_code_or_container_hash_invalid" >&2
  exit 2
fi

policy="${T39_CODE_ROOT}/configs/evaluation/pilot120_early_analysis_policy_v1.json"
analysis_policy="${T39_CODE_ROOT}/configs/evaluation/pilot120_t39_evidence_policy_v1.json"
execution_contract="${T39_OUTPUT_ROOT}/t39_execution_contract.json"
common_export="ALL,T39_CODE_ROOT=${T39_CODE_ROOT},T39_OUTPUT_ROOT=${T39_OUTPUT_ROOT},T39_TRAINING_SITE_PACKAGES=${T39_TRAINING_SITE_PACKAGES},T39_HF_HOME=${T39_HF_HOME},T39_CONTAINER=${T39_CONTAINER},T39_CONTAINER_SHA256=${T39_CONTAINER_SHA256},T39_CODE_COMMIT=${T39_CODE_COMMIT},T39_SELECTED_ADAPTER=${T39_SELECTED_ADAPTER},T39_ADAPTER_IDENTITY=${T39_ADAPTER_IDENTITY},T39_ADAPTER_SCALE=${T39_ADAPTER_SCALE},T39_MODEL_SNAPSHOT=${T39_MODEL_SNAPSHOT},T39_EXECUTION_CONTRACT=${execution_contract},T39_EARLY_POLICY=${policy},T39_ANALYSIS_POLICY=${analysis_policy}"
submit() {
  local dependency="$1"
  local export_values="$2"
  local script_path="$3"
  sbatch --parsable --dependency="${dependency}" --export="${export_values}" "${script_path}"
}

base=$(submit "afterany:${T39_AFTER_EVIDENCE_JOB}" "${common_export},T39_REPLICATE=${T39_REPLICATE},T39_COMPONENT_OUTPUT=${replicate_root}/direct_base" "${T39_CODE_ROOT}/cluster/pilot120/t39_direct_base.sbatch")
adapter=$(submit "afterany:${base}" "${common_export},T39_REPLICATE=${T39_REPLICATE},T39_COMPONENT_OUTPUT=${replicate_root}/selected_adapter" "${T39_CODE_ROOT}/cluster/pilot120/t39_selected_adapter.sbatch")
manager=$(submit "afterany:${adapter}" "${common_export},T39_REPLICATE=${T39_REPLICATE},T39_COMPONENT_OUTPUT=${replicate_root}/manager" "${T39_CODE_ROOT}/cluster/pilot120/t39_manager_bundle.sbatch")
evidence=$(submit "afterany:${manager}" "${common_export},T39_REPLICATE=${T39_REPLICATE},T39_REPLICATE_ROOT=${replicate_root}" "${T39_CODE_ROOT}/cluster/pilot120/t39_replica_evidence.sbatch")
printf '%s-base\t%s\tafterany:%s\n%s-adapter\t%s\tafterany:%s\n%s-manager\t%s\tafterany:%s\n%s-evidence\t%s\tafterany:%s\n' \
  "${T39_REPLICATE}" "${base}" "${T39_AFTER_EVIDENCE_JOB}" \
  "${T39_REPLICATE}" "${adapter}" "${base}" \
  "${T39_REPLICATE}" "${manager}" "${adapter}" \
  "${T39_REPLICATE}" "${evidence}" "${manager}" >> "${T39_OUTPUT_ROOT}/t39_submission_jobs.tsv"
printf 'replicate=%s evidence_job=%s output_root=%s\n' "${T39_REPLICATE}" "${evidence}" "${T39_OUTPUT_ROOT}"
