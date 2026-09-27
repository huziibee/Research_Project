#!/usr/bin/env bash
# T0.7 matched baseline completion: Raw + Fine-Tune intent_box @ T=0.7 seed 0,
# then official two-judge on Raw/FT + existing GF/Blind T0.7 intents.
#SBATCH --job-name=p120-t07-match
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
#SBATCH --time=2-00:00:00
#SBATCH --exclude=mscluster106,mscluster107,mscluster108,mscluster109,mscluster111
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/p120-t07-match-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/p120-t07-match-%j.err

set -euo pipefail
umask 077

: "${T07_CODE_ROOT:?}"
: "${T07_OUTPUT:?}"
: "${GFV2_CONTAINER:?}"
: "${GFV2_HF_HOME:?}"
: "${GFV2_TRAINING_SITE_PACKAGES:?}"
: "${A01_CONTAINER_SIF:?}"

CODE="${T07_CODE_ROOT}"
OUT="${T07_OUTPUT}"
EXP="${OUT}/t07_matched_baseline_completion_20260922"
ADAPTER="${GFV2_SELECTED_ADAPTER:-/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/early_pilot_package_excluding_clara1170_v1}"
IDENTITY="${GFV2_ADAPTER_IDENTITY:-${ADAPTER}/adapter_identity.json}"
PROTO="${CODE}/pilot120_intent_evaluation_20260902/pilot120_intent_evaluation_20260902/protocol"
export A01_CONTAINER_SIF A01_MAX_MODEL_LEN="${A01_MAX_MODEL_LEN:-8192}" A02_READY_TIMEOUT_SECONDS="${A02_READY_TIMEOUT_SECONDS:-1800}"
export A01_GPU_MEM_UTIL="${A01_GPU_MEM_UTIL:-0.70}"
export APPTAINER_BIND="${APPTAINER_BIND:-/home-mscluster/mbangie/models:/home-mscluster/mbangie/models,/home-mscluster/mbangie/t12-hpc:/home-mscluster/mbangie/t12-hpc}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export GFV2_ADAPTER_IDENTITY="${IDENTITY}"

mkdir -p "${EXP}" /home-mscluster/mbangie/t12-hpc/logs
cd "${CODE}"

# Exclusive node can still show leftover VRAM from the previous occupant.
# Wait rather than instant-fail (58561 died in 0s on busy_gpu:29800).
GPU_USED=999999
for attempt in $(seq 1 18); do
  GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 || echo 999999)"
  GPU_USED="${GPU_USED%% *}"
  GPU_USED="${GPU_USED:-999999}"
  echo "gpu_preflight attempt=${attempt} used_mib=${GPU_USED}"
  nvidia-smi || true
  if [[ "${GPU_USED}" -le 1000 ]]; then
    break
  fi
  sleep 20
done
if [[ "${GPU_USED}" -gt 1000 ]]; then
  echo "busy_gpu:${GPU_USED}" >&2
  exit 42
fi

test -f "${EXP}/01_manifest.json" || { echo "missing_freeze" >&2; exit 2; }
test -f "${IDENTITY}" || { echo "missing_adapter_identity" >&2; exit 3; }
test -f "${PROTO}/JUDGE_PROMPT.txt" || { echo "missing_judge_protocol" >&2; exit 4; }

python3 - <<'PY'
import json, os, sys
ident = json.loads(open(os.environ["GFV2_ADAPTER_IDENTITY"], encoding="utf-8").read())
# Identity was unofficial at T0 final-close; officialized 2026-09-13 on the same adapter path.
# Accept either: official+selected, or unofficial with allow flag at emit time.
official = ident.get("valid_for_official_use") is True
selected = ident.get("selected_adapter") is True
if official and not selected:
    print("official_adapter_requires_selected", file=sys.stderr)
    raise SystemExit(2)
print(
    "adapter_ok selected=%s official=%s id=%s scale=%s"
    % (selected, official, ident.get("adapter_id"), ident.get("adapter_scale"))
)
PY

ENV_CSV="PYTHONPATH=${GFV2_TRAINING_SITE_PACKAGES}:${CODE}/src:${CODE}/scripts,HF_HOME=${GFV2_HF_HOME},HUGGINGFACE_HUB_CACHE=${GFV2_HF_HOME}/hub,TRANSFORMERS_CACHE=${GFV2_HF_HOME}/hub,HOME=${HOME},PATH=/usr/local/bin:/usr/bin:/bin"
QWEN=(/usr/bin/apptainer exec --nv --cleanenv --env "${ENV_CSV}" --bind "${CODE}:${CODE}" --bind "${OUT}:${OUT}" --bind "${GFV2_HF_HOME}:${GFV2_HF_HOME}" --bind "${GFV2_TRAINING_SITE_PACKAGES}:${GFV2_TRAINING_SITE_PACKAGES}" --bind "$(dirname "${ADAPTER}"):$(dirname "${ADAPTER}")" "${GFV2_CONTAINER}" python3)

