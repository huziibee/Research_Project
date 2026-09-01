#!/bin/bash
# Submit the scheduler-safe first stage of the approved 72-hour T39 chain.
set -euo pipefail
umask 077
: "${T39_CODE_ROOT:?}"
: "${T39_OUTPUT_ROOT:?}"
: "${T39_TRAINING_SITE_PACKAGES:?}"
: "${T39_HF_HOME:?}"
: "${T39_CONTAINER:?}"
: "${T39_SELECTED_ADAPTER:?}"
: "${T39_ADAPTER_IDENTITY:?}"
: "${T39_ADAPTER_SCALE:?}"
: "${T39_CODE_COMMIT:?}"
: "${T39_CONTAINER_SHA256:?}"

if [[ -e "${T39_OUTPUT_ROOT}" ]]; then
  echo "t39_output_root_must_be_new:${T39_OUTPUT_ROOT}" >&2
  exit 2
fi
mkdir -p "${T39_OUTPUT_ROOT}"
if [[ ! "${T39_CODE_COMMIT}" =~ ^[0-9a-fA-F]{40}$ || ! "${T39_CONTAINER_SHA256}" =~ ^[0-9a-fA-F]{64}$ ]]; then
  echo "t39_immutable_code_or_container_hash_invalid" >&2
  exit 2
fi

policy="${T39_CODE_ROOT}/configs/evaluation/pilot120_early_analysis_policy_v1.json"
analysis_policy="${T39_CODE_ROOT}/configs/evaluation/pilot120_t39_evidence_policy_v1.json"
common_export="ALL,T39_CODE_ROOT=${T39_CODE_ROOT},T39_OUTPUT_ROOT=${T39_OUTPUT_ROOT},T39_TRAINING_SITE_PACKAGES=${T39_TRAINING_SITE_PACKAGES},T39_HF_HOME=${T39_HF_HOME},T39_CONTAINER=${T39_CONTAINER},T39_CONTAINER_SHA256=${T39_CONTAINER_SHA256},T39_CODE_COMMIT=${T39_CODE_COMMIT},T39_SELECTED_ADAPTER=${T39_SELECTED_ADAPTER},T39_ADAPTER_IDENTITY=${T39_ADAPTER_IDENTITY},T39_ADAPTER_SCALE=${T39_ADAPTER_SCALE},T39_EARLY_POLICY=${policy},T39_ANALYSIS_POLICY=${analysis_policy}"

submit() {
  local dependency="$1"
  local export_values="$2"
  local script_path="$3"
  if [[ "${dependency}" == "none" ]]; then
    sbatch --parsable --export="${export_values}" "${script_path}"
  else
    sbatch --parsable --dependency="${dependency}" --export="${export_values}" "${script_path}"
  fi
}

preflight=$(submit "none" "${common_export}" "${T39_CODE_ROOT}/cluster/pilot120/t39_provenance_preflight.sbatch")
printf 'stage\tjob_id\tdependency\npreflight\t%s\tnone\n' "${preflight}" > "${T39_OUTPUT_ROOT}/t39_submission_jobs.tsv"
t40=$(submit "afterok:${preflight}" "${common_export}" "${T39_CODE_ROOT}/cluster/pilot120/t40_interpretation_audit.sbatch")
printf 't40-interpretation-audit\t%s\tafterok:%s\n' "${t40}" "${preflight}" >> "${T39_OUTPUT_ROOT}/t39_submission_jobs.tsv"

previous="${preflight}"
# The account permits ten queued jobs. Preflight, T40, and two serial replica
# chains exactly fill that allowance. R3--R5 and the final audit are submitted
# by the guarded continuation helpers after earlier evidence jobs are terminal.
for replicate in R1 R2; do
  replicate_root="${T39_OUTPUT_ROOT}/${replicate}"
  if [[ "${previous}" == "${preflight}" ]]; then
    base_dependency="afterok:${previous}"
    prior_label="afterok"
  else
    base_dependency="afterany:${previous}"
    prior_label="afterany"
  fi
  base=$(submit "${base_dependency}" "${common_export},T39_REPLICATE=${replicate},T39_COMPONENT_OUTPUT=${replicate_root}/direct_base" "${T39_CODE_ROOT}/cluster/pilot120/t39_direct_base.sbatch")
  adapter=$(submit "afterany:${base}" "${common_export},T39_REPLICATE=${replicate},T39_COMPONENT_OUTPUT=${replicate_root}/selected_adapter" "${T39_CODE_ROOT}/cluster/pilot120/t39_selected_adapter.sbatch")
  manager=$(submit "afterany:${adapter}" "${common_export},T39_REPLICATE=${replicate},T39_COMPONENT_OUTPUT=${replicate_root}/manager" "${T39_CODE_ROOT}/cluster/pilot120/t39_manager_bundle.sbatch")
  evidence=$(submit "afterany:${manager}" "${common_export},T39_REPLICATE=${replicate},T39_REPLICATE_ROOT=${replicate_root}" "${T39_CODE_ROOT}/cluster/pilot120/t39_replica_evidence.sbatch")
  printf '%s-base\t%s\tafter%s:%s\n%s-adapter\t%s\tafterany:%s\n%s-manager\t%s\tafterany:%s\n%s-evidence\t%s\tafterany:%s\n' \
    "${replicate}" "${base}" "${prior_label#after}" "${previous}" \
    "${replicate}" "${adapter}" "${base}" \
    "${replicate}" "${manager}" "${adapter}" \
    "${replicate}" "${evidence}" "${manager}" >> "${T39_OUTPUT_ROOT}/t39_submission_jobs.tsv"
  previous="${evidence}"
done
printf 'staging-boundary\tnone\tR1-R2 only: account queue cap; R3-R5 require guarded continuation\n' >> "${T39_OUTPUT_ROOT}/t39_submission_jobs.tsv"
printf 'preflight=%s staged_replicates=R1,R2 output_root=%s\n' "${preflight}" "${T39_OUTPUT_ROOT}"
