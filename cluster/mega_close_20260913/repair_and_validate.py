#!/usr/bin/env python3
from pathlib import Path
import re
import py_compile

ROOTS = [
    Path("/home-mscluster/mbangie/t12-hpc/code/final_close-20260913"),
    Path("/home-mscluster/mbangie/t12-hpc/code/temp_sweep-20260913"),
    Path("/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913"),
]

DIRECT_CALL = (
    "adapter_id = selected_adapter_identity("
    "adapter_identity, "
    "adapter_scale=float(args.adapter_scale), "
    'allow_unofficial=bool(getattr(args, "allow_unofficial_adapter", False))'
    ")"
)
CONSUMER_CALL = (
    "selected_adapter_identity(identity, adapter_scale=args.adapter_scale, "
    "allow_unofficial=bool(getattr(args, 'allow_unofficial_adapter', False)))"
)

for root in ROOTS:
    path = root / "scripts" / "evaluate_pilot_120_direct_base.py"
    text = path.read_text(encoding="utf-8")
    text = re.sub(
        r"adapter_id = selected_adapter_identity\([\s\S]*?\)\n(?:\s*\)\n)?",
        DIRECT_CALL + "\n",
        text,
        count=1,
    )
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        if line.strip() == ")" and i and "selected_adapter_identity(" in lines[i - 1]:
            continue
        out.append(line)
    text = "\n".join(out) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    py_compile.compile(str(path), doraise=True)
    print("direct_ok", path)

    for name in ("evaluate_goal_first_manager_v2.py", "evaluate_pilot_120_manager_systems.py"):
        p = root / "scripts" / name
        if not p.is_file():
            continue
        t = p.read_text(encoding="utf-8")
        t = re.sub(r"selected_adapter_identity\([^\n]+\)", CONSUMER_CALL, t, count=1)
        p.write_text(t, encoding="utf-8", newline="\n")
        py_compile.compile(str(p), doraise=True)
        print("consumer_ok", p)

    for sweep in root.glob("cluster/**/sweep.sbatch"):
        t = sweep.read_text(encoding="utf-8")
        t2 = t.replace(
            '"--allow-unofficial-adapter", "--allow-unofficial-adapter"',
            '"--allow-unofficial-adapter"',
        )
        if t2 != t:
            sweep.write_text(t2, encoding="utf-8", newline="\n")
            print("deduped", sweep)

mega = Path("/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913/cluster/mega_close_20260913/mega.sbatch")
scripts_dir = Path("/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913/scripts")
t = mega.read_text(encoding="utf-8")
t = t.replace(
    '"--allow-unofficial-adapter", "--allow-unofficial-adapter"',
    '"--allow-unofficial-adapter"',
)
# Force smoke commands to use scripts that exist
goal = "evaluate_goal_first_manager_v2.py"
direct = "evaluate_pilot_120_direct_base.py"
assert (scripts_dir / goal).is_file(), goal
assert (scripts_dir / direct).is_file(), direct

# Replace first two qwen smoke evaluator lines by rewriting the smoke block anchors
t = re.sub(
    r"(echo \"phase:smoke_temp_5\"[\s\S]*?)qwen scripts/evaluate_[A-Za-z0-9_]+\.py",
    rf"\1qwen scripts/{goal}",
    t,
    count=1,
)
# after first replacement, second smoke qwen for direct
# Find unofficial_adapter smoke invocation
t = re.sub(
    r"(SMOKE_OUT}/unofficial_adapter\"[\s\S]{0,80}?)qwen scripts/evaluate_[A-Za-z0-9_]+\.py",
    rf"\1qwen scripts/{direct}",
    t,
    count=1,
)
# fallback: any missing evaluate_* refs in smoke section
smoke_start = t.find('echo "phase:smoke_temp_5"')
smoke_end = t.find('echo "phase:', smoke_start + 10)
if smoke_end < 0:
    smoke_end = smoke_start + 2500
smoke = t[smoke_start:smoke_end]
for m in re.finditer(r"scripts/(evaluate_[A-Za-z0-9_]+\.py)", smoke):
    name = m.group(1)
    exists = (scripts_dir / name).is_file()
    print("smoke_ref", name, exists)
    if not exists:
        raise SystemExit(f"bad_smoke_ref:{name}")

mega.write_text(t, encoding="utf-8", newline="\n")
print("mega_ok", mega)

# rewrite submit with known-good defaults from final_close submit
submit = Path("/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913/cluster/mega_close_20260913/submit.sh")
submit.write_text(
    """#!/usr/bin/env bash
set -euo pipefail
umask 077
: "${MEGA_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913}"
: "${CLOSE_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/final_close-20260913}"
: "${SWEEP_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/temp_sweep-20260913}"
: "${SWEEP_NATIVE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/temp_sweep-native-20260913}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${A01_CONTAINER_SIF:=/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif}"
: "${GFV2_SELECTED_ADAPTER:=/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/early_pilot_package_excluding_clara1170_v1}"
: "${GFV2_ADAPTER_IDENTITY:=${GFV2_SELECTED_ADAPTER}/adapter_identity.json}"
: "${GFV2_ADAPTER_SCALE:=0.18}"
mkdir -p "${CLOSE_OUTPUT}" "${SWEEP_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs
export MEGA_CODE_ROOT CLOSE_OUTPUT SWEEP_OUTPUT SWEEP_NATIVE_ROOT
export CLOSE_CODE_ROOT="${MEGA_CODE_ROOT}"
export SWEEP_CODE_ROOT="${MEGA_CODE_ROOT}"
export GFV2_TRAINING_SITE_PACKAGES GFV2_HF_HOME GFV2_CONTAINER A01_CONTAINER_SIF
export GFV2_SELECTED_ADAPTER GFV2_ADAPTER_IDENTITY GFV2_ADAPTER_SCALE
job_id=$(sbatch --parsable --export=ALL \\
  "${MEGA_CODE_ROOT}/cluster/mega_close_20260913/mega.sbatch")
printf 'job_id\\t%s\\nclose_out\\t%s\\nsweep_out\\t%s\\ncode\\t%s\\n' \\
  "${job_id}" "${CLOSE_OUTPUT}" "${SWEEP_OUTPUT}" "${MEGA_CODE_ROOT}" \\
  | tee "${CLOSE_OUTPUT}/mega_submission.tsv"
echo "submitted ${job_id}"
""",
    encoding="utf-8",
    newline="\n",
)
submit.chmod(0o755)
print("submit_ok")
print("ALL_OK")
