#!/usr/bin/env bash
# Retry only the three failed follow-on natives. Does not overwrite complete files.
# Order: Gemma Indirect, GLM AmbiK, GLM Indirect.
#SBATCH --job-name=gf-native-retry
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=1-00:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/gf-native-retry-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/gf-native-retry-%j.err

set -euo pipefail
umask 077
: "${FOLLOWON_NATIVE_ROOT:?}"
: "${FOLLOWON_OUTPUT:?}"
: "${GFV2_CODE_ROOT:?}"
: "${A01_CONTAINER_SIF:?}"

export A01_CONTAINER_SIF A01_MAX_MODEL_LEN="${A01_MAX_MODEL_LEN:-8192}" A02_READY_TIMEOUT_SECONDS="${A02_READY_TIMEOUT_SECONDS:-900}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1

mkdir -p "${FOLLOWON_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs
cd "${GFV2_CODE_ROOT}"

GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
if [[ "${GPU_USED}" -gt 1000 ]]; then
  echo "busy_gpu:${GPU_USED}" >&2
  exit 42
fi

export RETRY_OUT="${FOLLOWON_OUTPUT}/native_retry"
mkdir -p "${RETRY_OUT}"

python3 - <<'PY'
import json, os
from pathlib import Path

out = Path(os.environ["FOLLOWON_OUTPUT"])
native = os.environ["FOLLOWON_NATIVE_ROOT"]
retry_out = Path(os.environ.get("RETRY_OUT") or (out / "native_retry"))
ports = {"gemma4": 8521, "glm47": 8522}
models = {
    "gemma4": ("/home-mscluster/mbangie/models/dual_llm_benchmark_v1/gemma-4-26b-a4b-it", "4d7ae4984b7db7de8f8457170b3f1a419ee76d52"),
    "glm47": ("/home-mscluster/mbangie/models/dual_llm_benchmark_v1/glm-4.7-flash-bf16", "7dd20894a642a0aa287e9827cb1a1f7f91386b67"),
}
wanted = (
    ("gemma4", "indirect", "indirect.jsonl", "indirect_pragmatic_prompt_v1.txt", 906),
    ("glm47", "ambik", "ambik_packet.jsonl", "ambik_ambiguity_type_prompt_v2_safety_first.txt", 1000),
    ("glm47", "indirect", "indirect.jsonl", "indirect_pragmatic_prompt_v1.txt", 906),
)

def complete(system: str, task: str, expected: int) -> bool:
    pred = out / "native" / system / task / "predictions.jsonl"
    if not pred.is_file():
        return False
    n = sum(1 for line in pred.open(encoding="utf-8") if line.strip())
    return n >= expected

tasks = []
skipped = []
for system, task, packet, prompt, expected in wanted:
    dest = out / "native" / system / task
    dest.mkdir(parents=True, exist_ok=True)
    if complete(system, task, expected):
        skipped.append({"id": f"{system}_{task}", "status": "SKIPPED_ALREADY_COMPLETE", "expected_rows": expected})
        print(f"skip_task {system}_{task} already_complete")
        continue
    for leftover in (dest / "predictions.jsonl", dest / "run_manifest.json"):
        if leftover.exists():
            raise SystemExit(f"partial_output_exists:{leftover}")
    model, revision = models[system]
    runner = f"{native}/scripts/run_ambik_ambiguity_type.py" if task == "ambik" else f"{native}/scripts/run_native_context_structured.py"
    runner_args = []
    if task != "ambik":
        runner_args.extend(["--task", task])
    runner_args.extend([
        "--packet", f"{native}/inputs/{packet}",
        "--prompt", f"{native}/protocol/{prompt}",
        "--model", model,
        "--revision", revision,
        "--port", str(ports[system]),
        "--out", str(dest / "predictions.jsonl"),
        "--manifest-out", str(dest / "run_manifest.json"),
        "--seed", "20260911",
    ])
    argv = [
        "python3",
        f"{native}/scripts/annotation/server_lifecycle.py",
        "--model", model,
        "--revision", revision,
        "--port", str(ports[system]),
        "--runner", runner,
        "--log", str(dest / "retry_server.log"),
        "--runner-args",
        *runner_args,
    ]
    tasks.append({
        "id": f"{system}_{task}",
        "required": True,
        "min_remaining_seconds": 1800,
        "expected_rows": expected,
        "argv": argv,
    })

(retry_out / "skip_manifest.json").write_text(json.dumps({"skipped": skipped}, indent=2) + "\n", encoding="utf-8")
if not tasks:
    print(json.dumps({"status": "SKIPPED_NO_REMAINING_NATIVE_RETRIES", "skipped": skipped}, sort_keys=True))
    raise SystemExit(0)
(retry_out / "tasks.json").write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
print(f"wrote {retry_out / 'tasks.json'} n_tasks={len(tasks)}")
PY

if [[ ! -f "${RETRY_OUT}/tasks.json" ]]; then
  echo "no_retry_tasks"
  exit 0
fi

exec python3 "${GFV2_CODE_ROOT}/scripts/cluster_isolated_task_runner.py" \
  --tasks "${RETRY_OUT}/tasks.json" \
  --output-dir "${RETRY_OUT}"
