#!/usr/bin/env python3
from pathlib import Path
import re, json, os, shutil, stat

FINAL = Path("/home-mscluster/mbangie/t12-hpc/code/final_close-20260913")
SWEEP = Path("/home-mscluster/mbangie/t12-hpc/code/temp_sweep-20260913")
MEGA = Path("/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913")
NATIVE = Path("/home-mscluster/mbangie/t12-hpc/code/temp_sweep-native-20260913")

if MEGA.exists():
    shutil.rmtree(MEGA)
MEGA.mkdir(parents=True)

# copy trees
def copytree(src: Path, dst: Path):
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "__pycache__"))

copytree(FINAL, MEGA)
# overlay sweep scripts + cluster sweep
shutil.copytree(SWEEP / "scripts", MEGA / "scripts", dirs_exist_ok=True)
sweep_cluster_src = next((SWEEP / "cluster").glob("*/sweep.sbatch")).parent
sweep_cluster_dst = MEGA / "cluster" / sweep_cluster_src.name
sweep_cluster_dst.mkdir(parents=True, exist_ok=True)
for p in sweep_cluster_src.iterdir():
    target = sweep_cluster_dst / p.name
    if p.is_file():
        shutil.copy2(p, target)

close_sbatch = next((MEGA / "cluster").glob("*/close.sbatch"))
sweep_sbatch = next((MEGA / "cluster").glob("*/sweep.sbatch"))
close_text = close_sbatch.read_text(encoding="utf-8")
sweep_text = sweep_sbatch.read_text(encoding="utf-8")

scripts = {p.name for p in (MEGA / "scripts").glob("*.py")}
print("SCRIPTS_EVAL", sorted(x for x in scripts if x.startswith("evaluate_")))

goal = "evaluate_goal_first_manager_v2.py"
direct = "evaluate_pilot_120_direct_base.py"
intent = "evaluate_pilot_120_intent_box.py"
for required in (goal, direct, intent):
    if required not in scripts:
        raise SystemExit(f"missing_required_script:{required}")
print("goal", goal, "direct", direct, "intent", intent)

goal_txt = (MEGA / "scripts" / goal).read_text(encoding="utf-8")
direct_txt = (MEGA / "scripts" / direct).read_text(encoding="utf-8")
assert "--allow-unofficial-adapter" in direct_txt, "patch missing on direct"
assert "--allow-unofficial-adapter" in goal_txt, "patch missing on goal"
assert "--limit" in goal_txt, "limit missing on goal"
assert "--limit" in direct_txt, "limit missing on direct"

# Discover required env vars from close
req = re.findall(r':\s*"\$\{([A-Z0-9_]+):\?\}"', close_text)
print("CLOSE_REQUIRED", req)
code_var = next(v for v in req if "CODE" in v)
out_var = next(v for v in req if "OUT" in v)

# Discover adapter env names used in close
adapter_vars = sorted(set(re.findall(r"\$\{(GFV2_[A-Z0-9_]+)", close_text)))
print("GFV2_VARS", adapter_vars)
adapter_var = next(v for v in adapter_vars if "ADAPTER" in v and "IDENTITY" not in v and "SCALE" not in v)
ident_var = next(v for v in adapter_vars if "IDENTITY" in v)
scale_var = next(v for v in adapter_vars if "SCALE" in v)

# Discover system id constant
m = re.search(r'(SELECTED_[A-Z_]*SYSTEM[A-Z_]*|ADAPTER_SYSTEM_ID)\s*=\s*"([^"]+)"', direct_txt)
sys_id = m.group(2) if m else None
if not sys_id:
    m = re.search(r'--system-id", default="([^"]+)"', direct_txt)
    # find SELECTED adapter system id assignment
    m = re.search(r'^\s*([A-Z0-9_]*ADAPTER[A-Z0-9_]*SYSTEM[A-Z0-9_]*)\s*=\s*"([^"]+)"', direct_txt, re.M)
    sys_id = m.group(2) if m else "t28_selected_adapter_llm"
print("SYS_ID", sys_id)

# Discover root/output option names
root_opt = "--root" if '"--root"' in goal_txt or "'--root'" in goal_txt else None
out_opt = "--output-dir" if '"--output-dir"' in goal_txt else "--out"
assert root_opt

# strip SBATCH lines
def strip_sbatch(text: str) -> str:
    lines = [ln for ln in text.splitlines() if not ln.startswith("#SBATCH")]
    if lines and lines[0].startswith("#!"):
        lines = lines[1:]
    return "\n".join(lines).strip() + "\n"

close_body = strip_sbatch(close_text)
sweep_body = strip_sbatch(sweep_text)
# remove leading set from close; mega owns set -euo for close section
cl = close_body.splitlines()
if cl and cl[0].startswith("set -"):
    close_body = "\n".join(cl[1:]).strip() + "\n"

