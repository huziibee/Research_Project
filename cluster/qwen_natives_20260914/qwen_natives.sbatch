#!/usr/bin/env bash
# Qwen / official adapter on the four native packets (T=0, one replica).
# Same official fields as Gemma/GLM natives. Not Pilot-120 manager routing.
#SBATCH --job-name=qwen-natives
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=3-00:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/qwen-natives-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/qwen-natives-%j.err

set -euo pipefail
umask 077
: "${QWEN_NATIVE_CODE_ROOT:?}"
: "${QWEN_NATIVE_OUTPUT:?}"
: "${SWEEP_NATIVE_ROOT:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_CONTAINER:?}"
: "${GFV2_SELECTED_ADAPTER:?}"
: "${GFV2_ADAPTER_IDENTITY:?}"
: "${GFV2_ADAPTER_SCALE:?}"

export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
cd "${QWEN_NATIVE_CODE_ROOT}"
mkdir -p "${QWEN_NATIVE_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs

GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
GPU_USED="${GPU_USED%% *}"
if [[ "${GPU_USED}" -gt 1000 ]]; then
  echo "busy_gpu:${GPU_USED}" >&2
  exit 42
fi

ENV_CSV="PYTHONPATH=${GFV2_TRAINING_SITE_PACKAGES}:${QWEN_NATIVE_CODE_ROOT}/src:${QWEN_NATIVE_CODE_ROOT}/scripts,HF_HOME=${GFV2_HF_HOME},HUGGINGFACE_HUB_CACHE=${GFV2_HF_HOME}/hub,TRANSFORMERS_CACHE=${GFV2_HF_HOME}/hub"
qwen() {
  /usr/bin/apptainer exec --nv --cleanenv --env "${ENV_CSV}" "${GFV2_CONTAINER}" python3 "$@"
}

count_jsonl() {
  local path="$1"
  if [[ ! -f "${path}" ]]; then
    echo 0
    return
  fi
  python3 -c "import pathlib; print(sum(1 for line in pathlib.Path('${path}').read_text(encoding='utf-8').splitlines() if line.strip()))"
}

NATIVE="${SWEEP_NATIVE_ROOT}"
ADAPTER="${GFV2_SELECTED_ADAPTER}"
IDENTITY="${GFV2_ADAPTER_IDENTITY}"
SCALE="${GFV2_ADAPTER_SCALE}"
SEED=20260914

declare -a TASKS=(vague ambik indirect clara)
declare -a PACKETS=(vague_inference_packet.jsonl ambik_packet.jsonl indirect.jsonl clara.jsonl)
declare -a PROMPTS=(vague_goal_triplet_prompt_v1.txt ambik_ambiguity_type_prompt_v2_safety_first.txt indirect_pragmatic_prompt_v1.txt clara_context_routing_prompt_v1.txt)
declare -a EXPECTED=(3354 1000 906 10444)

echo "phase:prove_n4"
PROVE="${QWEN_NATIVE_OUTPUT}/prove_n4"
mkdir -p "${PROVE}/direct_base_llm/vague" "${PROVE}/t28_selected_adapter_llm/vague"
qwen scripts/run_native_qwen_generate.py \
  --task vague \
  --packet "${NATIVE}/inputs/vague_inference_packet.jsonl" \
  --prompt "${NATIVE}/protocol/vague_goal_triplet_prompt_v1.txt" \
  --output-dir "${PROVE}/direct_base_llm/vague" \
  --system-id direct_base_llm \
  --limit 4 --temperature 0.0 --seed "${SEED}"
qwen scripts/run_native_qwen_generate.py \
  --task vague \
  --packet "${NATIVE}/inputs/vague_inference_packet.jsonl" \
  --prompt "${NATIVE}/protocol/vague_goal_triplet_prompt_v1.txt" \
  --output-dir "${PROVE}/t28_selected_adapter_llm/vague" \
  --system-id t28_selected_adapter_llm \
  --adapter "${ADAPTER}" \
  --adapter-identity "${IDENTITY}" \
  --adapter-scale "${SCALE}" \
  --limit 4 --temperature 0.0 --seed "${SEED}"
python3 - <<'PY'
from pathlib import Path
import os
prove = Path(os.environ["QWEN_NATIVE_OUTPUT"]) / "prove_n4"
for path in prove.rglob("predictions.jsonl"):
    n = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    assert n >= 4, path
print("prove_ok")
PY

run_task() {
  local system="$1"
  local task="$2"
  local packet="$3"
  local prompt="$4"
  local expected="$5"
  local dest="${QWEN_NATIVE_OUTPUT}/${system}/${task}"
  mkdir -p "${dest}"
  local have
  have="$(count_jsonl "${dest}/predictions.jsonl")"
  if [[ "${have}" -ge "${expected}" ]]; then
    echo "skip:${system}:${task}:${have}"
    return 0
  fi
  echo "phase:${system}:${task}:have=${have}:need=${expected}"
  extra=()
  if [[ "${system}" == "t28_selected_adapter_llm" ]]; then
    extra=(--adapter "${ADAPTER}" --adapter-identity "${IDENTITY}" --adapter-scale "${SCALE}")
  fi
  qwen scripts/run_native_qwen_generate.py \
    --task "${task}" \
    --packet "${NATIVE}/inputs/${packet}" \
    --prompt "${NATIVE}/protocol/${prompt}" \
    --output-dir "${dest}" \
    --system-id "${system}" \
    --temperature 0.0 \
    --seed "${SEED}" \
    "${extra[@]}"
}

for system in direct_base_llm t28_selected_adapter_llm; do
  for i in 0 1 2 3; do
    run_task "${system}" "${TASKS[$i]}" "${PACKETS[$i]}" "${PROMPTS[$i]}" "${EXPECTED[$i]}"
  done
done

python3 - <<PY
import json, os
from pathlib import Path
out = Path(os.environ["QWEN_NATIVE_OUTPUT"])
payload = {
  "job_name": "qwen-natives",
  "systems": ["direct_base_llm", "t28_selected_adapter_llm"],
  "tasks": ["vague", "ambik", "indirect", "clara"],
  "temperature": 0.0,
  "seed": 20260914,
  "not_pilot120_manager_routing": True,
  "degree_timid_not_applicable": True,
  "clara_context_blind_is_packet_condition": True,
  "gemma_glm_natives_remain_separate": True,
  "output": str(out),
}
(out / "QWEN_NATIVES_STATUS.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(json.dumps(payload, indent=2))
PY
echo "qwen_natives_complete"
