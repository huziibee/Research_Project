#!/usr/bin/env bash
# Official close-out: comparable intent boxes + two-judge intent on those boxes
# and on the existing new-manager intent_summary. Does not overwrite T39/T41.
#SBATCH --job-name=final-close
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=2-00:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/final-close-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/final-close-%j.err

set -euo pipefail
umask 077
: "${CLOSE_CODE_ROOT:?}"
: "${CLOSE_OUTPUT:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_CONTAINER:?}"
: "${A01_CONTAINER_SIF:?}"

export A01_CONTAINER_SIF A01_MAX_MODEL_LEN="${A01_MAX_MODEL_LEN:-8192}" A02_READY_TIMEOUT_SECONDS="${A02_READY_TIMEOUT_SECONDS:-900}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1

case "${CLOSE_CODE_ROOT}${CLOSE_OUTPUT}" in
  *t39*|*t41*|*goal_first_v2-20260911*|*goal_first_followon-20260912b*)
    echo "refusing_frozen_path" >&2
    exit 2
    ;;
esac

cd "${CLOSE_CODE_ROOT}"
mkdir -p "${CLOSE_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs

ENV_CSV="PYTHONPATH=${GFV2_TRAINING_SITE_PACKAGES}:${CLOSE_CODE_ROOT}/src:${CLOSE_CODE_ROOT}/scripts,HF_HOME=${GFV2_HF_HOME},HUGGINGFACE_HUB_CACHE=${GFV2_HF_HOME}/hub,TRANSFORMERS_CACHE=${GFV2_HF_HOME}/hub"
QWEN=(/usr/bin/apptainer exec --nv --cleanenv --env "${ENV_CSV}" "${GFV2_CONTAINER}" python3)
RAW_OUT="${CLOSE_OUTPUT}/intent_box/direct_base_llm"
FT_OUT="${CLOSE_OUTPUT}/intent_box/t28_selected_adapter_llm"
BOX_PACKET="${CLOSE_OUTPUT}/packets/intent_box_sgc"
GFV2_PACKET="${CLOSE_CODE_ROOT}/outputs/gfv2_intent_summary_sgc_packet_20260913"
PROTO="${CLOSE_CODE_ROOT}/pilot120_intent_evaluation_20260902/pilot120_intent_evaluation_20260902/protocol"
INTENT_GOLD="${CLOSE_CODE_ROOT}/pilot120_intent_evaluation_20260902/pilot120_intent_evaluation_20260902/data/intent_gold_references_120.jsonl"
PILOT_GOLD="${CLOSE_CODE_ROOT}/data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl"
ADAPTER="${GFV2_SELECTED_ADAPTER:-/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/early_pilot_package_excluding_clara1170_v1}"
IDENTITY="${GFV2_ADAPTER_IDENTITY:-${ADAPTER}/adapter_identity.json}"
export GFV2_ADAPTER_IDENTITY="${IDENTITY}"

for path in \
  "${GFV2_PACKET}/blind_judge_pass_1_120.jsonl" \
  "${GFV2_PACKET}/blind_judge_pass_2_120.jsonl" \
  "${PROTO}/JUDGE_GUIDE.md" \
  "${PROTO}/JUDGE_PROMPT.txt" \
  "${PROTO}/judge_output_schema.json" \
  "${PROTO}/synthetic_judge_calibration.jsonl" \
  "${INTENT_GOLD}" \
  "${PILOT_GOLD}" \
  "${CLOSE_CODE_ROOT}/scripts/evaluate_pilot_120_intent_box.py" \
  "${CLOSE_CODE_ROOT}/scripts/build_intent_box_sgc_packet_20260913.py" \
  "${CLOSE_CODE_ROOT}/scripts/finalize_sgc_rates_20260913.py" \
  "${CLOSE_CODE_ROOT}/scripts/semantic_intent/run_blind_semantic_judge.py" \
  "${CLOSE_CODE_ROOT}/scripts/annotation/server_lifecycle.py" \
  "${IDENTITY}"
