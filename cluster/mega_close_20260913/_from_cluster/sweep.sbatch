#!/usr/bin/env bash
# Generation-only temperature sweep. New versioned dirs only.
# Logical grid: idx = temp_i * 3 + replica_i for idx in 0..11.
# A Slurm --array=0-11 is rejected on mss_biggpu (MaxSubmitJobsPerUser=6)
# and would not run in parallel anyway (MaxJobsPerUser=1). This one job
# walks all 12 slices with skip-if-exists so a requeue can continue.
#SBATCH --job-name=temp-sweep
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=3-00:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/temp-sweep-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/temp-sweep-%j.err

set -u
umask 077
: "${SWEEP_CODE_ROOT:?}"
: "${SWEEP_NATIVE_ROOT:?}"
: "${SWEEP_OUTPUT:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_CONTAINER:?}"
: "${A01_CONTAINER_SIF:?}"

export A01_CONTAINER_SIF A01_MAX_MODEL_LEN="${A01_MAX_MODEL_LEN:-8192}" A02_READY_TIMEOUT_SECONDS="${A02_READY_TIMEOUT_SECONDS:-900}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1

case "${SWEEP_CODE_ROOT}${SWEEP_NATIVE_ROOT}${SWEEP_OUTPUT}" in
  *t39*|*t41*|*goal_first_v2-20260911*|*goal_first_followon-20260912b*)
    echo "refusing_frozen_path" >&2
    exit 2
    ;;
esac

cd "${SWEEP_CODE_ROOT}"
mkdir -p /home-mscluster/mbangie/t12-hpc/logs

GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
if [[ "${GPU_USED}" -gt 1000 ]]; then
  echo "busy_gpu:${GPU_USED}" >&2
  exit 42
fi

sweep_seconds_left() {
  python3 - <<'PY'
import os
import time
end = os.environ.get("SLURM_JOB_END_TIME", "")
if end.isdigit():
    print(max(0, int(float(end) - time.time())))
else:
    print(999999)
PY
}

final_rc=0
for IDX in 0 1 2 3 4 5 6 7 8 9 10 11; do
SECS_LEFT="$(sweep_seconds_left)"
if [[ "${SECS_LEFT}" -lt 7200 ]]; then
  echo "stop_for_requeue:seconds_left=${SECS_LEFT}:next_idx=${IDX}"
  break
fi
TEMP_I=$((IDX / 3))
REPLICA_I=$((IDX % 3))
TEMPS=(0.0 0.3 0.7 1.0)
TEMP="${TEMPS[$TEMP_I]}"
REPLICA_N=$((REPLICA_I + 1))
REPLICA="R${REPLICA_N}"
TEMP_HUNDRED="$(python3 -c "print(int(float('${TEMP}') * 100))")"
SEED=$((20260913 + REPLICA_I * 1000 + TEMP_HUNDRED))
SLICE_OUT="${SWEEP_OUTPUT}/T${TEMP}/${REPLICA}"

export SWEEP_TEMP="${TEMP}" SWEEP_REPLICA="${REPLICA}" SWEEP_REPLICA_I="${REPLICA_I}"
export SWEEP_SEED="${SEED}" SWEEP_SLICE_OUT="${SLICE_OUT}"
export SWEEP_ARRAY_TASK_ID="${IDX}"

mkdir -p "${SLICE_OUT}"
echo "starting_slice:idx=${IDX}:T${TEMP}/${REPLICA}:seed=${SEED}"

python3 - <<'PY'
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

code = os.environ["SWEEP_CODE_ROOT"]
native = os.environ["SWEEP_NATIVE_ROOT"]
container = os.environ["GFV2_CONTAINER"]
site = os.environ["GFV2_TRAINING_SITE_PACKAGES"]
hf = os.environ["GFV2_HF_HOME"]
adapter = os.environ.get("GFV2_SELECTED_ADAPTER", "")
identity = os.environ.get("GFV2_ADAPTER_IDENTITY", "")
scale = os.environ.get("GFV2_ADAPTER_SCALE", "0.18")
temp = os.environ["SWEEP_TEMP"]
replica = os.environ["SWEEP_REPLICA"]
replica_i = int(os.environ["SWEEP_REPLICA_I"])
seed = int(os.environ["SWEEP_SEED"])
out = Path(os.environ["SWEEP_SLICE_OUT"])
out.mkdir(parents=True, exist_ok=True)