qwen() { "${QWEN[@]}" "$@"; }

count_jsonl() {
  local path="$1"
  if [[ ! -f "${path}" ]]; then echo 0; return; fi
  python3 -c "import pathlib; p=pathlib.Path('${path}'); print(sum(1 for line in p.read_text(encoding='utf-8').splitlines() if line.strip()))"
}

RAW_DIR="${EXP}/emit/direct_base_llm"
FT_DIR="${EXP}/emit/t28_selected_adapter_llm"
RAW_PRED="${EXP}/06_raw_qwen_t07.predictions.jsonl"
FT_PRED="${EXP}/07_finetune_t07.predictions.jsonl"

# Existing manager artifacts (do not re-emit)
GF_PRED="${T07_GF_PREDS:-${CODE}/artifacts_t07/goal_first_manager_v2.predictions.jsonl}"
BLIND_PRED="${T07_BLIND_PREDS:-${CODE}/artifacts_t07/goal_first_context_blind_v2.predictions.jsonl}"
DEGREE_PRED="${T07_DEGREE_PREDS:-${CODE}/artifacts_t07/degree_based_router_v2.predictions.jsonl}"
TIMID_PRED="${T07_TIMID_PREDS:-${CODE}/artifacts_t07/rich_conservative_manager_v2.predictions.jsonl}"

for p in "${GF_PRED}" "${BLIND_PRED}" "${DEGREE_PRED}" "${TIMID_PRED}"; do
  test -f "${p}" || { echo "missing_manager_artifact:${p}" >&2; exit 5; }
done

if [[ "$(count_jsonl "${RAW_PRED}")" -lt 120 ]]; then
  echo "phase:raw_intent_box_t07"
  mkdir -p "${RAW_DIR}"
  qwen scripts/evaluate_pilot_120_intent_box.py \
    --root "${CODE}" \
    --output-dir "${RAW_DIR}" \
    --system-id direct_base_llm \
    --temperature 0.7 \
    --seed 0
  cp -f "${RAW_DIR}/direct_base_llm.predictions.jsonl" "${RAW_PRED}"
else
  echo "skip:raw_intent_box_t07"
fi

if [[ "$(count_jsonl "${FT_PRED}")" -lt 120 ]]; then
  echo "phase:finetune_intent_box_t07"
  mkdir -p "${FT_DIR}"
  # Adapter identity is now official+selected (officialized 2026-09-13 on same weights).
  # Do not pass --allow-unofficial-adapter when valid_for_official_use is true.
  FT_ARGS=(
    scripts/evaluate_pilot_120_intent_box.py
    --root "${CODE}"
    --output-dir "${FT_DIR}"
    --system-id t28_selected_adapter_llm
    --adapter "${ADAPTER}"
    --adapter-identity "${IDENTITY}"
    --adapter-scale "${GFV2_ADAPTER_SCALE:-0.18}"
    --temperature 0.7
    --seed 0
  )
  if python3 -c "import json,os; i=json.load(open(os.environ['GFV2_ADAPTER_IDENTITY'])); raise SystemExit(0 if i.get('valid_for_official_use') is True else 1)"; then
    echo "using_official_adapter_path"
  else
    FT_ARGS+=(--allow-unofficial-adapter)
    echo "using_unofficial_adapter_path"
  fi
  qwen "${FT_ARGS[@]}"
  cp -f "${FT_DIR}/t28_selected_adapter_llm.predictions.jsonl" "${FT_PRED}"
else
  echo "skip:finetune_intent_box_t07"
fi

