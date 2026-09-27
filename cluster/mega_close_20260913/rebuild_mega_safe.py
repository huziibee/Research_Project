#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess

MEGA = Path("/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913")
CLOSE = MEGA / "cluster/final_close_20260913/close.sbatch"
SWEEP = MEGA / "cluster/temp_sweep_20260913/sweep.sbatch"
OUT = MEGA / "cluster/mega_close_20260913/mega.sbatch"

scripts = {p.name for p in (MEGA / "scripts").glob("*.py")}
goal = "evaluate_goal_first_manager_v2.py"
direct = "evaluate_pilot_120_direct_base.py"
assert goal in scripts and direct in scripts


def strip_sbatch(text: str) -> str:
    lines = [ln for ln in text.splitlines() if not ln.startswith("#SBATCH")]
    if lines and lines[0].startswith("#!"):
        lines = lines[1:]
    return "\n".join(lines).strip() + "\n"


close = strip_sbatch(CLOSE.read_text(encoding="utf-8"))
sweep = strip_sbatch(SWEEP.read_text(encoding="utf-8"))
# drop leading set from close; header owns it
if close.startswith("set -"):
    close = "\n".join(close.splitlines()[1:]).lstrip() + "\n"

smoke = f'''
echo "phase:smoke_temp_5"
SMOKE_OUT="${{CLOSE_OUTPUT}}/smoke_temp_5/T0.0/R1"
mkdir -p "${{SMOKE_OUT}}/goal_first_v2" "${{SMOKE_OUT}}/unofficial_adapter"
ADAPTER="${{GFV2_SELECTED_ADAPTER}}"
IDENTITY="${{GFV2_ADAPTER_IDENTITY:-${{ADAPTER}}/adapter_identity.json}}"
SCALE="${{GFV2_ADAPTER_SCALE:-0.18}}"
export SMOKE_OUT

qwen scripts/{goal} \\
  --root "${{CLOSE_CODE_ROOT}}" \\
  --output-dir "${{SMOKE_OUT}}/goal_first_v2" \\
  --adapter "${{ADAPTER}}" \\
  --adapter-identity "${{IDENTITY}}" \\
  --adapter-scale "${{SCALE}}" \\
  --allow-unofficial-adapter \\
  --limit 5 \\
  --temperature 0.0 \\
  --seed 20260913

qwen scripts/{direct} \\
  --root "${{CLOSE_CODE_ROOT}}" \\
  --output-dir "${{SMOKE_OUT}}/unofficial_adapter" \\
  --system-id t28_selected_adapter_llm \\
  --adapter "${{ADAPTER}}" \\
  --adapter-identity "${{IDENTITY}}" \\
  --adapter-scale "${{SCALE}}" \\
  --allow-unofficial-adapter \\
  --limit 5 \\
  --temperature 0.0 \\
  --seed 20260913

python3 - <<'PY'
import json
from pathlib import Path
import os
smoke = Path(os.environ["SMOKE_OUT"])
files = []
for path in sorted(smoke.rglob("*")):
    if not path.is_file():
        continue
    if "prediction" not in path.name.lower():
        continue
    n = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    files.append({{"path": str(path), "n": n}})
print(json.dumps({{"smoke_files": files}}, indent=2))
if not any(f["n"] >= 5 for f in files):
    raise SystemExit("smoke_temp_failed")
Path(os.environ["CLOSE_OUTPUT"], "SMOKE_OK.json").write_text(
    json.dumps({{"ok": True, "files": files}}, indent=2) + "\\n", encoding="utf-8"
)
print("smoke_temp_ok")
PY
'''

# Insert AFTER qwen() function definition if present, else after first gpu_free echo
m = re.search(r"^qwen\(\) \{[\s\S]*?^\}\s*$", close, re.M)
if m:
    idx = m.end()
else:
    m = re.search(r'echo "gpu_free:[^"]*"', close)
    if not m:
        raise SystemExit("no_safe_insert_point")
    idx = close.find("\n", m.end()) + 1

close2 = close[:idx] + "\n" + smoke + "\n" + close[idx:]

