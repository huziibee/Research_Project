#!/usr/bin/env python3
from pathlib import Path
import re

PATHS = [
    Path("/home-mscluster/mbangie/t12-hpc/code/final_close-20260913/scripts/evaluate_pilot_120_direct_base.py"),
    Path("/home-mscluster/mbangie/t12-hpc/code/temp_sweep-20260913/scripts/evaluate_pilot_120_direct_base.py"),
    Path("/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913/scripts/evaluate_pilot_120_direct_base.py"),
    Path("/home-mscluster/mbangie/t12-hpc/code/final_close-20260913/scripts/evaluate_goal_first_manager_v2.py"),
    Path("/home-mscluster/mbangie/t12-hpc/code/temp_sweep-20260913/scripts/evaluate_goal_first_manager_v2.py"),
    Path("/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913/scripts/evaluate_goal_first_manager_v2.py"),
    Path("/home-mscluster/mbangie/t12-hpc/code/final_close-20260913/scripts/evaluate_pilot_120_manager_systems.py"),
    Path("/home-mscluster/mbangie/t12-hpc/code/temp_sweep-20260913/scripts/evaluate_pilot_120_manager_systems.py"),
    Path("/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913/scripts/evaluate_pilot_120_manager_systems.py"),
]

PAT = re.compile(
    r"adapter_scale=float\(args\.adapter_scale,\s*"
    r"allow_unofficial=bool\(getattr\(args,\s*['\"]allow_unofficial_adapter['\"],\s*False\)\)\)"
)
REPL = (
    'adapter_scale=float(args.adapter_scale), '
    'allow_unofficial=bool(getattr(args, "allow_unofficial_adapter", False)))'
)

for path in PATHS:
    if not path.is_file():
        print("missing", path)
        continue
    text = path.read_text(encoding="utf-8")
    text2, n = PAT.subn(REPL, text)
    # also fix if missing final closing paren on selected_adapter_identity call
    text2, n2 = re.subn(
        r"(selected_adapter_identity\([^\n]*allow_unofficial=bool\(getattr\(args, [\"']allow_unofficial_adapter[\"'], False\)\))\s*$",
        r"\1)",
        text2,
        flags=re.M,
    )
    if text2 != text:
        path.write_text(text2, encoding="utf-8", newline="\n")
        print("fixed", path, "n=", n, "n2=", n2)
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "selected_adapter_identity(" in line:
            print("CALL", path.name, i, line.strip())
