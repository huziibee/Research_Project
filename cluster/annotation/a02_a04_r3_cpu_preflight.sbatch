#!/usr/bin/env bash
#SBATCH --job-name=a02-a04-r3-cpu-preflight
#SBATCH --partition=batch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=%x-%j.out
#SBATCH --error=%x-%j.err
set -Eeuo pipefail
ROOT="${SLURM_SUBMIT_DIR:?}"
OUT="${ROOT}/data/dual_llm_benchmark_v1/runs/r3-cpu-preflight-${SLURM_JOB_ID:-local}"
mkdir -p "$OUT"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
apptainer exec --cleanenv --env HF_HUB_OFFLINE=1,TRANSFORMERS_OFFLINE=1,HF_DATASETS_OFFLINE=1,HF_HUB_DISABLE_TELEMETRY=1 "${A01_CONTAINER_SIF:?}" python3 scripts/annotation/r3_cpu_preflight.py --output "$OUT/preflight.json" --gemma /home-mscluster/mbangie/models/dual_llm_benchmark_v1/gemma-4-26b-a4b-it --glm /home-mscluster/mbangie/models/dual_llm_benchmark_v1/glm-4.7-flash-bf16 --schema schemas/annotation/model_annotation.schema.json
