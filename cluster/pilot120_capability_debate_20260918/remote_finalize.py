#!/usr/bin/env python3
from pathlib import Path

base = Path("/home-mscluster/mbangie/t12-hpc/code/pilot120_capability_debate-20260918")
# LF-normalize new scripts only
for name in [
    "lib_capability_debate_20260918.py",
    "run_capability_llm_judge_20260918.py",
    "reroute_patched_capability_20260918.py",
    "run_ambiguity_debate_adjudicate_20260918.py",
]:
    p = base / "scripts" / name
    p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    print("lf", name)

# rewrite shells
import runpy
runpy.run_path("/tmp/rewrite_cap_debate_shells.py")

submit = (base / "cluster/pilot120_capability_debate_20260918/submit.sh").read_text(encoding="utf-8")
assert "dirname" in submit
assert "afterany" in submit
assert "#!/usr/bin/env bash" in submit
print("verify_ok")
