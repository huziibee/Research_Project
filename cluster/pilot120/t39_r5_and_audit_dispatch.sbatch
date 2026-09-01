#!/bin/bash
# CPU-only continuation controller: R5 after R3 evidence, then final audit after R4 evidence.
# It never runs inference or edits predictions; all substantive jobs retain their own afterany gates.
#SBATCH --job-name=p120-t39-r5-audit-dispatch
#SBATCH --partition=bigbatch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=14:00:00
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-t39-r5-audit-dispatch-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-t39-r5-audit-dispatch-%j.err

set -euo pipefail
umask 077
: "${T39_INFERENCE_CODE_ROOT:?}"
: "${T39_AUDIT_CODE_ROOT:?}"
: "${T39_ORCHESTRATION_CODE_ROOT:?}"
: "${T39_OUTPUT_ROOT:?}"
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

result="${T39_OUTPUT_ROOT}/t39_r5_and_audit_dispatch.tsv"
if [[ -e "${result}" ]]; then
  echo "t39_r5_and_audit_dispatch_result_exists" >&2
  exit 2
fi
if [[ ! -f "${T39_OUTPUT_ROOT}/t39_submission_jobs.tsv" ]]; then
  echo "t39_submission_manifest_missing" >&2
  exit 2
fi

r5_submission=$(env \
  T39_CODE_ROOT="${T39_INFERENCE_CODE_ROOT}" T39_OUTPUT_ROOT="${T39_OUTPUT_ROOT}" \
  T39_REPLICATE=R5 T39_AFTER_EVIDENCE_JOB="${T39_R4_EVIDENCE_JOB}" \
  T39_TRAINING_SITE_PACKAGES="${T39_TRAINING_SITE_PACKAGES}" T39_HF_HOME="${T39_HF_HOME}" \
  T39_CONTAINER="${T39_CONTAINER}" T39_CONTAINER_SHA256="${T39_CONTAINER_SHA256}" \
  T39_SELECTED_ADAPTER="${T39_SELECTED_ADAPTER}" T39_ADAPTER_IDENTITY="${T39_ADAPTER_IDENTITY}" \
  T39_ADAPTER_SCALE="${T39_ADAPTER_SCALE}" T39_CODE_COMMIT="${T39_CODE_COMMIT}" \
  T39_MODEL_SNAPSHOT="${T39_MODEL_SNAPSHOT}" \
  bash "${T39_INFERENCE_CODE_ROOT}/cluster/pilot120/submit_t39_replicate_continuation.sh")
r5_evidence=$(awk -F '\t' '$1 == "R5-evidence" { print $2 }' "${T39_OUTPUT_ROOT}/t39_submission_jobs.tsv")
if [[ ! "${r5_evidence}" =~ ^[0-9]+$ ]]; then
  echo "t39_r5_evidence_job_missing_after_submission" >&2
  exit 2
fi

while squeue --noheader --jobs="${T39_R4_EVIDENCE_JOB}" | grep -q .; do
  sleep 60
done

audit_submission=$(env \
  T39_CODE_ROOT="${T39_INFERENCE_CODE_ROOT}" T39_AUDIT_CODE_ROOT="${T39_AUDIT_CODE_ROOT}" \
  T39_OUTPUT_ROOT="${T39_OUTPUT_ROOT}" T39_TRAINING_SITE_PACKAGES="${T39_TRAINING_SITE_PACKAGES}" \
  T39_CONTAINER="${T39_CONTAINER}" \
  T39_EVIDENCE_JOB_IDS="48626:48631:48696:${T39_R4_EVIDENCE_JOB}:${r5_evidence}" \
  bash "${T39_ORCHESTRATION_CODE_ROOT}/cluster/pilot120/submit_t39_reproducibility_audit.sh")

temporary="${result}.tmp"
printf 'artifact\tvalue\nr5_submission\t%s\nr5_evidence_job\t%s\naudit_submission\t%s\n' \
  "${r5_submission}" "${r5_evidence}" "${audit_submission}" > "${temporary}"
mv "${temporary}" "${result}"
