#!/usr/bin/env bash
# Follow-on after goal-first v2 replica 1 (job 53074).
# Stage A: Qwen3-8B v2 replicas R2 then R3 on the frozen 53074 code tree.
# Stage B: Gemma then GLM native VAGUE/AmbiK/Indirect; CLARA last if time remains.
# Does not rerun or overwrite T39/T41.
#SBATCH --job-name=gf-followon
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=3-00:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/gf-followon-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/gf-followon-%j.err

set -u
umask 077
: "${GFV2_CODE_ROOT:?}"
: "${FOLLOWON_OUTPUT:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_CONTAINER:?}"
: "${FOLLOWON_NATIVE_ROOT:?}"
: "${A01_CONTAINER_SIF:?}"

export A01_CONTAINER_SIF A01_MAX_MODEL_LEN="${A01_MAX_MODEL_LEN:-8192}" A02_READY_TIMEOUT_SECONDS="${A02_READY_TIMEOUT_SECONDS:-900}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1

cd "${GFV2_CODE_ROOT}"
mkdir -p "${FOLLOWON_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs

GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
if [[ "${GPU_USED}" -gt 1000 ]]; then
  echo "busy_gpu:${GPU_USED}" >&2
  exit 42
fi

python3 - <<'PY'
import json
import os
from pathlib import Path

out = Path(os.environ["FOLLOWON_OUTPUT"])
code = os.environ["GFV2_CODE_ROOT"]
native = os.environ["FOLLOWON_NATIVE_ROOT"]
container = os.environ["GFV2_CONTAINER"]
site = os.environ["GFV2_TRAINING_SITE_PACKAGES"]
hf = os.environ["GFV2_HF_HOME"]
adapter = os.environ.get("GFV2_SELECTED_ADAPTER", "")
identity = os.environ.get("GFV2_ADAPTER_IDENTITY", "")
scale = os.environ.get("GFV2_ADAPTER_SCALE", "0.18")
env = (
    f"PYTHONPATH={site}:{code}/src,"
    f"HF_HOME={hf},"
    f"HUGGINGFACE_HUB_CACHE={hf}/hub,"
    f"TRANSFORMERS_CACHE={hf}/hub"
)

def qwen_eval(replica: str) -> list[str]:
    inner = [
        "python3",
        "scripts/evaluate_goal_first_manager_v2.py",
        "--root",
        code,
        "--output-dir",
        str(out / replica / "manager"),
    ]
    if adapter:
        inner.extend(
            ["--adapter", adapter, "--adapter-identity", identity, "--adapter-scale", scale]
        )
    return [
        "bash",
        "-lc",
        "cd " + json.dumps(code) + " && " + " ".join(json.dumps(part) for part in [
            "/usr/bin/apptainer", "exec", "--nv", "--cleanenv", "--env", env, container, *inner
        ]),
    ]

def native_task(system: str, task: str, packet: str, prompt: str, expected: int, port: int) -> dict:
    model = {
        "gemma4": "/home-mscluster/mbangie/models/dual_llm_benchmark_v1/gemma-4-26b-a4b-it",
        "glm47": "/home-mscluster/mbangie/models/dual_llm_benchmark_v1/glm-4.7-flash-bf16",
    }[system]
    revision = {
        "gemma4": "4d7ae4984b7db7de8f8457170b3f1a419ee76d52",
        "glm47": "7dd20894a642a0aa287e9827cb1a1f7f91386b67",
    }[system]
    runner = {
        "vague": "scripts/run_vague_goal_triplet.py",
        "ambik": "scripts/run_ambik_ambiguity_type.py",
        "clara": "scripts/run_native_context_structured.py",
        "indirect": "scripts/run_native_context_structured.py",
    }[task]
    dest = out / "native" / system / task
    dest.mkdir(parents=True, exist_ok=True)
    runner_args: list[str] = []
    if task in {"clara", "indirect"}:
        runner_args.extend(["--task", task])
    runner_args.extend(
        [
            "--packet", f"{native}/inputs/{packet}",
            "--prompt", f"{native}/protocol/{prompt}",
            "--model", model,
            "--revision", revision,
            "--port", str(port),
            "--out", str(dest / "predictions.jsonl"),
            "--manifest-out", str(dest / "run_manifest.json"),
            "--seed", "20260911",
        ]
    )
    argv = [
        "python3",
        f"{native}/scripts/annotation/server_lifecycle.py",
        "--model", model,
        "--revision", revision,
        "--port", str(port),
        "--runner", f"{native}/{runner}",
        "--log", str(dest / "server.log"),
        "--runner-args",
        *runner_args,
    ]
    return {
        "id": f"{system}_{task}",
        "required": True,
        "min_remaining_seconds": 7200 if task == "clara" else 3600,
        "expected_rows": expected,
        "argv": argv,
    }

tasks = [
    {"id": "v2_R2", "required": True, "min_remaining_seconds": 1800, "argv": qwen_eval("R2")},
    {"id": "v2_R3", "required": True, "min_remaining_seconds": 1800, "argv": qwen_eval("R3")},
]
ports = {"gemma4": 8501, "glm47": 8502}
packets = (
    ("vague", "vague_inference_packet.jsonl", "vague_goal_triplet_prompt_v1.txt", 3354),
    ("ambik", "ambik_packet.jsonl", "ambik_ambiguity_type_prompt_v2_safety_first.txt", 1000),
    ("indirect", "indirect.jsonl", "indirect_pragmatic_prompt_v1.txt", 906),
    ("clara", "clara.jsonl", "clara_context_routing_prompt_v1.txt", 10444),
)
for system in ("gemma4", "glm47"):
    for task, packet, prompt, expected in packets:
        tasks.append(native_task(system, task, packet, prompt, expected, ports[system]))

(out / "tasks.json").write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out / 'tasks.json'} n_tasks={len(tasks)}")
PY

exec python3 "${GFV2_CODE_ROOT}/scripts/cluster_isolated_task_runner.py" \
  --tasks "${FOLLOWON_OUTPUT}/tasks.json" \
  --output-dir "${FOLLOWON_OUTPUT}"
