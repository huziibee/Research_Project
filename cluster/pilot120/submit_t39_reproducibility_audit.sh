#!/bin/bash
# Submit the one final audit after all five evidence jobs have terminal states.
set -euo pipefail
umask 077
: "${T39_CODE_ROOT:?}"
: "${T39_OUTPUT_ROOT:?}"
: "${T39_TRAINING_SITE_PACKAGES:?}"
: "${T39_CONTAINER:?}"
: "${T39_EVIDENCE_JOB_IDS:?}"

if [[ ! -d "${T39_OUTPUT_ROOT}" || ! -f "${T39_OUTPUT_ROOT}/t39_submission_jobs.tsv" ]]; then
  echo "t39_initial_staging_manifest_missing" >&2
  exit 2
fi
if [[ -e "${T39_OUTPUT_ROOT}/t39_reproducibility_audit_submission.tsv" ]]; then
  echo "t39_reproducibility_audit_already_submitted" >&2
  exit 2
fi
IFS=: read -r -a evidence_jobs <<< "${T39_EVIDENCE_JOB_IDS}"
if [[ "${#evidence_jobs[@]}" -ne 5 ]]; then
  echo "t39_requires_exactly_five_evidence_job_ids" >&2
  exit 2
fi
for job in "${evidence_jobs[@]}"; do
  if [[ ! "${job}" =~ ^[0-9]+$ ]]; then
    echo "t39_evidence_job_id_invalid:${job}" >&2
    exit 2
  fi
done
if ! grep -q '"status": "T39_PROVENANCE_PREFLIGHT_PASSED"' "${T39_OUTPUT_ROOT}/t39_provenance_preflight.json"; then
  echo "t39_preflight_not_passed_for_final_audit" >&2
  exit 2
fi

dependency=$(IFS=:; printf '%s' "${evidence_jobs[*]}")
export_values="ALL,T39_CODE_ROOT=${T39_CODE_ROOT},T39_OUTPUT_ROOT=${T39_OUTPUT_ROOT},T39_TRAINING_SITE_PACKAGES=${T39_TRAINING_SITE_PACKAGES},T39_CONTAINER=${T39_CONTAINER}"
audit=$(sbatch --parsable --dependency="afterany:${dependency}" --export="${export_values}" "${T39_CODE_ROOT}/cluster/pilot120/t39_reproducibility_audit.sbatch")
printf 'reproducibility-audit\t%s\tafterany:%s\n' "${audit}" "${dependency}" >> "${T39_OUTPUT_ROOT}/t39_submission_jobs.tsv"
printf 'audit_job=%s output_root=%s\n' "${audit}" "${T39_OUTPUT_ROOT}" > "${T39_OUTPUT_ROOT}/t39_reproducibility_audit_submission.tsv"
