#!/usr/bin/env python3
from pathlib import Path
import subprocess

p = Path(
    "/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913/cluster/mega_close_20260913/mega_official.sbatch"
)
text = p.read_text(encoding="utf-8")
marker = 'print("adapter_identity_ok selected_adapter=%s valid_for_official_use=%s adapter_scale=%s" % ('
idx = text.find(marker)
if idx < 0:
    raise SystemExit("identity_print_missing")
# Find end of this print(...) statement
close_paren = text.find("))\n", idx)
if close_paren < 0:
    raise SystemExit("print_close_missing")
after = close_paren + 3
# If PY terminator already present, leave it
window = text[after : after + 40]
if not window.lstrip().startswith("PY"):
    text = text[:after] + "PY\n" + text[after:]
    print("inserted_PY")
else:
    print("PY_already_present")

bad = 'mkdir -p "${PROVE_OUT}/{goal_first_v2,official_adapter,intent_box_raw,intent_box_ft}"'
good = (
    'mkdir -p "${PROVE_OUT}/goal_first_v2" '
    '"${PROVE_OUT}/official_adapter" '
    '"${PROVE_OUT}/intent_box_raw" '
    '"${PROVE_OUT}/intent_box_ft"'
)
if bad in text:
    text = text.replace(bad, good)
    print("fixed_mkdir")

p.write_text(text, encoding="utf-8", newline="\n")
subprocess.check_call(["bash", "-n", str(p)])
print("bash_n_ok")
# sanity: first python heredoc must close before gpu wait loop
i = text.find("adapter_must_be_official_selected")
j = text.find("for _wait", i)
chunk = text[i:j]
if "PY" not in chunk:
    raise SystemExit("still_missing_PY_before_wait_loop")
print("heredoc_ok")