# soften sweep busy exit
sweep2 = re.sub(
    r'if \[\[ "\$\{GPU_[A-Z_]+\}" -gt 1000 \]\]; then\n  echo "busy_gpu:[^"]*" >&2\n  exit 42\nfi',
    'for _w in $(seq 1 30); do\n'
    '  _g="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"\n'
    '  _g="${_g%% *}"\n'
    '  if [[ "${_g}" -le 1000 ]]; then echo "gpu_free_before_sweep:${_g}"; break; fi\n'
    '  echo "waiting_gpu_before_sweep:${_g}:try=${_w}"; sleep 20\n'
    'done\n'
    'if [[ "${_g}" -gt 1000 ]]; then echo "busy_gpu:${_g}" >&2; exit 42; fi',
    sweep,
    count=1,
)
sweep2 = sweep2.replace(
    '"--allow-unofficial-adapter", "--allow-unofficial-adapter"',
    '"--allow-unofficial-adapter"',
)
# drop leading set from sweep if present; we switch with set +e around it
if sweep2.startswith("set -"):
    # keep set -u behavior by leaving it
    pass

header = '''#!/usr/bin/env bash
# One job: 5-row unofficial-adapter smoke -> final close -> full temp sweep.
# Does not overwrite T39/T41. Does not flip selected_adapter.
#SBATCH --job-name=mega-close
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=3-00:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/mega-close-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/mega-close-%j.err

set -euo pipefail
umask 077
: "${MEGA_CODE_ROOT:?}"
: "${CLOSE_OUTPUT:?}"
: "${SWEEP_OUTPUT:?}"
: "${SWEEP_NATIVE_ROOT:?}"
export CLOSE_CODE_ROOT="${MEGA_CODE_ROOT}"
export SWEEP_CODE_ROOT="${MEGA_CODE_ROOT}"
export SWEEP_NATIVE_ROOT SWEEP_OUTPUT CLOSE_OUTPUT

'''

bridge = '''
echo "final_close_section_complete"
python3 - <<'PY'
import json, os
from pathlib import Path
out = Path(os.environ["CLOSE_OUTPUT"])
payload = {"close_section": "complete", "smoke_ok": (out / "SMOKE_OK.json").is_file(), "next": "temp_sweep"}
(out / "CLOSE_HANDOFF.json").write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
print(json.dumps(payload, indent=2))
PY
echo "phase:temp_sweep_all_slices"
set +e
'''

footer = '''
sweep_rc=$?
set -e
python3 - <<PY
import json, os
from pathlib import Path
out = Path(os.environ["CLOSE_OUTPUT"])
payload = {
  "job_name": "mega-close",
  "smoke_ok": (out / "SMOKE_OK.json").is_file(),
  "close_output": str(out),
  "sweep_output": os.environ.get("SWEEP_OUTPUT"),
  "sweep_rc": int("$sweep_rc"),
  "did_not_overwrite_t39_t41": True,
  "fine_tune_remains_unofficial": True,
}
(out / "MEGA_STATUS.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
print(json.dumps(payload, indent=2, sort_keys=True))
PY
if [[ "$sweep_rc" -ne 0 ]]; then
  echo "temp_sweep_failed_rc=$sweep_rc" >&2
  exit "$sweep_rc"
fi
echo "mega_close_complete"
'''

text = header + close2 + bridge + sweep2 + footer
OUT.write_text(text, encoding="utf-8", newline="\n")
# bash syntax check
subprocess.check_call(["bash", "-n", str(OUT)])
print("syntax_ok", OUT, OUT.stat().st_size)
# ensure smoke not inside for-path loop: find for path in and smoke
pos_for = text.find("for path in")
pos_smoke = text.find('echo "phase:smoke_temp_5"')
pos_do = text.find("\ndo\n", pos_for)
pos_done = text.find("\ndone\n", pos_for)
print("positions", {"for": pos_for, "smoke": pos_smoke, "do": pos_do, "done": pos_done})
if pos_for >= 0 and pos_do >= 0 and pos_done > pos_do and pos_do < pos_smoke < pos_done:
    raise SystemExit("smoke_still_inside_for_loop")
print("smoke_placement_ok")