# Find insertion point: first occurrence of intent box script name
idx = close_body.find(intent)
if idx < 0:
    raise SystemExit("intent_box_call_not_found_in_close")
idx = close_body.rfind("\n", 0, idx) + 1
# walk back to include the surrounding if/echo block start if nearby
window = close_body[max(0, idx-400):idx]
# Prefer to insert before the nearest preceding echo phase line
phase_pos = window.rfind('echo "')
if phase_pos >= 0:
    idx = max(0, idx-400) + phase_pos

smoke = f'''
echo "phase:smoke_temp_5"
SMOKE_OUT="${{{out_var}}}/smoke_temp_5/T0.0/R1"
mkdir -p "${{SMOKE_OUT}}/goal_first_v2" "${{SMOKE_OUT}}/unofficial_adapter"
ADAPTER="${{{adapter_var}}}"
IDENTITY="${{{ident_var}:-${{ADAPTER}}/adapter_identity.json}}"
SCALE="${{{scale_var}:-0.18}}"

qwen scripts/{goal} \\
  {root_opt} "${{{code_var}}}" \\
  {out_opt} "${{SMOKE_OUT}}/goal_first_v2" \\
  --adapter "${{ADAPTER}}" \\
  --adapter-identity "${{IDENTITY}}" \\
  --adapter-scale "${{SCALE}}" \\
  --allow-unofficial-adapter \\
  --limit 5 \\
  --temperature 0.0 \\
  --seed 20260913

qwen scripts/{direct} \\
  {root_opt} "${{{code_var}}}" \\
  {out_opt} "${{SMOKE_OUT}}/unofficial_adapter" \\
  --system-id {sys_id} \\
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
smoke = Path(os.environ["SMOKE_OUT"]) if False else Path(r"${{SMOKE_OUT}}")
files=[]
for path in sorted(smoke.rglob("*")):
    if not path.is_file():
        continue
    if "prediction" not in path.name.lower():
        continue
    n=sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    files.append({{"path":str(path),"n":n}})
print(json.dumps({{"smoke_files":files}}, indent=2))
if sum(1 for f in files if f["n"]>=5) < 1:
    raise SystemExit("smoke_temp_failed")
Path(r"${{{out_var}}}/SMOKE_OK.json").write_text(json.dumps({{"ok":True,"files":files}}, indent=2)+"\\n", encoding="utf-8")
print("smoke_temp_ok")
PY
export SMOKE_OUT
'''

# Ensure qwen helper exists before smoke — smoke must come AFTER qwen() definition.
# So insert after "qwen() {" block end, or before intent if qwen already defined earlier than intent.
qwen_def = re.search(r"^qwen\(\) \{[\s\S]*?^\}\s*$", close_body, re.M)
if qwen_def and qwen_def.end() < idx:
    idx = max(idx, qwen_def.end())
    # move to next newline after function
    nl = close_body.find("\n", idx)
    idx = nl + 1 if nl >= 0 else idx

close_with_smoke = close_body[:idx] + "\n" + smoke + "\n" + close_body[idx:]

# Soften sweep busy exit
sweep_soft = sweep_body
sweep_soft = re.sub(
    r'if \[\[ "\$\{GPU_[A-Z_]+\}" -gt 1000 \]\]; then\n  echo "busy_gpu:.*?\" >&2\n  exit 42\nfi',
    'for _w in $(seq 1 30); do\n'
    '  _g="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"\n'
    '  _g="${_g%% *}"\n'
    '  if [[ "${_g}" -le 1000 ]]; then echo "gpu_free_before_sweep:${_g}"; break; fi\n'
    '  echo "waiting_gpu_before_sweep:${_g}:try=${_w}"; sleep 20\n'
    'done\n'
    'if [[ "${_g}" -gt 1000 ]]; then echo "busy_gpu:${_g}" >&2; exit 42; fi',
    sweep_soft,
    count=1,
    flags=re.S,
)

header = f'''#!/usr/bin/env bash
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
: "${{MEGA_CODE_ROOT:?}}"
: "${{{out_var}:?}}"
: "${{SWEEP_OUTPUT:?}}"
: "${{SWEEP_NATIVE_ROOT:?}}"
export {code_var}="${{MEGA_CODE_ROOT}}"
export SWEEP_CODE_ROOT="${{MEGA_CODE_ROOT}}"
export SWEEP_NATIVE_ROOT SWEEP_OUTPUT
export {out_var}

'''

bridge = f'''
echo "final_close_section_complete"
python3 - <<PY
import json
from pathlib import Path
out = Path("${{{out_var}}}")
payload = {{"close_section":"complete","smoke_ok":(out/"SMOKE_OK.json").is_file(),"next":"temp_sweep"}}
(out/"CLOSE_HANDOFF.json").write_text(json.dumps(payload, indent=2)+"\\n", encoding="utf-8")
print(json.dumps(payload, indent=2))
PY
echo "phase:temp_sweep_all_slices"
set +e
'''

