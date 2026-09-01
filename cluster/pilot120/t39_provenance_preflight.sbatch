#!/bin/bash
# T39 CPU-only provenance gate. A failure prevents all GPU replay work.
#SBATCH --job-name=p120-t39-preflight
#SBATCH --partition=bigbatch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-t39-preflight-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-t39-preflight-%j.err

set -euo pipefail
umask 077
: "${T39_CODE_ROOT:?}"
: "${T39_TRAINING_SITE_PACKAGES:?}"
: "${T39_CONTAINER:?}"
: "${T39_EARLY_POLICY:?}"
: "${T39_ANALYSIS_POLICY:?}"
: "${T39_ADAPTER_IDENTITY:?}"
: "${T39_OUTPUT_ROOT:?}"
: "${T39_CODE_COMMIT:?}"
: "${T39_CONTAINER_SHA256:?}"
: "${T39_SELECTED_ADAPTER:?}"
: "${T39_ADAPTER_IDENTITY:?}"
: "${T39_MODEL_SNAPSHOT:?}"
cd "${T39_CODE_ROOT}"

failure_output="${T39_OUTPUT_ROOT}/t39_provenance_preflight_failure.json"
passed_output="${T39_OUTPUT_ROOT}/t39_provenance_preflight.json"
contract_output="${T39_OUTPUT_ROOT}/t39_execution_contract.json"
write_failure() {
  local reason="$1"
  if [[ ! -e "${passed_output}" && ! -e "${failure_output}" ]]; then
    printf '{\n  "status": "VERIFY_FAILED",\n  "stage": "t39_provenance_preflight",\n  "reason": "%s",\n  "scope": "non_protected_pilot120_v1_evidence_only",\n  "valid_for_official_use": false\n}\n' "${reason}" > "${failure_output}"
  fi
}

container_actual=$(sha256sum "${T39_CONTAINER}")
container_actual=${container_actual%% *}
if [[ "${container_actual}" != "${T39_CONTAINER_SHA256}" ]]; then
  write_failure "container_sha256_mismatch"
  echo "t39_container_sha256_mismatch" >&2
  exit 2
fi

if ! /usr/bin/apptainer exec --cleanenv \
  --env "PYTHONPATH=${T39_TRAINING_SITE_PACKAGES}:${T39_CODE_ROOT}/src" \
  "${T39_CONTAINER}" \
  python3 scripts/pilot120_t39_runtime_provenance.py \
  capture-contract \
  --root "${T39_CODE_ROOT}" \
  --container "${T39_CONTAINER}" \
  --adapter "${T39_SELECTED_ADAPTER}" \
  --adapter-identity "${T39_ADAPTER_IDENTITY}" \
  --model-snapshot "${T39_MODEL_SNAPSHOT}" \
  --code-commit "${T39_CODE_COMMIT}" \
  --expected-container-sha256 "${T39_CONTAINER_SHA256}" \
  --output "${contract_output}"; then
  write_failure "execution_contract_capture_failed"
  exit 1
fi

if ! /usr/bin/apptainer exec --cleanenv \
  --env "PYTHONPATH=${T39_TRAINING_SITE_PACKAGES}:${T39_CODE_ROOT}/src" \
  "${T39_CONTAINER}" \
  python3 scripts/pilot120_t39_evidence.py \
  --root "${T39_CODE_ROOT}" \
  --policy "${T39_EARLY_POLICY}" \
  --analysis-policy "${T39_ANALYSIS_POLICY}" \
  preflight \
  --adapter-identity "${T39_ADAPTER_IDENTITY}" \
  --code-commit "${T39_CODE_COMMIT}" \
  --container "${T39_CONTAINER}" \
  --container-sha256 "${T39_CONTAINER_SHA256}" \
  --execution-contract "${contract_output}" \
  --output "${passed_output}"; then
  write_failure "frozen_provenance_or_identity_validation_failed"
  exit 1
fi
