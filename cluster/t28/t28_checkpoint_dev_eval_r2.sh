#!/bin/bash
# T28 source-dev eval RESUBMISSION (r2) - uses fixed task_constrained_decoding.py
# Run from: /home-mscluster/mbangie/t28_r5_src after confirming probe job passed.
# Uses a fresh output dir (dev_eval_task_conditioned_r2) so all 2234 calls run fresh.
# sbatch excludes mscluster106-109 (setgroups/Apptainer risk + weak nodes); prefers 110/111.
EVAL_RUN_DIR=/home-mscluster/mbangie/t12-hpc/runs/t28-full-train/t28-full-train-20260728T222000Z-r5-retry5

T28_BUNDLE_ROOT=/home-mscluster/mbangie/t28_frozen_inputs/dbba6c1bdbb796b133abc63436b4a5ca4f8e08c89e4eca1be34d8000f49bae5b/inputs \
T28_CODE_ROOT=/home-mscluster/mbangie/t28_r5_src \
T28_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-hpc/training-site-packages \
T28_HF_HOME=/home-mscluster/mbangie/t12-hpc/hf-cache \
T28_ADAPTER="${EVAL_RUN_DIR}/adapter" \
T28_EVAL_OUTPUT="${EVAL_RUN_DIR}/dev_eval_task_conditioned_r2" \
T28_CONTAINER=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif \
sbatch /home-mscluster/mbangie/t28_r5_src/cluster/t28/t28_checkpoint_dev_eval.sbatch
