#!/usr/bin/env bash
# CPU-salvage a follow-on replica manager dir (R2/R3) if failed rows appear.
set -euo pipefail
: "${GFV2_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911}"
: "${FOLLOWON_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b}"
REP="${1:?usage: _salvage_followon_replica.sh R2|R3}"
MANAGER="${FOLLOWON_OUTPUT}/${REP}/manager"
test -d "${MANAGER}/predictions"
cd "${GFV2_CODE_ROOT}"
export PYTHONPATH="${GFV2_CODE_ROOT}/src:${GFV2_CODE_ROOT}/scripts:${PYTHONPATH:-}"
python3 scripts/cpu_salvage_goal_first_v2_failed_20260912.py \
  --root "${GFV2_CODE_ROOT}" \
  --manager-dir "${MANAGER}"
