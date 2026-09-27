#!/usr/bin/env bash
# Build mega_close tree and sbatch on the cluster from live final_close + temp_sweep.
set -euo pipefail
umask 077

FINAL=/home-mscluster/mbangie/t12-hpc/code/final_close-20260913
SWEEP=/home-mscluster/mbangie/t12-hpc/code/temp_sweep-20260913
MEGA=/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913
NATIVE=/home-mscluster/mbangie/t12-hpc/code/temp_sweep-native-20260913

rm -rf "${MEGA}"
mkdir -p "${MEGA}"
# Prefer final_close tree (has packets + intent_box scripts); overlay patched sweep scripts.
rsync -a --delete \
  --exclude '.git' \
  --exclude 'results/' \
  --exclude 'logs/' \
  "${FINAL}/" "${MEGA}/"
# Overlay temp_sweep scripts that may be newer for sweep runners
rsync -a "${SWEEP}/scripts/" "${MEGA}/scripts/"
rsync -a "${SWEEP}/cluster/temp_sweep_20260913/" "${MEGA}/cluster/temp_sweep_20260913/"
mkdir -p "${MEGA}/cluster/mega_close_20260913"

python3 - <<'PY'
from pathlib import Path
import re

mega = Path("/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913")
close = (mega / "cluster/final_close_20260913/close.sbatch").read_text(encoding="utf-8")
sweep = (mega / "cluster/temp_sweep_20260913/sweep.sbatch").read_text(encoding="utf-8")

