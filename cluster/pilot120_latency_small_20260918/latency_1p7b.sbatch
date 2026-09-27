#!/usr/bin/env bash
# Pilot-120 latency ablation: Qwen3-1.7B @ T=0.7 (tiny but still usable).
# Rationale: 0.6B is usually too weak for structured JSON; 4B is only a half-step
# from 8B. 1.7B is the speed/quality sweet spot in the same family as the 8B baseline.
#SBATCH --job-name=p120-lat-1p7b
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=0-12:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-lat-1p7b-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-lat-1p7b-%j.err

set -euo pipefail
umask 077

: "${LAT_CODE_ROOT:?}"
: "${LAT_OUTPUT:?}"
: "${GFV2_CONTAINER:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"

CODE="${LAT_CODE_ROOT}"
OUT="${LAT_OUTPUT}"
MODEL="${LAT_MODEL:-Qwen/Qwen3-1.7B}"
REV="${LAT_REVISION:-}"
LIMIT="${LAT_LIMIT:-0}"
TEMP="${LAT_TEMPERATURE:-0.7}"
ALLOW_DL="${LAT_ALLOW_HF_DOWNLOAD:-1}"
CONSTRAINED="${LAT_CONSTRAINED_ONLY:-0}"

mkdir -p "${OUT}" /home-mscluster/mbangie/t12-hpc/logs
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

TDIR="${OUT}/T${TEMP}"
export TDIR
mkdir -p "${TDIR}/predictions" "${TDIR}/scores"

EXTRA=(--base-model "${MODEL}" --temperature "${TEMP}" --seed 0)
if [[ -n "${REV}" ]]; then
  EXTRA+=(--base-revision "${REV}")
fi
if [[ "${ALLOW_DL}" == "1" ]]; then
  EXTRA+=(--allow-hf-download)
fi
if [[ "${LIMIT}" != "0" ]]; then
  EXTRA+=(--limit "${LIMIT}")
fi
if [[ "${CONSTRAINED}" == "1" ]]; then
  EXTRA+=(--constrained-only)
fi

echo "=== LATENCY ABLATION model=${MODEL} temp=${TEMP} limit=${LIMIT} constrained_only=${CONSTRAINED} ==="
qwen scripts/evaluate_goal_first_manager_v2.py \
  --root "${CODE}" \
  --output-dir "${TDIR}" \
  "${EXTRA[@]}"

python3 - <<'PY'
import json, statistics
from pathlib import Path
import os
tdir = Path(os.environ["TDIR"])
pred = tdir / "predictions" / "goal_first_manager_v2.predictions.jsonl"
lats = []
rows = []
for line in pred.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    row = json.loads(line)
    rows.append(row)
    if row.get("latency_ms") is not None:
        lats.append(float(row["latency_ms"]))
summary = {
    "n_rows": len(rows),
    "model": "Qwen/Qwen3-1.7B",
    "temperature": 0.7,
    "latency_ms_mean": (sum(lats)/len(lats) if lats else None),
    "latency_s_mean": ((sum(lats)/len(lats))/1000.0 if lats else None),
    "latency_ms_median": (statistics.median(lats) if lats else None),
    "model_id_sample": (rows[0].get("model_id") if rows else None),
    "failed": sum(1 for r in rows if r.get("failed")),
}
out = tdir / "scores" / "latency_summary.json"
out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
PY

echo LATENCY_ABLATION_DONE
