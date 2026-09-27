#!/usr/bin/env bash
# Repair failed rows on Qwen3-1.7B Pilot-120 latency emit @ T0.7.
# Pass 1: same thinking-on path as main emit.
# Pass 2: --constrained-only for hard IDs (proven on 8B repairs).
#SBATCH --job-name=p120-lat-1p7b-fix
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=0-06:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-lat-1p7b-fix-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-lat-1p7b-fix-%j.err

set -euo pipefail
umask 077

: "${LAT_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/pilot120_latency_1p7b-20260918}"
: "${LAT_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/pilot120_latency_1p7b-20260918}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"
: "${LAT_MODEL:=Qwen/Qwen3-1.7B}"
: "${LAT_TEMPERATURE:=0.7}"

CODE="${LAT_CODE_ROOT}"
OUT="${LAT_OUTPUT}"
TDIR="${OUT}/T${LAT_TEMPERATURE}"
MODEL="${LAT_MODEL}"
TEMP="${LAT_TEMPERATURE}"

mkdir -p /home-mscluster/mbangie/t12-hpc/logs "${TDIR}/scores"
cd "${CODE}"

GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
GPU_USED="${GPU_USED%% *}"
if [[ "${GPU_USED}" -gt 1000 ]]; then
  echo "busy_gpu:${GPU_USED}" >&2
  exit 42
fi

ENV_CSV="PYTHONPATH=${CODE}/src:${CODE}/scripts:${GFV2_TRAINING_SITE_PACKAGES},HF_HOME=${GFV2_HF_HOME},HOME=${HOME},PATH=/usr/local/bin:/usr/bin:/bin,HF_HUB_ENABLE_HF_TRANSFER=1"

qwen() {
  /usr/bin/apptainer exec --nv --cleanenv --env "${ENV_CSV}" \
    --bind "${CODE}:${CODE}" \
    --bind "${OUT}:${OUT}" \
    --bind "${GFV2_HF_HOME}:${GFV2_HF_HOME}" \
    --bind "${GFV2_TRAINING_SITE_PACKAGES}:${GFV2_TRAINING_SITE_PACKAGES}" \
    "${GFV2_CONTAINER}" \
    python3 "$@"
}

count_failed() {
  python3 - <<'PY'
import json
from pathlib import Path
import os
tdir = Path(os.environ["TDIR"])
total = 0
for p in sorted((tdir / "predictions").glob("*.predictions.jsonl")):
    n = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line).get("failed"):
            n += 1
    print(f"{p.name}\t{n}")
    total += n
print(f"TOTAL_FAILED_ROWS\t{total}")
PY
}

export TDIR
echo "=== BEFORE REPAIR ==="
count_failed

echo "=== PASS1 repair-failed thinking-on model=${MODEL} temp=${TEMP} ==="
qwen scripts/evaluate_goal_first_manager_v2.py \
  --root "${CODE}" \
  --output-dir "${TDIR}" \
  --base-model "${MODEL}" \
  --allow-hf-download \
  --temperature "${TEMP}" \
  --seed 0 \
  --repair-failed || true

echo "=== AFTER PASS1 ==="
count_failed

echo "=== PASS2 repair-failed constrained-only ==="
qwen scripts/evaluate_goal_first_manager_v2.py \
  --root "${CODE}" \
  --output-dir "${TDIR}" \
  --base-model "${MODEL}" \
  --allow-hf-download \
  --temperature "${TEMP}" \
  --seed 0 \
  --repair-failed \
  --constrained-only || true

echo "=== AFTER PASS2 ==="
count_failed

python3 - <<'PY'
import json, statistics, os
from pathlib import Path
tdir = Path(os.environ["TDIR"])
pred = tdir / "predictions" / "goal_first_manager_v2.predictions.jsonl"
rows = [json.loads(l) for l in pred.read_text(encoding="utf-8").splitlines() if l.strip()]
lats = [float(r["latency_ms"]) for r in rows if r.get("latency_ms") is not None]
summary = {
    "n_rows": len(rows),
    "model": "Qwen/Qwen3-1.7B",
    "temperature": 0.7,
    "latency_ms_mean": (sum(lats)/len(lats) if lats else None),
    "latency_s_mean": ((sum(lats)/len(lats))/1000.0 if lats else None),
    "latency_ms_median": (statistics.median(lats) if lats else None),
    "failed": sum(1 for r in rows if r.get("failed")),
    "ok": sum(1 for r in rows if not r.get("failed")),
    "repaired_job": True,
}
out = tdir / "scores" / "latency_summary.json"
out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
PY

echo LATENCY_1P7B_REPAIR_DONE
