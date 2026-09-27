#!/usr/bin/env python3
"""Install debate-fix scripts and submit GPU repair job."""
import os
import subprocess
from pathlib import Path

CODE = Path("/home-mscluster/mbangie/t12-hpc/code/pilot120_capability_debate-20260918")
OUT = Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_capability_debate-20260918")
PACK = CODE / "cluster/pilot120_capability_debate_20260918"

for name in (
    "lib_capability_debate_20260918.py",
    "reparse_ambiguity_debate_20260918.py",
    "repair_ambiguity_debate_ids_20260918.py",
    "run_ambiguity_debate_adjudicate_20260918.py",
):
    src = Path("/tmp") / name
    if src.exists():
        data = src.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        (CODE / "scripts" / name).write_bytes(data)
        print("installed", name)

for name in ("debate_fix.sbatch",):
    src = Path("/tmp") / name
    data = src.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    (PACK / name).write_bytes(data)
    print("installed", name)

env = os.environ.copy()
env.update(
    {
        "CAP_CODE_ROOT": str(CODE),
        "CAP_OUTPUT": str(OUT),
        "CAP_PREDICTIONS": "/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915/T0.7/predictions/goal_first_manager_v2.predictions.jsonl",
        "GFV2_CONTAINER": "/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif",
        "GFV2_HF_HOME": "/home-mscluster/mbangie/t12-hpc/hf-cache",
        "GFV2_TRAINING_SITE_PACKAGES": "/home-mscluster/mbangie/t12-hpc/training-site-packages",
    }
)
jid = subprocess.check_output(
    ["sbatch", "--parsable", "--export=ALL", str(PACK / "debate_fix.sbatch")],
    env=env,
    text=True,
).strip()
print(f"submitted_debate_fix {jid}")
(OUT / "debate_fix_submission.tsv").write_text(
    f"debate_fix\t{jid}\tout\t{OUT}\n", encoding="utf-8"
)
subprocess.check_call(["squeue", "-u", "mbangie"])
