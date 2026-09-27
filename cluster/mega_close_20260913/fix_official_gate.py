#!/usr/bin/env python3
from pathlib import Path
import re
import shutil
import subprocess

SBATCH = Path(
    "/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913/cluster/mega_close_20260913/mega_official.sbatch"
)
INTENT = Path(
    "/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913/scripts/evaluate_pilot_120_intent_box.py"
)

text = SBATCH.read_text(encoding="utf-8")
idx = text.find("refusing_official_adapter_flip")
if idx < 0:
    raise SystemExit("refuse_string_missing")
# Expand to surrounding if/print block
start = text.rfind("\nif ", 0, idx)
if start < 0:
    start = text.rfind("if ", 0, idx)
end = text.find("\n\n", idx)
if end < 0:
    end = idx + 300
chunk = text[start:end]
print("OLD_CHUNK:\n", chunk)
repl = '''
selected = ident.get("selected_adapter", ident.get("selected_adapter"))
official = ident.get("valid_for_official_use", ident.get("valid_for_official_use"))
scale = ident.get("adapter_scale")
if selected is not True or official is not True:
    print("adapter_must_be_official_selected", selected, official, file=sys.stderr)
    raise SystemExit(2)
if scale is None:
    print("adapter_scale_missing", file=sys.stderr)
    raise SystemExit(2)
print("adapter_identity_ok selected_adapter=%s valid_for_official_use=%s adapter_scale=%s" % (
    selected, official, scale))
'''
text2 = text[:start] + repl + text[end:]
text2 = text2.replace(" \\\n    --allow-unofficial-adapter", "")
text2 = text2.replace(" --allow-unofficial-adapter", "")
SBATCH.write_text(text2, encoding="utf-8", newline="\n")
subprocess.check_call(["bash", "-n", str(SBATCH)])
assert "refusing_official_adapter_flip" not in SBATCH.read_text(encoding="utf-8")
print("sbatch_ok")

t = INTENT.read_text(encoding="utf-8")
if "--limit" not in t:
    t = t.replace(
        'parser.add_argument("--seed"',
        'parser.add_argument("--limit", type=int, default=0, help="If >0, only first N source rows.")\n'
        '    parser.add_argument("--seed"',
        1,
    )
    t = re.sub(
        r"(source_rows = [^\n]+\n)",
        r'\1    if getattr(args, "limit", 0) and args.limit > 0:\n'
        r"        source_rows = source_rows[: int(args.limit)]\n",
        t,
        count=1,
    )
    INTENT.write_text(t, encoding="utf-8", newline="\n")
    print("intent_limit_ok")
else:
    print("intent_limit_already")

for root in (
    Path("/home-mscluster/mbangie/t12-hpc/code/final_close-20260913"),
    Path("/home-mscluster/mbangie/t12-hpc/code/temp_sweep-20260913"),
):
    dst = root / "scripts" / "evaluate_pilot_120_intent_box.py"
    if dst.is_file():
        shutil.copy2(INTENT, dst)
        print("synced", dst)

print("ALL_PATCHED")