do
  if [[ ! -f "${path}" ]]; then
    echo "missing_preflight:${path}" >&2
    exit 2
  fi
done

python3 - <<'PY'
import json, os, sys
ident = json.loads(open(os.environ["GFV2_ADAPTER_IDENTITY"], encoding="utf-8").read())
if ident.get("valid_for_official_use") is True:
    print("refusing_official_adapter_flip", file=sys.stderr)
    raise SystemExit(2)
print("adapter_identity_ok selected_adapter=%s valid_for_official_use=%s" % (
    ident.get("selected_adapter"), ident.get("valid_for_official_use")))
PY

for _wait in $(seq 1 30); do
  GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
  GPU_USED="${GPU_USED%% *}"
  if [[ "${GPU_USED}" -le 1000 ]]; then
    echo "gpu_free:${GPU_USED}"
    break
  fi
  echo "waiting_gpu:${GPU_USED}:try=${_wait}"
  sleep 20
done
if [[ "${GPU_USED}" -gt 1000 ]]; then
  echo "busy_gpu:${GPU_USED}" >&2
  exit 42
fi

qwen() {
  "${QWEN[@]}" "$@"
}

count_jsonl() {
  local path="$1"
  if [[ ! -f "${path}" ]]; then
    echo 0
    return
  fi
  python3 -c "import pathlib; p=pathlib.Path('${path}'); print(sum(1 for line in p.read_text(encoding='utf-8').splitlines() if line.strip()))"
}

if [[ "$(count_jsonl "${RAW_OUT}/direct_base_llm.predictions.jsonl")" -lt 120 ]]; then
  echo "phase:raw_intent_box"
  mkdir -p "${RAW_OUT}"
  qwen scripts/evaluate_pilot_120_intent_box.py \
    --root "${CLOSE_CODE_ROOT}" \
    --output-dir "${RAW_OUT}" \
    --system-id direct_base_llm \
    --temperature 0.0 \
    --seed 20260913
else
  echo "skip:raw_intent_box"
fi

if [[ "$(count_jsonl "${FT_OUT}/t28_selected_adapter_llm.predictions.jsonl")" -lt 120 ]]; then
  echo "phase:fine_tune_intent_box"
  mkdir -p "${FT_OUT}"
  qwen scripts/evaluate_pilot_120_intent_box.py \
    --root "${CLOSE_CODE_ROOT}" \
    --output-dir "${FT_OUT}" \
    --system-id t28_selected_adapter_llm \
    --adapter "${ADAPTER}" \
    --adapter-identity "${IDENTITY}" \
    --adapter-scale "${GFV2_ADAPTER_SCALE:-0.18}" \
    --allow-unofficial-adapter \
    --temperature 0.0 \
    --seed 20260913
else
  echo "skip:fine_tune_intent_box"
fi

echo "phase:speech_act_local"
python3 "${CLOSE_CODE_ROOT}/scripts/score_intent_box_speech_act_20260913.py" \
  "${RAW_OUT}/direct_base_llm.predictions.jsonl" \
  "${PILOT_GOLD}" \
  "${CLOSE_OUTPUT}/intent_box/direct_base_llm.speech_act.json"
python3 "${CLOSE_CODE_ROOT}/scripts/score_intent_box_speech_act_20260913.py" \
  "${FT_OUT}/t28_selected_adapter_llm.predictions.jsonl" \
  "${PILOT_GOLD}" \
  "${CLOSE_OUTPUT}/intent_box/t28_selected_adapter_llm.speech_act.json"

if [[ ! -f "${BOX_PACKET}/blind_judge_pass_1_120.jsonl" ]]; then
  echo "phase:build_box_packet"
  qwen scripts/build_intent_box_sgc_packet_20260913.py \
    --raw "${RAW_OUT}/direct_base_llm.predictions.jsonl" \
    --fine-tune "${FT_OUT}/t28_selected_adapter_llm.predictions.jsonl" \
    --out "${BOX_PACKET}"