footer = f'''
sweep_rc=$?
set -e
python3 - <<PY
import json, os
from pathlib import Path
out = Path(os.environ["{out_var}"])
payload = {{
  "job_name": "mega-close",
  "smoke_ok": (out / "SMOKE_OK.json").is_file(),
  "close_output": str(out),
  "sweep_output": os.environ.get("SWEEP_OUTPUT"),
  "sweep_rc": int("$sweep_rc"),
  "did_not_overwrite_t39_t41": True,
  "fine_tune_remains_unofficial": True,
}}
(out / "MEGA_STATUS.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
print(json.dumps(payload, indent=2, sort_keys=True))
PY
if [[ "$sweep_rc" -ne 0 ]]; then
  echo "temp_sweep_failed_rc=$sweep_rc" >&2
  exit "$sweep_rc"
fi
echo "mega_close_complete"
'''

out_dir = MEGA / "cluster" / "mega_close_20260913"
out_dir.mkdir(parents=True, exist_ok=True)
mega_path = out_dir / "mega.sbatch"
mega_path.write_text(header + close_with_smoke + bridge + sweep_soft + footer, encoding="utf-8", newline="\n")
print("WROTE", mega_path, mega_path.stat().st_size)

# Read live defaults from final submit.sh
submit_src = next((FINAL / "cluster").glob("*/submit.sh"))
src = submit_src.read_text(encoding="utf-8")
defaults = dict(re.findall(r':\s*"\$\{([A-Z0-9_]+):=([^}]+)\}"', src))
print("SUBMIT_DEFAULTS_KEYS", sorted(defaults))

def d(key, fallback):
    return defaults.get(key, fallback)

submit = f'''#!/usr/bin/env bash
set -euo pipefail
umask 077
: "${{MEGA_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913}}"
: "${{{out_var}:={d(out_var, "/home-mscluster/mbangie/t12-hpc/results/final_close-20260913")}}}"
: "${{SWEEP_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/temp_sweep-20260913}}"
: "${{SWEEP_NATIVE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/temp_sweep-native-20260913}}"
: "${{GFV2_TRAINING_SITE_PACKAGES:={d("GFV2_TRAINING_SITE_PACKAGES", "/home-mscluster/mbangie/t12-hpc/training-site-packages")}}}"
: "${{GFV2_HF_HOME:={d("GFV2_HF_HOME", "/home-mscluster/mbangie/t12-hpc/hf-cache")}}}"
: "${{GFV2_CONTAINER:={d("GFV2_CONTAINER", "/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif")}}}"
: "${{A01_CONTAINER_SIF:={d("A01_CONTAINER_SIF", "/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif")}}}"
: "${{{adapter_var}:={d(adapter_var, "/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/early_pilot_package_excluding_clara1170_v1")}}}"
: "${{{ident_var}:=${{{adapter_var}}}/adapter_identity.json}}"
: "${{{scale_var}:={d(scale_var, "0.18")}}}"
mkdir -p "${{{out_var}}}" "${{SWEEP_OUTPUT}}" /home-mscluster/mbangie/t12-hpc/logs
export MEGA_CODE_ROOT {out_var} SWEEP_OUTPUT SWEEP_NATIVE_ROOT
export {code_var}="${{MEGA_CODE_ROOT}}"
export SWEEP_CODE_ROOT="${{MEGA_CODE_ROOT}}"
export GFV2_TRAINING_SITE_PACKAGES GFV2_HF_HOME GFV2_CONTAINER A01_CONTAINER_SIF
export {adapter_var} {ident_var} {scale_var}
# alias spellings used by some scripts
export GFV2_TRAINING_SITE_PACKAGES GFV2_HF_HOME GFV2_CONTAINER
job_id=$(sbatch --parsable --export=ALL \\
  "${{MEGA_CODE_ROOT}}/cluster/mega_close_20260913/mega.sbatch")
printf 'job_id\\t%s\\nclose_out\\t%s\\nsweep_out\\t%s\\ncode\\t%s\\n' \\
  "${{job_id}}" "${{{out_var}}}" "${{SWEEP_OUTPUT}}" "${{MEGA_CODE_ROOT}}" \\
  | tee "${{{out_var}}}/mega_submission.tsv"
echo "submitted ${{job_id}}"
'''
submit_path = out_dir / "submit.sh"
submit_path.write_text(submit, encoding="utf-8", newline="\n")
submit_path.chmod(submit_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
print("WROTE", submit_path)
print("NATIVE_EXISTS", NATIVE.is_dir())
print("DONE")