# Validate n=120 and temperature in manifests
python3 - <<PY
import json
from pathlib import Path
exp = Path("${EXP}")
for name in ("06_raw_qwen_t07.predictions.jsonl", "07_finetune_t07.predictions.jsonl"):
    rows = [json.loads(l) for l in (exp/name).read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 120, name
    ids = [r["record_id"] for r in rows]
    frozen = [l.strip() for l in (exp/"02_input_case_ids.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert ids == frozen, f"order_mismatch:{name}"
print("prediction_validation_ok")
for man in [Path("${RAW_DIR}/run_manifest.json"), Path("${FT_DIR}/run_manifest.json")]:
    if man.exists():
        m = json.loads(man.read_text(encoding="utf-8"))
        assert float(m["temperature"]) == 0.7, man
        assert int(m["seed"]) == 0, man
print("manifest_temperature_seed_ok")
PY

BOX_PACKET="${EXP}/packets/intent_box_sgc_t07"
MGR_PACKET="${EXP}/packets/manager_sgc_t07"
if [[ ! -f "${BOX_PACKET}/blind_judge_pass_1_120.jsonl" ]]; then
  echo "phase:build_box_packet"
  qwen scripts/build_intent_box_sgc_packet_20260913.py \
    --raw "${RAW_PRED}" \
    --fine-tune "${FT_PRED}" \
    --out "${BOX_PACKET}"
fi
if [[ ! -f "${MGR_PACKET}/blind_judge_pass_1_120.jsonl" ]]; then
  echo "phase:build_manager_packet"
  qwen scripts/build_t07_manager_sgc_packet_20260922.py \
    --goal-first "${GF_PRED}" \
    --context-blind "${BLIND_PRED}" \
    --out "${MGR_PACKET}"
fi

# Combined judging packet copy for artifact 10
python3 - <<PY
import json
from pathlib import Path
exp = Path("${EXP}")
rows = []
for packet in [Path("${BOX_PACKET}"), Path("${MGR_PACKET}")]:
    for pass_i in (1, 2):
        p = packet / f"blind_judge_pass_{pass_i}_120.jsonl"
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
with (exp / "10_t07_intent_judging_packet.jsonl").open("w", encoding="utf-8") as fh:
    for row in rows:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
print("wrote_combined_packet", len(rows))
PY

echo "phase:gpu_settle_before_judges"
nvidia-smi || true
sleep 8

run_judge_packet() {
  local name="$1"
  local packet="$2"
  local dest="${EXP}/judges/${name}"
  mkdir -p "${dest}"
  local judge_id model revision
  for spec in "Judge_A|/home-mscluster/mbangie/models/dual_llm_benchmark_v1/gemma-4-26b-a4b-it|4d7ae4984b7db7de8f8457170b3f1a419ee76d52" \
              "Judge_B|/home-mscluster/mbangie/models/dual_llm_benchmark_v1/glm-4.7-flash-bf16|7dd20894a642a0aa287e9827cb1a1f7f91386b67"; do
    IFS='|' read -r judge_id model revision <<<"${spec}"
    local pass
    for pass in 1 2; do
      local outf="${dest}/${judge_id}_pass_${pass}.jsonl"
      if [[ "$(count_jsonl "${outf}")" -ge 120 ]]; then
        echo "skip:${name}:${judge_id}:pass${pass}"
        continue
      fi
      echo "phase:judge:${name}:${judge_id}:pass${pass}"
      python3 "${CODE}/scripts/annotation/server_lifecycle.py" \
        --model "${model}" \
        --revision "${revision}" \
        --port $((8200 + pass)) \
        --log "${dest}/${judge_id}_pass_${pass}.server.log" \
        --runner "${CODE}/scripts/semantic_intent/run_blind_semantic_judge.py" \
        --runner-args \
          --packet "${packet}/blind_judge_pass_${pass}_120.jsonl" \
          --guide "${PROTO}/JUDGE_GUIDE.md" \
          --prompt "${PROTO}/JUDGE_PROMPT.txt" \
          --schema "${PROTO}/judge_output_schema.json" \
          --calibration "${PROTO}/synthetic_judge_calibration.jsonl" \
          --judge-id "${judge_id}" \
          --model "${model}" \
          --revision "${revision}" \
          --port $((8200 + pass)) \
          --out "${outf}" \
          --manifest-out "${dest}/${judge_id}_pass_${pass}.manifest.json" \
          --seed $((20260922 + pass))
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

run_judge_packet "intent_box_raw_ft" "${BOX_PACKET}"
run_judge_packet "gfv2_intent_summary_t07" "${MGR_PACKET}"

# Copy judge combined files to numbered artifacts
cp -f "${EXP}/judges/intent_box_raw_ft/Judge_A_combined.jsonl" "${EXP}/11_t07_judge1_results.jsonl"
cp -f "${EXP}/judges/intent_box_raw_ft/Judge_B_combined.jsonl" "${EXP}/12_t07_judge2_results.jsonl"

echo "phase:score"
python3 "${CODE}/scripts/score_t07_matched_baseline_20260922.py" \
  --experiment-dir "${EXP}" \
  --gf-preds "${GF_PRED}" \
  --degree-preds "${DEGREE_PRED}" \
  --timid-preds "${TIMID_PRED}" \
  --blind-preds "${BLIND_PRED}"

echo T07_MATCHED_BASELINE_DONE
printf 'out\t%s\n' "${EXP}" | tee "${EXP}/run_complete.tsv"