else
  echo "skip:build_box_packet"
fi

run_judge_packet() {
  local name="$1"
  local packet="$2"
  local dest="${CLOSE_OUTPUT}/judges/${name}"
  mkdir -p "${dest}"
  local judge_id model revision
  for spec in "Judge_A|/home-mscluster/mbangie/models/dual_llm_benchmark_v1/gemma-4-26b-a4b-it|4d7ae4984b7db7de8f8457170b3f1a419ee76d52" \
              "Judge_B|/home-mscluster/mbangie/models/dual_llm_benchmark_v1/glm-4.7-flash-bf16|7dd20894a642a0aa287e9827cb1a1f7f91386b67"; do
    IFS='|' read -r judge_id model revision <<<"${spec}"
    local pass
    for pass in 1 2; do
      local out="${dest}/${judge_id}_pass_${pass}.jsonl"
      if [[ "$(count_jsonl "${out}")" -ge 120 ]]; then
        echo "skip:${name}:${judge_id}:pass${pass}"
        continue
      fi
      echo "phase:judge:${name}:${judge_id}:pass${pass}"
      python3 "${CLOSE_CODE_ROOT}/scripts/annotation/server_lifecycle.py" \
        --model "${model}" \
        --revision "${revision}" \
        --port $((8100 + pass)) \
        --log "${dest}/${judge_id}_pass_${pass}.server.log" \
        --runner "${CLOSE_CODE_ROOT}/scripts/semantic_intent/run_blind_semantic_judge.py" \
        --runner-args \
          --packet "${packet}/blind_judge_pass_${pass}_120.jsonl" \
          --guide "${PROTO}/JUDGE_GUIDE.md" \
          --prompt "${PROTO}/JUDGE_PROMPT.txt" \
          --schema "${PROTO}/judge_output_schema.json" \
          --calibration "${PROTO}/synthetic_judge_calibration.jsonl" \
          --judge-id "${judge_id}" \
          --model "${model}" \
          --revision "${revision}" \
          --port $((8100 + pass)) \
          --out "${out}" \
          --manifest-out "${dest}/${judge_id}_pass_${pass}.manifest.json" \
          --seed $((20260913 + pass))
    done
    python3 - <<PY
from pathlib import Path
dest = Path("${dest}")
parts = []
for pass_i in (1, 2):
    path = dest / f"${judge_id}_pass_{pass_i}.jsonl"
    parts.append(path.read_text(encoding="utf-8"))
(dest / f"${judge_id}_combined.jsonl").write_text("".join(parts), encoding="utf-8")
PY
  done
  mkdir -p "${dest}/final"
  qwen scripts/finalize_sgc_rates_20260913.py \
    --judge-a "${dest}/Judge_A_combined.jsonl" \
    --judge-b "${dest}/Judge_B_combined.jsonl" \
    --mapping "${packet}/SEALED_evaluation_mapping.jsonl" \
    --out "${dest}/final"
}

run_judge_packet "gfv2_intent_summary" "${GFV2_PACKET}"
run_judge_packet "intent_box_raw_ft" "${BOX_PACKET}"

python3 - <<PY
import json
from pathlib import Path
out = Path("${CLOSE_OUTPUT}") / "CLOSE_STATUS.json"
payload = {
    "job_name": "final-close",
    "did_not_overwrite_t39_t41": True,
    "did_not_rerun_new_manager": True,
    "used_existing_gfv2_intent_summary_packet": True,
    "generated_comparable_intent_boxes_for_raw_and_fine_tune": True,
    "fine_tune_remains_unofficial": True,
    "did_not_invent_gold_cpc": True,
    "did_not_invent_gold_risk": True,
    "qwen_natives_not_in_this_job": True,
    "outputs": str(Path("${CLOSE_OUTPUT}")),
}
out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(payload, indent=2, sort_keys=True))
PY
echo "final_close_complete"