env = (
    f"PYTHONPATH={site}:{code}/src:{code}/scripts,"
    f"HF_HOME={hf},"
    f"HUGGINGFACE_HUB_CACHE={hf}/hub,"
    f"TRANSFORMERS_CACHE={hf}/hub"
)

V2_SYSTEMS = (
    "goal_first_manager_v2",
    "rich_conservative_manager_v2",
    "goal_first_context_blind_v2",
    "degree_based_router_v2",
)
OLD_SYSTEMS = (
    "degree_based_router",
    "context_blind_manager",
    "full_type_risk_aware_manager",
)


def jsonl_count(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def complete_named(directory: Path, names: tuple[str, ...], expected: int) -> bool:
    return all(jsonl_count(directory / "predictions" / f"{name}.predictions.jsonl") >= expected for name in names)


def complete_file(path: Path, expected: int) -> bool:
    return jsonl_count(path) >= expected


def retire_incomplete(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path.rename(path.with_name(f"{path.name}.incomplete.{stamp}"))


def qwen_cmd(inner: list[str]) -> list[str]:
    return [
        "bash",
        "-lc",
        "cd " + json.dumps(code) + " && " + " ".join(
            json.dumps(part)
            for part in ["/usr/bin/apptainer", "exec", "--nv", "--cleanenv", "--env", env, container, *inner]
        ),
    ]


def native_task(system: str, task: str, packet: str, prompt: str, expected: int, port: int) -> dict | None:
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
    pred = dest / "predictions.jsonl"
    if complete_file(pred, expected):
        return None
    for leftover in (pred, dest / "run_manifest.json"):
        retire_incomplete(leftover)
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
            "--out", str(pred),
            "--manifest-out", str(dest / "run_manifest.json"),
            "--seed", str(seed),
            "--temperature", temp,
        ]
    )
    return {
        "id": f"{system}_{task}",
        "required": True,
        "min_remaining_seconds": 7200 if task == "clara" else 3600,
        "expected_rows": expected,
        "argv": [
            "python3",
            f"{native}/scripts/annotation/server_lifecycle.py",
            "--model", model,
            "--revision", revision,
            "--port", str(port),
            "--runner", f"{native}/{runner}",
            "--log", str(dest / "server.log"),
            "--runner-args",
            *runner_args,
        ],
    }


tasks: list[dict] = []
skipped: list[dict] = []

v2_dir = out / "goal_first_v2"
if complete_named(v2_dir, V2_SYSTEMS, 120):
    skipped.append({"id": "goal_first_v2", "reason": "predictions_120_of_120"})
else:
    inner = [
        "python3",
        "scripts/evaluate_goal_first_manager_v2.py",
        "--root", code,
        "--output-dir", str(v2_dir),
        "--temperature", temp,
        "--seed", str(seed),
    ]
    if adapter:
        inner.extend(["--adapter", adapter, "--adapter-identity", identity, "--adapter-scale", scale])
    tasks.append({"id": "goal_first_v2", "required": True, "min_remaining_seconds": 1800, "argv": qwen_cmd(inner)})

base_dir = out / "direct_base"
base_pred = base_dir / "direct_base_llm.predictions.jsonl"
if complete_file(base_pred, 120):
    skipped.append({"id": "direct_base", "reason": "predictions_120_of_120"})
else:
    inner = [
        "python3",
        "scripts/evaluate_pilot_120_direct_base.py",
        "--root", code,
        "--output-dir", str(base_dir),
        "--system-id", "direct_base_llm",
        "--temperature", temp,
        "--seed", str(seed),
    ]
    tasks.append({"id": "direct_base", "required": True, "min_remaining_seconds": 1800, "argv": qwen_cmd(inner)})

adapter_dir = out / "unofficial_adapter"
adapter_pred = adapter_dir / "t28_selected_adapter_llm.predictions.jsonl"
if complete_file(adapter_pred, 120):
    skipped.append({"id": "unofficial_adapter", "reason": "predictions_120_of_120"})
else:
    if not adapter:
        raise SystemExit("unofficial_adapter_path_missing")
    inner = [
        "python3",
        "scripts/evaluate_pilot_120_direct_base.py",
        "--root", code,
        "--output-dir", str(adapter_dir),
        "--system-id", "t28_selected_adapter_llm",
        "--adapter", adapter,
        "--adapter-identity", identity,
        "--adapter-scale", scale,
        "--temperature", temp,
        "--seed", str(seed),
    ]
    tasks.append({"id": "unofficial_adapter", "required": True, "min_remaining_seconds": 1800, "argv": qwen_cmd(inner)})

