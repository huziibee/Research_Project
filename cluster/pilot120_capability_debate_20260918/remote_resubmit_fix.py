#!/usr/bin/env python3
import os
import shutil
import subprocess
from pathlib import Path

CODE = Path("/home-mscluster/mbangie/t12-hpc/code/pilot120_capability_debate-20260918")
OUT = Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_capability_debate-20260918")
PACK = CODE / "cluster/pilot120_capability_debate_20260918"

# Move uploaded wrappers from /tmp if present
for name in ("capability_debate.sbatch", "submit.sh"):
    src = Path("/tmp") / name
    if src.exists():
        data = src.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        (PACK / name).write_bytes(data)
        print("installed", name)

# LF scripts already under CODE/scripts from scp
for name in [
    "lib_capability_debate_20260918.py",
    "run_capability_llm_judge_20260918.py",
    "run_ambiguity_debate_adjudicate_20260918.py",
]:
    p = CODE / "scripts" / name
    p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    print("lf", name)

judge = OUT / "capability_judge"
judge.mkdir(parents=True, exist_ok=True)
for name in ("capability_judgments.jsonl", "capability_judge_progress.json"):
    p = judge / name
    if p.exists():
        bak = judge / f"{name}.failed_56315.bak"
        if not bak.exists():
            shutil.copy2(p, bak)
        p.unlink()
        print("cleared", name)

# Verify enable_thinking in judge script
text = (CODE / "scripts/run_capability_llm_judge_20260918.py").read_text(encoding="utf-8")
assert "enable_thinking=False" in text
assert "dirname" in (PACK / "submit.sh").read_text(encoding="utf-8")
assert "--max-new-tokens 512" in (PACK / "capability_debate.sbatch").read_text(encoding="utf-8")
print("verify_ok")

env = os.environ.copy()
env.update(
    {
        "CAP_CODE_ROOT": str(CODE),
        "CAP_OUTPUT": str(OUT),
        "CAP_PREDICTIONS": "/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915/T0.7/predictions/goal_first_manager_v2.predictions.jsonl",
        "GFV2_CONTAINER": "/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif",
        "GFV2_HF_HOME": "/home-mscluster/mbangie/t12-hpc/hf-cache",
        "GFV2_TRAINING_SITE_PACKAGES": "/home-mscluster/mbangie/t12-hpc/training-site-packages",
        "AFTERANY": "none",
    }
)
subprocess.check_call(["chmod", "+x", str(PACK / "submit.sh")])
subprocess.check_call(["bash", str(PACK / "submit.sh")], env=env)
