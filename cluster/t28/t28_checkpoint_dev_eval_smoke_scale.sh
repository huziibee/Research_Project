#!/bin/bash
# Subset smoke: ambiguity collapse check with attenuated LoRA scale.
# Fresh output dir; does not touch dev_eval_task_conditioned_r2.
# Evidence: scale=0.35 still adapter True=0; scale=0.10 recovered 21/48 True cases.
# Prefer mscluster111 when idle; exclude 106-109 only (no hard pin).
set -euo pipefail
EVAL_RUN_DIR=/home-mscluster/mbangie/t12-hpc/runs/t28-full-train/t28-full-train-20260728T222000Z-r5-retry5
CODE_ROOT=/home-mscluster/mbangie/t28_r5_src
CALL_IDS="${CODE_ROOT}/cluster/t28/smoke_ambiguity_call_ids_64.txt"
SCALE="${1:-0.10}"
OUT_DIR="${EVAL_RUN_DIR}/dev_eval_smoke_adapter_scale$(echo "$SCALE" | tr -d '.')_r1"

T28_BUNDLE_ROOT=/home-mscluster/mbangie/t28_frozen_inputs/dbba6c1bdbb796b133abc63436b4a5ca4f8e08c89e4eca1be34d8000f49bae5b/inputs \
T28_CODE_ROOT="${CODE_ROOT}" \
T28_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-hpc/training-site-packages \
T28_HF_HOME=/home-mscluster/mbangie/t12-hpc/hf-cache \
T28_ADAPTER="${EVAL_RUN_DIR}/adapter" \
T28_EVAL_OUTPUT="${OUT_DIR}" \
T28_CONTAINER=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif \
T28_EVAL_EXTRA_ARGS="--task-ids predict_ambiguity_v1 --call-ids-file ${CALL_IDS} --adapter-scale ${SCALE}" \
sbatch --job-name=t28-smoke-scale --time=02:00:00 "${CODE_ROOT}/cluster/t28/t28_checkpoint_dev_eval.sbatch"
