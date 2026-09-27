#!/usr/bin/env bash
# Exploratory text-only Figure 6 flow; no frozen evidence is modified.
#SBATCH --job-name=p120-fig6-v1
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=2-12:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109,mscluster111
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-fig6-v1-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-fig6-v1-%j.err

set -euo pipefail
umask 077
: "${FIG6_CODE:?}"
: "${FIG6_OUT:?}"
: "${GFV2_CONTAINER:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"

test -f "${FIG6_CODE}/pyproject.toml"
test -f "${FIG6_CODE}/scripts/run_fig6_flow_v1.py"
test -f "${FIG6_CODE}/scripts/score_fig6_flow_v1.py"
test -f "${FIG6_CODE}/src/ambiguity_manager/systems/fig6_flow_v1.py"
test -f "${FIG6_CODE}/data/annotations/pilot_120_v1/source_canonical.jsonl"
test -f "${FIG6_CODE}/data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl"
test -f "${FIG6_CODE}/data/annotations/pilot_120_v1/pilot_120_gold_cpc_official.jsonl"
test -f "${FIG6_CODE}/data/annotations/pilot_120_v1/pilot_120_gold_risk_official.jsonl"
test -f "${GFV2_CONTAINER}"
test -d "${GFV2_HF_HOME}"
test -d "${GFV2_TRAINING_SITE_PACKAGES}"

mkdir -p "${FIG6_OUT}"
cd "${FIG6_CODE}"
export PYTHONPATH="${FIG6_CODE}/src:${FIG6_CODE}/scripts"
echo '=== FROZEN INPUT AND SCHEMA PREFLIGHT ==='
python3 scripts/run_fig6_flow_v1.py --out "${FIG6_OUT}"

ENV_CSV="PYTHONPATH=${GFV2_TRAINING_SITE_PACKAGES}:${FIG6_CODE}/src:${FIG6_CODE}/scripts,HF_HOME=${GFV2_HF_HOME},T12_TRAINING_SITE_PACKAGES=${GFV2_TRAINING_SITE_PACKAGES},HOME=${HOME},PATH=/usr/local/bin:/usr/bin:/bin"
qwen() {
  /usr/bin/apptainer exec --nv --cleanenv --env "${ENV_CSV}" \
    --bind "${FIG6_CODE}:${FIG6_CODE}:ro" \
    --bind "${FIG6_OUT}:${FIG6_OUT}" \
    --bind "${GFV2_HF_HOME}:${GFV2_HF_HOME}" \
    --bind "${GFV2_TRAINING_SITE_PACKAGES}:${GFV2_TRAINING_SITE_PACKAGES}" \
    "${GFV2_CONTAINER}" python3 "$@"
}

echo '=== GPU PREFLIGHT ==='
qwen - <<'PY'
import torch
from ambiguity_manager.model.task_constrained_decoding import compile_task_constraint
from run_fig6_flow_v1 import SCHEMA
compile_task_constraint(SCHEMA)
print('schema_constraint_ok', flush=True)
print('cuda_available', torch.cuda.is_available(), flush=True)
if not torch.cuda.is_available():
    raise SystemExit('cuda_preflight_failed')
PY

echo '=== FRESH FIGURE 6 EMIT ==='
if [[ "${FIG6_SMOKE_ONLY:-0}" == "1" || "${FIG6_SMOKE_THEN_FULL:-0}" == "1" ]]; then
  smoke_out="${FIG6_OUT}"
  if [[ "${FIG6_SMOKE_THEN_FULL:-0}" == "1" ]]; then
    smoke_out="${FIG6_OUT}/smoke"
    mkdir -p "${smoke_out}"
  fi
  qwen scripts/run_fig6_flow_v1.py --out "${smoke_out}" --run \
    --record-id CA-0007 --record-id CA-0702 --record-id CA-0808
  python3 - "${smoke_out}/predictions.jsonl" <<'PY'
import json
import pathlib
import sys
rows = [json.loads(line) for line in pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').splitlines()]
expected = {'CA-0007', 'CA-0702', 'CA-0808'}
if len(rows) != 3 or {row['record_id'] for row in rows} != expected or any(row['failed'] for row in rows):
    raise SystemExit('FIG6_SMOKE_FAILED')
print('FIG6_SMOKE_OK n=3', flush=True)
PY
  sha256sum "${smoke_out}/predictions.jsonl" > "${smoke_out}/SHA256_FINAL.txt"
  echo FIG6_FLOW_V1_SMOKE_DONE
  if [[ "${FIG6_SMOKE_ONLY:-0}" == "1" ]]; then
    exit 0
  fi
fi
qwen scripts/run_fig6_flow_v1.py --out "${FIG6_OUT}" --run
echo '=== EXPLORATORY FROZEN-GOLD SCORE ==='
python3 scripts/score_fig6_flow_v1.py \
  --pred "${FIG6_OUT}/predictions.jsonl" \
  --out "${FIG6_OUT}/score.json"
sha256sum "${FIG6_OUT}/predictions.jsonl" "${FIG6_OUT}/score.json" \
  > "${FIG6_OUT}/SHA256_FINAL.txt"
cat "${FIG6_OUT}/SHA256_FINAL.txt"
echo FIG6_FLOW_V1_JOB_DONE
