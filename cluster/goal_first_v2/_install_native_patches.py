#!/usr/bin/env python3
import shutil
from pathlib import Path

native = Path("/home-mscluster/mbangie/t12-hpc/code/followon-native-20260911")
bak = native / "scripts" / "_bak_20260912c"
bak.mkdir(parents=True, exist_ok=True)
mapping = {
    Path("/tmp/run_ambik_ambiguity_type.py"): native / "scripts" / "run_ambik_ambiguity_type.py",
    Path("/tmp/run_native_context_structured.py"): native / "scripts" / "run_native_context_structured.py",
    Path("/tmp/retry_missing_natives.sbatch"): native / "cluster" / "followon_53074" / "retry_missing_natives.sbatch",
    Path("/tmp/submit_retry_missing_natives.sh"): native / "cluster" / "followon_53074" / "submit_retry_missing_natives.sh",
}
for src, dest in mapping.items():
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.suffix == ".py":
        shutil.copy2(dest, bak / dest.name)
    shutil.copy2(src, dest)
    dest.chmod(0o755 if dest.suffix in {".sh", ".sbatch"} else 0o644)
    print("installed", dest, "bytes", dest.stat().st_size)
print("backup", bak)
