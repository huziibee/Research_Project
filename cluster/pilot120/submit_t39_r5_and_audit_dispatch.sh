#!/bin/bash
# Submit exactly one CPU-only controller after R3 evidence; it advances R5 and final audit without GPU inference.
set -euo pipefail
umask 077
: "${T39_INFERENCE_CODE_ROOT:?}"
: "${T39_AUDIT_CODE_ROOT:?}"
: "${T39_OUTPUT_ROOT:?}"
: "${T39_R3_EVIDENCE_JOB:?}"
: "${T39_R4_EVIDENCE_JOB:?}"
: "${T39_TRAINING_SITE_PACKAGES:?}"
: "${T39_HF_HOME:?}"
: "${T39_CONTAINER:?}"
: "${T39_CONTAINER_SHA256:?}"
: "${T39_SELECTED_ADAPTER:?}"
: "${T39_ADAPTER_IDENTITY:?}"
: "${T39_ADAPTER_SCALE:?}"
: "${T39_CODE_COMMIT:?}"
: "${T39_MODEL_SNAPSHOT:?}"

marker="${T39_OUTPUT_ROOT}/t39_r5_and_audit_dispatch_submission.tsv"
if [[ -e "${marker}" ]]; then
  echo "t39_r5_and_audit_dispatch_already_submitted" >&2
  exit 2
fi
exports="ALL,T39_INFERENCE_CODE_ROOT=${T39_INFERENCE_CODE_ROOT},T39_AUDIT_CODE_ROOT=${T39_AUDIT_CODE_ROOT},T39_OUTPUT_ROOT=${T39_OUTPUT_ROOT},T39_R4_EVIDENCE_JOB=${T39_R4_EVIDENCE_JOB},T39_TRAINING_SITE_PACKAGES=${T39_TRAINING_SITE_PACKAGES},T39_HF_HOME=${T39_HF_HOME},T39_CONTAINER=${T39_CONTAINER},T39_CONTAINER_SHA256=${T39_CONTAINER_SHA256},T39_SELECTED_ADAPTER=${T39_SELECTED_ADAPTER},T39_ADAPTER_IDENTITY=${T39_ADAPTER_IDENTITY},T39_ADAPTER_SCALE=${T39_ADAPTER_SCALE},T39_CODE_COMMIT=${T39_CODE_COMMIT},T39_MODEL_SNAPSHOT=${T39_MODEL_SNAPSHOT}"
job=$(sbatch --parsable --dependency="afterany:${T39_R3_EVIDENCE_JOB}" --export="${exports}" "${T39_AUDIT_CODE_ROOT}/cluster/pilot120/t39_r5_and_audit_dispatch.sbatch")
printf 'dispatcher_job\tr3_evidence_job\tr4_evidence_job\n%s\t%s\t%s\n' "${job}" "${T39_R3_EVIDENCE_JOB}" "${T39_R4_EVIDENCE_JOB}" > "${marker}"
printf 'dispatcher_job=%s\n' "${job}"
