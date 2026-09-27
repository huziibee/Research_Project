#!/usr/bin/env bash
# Versioned answered/seed-0 technical sensitivity rerun: three failed steps.
# Original recovery outputs are read-only. No control or seed-1 GPU work.
#SBATCH --job-name=p120-rec-tech-v1
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=0-16:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109,mscluster111
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-rec-tech-v1-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-rec-tech-v1-%j.err

set -euo pipefail
umask 077
: "${REC_TECH_CODE:?}"
: "${REC_TECH_ORIGINAL_EXP:?}"
: "${REC_TECH_OUT:?}"
: "${GFV2_CONTAINER:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"

test -d "${REC_TECH_ORIGINAL_EXP}"
test -f "${REC_TECH_CODE}/scripts/recovery_technical_rerun_v1.py"
test -f "${REC_TECH_CODE}/pyproject.toml"
test -f "${REC_TECH_CODE}/configs/annotation/route_precedence_v1.json"
test -f "${REC_TECH_CODE}/configs/model/t27c_constrained_decoding_v1.json"
test -f "${GFV2_CONTAINER}"
test -d "${GFV2_HF_HOME}"
test -d "${GFV2_TRAINING_SITE_PACKAGES}"
if [[ -e "${REC_TECH_OUT}" ]] && [[ -n "$(find "${REC_TECH_OUT}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "versioned_output_nonempty:${REC_TECH_OUT}" >&2
  exit 3
fi
mkdir -p "${REC_TECH_OUT}"
cd "${REC_TECH_CODE}"

ENV_CSV="PYTHONPATH=${GFV2_TRAINING_SITE_PACKAGES}:${REC_TECH_CODE}/src:${REC_TECH_CODE}/scripts,HF_HOME=${GFV2_HF_HOME},T12_TRAINING_SITE_PACKAGES=${GFV2_TRAINING_SITE_PACKAGES},HOME=${HOME},PATH=/usr/local/bin:/usr/bin:/bin"
qwen() {
  /usr/bin/apptainer exec --nv --cleanenv --env "${ENV_CSV}" \
    --bind "${REC_TECH_CODE}:${REC_TECH_CODE}" \
    --bind "${REC_TECH_ORIGINAL_EXP}:${REC_TECH_ORIGINAL_EXP}:ro" \
    --bind "${REC_TECH_OUT}:${REC_TECH_OUT}" \
    --bind "${GFV2_HF_HOME}:${GFV2_HF_HOME}" \
    --bind "${GFV2_TRAINING_SITE_PACKAGES}:${GFV2_TRAINING_SITE_PACKAGES}" \
    "${GFV2_CONTAINER}" python3 "$@"
}

echo '=== FROZEN ORIGINAL PREFLIGHT ==='
qwen scripts/recovery_technical_rerun_v1.py \
  --original-exp "${REC_TECH_ORIGINAL_EXP}" --out "${REC_TECH_OUT}"
echo '=== ROUTER AND CONSTRAINT CONFIG PREFLIGHT ==='
qwen - <<'PY'
from ambiguity_manager.systems.manager import GoalFirstManagerV2
from ambiguity_manager.model.task_constrained_decoding import load_constraint_config
GoalFirstManagerV2()
load_constraint_config()
print('ROUTER_CONFIG_OK', flush=True)
PY
echo '=== GPU PREFLIGHT ==='
qwen - <<'PY'
import torch
print("cuda_available", torch.cuda.is_available())
print("device_count", torch.cuda.device_count())
if not torch.cuda.is_available():
    raise SystemExit("cuda_preflight_failed")
PY
echo '=== THREE FAILED ANSWERED STEPS ONLY ==='
qwen scripts/recovery_technical_rerun_v1.py \
  --original-exp "${REC_TECH_ORIGINAL_EXP}" --out "${REC_TECH_OUT}" --run
echo '=== OUTPUT HASHES ==='
sha256sum "${REC_TECH_OUT}/answered_failed_step_reruns.jsonl" \
  "${REC_TECH_OUT}/technical_rerun_report.json" \
  "${REC_TECH_OUT}/original_failed_rows.jsonl" \
  > "${REC_TECH_OUT}/SHA256_FINAL.txt"
cat "${REC_TECH_OUT}/SHA256_FINAL.txt"
echo TECHNICAL_RERUN_JOB_DONE