old_dir = out / "old_manager"
if complete_named(old_dir, OLD_SYSTEMS, 120):
    skipped.append({"id": "old_manager", "reason": "predictions_120_of_120"})
else:
    inner = [
        "python3",
        "scripts/evaluate_pilot_120_manager_systems.py",
        "--root", code,
        "--output-dir", str(old_dir),
        "--temperature", temp,
        "--seed", str(seed),
    ]
    if adapter:
        inner.extend(["--adapter", adapter, "--adapter-identity", identity, "--adapter-scale", scale])
    tasks.append({"id": "old_manager", "required": True, "min_remaining_seconds": 1800, "argv": qwen_cmd(inner)})

ports = {"gemma4": 8601, "glm47": 8602}
packets = (
    ("vague", "vague_inference_packet.jsonl", "vague_goal_triplet_prompt_v1.txt", 3354),
    ("ambik", "ambik_packet.jsonl", "ambik_ambiguity_type_prompt_v2_safety_first.txt", 1000),
    ("indirect", "indirect.jsonl", "indirect_pragmatic_prompt_v1.txt", 906),
    ("clara", "clara.jsonl", "clara_context_routing_prompt_v1.txt", 10444),
)
for system in ("gemma4", "glm47"):
    for task, packet, prompt, expected in packets:
        built = native_task(system, task, packet, prompt, expected, ports[system])
        if built is None:
            skipped.append({"id": f"{system}_{task}", "reason": "predictions_expected_rows"})
        else:
            tasks.append(built)

plan = {
    "temperature": float(temp),
    "replica": replica,
    "replica_index": replica_i,
    "seed": seed,
    "seed_formula": "20260913 + replica_i * 1000 + int(temp * 100)",
    "array_task_id": int(os.environ["SWEEP_ARRAY_TASK_ID"]),
    "job_id": os.environ.get("SLURM_JOB_ID"),
    "array_job_id": os.environ.get("SLURM_ARRAY_JOB_ID"),
    "node": os.environ.get("SLURMD_NODENAME"),
    "output_dir": str(out),
    "claim_boundary": (
        "Generation temperature sweep only. New versioned dirs. Adapter unofficial. "
        "No official two-judge SGC. Do not mint task success from routes. "
        "Do not gold-fill empty native outputs. Does not overwrite T39/T41 or frozen goal_first trees."
    ),
    "started_at_utc": datetime.now(timezone.utc).isoformat(),
    "started_at_epoch": time.time(),
    "n_tasks": len(tasks),
    "skipped": skipped,
    "task_ids": [task["id"] for task in tasks],
}
(out / "slice_plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
(out / "tasks.json").write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"slice": str(out), "n_tasks": len(tasks), "skipped": [item["id"] for item in skipped]}, sort_keys=True))
PY

runner_rc=0
if python3 -c "import json,sys; sys.exit(0 if json.load(open('${SLICE_OUT}/tasks.json',encoding='utf-8')) else 1)"; then
  python3 "${SWEEP_CODE_ROOT}/scripts/cluster_isolated_task_runner.py" \
    --tasks "${SLICE_OUT}/tasks.json" \
    --output-dir "${SLICE_OUT}"
  runner_rc=$?
else
  echo "all_slice_tasks_already_complete:${SLICE_OUT}"
fi

python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

out = Path(os.environ["SWEEP_SLICE_OUT"])
plan = json.loads((out / "slice_plan.json").read_text(encoding="utf-8"))
ledger = []
ledger_path = out / "task_ledger.jsonl"
if ledger_path.is_file():
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ledger.append(json.loads(line))
plan["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
plan["task_ledger_status"] = [item.get("status") for item in ledger]
plan["status"] = "SLICE_COMPLETE"
(out / "slice_manifest.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {out / 'slice_manifest.json'}")
PY

if [[ "${runner_rc}" -ne 0 ]]; then
  final_rc=2
fi
echo "finished_slice:idx=${IDX}:T${TEMP}/${REPLICA}:rc=${runner_rc}"
done
exit "${final_rc}"
