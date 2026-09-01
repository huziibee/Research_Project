#!/bin/bash
# Submit the one final audit after all five evidence jobs have terminal states.
set -euo pipefail
umask 077
: "${T39_CODE_ROOT:?}"
: "${T39_OUTPUT_ROOT:?}"
: "${T39_TRAINING_SITE_PACKAGES:?}"
: "${T39_CONTAINER:?}"
: "${T39_EVIDENCE_JOB_IDS:?}"
T39_AUDIT_CODE_ROOT="${T39_AUDIT_CODE_ROOT:-${T39_CODE_ROOT}}"

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

select_evidence() {
  local replicate="$1"
  local replicate_root="${T39_OUTPUT_ROOT}/${replicate}"
  local marker="${replicate_root}/t39_same_protocol_recovery.tsv"
  if [[ ! -e "${marker}" ]]; then
    printf '%s/t39_evidence_atlas.json' "${replicate_root}"
    return
  fi
  local selected_root
  selected_root=$(awk -F '\t' 'NR == 2 { print $4 }' "${marker}")
  local selected_replicate
  selected_replicate=$(awk -F '\t' 'NR == 2 { print $1 }' "${marker}")
  if [[ "${selected_replicate}" != "${replicate}" || "${selected_root}" != "${replicate_root}/recovery_1" ]]; then
    echo "t39_recovery_marker_invalid:${marker}" >&2
    exit 2
  fi
  printf '%s/t39_evidence_atlas.json' "${selected_root}"
}

r1_evidence=$(select_evidence R1)
r2_evidence=$(select_evidence R2)
r3_evidence=$(select_evidence R3)
r4_evidence=$(select_evidence R4)
r5_evidence=$(select_evidence R5)
dependency=$(IFS=:; printf '%s' "${evidence_jobs[*]}")
export_values="ALL,T39_CODE_ROOT=${T39_CODE_ROOT},T39_AUDIT_CODE_ROOT=${T39_AUDIT_CODE_ROOT},T39_OUTPUT_ROOT=${T39_OUTPUT_ROOT},T39_TRAINING_SITE_PACKAGES=${T39_TRAINING_SITE_PACKAGES},T39_CONTAINER=${T39_CONTAINER},T39_R1_EVIDENCE=${r1_evidence},T39_R2_EVIDENCE=${r2_evidence},T39_R3_EVIDENCE=${r3_evidence},T39_R4_EVIDENCE=${r4_evidence},T39_R5_EVIDENCE=${r5_evidence}"
audit=$(sbatch --parsable --dependency="afterany:${dependency}" --export="${export_values}" "${T39_AUDIT_CODE_ROOT}/cluster/pilot120/t39_reproducibility_audit.sbatch")
printf 'reproducibility-audit\t%s\tafterany:%s\n' "${audit}" "${dependency}" >> "${T39_OUTPUT_ROOT}/t39_submission_jobs.tsv"
printf 'audit_job\toutput_root\tr1_evidence\tr2_evidence\tr3_evidence\tr4_evidence\tr5_evidence\n%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
  "${audit}" "${T39_OUTPUT_ROOT}" "${r1_evidence}" "${r2_evidence}" "${r3_evidence}" "${r4_evidence}" "${r5_evidence}" > "${T39_OUTPUT_ROOT}/t39_reproducibility_audit_submission.tsv"
