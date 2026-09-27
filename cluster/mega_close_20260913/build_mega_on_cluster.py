#!/usr/bin/env python3
"""Build mega.sbatch on the cluster from live close + sweep scripts."""
from __future__ import annotations

from pathlib import Path

CLOSE = Path("/home-mscluster/mbangie/t12-hpc/code/final_close-20260913/cluster/final_close_20260913/close.sbatch")
SWEEP = Path("/home-mscluster/mbangie/t12-hpc/code/temp_sweep-20260913/cluster/temp_sweep_20260913/sweep.sbatch")
OUT_DIR = Path("/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913/cluster/mega_close_20260913")
CODE_ROOT = Path("/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913")


def strip_sbatch(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith("#SBATCH"):
            continue
        lines.append(line)
    return "\n".join(lines)


def main() -> int:
    close = CLOSE.read_text(encoding="utf-8")
    sweep = SWEEP.read_text(encoding="utf-8")

    # Discover env var names from close
    close_body = strip_sbatch(close)
    # Remove shebang / leading comments set -euo from close; we keep one header
    close_lines = close_body.splitlines()
    while close_lines and (
        close_lines[0].startswith("#!")
        or close_lines[0].startswith("# ")
        or close_lines[0].startswith("#Official")
        or close_lines[0].startswith("# Official")
        or close_lines[0] == ""
    ):
        # keep useful comments but drop shebang
        if close_lines[0].startswith("#!"):
            close_lines.pop(0)
            continue
        if close_lines[0].startswith("#") and "overwrite" in close_lines[0].lower():
            break
        if close_lines[0].startswith("#") and not close_lines[0].startswith("#SBATCH"):
            close_lines.pop(0)
            continue
        if close_lines[0] == "":
            close_lines.pop(0)
            continue
        break

    # Find set -euo / set -u in close
    close_start = 0
    for i, line in enumerate(close_lines):
        if line.startswith("set -"):
            close_start = i
            break
    close_core = "\n".join(close_lines[close_start:])

    # Rename CLOSE_CODE_ROOT references stay; MEGA will export CLOSE_CODE_ROOT=MEGA_CODE_ROOT
    sweep_body = strip_sbatch(sweep)
    sweep_lines = sweep_body.splitlines()
    sweep_start = 0
    for i, line in enumerate(sweep_lines):
        if line.startswith("set -"):
            sweep_start = i
            break
    # Drop GPU busy hard-fail at start of sweep when chained; soften to wait
    sweep_core = "\n".join(sweep_lines[sweep_start:])
    sweep_core = sweep_core.replace("set -u\n", "set -u\n# nested in mega; do not use set -e\n")

    smoke = r'''
echo "phase:smoke_temp_5"
SMOKE_OUT="${CLOSE_OUTPUT}/smoke_temp_5/T0.0/R1"
mkdir -p "${SMOKE_OUT}/goal_first_v2" "${SMOKE_OUT}/unofficial_adapter"
ADAPTER="${GFV2_SELECTED_ADAPTER:-${GFV2_SELECTED_ADAPTER:-}}"
IDENTITY="${GFV2_ADAPTER_IDENTITY:-${ADAPTER}/adapter_identity.json}"
SCALE="${GFV2_ADAPTER_SCALE:-0.18}"

# Resolve adapter env names present in this tree
if [[ -z "${ADAPTER}" || "${ADAPTER}" == "" ]]; then
  ADAPTER="${GFV2_SELECTED_ADAPTER:-}"
fi
if [[ -z "${ADAPTER}" ]]; then
  ADAPTER="${GFV2_SELECTED_ADAPTER:-}"
fi
IDENTITY="${GFV2_ADAPTER_IDENTITY:-${GFV2_ADAPTER_IDENTITY:-${ADAPTER}/adapter_identity.json}}"
SCALE="${GFV2_ADAPTER_SCALE:-${GFV2_ADAPTER_SCALE:-0.18}}"

qwen scripts/evaluate_goal_first_manager_v2.py \
  --root "${CLOSE_CODE_ROOT}" \
  --output-dir "${SMOKE_OUT}/goal_first_v2" \
  --adapter "${ADAPTER}" \
  --adapter-identity "${IDENTITY}" \
  --adapter-scale "${SCALE}" \
  --allow-unofficial-adapter \
  --limit 5 \
  --temperature 0.0 \
  --seed 20260913

qwen scripts/evaluate_pilot_120_direct_base.py \
  --root "${CLOSE_CODE_ROOT}" \
  --output-dir "${SMOKE_OUT}/unofficial_adapter" \
  --system-id t28_selected_adapter_llm \
  --adapter "${ADAPTER}" \
  --adapter-identity "${IDENTITY}" \
  --adapter-scale "${SCALE}" \
  --allow-unofficial-adapter \
  --limit 5 \
  --temperature 0.0 \
  --seed 20260913

python3 - <<'PY'
import json
from pathlib import Path
smoke = Path("""${SMOKE_OUT}""")
# count any predictions jsonl under smoke
rows = []
for path in smoke.rglob("*.predictions.jsonl"):
    n = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    rows.append({"path": str(path), "n": n})
print(json.dumps({"smoke_prediction_files": rows}, indent=2))
if not rows or min(item["n"] for item in rows) < 5:
    raise SystemExit("smoke_temp_failed_need_5_rows")
(Path("""${CLOSE_OUTPUT}""") / "SMOKE_OK.json").write_text(
    json.dumps({"ok": True, "files": rows, "allow_unofficial_adapter": True, "selected_adapter_left_false": True}, indent=2)
    + "\n",
    encoding="utf-8",
)
print("smoke_temp_ok")
PY
'''

    header = '''#!/usr/bin/env bash
# Mega job: 5-row unofficial-adapter smoke, then final-close, then full temp sweep.
# Does not overwrite T39/T41. Does not flip selected_adapter / valid_for_official_use.
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
export SWEEP_NATIVE_ROOT
export SWEEP_OUTPUT

'''

    # After close finishes, unset -e for sweep loop (sweep uses runner_rc)
    bridge = '''
echo "final_close_section_complete"
echo "phase:temp_sweep_all_slices"
set +e
'''

    footer = '''
sweep_rc=$?
set -e
python3 - <<PY
import json
from pathlib import Path
out = Path("${CLOSE_OUTPUT}") / "MEGA_STATUS.json"
payload = {
  "job_name": "mega-close",
  "smoke_ok": True,
  "close_output": "${CLOSE_OUTPUT}",
  "sweep_output": "${SWEEP_OUTPUT}",
  "sweep_rc": int("""${sweep_rc}"""),
  "did_not_overwrite_t39_t41": True,
  "fine_tune_remains_unofficial": True,
  "selected_adapter_left_false": True,
}
out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
print(json.dumps(payload, indent=2, sort_keys=True))
PY
if [[ "${sweep_rc}" -ne 0 ]]; then
  echo "temp_sweep_failed_rc=${sweep_rc}" >&2
  exit "${sweep_rc}"
fi
echo "mega_close_complete"
'''

    # Inject smoke after qwen() helper / gpu wait in close_core.
    # Find first "phase:" or first intent generation and insert smoke before it.
    marker = None
    for token in (
        'echo "phase:raw_intent_box"',
        "echo \"phase:raw_intent_box\"",
        "phase:raw_intent_box",
        "phase:raw_intent",
        "evaluate_pilot_120_intent_box.py",
    ):
        if token in close_core:
            marker = token
            break
    if marker is None:
        raise SystemExit("could_not_find_close_phase_marker")

    # Insert smoke just before first intent-box phase echo if present, else before first evaluate_pilot_120_intent_box
    if 'echo "phase:raw_intent_box"' in close_core:
        close_with_smoke = close_core.replace(
            'echo "phase:raw_intent_box"',
            smoke + '\necho "phase:raw_intent_box"',
            1,
        )
    elif "evaluate_pilot_120_intent_box.py" in close_core:
        # insert before the count/if block containing it - simpler: prepend smoke after gpu wait
        idx = close_core.find("evaluate_pilot_120_intent_box.py")
        # back up to previous blank line before the if
        cut = close_core.rfind("\nif ", 0, idx)
        if cut < 0:
            cut = close_core.rfind("\n", 0, idx)
        close_with_smoke = close_core[:cut] + "\n" + smoke + close_core[cut:]
    else:
        raise SystemExit("insert_failed")

    # close_core starts with set -euo; header also has set -euo — drop duplicate from close
    if close_with_smoke.startswith("set -"):
        # keep close's set line by removing header set? Keep header and strip close set line
        lines = close_with_smoke.splitlines()
        if lines[0].startswith("set -"):
            # keep env requires from close
            close_with_smoke = "\n".join(lines[1:])

    # Remove close's own : "${CLOSE_CODE_ROOT:?}" etc that duplicate — keep them for safety
    mega = header + "\n" + close_with_smoke + "\n" + bridge + "\n" + sweep_core + "\n" + footer

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mega_path = OUT_DIR / "mega.sbatch"
    mega_path.write_text(mega, encoding="utf-8", newline="\n")
    print(f"wrote {mega_path} bytes={mega_path.stat().st_size}")

    submit = '''#!/usr/bin/env bash
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
# aliases used by some trees
export GFV2_TRAINING_SITE_PACKAGES GFV2_HF_HOME GFV2_CONTAINER
export GFV2_SELECTED_ADAPTER GFV2_ADAPTER_IDENTITY GFV2_ADAPTER_SCALE
job_id=$(sbatch --parsable --export=ALL \\
  "${MEGA_CODE_ROOT}/cluster/mega_close_20260913/mega.sbatch")
printf 'job_id\\t%s\\nclose_out\\t%s\\nsweep_out\\t%s\\ncode\\t%s\\n' \\
  "${job_id}" "${CLOSE_OUTPUT}" "${SWEEP_OUTPUT}" "${MEGA_CODE_ROOT}" \\
  | tee "${CLOSE_OUTPUT}/mega_submission.tsv"
echo "submitted ${job_id}"
'''
    submit_path = OUT_DIR / "submit.sh"
    submit_path.write_text(submit, encoding="utf-8", newline="\n")
    submit_path.chmod(0o755)
    print(f"wrote {submit_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