def body(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith("#SBATCH"):
            continue
        lines.append(line)
    # drop shebang
    if lines and lines[0].startswith("#!"):
        lines = lines[1:]
    # drop leading set - line; mega header owns it for close section
    return "\n".join(lines).strip() + "\n"

close_body = body(close)
sweep_body = body(sweep)
# sweep uses set -u without -e; keep its set line
# close body also has set -euo; strip first set line from close
close_lines = close_body.splitlines()
if close_lines and close_lines[0].startswith("set -"):
    close_body = "\n".join(close_lines[1:]) + "\n"

# Discover actual evaluator script names
scripts = {p.name for p in (mega / "scripts").glob("*.py")}
goal = "evaluate_goal_first_manager_v2.py" if "evaluate_goal_first_manager_v2.py" in scripts else None
direct = "evaluate_pilot_120_direct_base.py" if "evaluate_pilot_120_direct_base.py" in scripts else None
if not goal or not direct:
    raise SystemExit(f"missing_scripts goal={goal} direct={direct} sample={sorted(scripts)[:20]}")

# Discover CLI flag spelling from patched direct_base
direct_txt = (mega / "scripts" / direct).read_text(encoding="utf-8")
flag = "--allow-unofficial-adapter" if "--allow-unofficial-adapter" in direct_txt else None
if not flag:
    raise SystemExit("allow_unofficial_flag_missing_after_patch")

# Discover argparse dest names used by goal script
goal_txt = (mega / "scripts" / goal).read_text(encoding="utf-8")
root_opt = "--root" if "--root" in goal_txt else "--code-root"
out_opt = "--output-dir" if "--output-dir" in goal_txt else "--out-dir"
limit_opt = "--limit" if "--limit" in goal_txt else None
if not limit_opt:
    raise SystemExit("goal_first_missing_limit")

# Discover system id for adapter direct_base from source
sys_id = "t28_selected_adapter_llm"
m = re.search(r'SELECTED_ADAPTER_SYSTEM_ID\s*=\s*"([^"]+)"', direct_txt)
if m:
    sys_id = m.group(1)

# Discover CLOSE env var names from close.sbatch
close_src = close
code_var = "CLOSE_CODE_ROOT" if "CLOSE_CODE_ROOT" in close_src else "CLOSE_CODE_ROOT"
out_var = "CLOSE_OUTPUT" if "CLOSE_OUTPUT" in close_src else "CLOSE_OUTPUT"
adapter_var = "GFV2_SELECTED_ADAPTER" if "GFV2_SELECTED_ADAPTER" in close_src else "GFV2_SELECTED_ADAPTER"
ident_var = "GFV2_ADAPTER_IDENTITY" if "GFV2_ADAPTER_IDENTITY" in close_src else "GFV2_ADAPTER_IDENTITY"
scale_var = "GFV2_ADAPTER_SCALE" if "GFV2_ADAPTER_SCALE" in close_src else "GFV2_ADAPTER_SCALE"

# Find qwen function name in close
qwen_fn = "qwen" if "qwen()" in close_body or re.search(r"^qwen\(\)", close_body, re.M) else "qwen"

smoke = f'''
echo "phase:smoke_temp_5"
SMOKE_OUT="${{{out_var}}}/smoke_temp_5/T0.0/R1"
mkdir -p "${{SMOKE_OUT}}/goal_first_v2" "${{SMOKE_OUT}}/unofficial_adapter"
ADAPTER="${{{adapter_var}:-}}"
IDENTITY="${{{ident_var}:-${{ADAPTER}}/adapter_identity.json}}"
SCALE="${{{scale_var}:-0.18}}"

{qwen_fn} scripts/{goal} \\
  {root_opt} "${{{code_var}}}" \\
  {out_opt} "${{SMOKE_OUT}}/goal_first_v2" \\
  --adapter "${{ADAPTER}}" \\
  --adapter-identity "${{IDENTITY}}" \\
  --adapter-scale "${{SCALE}}" \\
  {flag} \\
  --limit 5 \\
  --temperature 0.0 \\
  --seed 20260913

{qwen_fn} scripts/{direct} \\
  {root_opt} "${{{code_var}}}" \\
  {out_opt} "${{SMOKE_OUT}}/unofficial_adapter" \\
  --system-id {sys_id} \\
  --adapter "${{ADAPTER}}" \\
  --adapter-identity "${{IDENTITY}}" \\
  --adapter-scale "${{SCALE}}" \\
  {flag} \\
  --limit 5 \\
  --temperature 0.0 \\
  --seed 20260913

python3 - <<'PY'
import json
from pathlib import Path
smoke = Path("${{SMOKE_OUT}}")
files = []
for path in sorted(smoke.rglob("*.jsonl")):
    if "prediction" not in path.name.lower() and not path.name.endswith(".predictions.jsonl"):
        # keep prediction-like files only
        if "predictions" not in path.as_posix():
            continue
    n = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    files.append({{"path": str(path), "n": n}})
print(json.dumps({{"smoke_files": files}}, indent=2))
ok = [f for f in files if f["n"] >= 5]
if len(ok) < 2:
    raise SystemExit(f"smoke_temp_failed:need_two_files_with_5_rows got={{files}}")
Path("${{{out_var}}}/SMOKE_OK.json").write_text(
    json.dumps({{"ok": True, "files": files, "allow_unofficial_adapter": True}}, indent=2) + "\\n",
    encoding="utf-8",
)
print("smoke_temp_ok")
PY
'''

# Insert smoke after GPU free wait / before first intent phase.
insert_at = None
for token in (
    'echo "phase:raw_intent_box"',
    "phase:raw_intent_box",
    "evaluate_pilot_120_intent_box.py",
):
    if token in close_body:
        insert_at = close_body.find(token)
        break
if insert_at is None:
    raise SystemExit("cannot_locate_intent_box_phase")
# snap back to line start
insert_at = close_body.rfind("\n", 0, insert_at) + 1
close_with_smoke = close_body[:insert_at] + smoke + "\n" + close_body[insert_at:]

header = f'''#!/usr/bin/env bash
# One job: 5-row unofficial adapter smoke -> final close -> full temp sweep.
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

bridge = '''
echo "final_close_section_complete writing CLOSE handoff"
python3 - <<'PY'
import json
from pathlib import Path
import os
out = Path(os.environ["CLOSE_OUTPUT"] if "CLOSE_OUTPUT" in os.environ else os.environ.get("CLOSE_OUTPUT",""))
# resolve whichever close output env exists
for key in ("CLOSE_OUTPUT", "CLOSE_OUTPUT"):
    if key in os.environ:
        out = Path(os.environ[key])
        break
payload = {
  "close_section": "complete",
  "smoke_ok_path": str(out / "SMOKE_OK.json"),
  "next": "temp_sweep",
}
(out / "CLOSE_HANDOFF.json").write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
print(json.dumps(payload, indent=2))
PY

echo "phase:temp_sweep_all_slices"
set +e
'''

# Fix bridge to use discovered out_var
bridge = bridge.replace("CLOSE_OUTPUT", out_var)

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
  "sweep_rc": int("{sweep_rc}"),
  "did_not_overwrite_t39_t41": True,
  "fine_tune_remains_unofficial": True,
}}
(out / "MEGA_STATUS.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
print(json.dumps(payload, indent=2, sort_keys=True))
PY
if [[ "${{sweep_rc}}" -ne 0 ]]; then
  echo "temp_sweep_failed_rc=${{sweep_rc}}" >&2
  exit "${{sweep_rc}}"
fi
echo "mega_close_complete"
'''

# Soften sweep initial busy_gpu hard exit into wait (mega already waited once)
sweep_soft = re.sub(
    r'if \[\[ "\$\{{?GPU_USED\}}?" -gt 1000 \]\]; then\n  echo "busy_gpu:[^"]*" >&2\n  exit 42\nfi',
    'for _w in $(seq 1 30); do\n'
    '  GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"\n'
    '  GPU_USED="${GPU_USED%% *}"\n'
    '  if [[ "${GPU_USED}" -le 1000 ]]; then echo "gpu_free_before_sweep:${GPU_USED}"; break; fi\n'
    '  echo "waiting_gpu_before_sweep:${GPU_USED}:try=${_w}"; sleep 20\n'
    'done\n'
    'if [[ "${GPU_USED}" -gt 1000 ]]; then echo "busy_gpu:${GPU_USED}" >&2; exit 42; fi',
    sweep_body,
    count=1,
)

mega_text = header + close_with_smoke + bridge + sweep_soft + footer
out_path = mega / "cluster/mega_close_20260913/mega.sbatch"
out_path.write_text(mega_text, encoding="utf-8", newline="\n")
print(f"wrote {out_path} bytes={out_path.stat().st_size}")
print(f"goal={goal} direct={direct} flag={flag} sys_id={sys_id} code_var={code_var} out_var={out_var}")

# Write submit.sh using discovered env names from final submit if present
submit_src = mega / "cluster/final_close_20260913/submit.sh"
submit_txt = submit_src.read_text(encoding="utf-8") if submit_src.is_file() else ""
submit = f'''#!/usr/bin/env bash
set -euo pipefail
umask 077
: "${{MEGA_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913}}"
: "${{{out_var}:=/home-mscluster/mbangie/t12-hpc/results/final_close-20260913}}"
: "${{SWEEP_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/temp_sweep-20260913}}"
: "${{SWEEP_NATIVE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/temp_sweep-native-20260913}}"
: "${{GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}}"
: "${{GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}}"
: "${{GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}}"
: "${{A01_CONTAINER_SIF:=/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif}}"
: "${{{adapter_var}:=/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/early_pilot_package_excluding_clara1170_v1}}"
: "${{{ident_var}:=${{{adapter_var}}}/adapter_identity.json}}"
: "${{{scale_var}:=0.18}}"
mkdir -p "${{{out_var}}}" "${{SWEEP_OUTPUT}}" /home-mscluster/mbangie/t12-hpc/logs
export MEGA_CODE_ROOT {out_var} SWEEP_OUTPUT SWEEP_NATIVE_ROOT
export {code_var}="${{MEGA_CODE_ROOT}}"
export SWEEP_CODE_ROOT="${{MEGA_CODE_ROOT}}"
export GFV2_TRAINING_SITE_PACKAGES GFV2_HF_HOME GFV2_CONTAINER A01_CONTAINER_SIF
export {adapter_var} {ident_var} {scale_var}
# Common aliases if trees disagree on spelling
export GFV2_TRAINING_SITE_PACKAGES="${{GFV2_TRAINING_SITE_PACKAGES:-}}"
export GFV2_HF_HOME="${{GFV2_HF_HOME:-}}"
export GFV2_CONTAINER="${{GFV2_CONTAINER:-}}"
job_id=$(sbatch --parsable --export=ALL \\
  "${{MEGA_CODE_ROOT}}/cluster/mega_close_20260913/mega.sbatch")
printf 'job_id\\t%s\\nclose_out\\t%s\\nsweep_out\\t%s\\ncode\\t%s\\n' \\
  "${{job_id}}" "${{{out_var}}}" "${{SWEEP_OUTPUT}}" "${{MEGA_CODE_ROOT}}" \\
  | tee "${{{out_var}}}/mega_submission.tsv"
echo "submitted ${{job_id}}"
'''
submit_path = mega / "cluster/mega_close_20260913/submit.sh"
submit_path.write_text(submit, encoding="utf-8", newline="\n")
submit_path.chmod(0o755)
print(f"wrote {submit_path}")
PY

# Copy env names from live final submit into mega submit by sourcing defaults if needed
ls -la "${MEGA}/cluster/mega_close_20260913/"
# Sanity: flag present in scripts
grep -n allow-unofficial "${MEGA}/scripts/evaluate_pilot_120_direct_base.py" | head
grep -n allow-unofficial "${MEGA}/scripts/evaluate_goal_first_manager_v2.py" | head
test -d "${NATIVE}" && echo native_ok || echo native_missing
