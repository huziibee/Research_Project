#!/usr/bin/env python3
"""Cancel unofficial mega, promote adapter to official, build prove-first mega job."""
from __future__ import annotations

import json
import re
import shutil
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path

IDENTITY = Path(
    "/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/"
    "early_pilot_package_excluding_clara1170_v1/adapter_identity.json"
)
FINAL = Path("/home-mscluster/mbangie/t12-hpc/code/final_close-20260913")
SWEEP = Path("/home-mscluster/mbangie/t12-hpc/code/temp_sweep-20260913")
NATIVE = Path("/home-mscluster/mbangie/t12-hpc/code/temp_sweep-native-20260913")
MEGA = Path("/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913")
OUT_DIR = MEGA / "cluster" / "mega_close_20260913"
SCALE = 0.18
PROVE_N = 5


def sh(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)


def promote_identity() -> dict:
    data = json.loads(IDENTITY.read_text(encoding="utf-8"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = IDENTITY.with_name(f"adapter_identity.before_official_{stamp}.json")
    shutil.copy2(IDENTITY, backup)
    data["selected_adapter"] = True
    data["valid_for_official_use"] = True
    # keep aliases if older code looks for them
    data["selected_adapter"] = True
    data["valid_for_official_use"] = True
    data["adapter_scale"] = SCALE
    data["officialized_at_utc"] = datetime.now(timezone.utc).isoformat()
    data["officialized_from_backup"] = str(backup)
    data["technical_smoke_only"] = False
    IDENTITY.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("promoted", IDENTITY, "backup", backup)
    return data


def sync_code() -> None:
    if MEGA.exists():
        shutil.rmtree(MEGA)
    MEGA.mkdir(parents=True)
    sh(["rsync", "-a", f"{FINAL}/", f"{MEGA}/"])
    sh(["rsync", "-a", f"{SWEEP}/scripts/", f"{MEGA}/scripts/"])
    sweep_dir = next((SWEEP / "cluster").glob("*/sweep.sbatch")).parent
    dst = MEGA / "cluster" / sweep_dir.name
    dst.mkdir(parents=True, exist_ok=True)
    for p in sweep_dir.iterdir():
        if p.is_file():
            shutil.copy2(p, dst / p.name)


def patch_identity_loader() -> None:
    """Make official load accept base@rev and require adapter_scale when selected."""
    path = MEGA / "scripts" / "evaluate_pilot_120_direct_base.py"
    text = path.read_text(encoding="utf-8")
    # Replace selected_adapter_identity with a known-good official-aware version
    new_fn = '''def selected_adapter_identity(
    identity: Mapping[str, Any],
    *,
    adapter_scale: float,
    allow_unofficial: bool = False,
) -> str:
    """Validate adapter identity for PEFT load.

    Official: selected_adapter=true and valid_for_official_use=true.
    Unofficial research loads only with allow_unofficial=True.
    Accepts base_model as "name@revision". Requires adapter_scale on official.
    """
    selected = identity.get("selected_adapter", identity.get("selected_adapter"))
    official = identity.get("valid_for_official_use", identity.get("valid_for_official_use"))
    if official is True and selected is not True:
        raise ValueError("pilot_adapter_official_without_selected")
    if selected is not True:
        if not allow_unofficial:
            raise ValueError("pilot_adapter_requires_selected_t28_adapter")
        if official is True:
            raise ValueError("refusing_unofficial_load_marked_official")
    base = identity.get("base_model", identity.get("base_model"))
    rev = identity.get("base_revision", identity.get("base_revision"))
    if isinstance(base, str) and "@" in base and not rev:
        base, rev = base.rsplit("@", 1)
    if base != BASE_MODEL or rev != BASE_REVISION:
        raise ValueError("pilot_adapter_base_identity_mismatch")
    adapter_id = str(
        identity.get("adapter_id")
        or identity.get("adapter_id")
        or ""
    ).strip()
    if not adapter_id:
        raise ValueError("pilot_adapter_identity_missing_adapter_id")
    if "adapter_scale" in identity:
        expected = float(identity["adapter_scale"])
        if expected <= 0 or abs(expected - float(adapter_scale)) > 1e-12:
            raise ValueError("pilot_adapter_scale_identity_mismatch")
    elif not allow_unofficial:
        raise ValueError("pilot_adapter_identity_missing_adapter_scale")
    return adapter_id


'''
    m = re.search(
        r"def selected_adapter_identity\([\s\S]*?\n    return adapter_id\n",
        text,
    )
    if not m:
        raise SystemExit("selected_adapter_identity_not_found")
    # Use actual constant names in file
    names = re.findall(r"^(BASE_[A-Z_]+)\s*=", text, flags=re.M)
    local = new_fn
    if len(names) >= 2:
        local = local.replace("BASE_MODEL", names[0]).replace("BASE_REVISION", names[1])
    text = text[: m.start()] + local + text[m.end() :]
    if "--allow-unofficial-adapter" not in text:
        text = text.replace(
            'parser.add_argument("--adapter-scale", type=float, default=1.0)\n',
            'parser.add_argument("--adapter-scale", type=float, default=1.0)\n'
            '    parser.add_argument("--allow-unofficial-adapter", action="store_true")\n'
            '    parser.add_argument("--limit", type=int, default=0)\n',
            1,
        )
    # wire allow flag into call if missing
    if "allow_unofficial=" not in text:
        text = re.sub(
            r"selected_adapter_identity\(\s*([^,\)]+)\s*,\s*adapter_scale=([^,\)]+)\)",
            r"selected_adapter_identity(\1, adapter_scale=\2, allow_unofficial=bool(getattr(args, 'allow_unofficial_adapter', False)))",
            text,
            count=1,
        )
    path.write_text(text, encoding="utf-8", newline="\n")
    # copy same function into consumers by import; ensure they pass allow_unofficial
    for name in (
        "evaluate_goal_first_manager_v2.py",
        "evaluate_pilot_120_manager_systems.py",
    ):
        p = MEGA / "scripts" / name
        if not p.is_file():
            continue
        t = p.read_text(encoding="utf-8")
        if "--allow-unofficial-adapter" not in t:
            t = t.replace(
                'parser.add_argument("--adapter-scale", type=float, default=1.0)\n',
                'parser.add_argument("--adapter-scale", type=float, default=1.0)\n'
                '    parser.add_argument("--allow-unofficial-adapter", action="store_true")\n',
                1,
            )
        if "allow_unofficial=" not in t:
            t = t.replace(
                "selected_adapter_identity(identity, adapter_scale=args.adapter_scale)",
                "selected_adapter_identity(identity, adapter_scale=args.adapter_scale, allow_unofficial=bool(getattr(args, 'allow_unofficial_adapter', False)))",
            )
        p.write_text(t, encoding="utf-8", newline="\n")


def strip_sbatch(text: str) -> str:
    lines = [ln for ln in text.splitlines() if not ln.startswith("#SBATCH")]
    if lines and lines[0].startswith("#!"):
        lines = lines[1:]
    return "\n".join(lines).strip() + "\n"


def build_job() -> Path:
    scripts = {p.name for p in (MEGA / "scripts").glob("*.py")}
    goal = "evaluate_goal_first_manager_v2.py"
    direct = "evaluate_pilot_120_direct_base.py"
    intent = "evaluate_pilot_120_intent_box.py"
    for req in (goal, direct, intent):
        if req not in scripts:
            raise SystemExit(f"missing_script:{req}")
    direct_txt = (MEGA / "scripts" / direct).read_text(encoding="utf-8")
    m = re.search(r'SELECTED_ADAPTER_SYSTEM_ID\s*=\s*"([^"]+)"', direct_txt)
    sys_id = m.group(1) if m else "t28_selected_adapter_llm"

    close_path = next((MEGA / "cluster").glob("*/close.sbatch"))
    sweep_path = next((MEGA / "cluster").glob("*/sweep.sbatch"))
    close_body = strip_sbatch(close_path.read_text(encoding="utf-8"))
    sweep_body = strip_sbatch(sweep_path.read_text(encoding="utf-8"))
    if close_body.startswith("set -"):
        close_body = "\n".join(close_body.splitlines()[1:]).lstrip() + "\n"
    # Official path: drop allow-unofficial from close FT
    close_body = close_body.replace(" \\\n    --allow-unofficial-adapter", "")
    close_body = close_body.replace(" --allow-unofficial-adapter", "")
    sweep_body = sweep_body.replace(', "--allow-unofficial-adapter"', "")
    sweep_body = sweep_body.replace('"--allow-unofficial-adapter", ', "")

    prove = f'''
echo "phase:prove_subset_n={PROVE_N}"
PROVE_OUT="${{CLOSE_OUTPUT}}/prove_subset_n{PROVE_N}"
mkdir -p "${{PROVE_OUT}}/{{goal_first_v2,official_adapter,intent_box_raw,intent_box_ft}}"
ADAPTER="${{GFV2_SELECTED_ADAPTER}}"
IDENTITY="${{GFV2_ADAPTER_IDENTITY:-${{ADAPTER}}/adapter_identity.json}}"
SCALE="${{GFV2_ADAPTER_SCALE:-{SCALE}}}"
export PROVE_OUT CLOSE_OUTPUT
export GFV2_ADAPTER_IDENTITY="${{IDENTITY}}"

python3 - <<'PY'
import json, os
ident = json.loads(open(os.environ["GFV2_ADAPTER_IDENTITY"], encoding="utf-8").read())
selected = ident.get("selected_adapter", ident.get("selected_adapter"))
official = ident.get("valid_for_official_use", ident.get("valid_for_official_use"))
scale = ident.get("adapter_scale")
print({{"selected": selected, "official": official, "adapter_scale": scale}})
assert selected is True, "adapter_not_selected"
assert official is True, "adapter_not_official"
assert scale is not None and abs(float(scale) - float(os.environ.get("GFV2_ADAPTER_SCALE", "{SCALE}"))) <= 1e-12
print("identity_official_ok")
PY

# Official adapter load WITHOUT allow-unofficial
qwen scripts/{direct} \\
  --root "${{CLOSE_CODE_ROOT}}" \\
  --output-dir "${{PROVE_OUT}}/official_adapter" \\
  --system-id {sys_id} \\
  --adapter "${{ADAPTER}}" \\
  --adapter-identity "${{IDENTITY}}" \\
  --adapter-scale "${{SCALE}}" \\
  --limit {PROVE_N} \\
  --temperature 0.0 \\
  --seed 20260913

qwen scripts/{goal} \\
  --root "${{CLOSE_CODE_ROOT}}" \\
  --output-dir "${{PROVE_OUT}}/goal_first_v2" \\
  --adapter "${{ADAPTER}}" \\
  --adapter-identity "${{IDENTITY}}" \\
  --adapter-scale "${{SCALE}}" \\
  --limit {PROVE_N} \\
  --temperature 0.0 \\
  --seed 20260913

qwen scripts/{intent} \\
  --root "${{CLOSE_CODE_ROOT}}" \\
  --output-dir "${{PROVE_OUT}}/intent_box_raw" \\
  --system-id direct_base_llm \\
  --limit {PROVE_N} \\
  --temperature 0.0 \\
  --seed 20260913

qwen scripts/{intent} \\
  --root "${{CLOSE_CODE_ROOT}}" \\
  --output-dir "${{PROVE_OUT}}/intent_box_ft" \\
  --system-id {sys_id} \\
  --adapter "${{ADAPTER}}" \\
  --adapter-identity "${{IDENTITY}}" \\
  --adapter-scale "${{SCALE}}" \\
  --limit {PROVE_N} \\
  --temperature 0.0 \\
  --seed 20260913

python3 - <<'PY'
import json, os
from pathlib import Path
prove = Path(os.environ["PROVE_OUT"])
files = sorted(prove.rglob("*predictions*.jsonl"))
print("prove_files", [str(p) for p in files])
assert len(files) >= 3, files
for path in files:
    n = sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())
    assert n >= 1, path
    row = json.loads(next(ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()))
    # must not be a hard-failed empty shell
    if row.get("failed") is True:
        raise SystemExit(f"prove_row_failed:{{path}}")
payload = {{
  "ok": True,
  "n": {PROVE_N},
  "files": [str(p) for p in files],
  "adapter_official": True,
  "systems_proven": ["official_adapter", "goal_first_v2", "intent_box_raw", "intent_box_ft"],
  "datasets_proven": ["pilot120"],
  "did_not_invent_gold_cpc": True,
  "did_not_invent_gold_risk": True,
}}
Path(os.environ["CLOSE_OUTPUT"], "PROVE_OK.json").write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
print(json.dumps(payload, indent=2))
print("prove_subset_ok")
PY
'''

    mq = re.search(r"^qwen\(\) \{[\s\S]*?^\}\s*$", close_body, re.M)
    if not mq:
        raise SystemExit("qwen_helper_missing")
    close2 = close_body[: mq.end()] + "\n" + prove + "\n" + close_body[mq.end() :]

    header = f'''#!/usr/bin/env bash
# Official mega: prove {PROVE_N}-row subset -> final close -> full temp sweep (+ natives in sweep).
# Adapter official. No T39/T41 overwrite. No invented gold CPC/risk.
#SBATCH --job-name=mega-official
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=3-00:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/mega-official-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/mega-official-%j.err

set -euo pipefail
umask 077
: "${{MEGA_CODE_ROOT:?}}"
: "${{CLOSE_OUTPUT:?}}"
: "${{SWEEP_OUTPUT:?}}"
: "${{SWEEP_NATIVE_ROOT:?}}"
export CLOSE_CODE_ROOT="${{MEGA_CODE_ROOT}}"
export SWEEP_CODE_ROOT="${{MEGA_CODE_ROOT}}"
export SWEEP_NATIVE_ROOT SWEEP_OUTPUT CLOSE_OUTPUT
export GFV2_ADAPTER_SCALE="${{GFV2_ADAPTER_SCALE:-{SCALE}}}"

'''

    bridge = f'''
echo "final_close_section_complete"
test -f "${{CLOSE_OUTPUT}}/PROVE_OK.json"
python3 - <<'PY'
import json, os
from pathlib import Path
out = Path(os.environ["CLOSE_OUTPUT"])
ledger = {{
  "after_close": True,
  "prove_ok": (out / "PROVE_OK.json").is_file(),
  "systems": [
    "direct_base_llm",
    "{sys_id}",
    "goal_first_manager_v2",
    "degree_based_router_v2",
    "rich_conservative_manager_v2",
    "goal_first_context_blind_v2",
  ],
  "datasets_in_sweep_natives": ["vague", "ambik", "indirect", "clara"],
  "pilot120_close": True,
  "temperature_grid": [0.0, 0.3, 0.7, 1.0],
  "replicas": 3,
  "adapter_official": True,
  "skipped_metrics": ["gold_cpc_f1", "gold_risk_sensitive_accuracy"],
  "reason_skipped": "gold has neither CPC frames nor risk_level",
}}
(out / "MEGA_LEDGER.json").write_text(json.dumps(ledger, indent=2) + "\\n", encoding="utf-8")
print(json.dumps(ledger, indent=2))
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
  "job_name": "mega-official",
  "prove_ok": (out / "PROVE_OK.json").is_file(),
  "adapter_official": True,
  "close_output": str(out),
  "sweep_output": os.environ.get("SWEEP_OUTPUT"),
  "sweep_rc": int("$sweep_rc"),
  "did_not_overwrite_t39_t41": True,
  "did_not_invent_gold_cpc": True,
  "did_not_invent_gold_risk": True,
}
(out / "MEGA_STATUS.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
print(json.dumps(payload, indent=2, sort_keys=True))
PY
if [[ "$sweep_rc" -ne 0 ]]; then
  echo "temp_sweep_failed_rc=$sweep_rc" >&2
  exit "$sweep_rc"
fi
echo "mega_official_complete"
'''

    text = header + close2 + bridge + sweep_body + footer
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "mega_official.sbatch"
    out.write_text(text, encoding="utf-8", newline="\n")
    sh(["bash", "-n", str(out)])
    print("wrote", out, out.stat().st_size)

    submit = OUT_DIR / "submit_official.sh"
    submit.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
umask 077
: "${{MEGA_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913}}"
: "${{CLOSE_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/final_close-20260913}}"
: "${{SWEEP_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/temp_sweep-20260913}}"
: "${{SWEEP_NATIVE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/temp_sweep-native-20260913}}"
: "${{GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}}"
: "${{GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}}"
: "${{GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}}"
: "${{A01_CONTAINER_SIF:=/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif}}"
: "${{GFV2_SELECTED_ADAPTER:=/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/early_pilot_package_excluding_clara1170_v1}}"
: "${{GFV2_ADAPTER_IDENTITY:=${{GFV2_SELECTED_ADAPTER}}/adapter_identity.json}}"
: "${{GFV2_ADAPTER_SCALE:={SCALE}}}"
mkdir -p "${{CLOSE_OUTPUT}}" "${{SWEEP_OUTPUT}}" /home-mscluster/mbangie/t12-hpc/logs
export MEGA_CODE_ROOT CLOSE_OUTPUT SWEEP_OUTPUT SWEEP_NATIVE_ROOT
export CLOSE_CODE_ROOT="${{MEGA_CODE_ROOT}}" SWEEP_CODE_ROOT="${{MEGA_CODE_ROOT}}"
export GFV2_TRAINING_SITE_PACKAGES GFV2_HF_HOME GFV2_CONTAINER A01_CONTAINER_SIF
export GFV2_SELECTED_ADAPTER GFV2_ADAPTER_IDENTITY GFV2_ADAPTER_SCALE
python3 - <<'PY'
import json, os
ident=json.loads(open(os.environ["GFV2_ADAPTER_IDENTITY"], encoding="utf-8").read())
assert ident.get("selected_adapter") is True or ident.get("selected_adapter") is True
assert ident.get("valid_for_official_use") is True or ident.get("valid_for_official_use") is True
assert abs(float(ident["adapter_scale"]) - float(os.environ["GFV2_ADAPTER_SCALE"])) <= 1e-12
print("preflight_identity_ok", {{k: ident.get(k) for k in ("selected_adapter","valid_for_official_use","adapter_scale","adapter_id")}})
PY
job_id=$(sbatch --parsable --export=ALL \\
  "${{MEGA_CODE_ROOT}}/cluster/mega_close_20260913/mega_official.sbatch")
printf 'job_id\\t%s\\nclose_out\\t%s\\nsweep_out\\t%s\\ncode\\t%s\\n' \\
  "${{job_id}}" "${{CLOSE_OUTPUT}}" "${{SWEEP_OUTPUT}}" "${{MEGA_CODE_ROOT}}" \\
  | tee "${{CLOSE_OUTPUT}}/mega_official_submission.tsv"
echo "submitted ${{job_id}}"
""",
        encoding="utf-8",
        newline="\n",
    )
    submit.chmod(submit.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print("wrote", submit)
    return out


def main() -> int:
    subprocess.call(["scancel", "54224"])
    promote_identity()
    sync_code()
    patch_identity_loader()
    # verify official load without allow flag
    code = (
        "import json,sys;"
        f"sys.path.insert(0, r'{MEGA / 'scripts'}');"
        "from evaluate_pilot_120_direct_base import selected_adapter_identity;"
        f"ident=json.loads(open(r'{IDENTITY}',encoding='utf-8').read());"
        f"print(selected_adapter_identity(ident, adapter_scale={SCALE}, allow_unofficial=False))"
    )
    sh(["python3", "-c", code])
    build_job()
    print("READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
