#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path

env = os.environ.copy()
env.update(
    {
        "CAP_CODE_ROOT": "/home-mscluster/mbangie/t12-hpc/code/pilot120_capability_debate-20260918",
        "CAP_OUTPUT": "/home-mscluster/mbangie/t12-hpc/results/pilot120_capability_debate-20260918",
        "CAP_PREDICTIONS": "/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915/T0.7/predictions/goal_first_manager_v2.predictions.jsonl",
        "GFV2_CONTAINER": "/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif",
        "GFV2_HF_HOME": "/home-mscluster/mbangie/t12-hpc/hf-cache",
        "GFV2_TRAINING_SITE_PACKAGES": "/home-mscluster/mbangie/t12-hpc/training-site-packages",
        "AFTERANY": "55670",
    }
)
submit = Path(env["CAP_CODE_ROOT"]) / "cluster/pilot120_capability_debate_20260918/submit.sh"
subprocess.check_call(["chmod", "+x", str(submit)])
subprocess.check_call(["bash", str(submit)], env=env)
