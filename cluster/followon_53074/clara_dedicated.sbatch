#!/usr/bin/env bash
# Dedicated CLARA native runs (Gemma then GLM). CLARA is required, not optional.
# Skips systems already complete under FOLLOWON_OUTPUT/native/*/clara (avoid double-run).
#SBATCH --job-name=clara-native
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=3-00:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/clara-native-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/clara-native-%j.err

set -euo pipefail
umask 077
: "${FOLLOWON_NATIVE_ROOT:?}"
: "${CLARA_OUTPUT:?}"
: "${A01_CONTAINER_SIF:?}"
: "${GFV2_CODE_ROOT:?}"
: "${FOLLOWON_OUTPUT:=}"

mkdir -p "${CLARA_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs
cd "${GFV2_CODE_ROOT}"

EXPECTED_CLARA_ROWS="${EXPECTED_CLARA_ROWS:-10444}"

# If follow-on already finished both CLARA natives, exit 0 immediately (no GPU waste).
if [[ -n "${FOLLOWON_OUTPUT}" ]]; then
  python3 - <<'PY'
import json, os, sys
from pathlib import Path
follow = Path(os.environ["FOLLOWON_OUTPUT"])
expected = int(os.environ.get("EXPECTED_CLARA_ROWS", "10444"))
ok = True
for system in ("gemma4", "glm47"):
    pred = follow / "native" / system / "clara" / "predictions.jsonl"
    if not pred.is_file():
        ok = False
        break
    n = sum(1 for line in pred.open(encoding="utf-8") if line.strip())
    if n < expected:
        ok = False
        break
if ok:
    note = {
        "status": "SKIPPED_FOLLOWON_CLARA_COMPLETE",
        "expected_rows": expected,
        "followon_output": str(follow),
    }
    Path(os.environ["CLARA_OUTPUT"]).mkdir(parents=True, exist_ok=True)
    (Path(os.environ["CLARA_OUTPUT"]) / "skip_manifest.json").write_text(
        json.dumps(note, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(note, sort_keys=True))
    sys.exit(0)
print("followon_clara_incomplete_or_missing; continuing dedicated run")
PY
fi

GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
if [[ "${GPU_USED}" -gt 1000 ]]; then
  echo "busy_gpu:${GPU_USED}" >&2
  exit 42
fi

export A01_CONTAINER_SIF A01_MAX_MODEL_LEN="${A01_MAX_MODEL_LEN:-8192}" A02_READY_TIMEOUT_SECONDS="${A02_READY_TIMEOUT_SECONDS:-900}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1

python3 - <<'PY'
import json, os
from pathlib import Path
out = Path(os.environ["CLARA_OUTPUT"])
native = os.environ["FOLLOWON_NATIVE_ROOT"]
follow = Path(os.environ.get("FOLLOWON_OUTPUT") or "")
expected = int(os.environ.get("EXPECTED_CLARA_ROWS", "10444"))
ports = {"gemma4": 8511, "glm47": 8512}
models = {
    "gemma4": ("/home-mscluster/mbangie/models/dual_llm_benchmark_v1/gemma-4-26b-a4b-it", "4d7ae4984b7db7de8f8457170b3f1a419ee76d52"),
    "glm47": ("/home-mscluster/mbangie/models/dual_llm_benchmark_v1/glm-4.7-flash-bf16", "7dd20894a642a0aa287e9827cb1a1f7f91386b67"),
}

def followon_clara_complete(system: str) -> bool:
    if not follow:
        return False
    pred = follow / "native" / system / "clara" / "predictions.jsonl"
    if not pred.is_file():
        return False
    n = sum(1 for line in pred.open(encoding="utf-8") if line.strip())
    return n >= expected

tasks = []
for system, (model, revision) in models.items():
    if followon_clara_complete(system):
        print(f"skip_task {system}_clara already_complete_under_followon")
        continue
    dest = out / system / "clara"
    dest.mkdir(parents=True, exist_ok=True)
    runner_args = [
        "--task", "clara",
        "--packet", f"{native}/inputs/clara.jsonl",
        "--prompt", f"{native}/protocol/clara_context_routing_prompt_v1.txt",
        "--model", model,
        "--revision", revision,
        "--port", str(ports[system]),
        "--out", str(dest / "predictions.jsonl"),
        "--manifest-out", str(dest / "run_manifest.json"),
        "--seed", "20260911",
    ]
    argv = [
        "python3",
        f"{native}/scripts/annotation/server_lifecycle.py",
        "--model", model,
        "--revision", revision,
        "--port", str(ports[system]),
        "--runner", f"{native}/scripts/run_native_context_structured.py",
        "--log", str(dest / "server.log"),
        "--runner-args",
        *runner_args,
    ]
    tasks.append({
        "id": f"{system}_clara",
        "required": True,
        "min_remaining_seconds": 3600,
        "expected_rows": expected,
        "argv": argv,
    })

if not tasks:
    note = {"status": "SKIPPED_NO_REMAINING_CLARA_TASKS", "followon_output": str(follow)}
    (out / "skip_manifest.json").write_text(json.dumps(note, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(note, sort_keys=True))
    raise SystemExit(0)

(out / "tasks.json").write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out / 'tasks.json'} n_tasks={len(tasks)}")
PY

exec python3 "${GFV2_CODE_ROOT}/scripts/cluster_isolated_task_runner.py" \
  --tasks "${CLARA_OUTPUT}/tasks.json" \
  --output-dir "${CLARA_OUTPUT}"
