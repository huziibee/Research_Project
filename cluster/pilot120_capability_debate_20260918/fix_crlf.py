#!/usr/bin/env python3
from pathlib import Path

roots = [
    Path("/home-mscluster/mbangie/t12-hpc/code/pilot120_capability_debate-20260918/cluster/pilot120_capability_debate_20260918"),
    Path("/home-mscluster/mbangie/t12-hpc/code/pilot120_capability_debate-20260918/scripts"),
]
patterns = ("*.sh", "*.sbatch", "*.py")
for root in roots:
    if not root.exists():
        continue
    for pattern in patterns:
        for path in root.glob(pattern):
            data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            path.write_bytes(data)
            print(f"fixed {path}")
