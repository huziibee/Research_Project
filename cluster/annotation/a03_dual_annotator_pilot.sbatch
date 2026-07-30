#!/usr/bin/env bash
#SBATCH --job-name=a03-dual-pilot
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
# Observed Blackwell nodes expose 12 CPUs; requesting 16 cannot schedule there.
#SBATCH --cpus-per-task=12
#SBATCH --mem=110G
#SBATCH --exclusive
# Target the previously verified Blackwell node; the guard still rejects a busy GPU.
#SBATCH --nodelist=mscluster110
#SBATCH --time=24:00:00
#SBATCH --output=%x-%j.out
#SBATCH --error=%x-%j.err
set -Eeuo pipefail
ROOT="${SLURM_SUBMIT_DIR:?}"; RUN_ID="a02-a04-r3-pilot-${SLURM_JOB_ID:-local}-20260730"; OUT="$ROOT/data/dual_llm_benchmark_v1/runs/$RUN_ID"; mkdir -p "$OUT"
exec > >(tee "$OUT/job.stdout.log") 2> >(tee "$OUT/job.stderr.log" >&2)
fail(){ echo "BLOCKED: $*" >&2; exit 42; }
log(){ echo "[$(date -Is)] [A02-A04-R3] $*"; }
log "START job=${SLURM_JOB_ID:-local} node=${SLURMD_NODENAME:-unknown} run=$RUN_ID"
log "allocation partition=${SLURM_JOB_PARTITION:-unknown} mem=${SLURM_MEM_PER_NODE:-unknown} cpus=${SLURM_CPUS_PER_TASK:-unknown} exclusive=true gres=none"
[[ "${SLURM_JOB_NUM_NODES:-1}" == 1 ]] || fail "one whole node required"
[[ "${SLURM_MEM_PER_NODE:-0}" -ge 96000 ]] || fail "visible host RAM below 96G safety minimum"
[[ "${SLURM_MEM_PER_NODE:-0}" -lt 122000 ]] || fail "requested memory must remain below observed node capacity"
[[ "${SLURM_JOB_GID:-0}" != "" ]] || true
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
command -v nvidia-smi >/dev/null || fail "nvidia-smi unavailable"
GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
GPU_MEM="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)"
[[ "$GPU_NAME" == *Blackwell* ]] || fail "non-Blackwell GPU allocated: $GPU_NAME"
[[ "${GPU_MEM:-0}" -ge 90000 ]] || fail "visible GPU VRAM below 90000 MiB: $GPU_MEM"
GPU_USED="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)"
if [[ "${GPU_USED:-999999}" -gt 1000 ]]; then
  echo "WAITING_FOR_IDLE_GPU: ${GPU_USED} MiB used; releasing allocation without model load" >&2
  fail "GPU was occupied at allocation time; resubmit after the node is genuinely idle"
fi
log "idle GPU confirmed; collecting pre-load system snapshot"
python3 scripts/annotation/runtime_preflight.py --output "$OUT/runtime_preflight.json" --container "${A01_CONTAINER_SIF:?}" --model-manifest configs/annotation/a02_a04_r3_model_selection_v2.json
log "runtime CPU/import preflight complete"
python3 - "$OUT/preflight.json" <<'PY'
import json,os,subprocess,sys
o={"hostname":subprocess.check_output(["hostname"],text=True).strip(),"job":os.environ.get("SLURM_JOB_ID"),"node":os.environ.get("SLURMD_NODENAME"),"meminfo":open("/proc/meminfo").read(),"swap":subprocess.check_output(["free","-h"],text=True),"filesystem":subprocess.check_output(["df","-h","."],text=True),"processes":subprocess.check_output(["ps","-eo","pid,comm,args"],text=True),"gpu":subprocess.check_output(["nvidia-smi","--query-gpu=name,memory.total,memory.used,driver_version","--format=csv,noheader"],text=True).strip(),"compute_capability":subprocess.check_output(["nvidia-smi","--query-gpu=compute_cap","--format=csv,noheader"],text=True).strip()}
open(sys.argv[1],"w").write(json.dumps(o,indent=2)+"\n")
PY
apptainer exec --nv "$A01_CONTAINER_SIF" python3 -c "import torch,vllm,transformers,compressed_tensors,mistral_common; print({'torch':torch.__version__,'vllm':vllm.__version__,'transformers':transformers.__version__,'compressed_tensors':compressed_tensors.__version__,'mistral_common':mistral_common.__version__})" > "$OUT/runtime_gpu_versions.txt"
GEMMA=/home-mscluster/mbangie/models/dual_llm_benchmark_v1/gemma-4-26b-a4b-it
GLM=/home-mscluster/mbangie/models/dual_llm_benchmark_v1/glm-4.7-flash-bf16
GEMMA_REV=4d7ae4984b7db7de8f8457170b3f1a419ee76d52
GLM_REV=7dd20894a642a0aa287e9827cb1a1f7f91386b67
log "GEMMA canary start model=$GEMMA revision=$GEMMA_REV"
python3 scripts/annotation/server_lifecycle.py --model "$GEMMA" --revision "$GEMMA_REV" --port 8001 --runner scripts/annotation/run_vllm_annotator.py --log "$OUT/gemma4.canary.server.log" --runner-args --model "$GEMMA" --revision "$GEMMA_REV" --annotator ANN-A --port 8001 --pilot data/dual_llm_benchmark_v1/manifests/a03_pilot_manifest.jsonl --output "$OUT/canary_gemma4" --cache "${A01_MODEL_CACHE:?}" --server-log "$OUT/gemma4.canary.server.log" --limit 2
log "GEMMA canary complete; validating and checking cleanup"
python3 scripts/annotation/validate_annotations.py --schema schemas/annotation/model_annotation.schema.json --input "$OUT/canary_gemma4/raw.jsonl"
python3 scripts/annotation/cleanup_evidence.py --output "$OUT/cleanup_a_canary.json" || true
python3 scripts/annotation/server_lifecycle.py --model "$GEMMA" --revision "$GEMMA_REV" --port 8001 --runner scripts/annotation/run_vllm_annotator.py --log "$OUT/gemma4.server.log" --runner-args --model "$GEMMA" --revision "$GEMMA_REV" --annotator ANN-A --port 8001 --pilot data/dual_llm_benchmark_v1/manifests/a03_pilot_manifest.jsonl --output "$OUT/annotator_a" --cache "${A01_MODEL_CACHE:?}" --server-log "$OUT/gemma4.server.log"
log "GEMMA 40-record annotation complete"
python3 scripts/annotation/validate_annotations.py --schema schemas/annotation/model_annotation.schema.json --input "$OUT/annotator_a/raw.jsonl"
python3 scripts/annotation/cleanup_evidence.py --output "$OUT/cleanup_a.json" || true
log "GLM canary start model=$GLM revision=$GLM_REV"
python3 scripts/annotation/server_lifecycle.py --model "$GLM" --revision "$GLM_REV" --port 8002 --runner scripts/annotation/run_vllm_annotator.py --log "$OUT/glm.canary.server.log" --runner-args --model "$GLM" --revision "$GLM_REV" --annotator ANN-B --port 8002 --pilot data/dual_llm_benchmark_v1/manifests/a03_pilot_manifest.jsonl --output "$OUT/canary_glm" --cache "${A01_MODEL_CACHE:?}" --server-log "$OUT/glm.canary.server.log" --limit 2
log "GLM canary complete; validating and checking cleanup"
python3 scripts/annotation/validate_annotations.py --schema schemas/annotation/model_annotation.schema.json --input "$OUT/canary_glm/raw.jsonl"
python3 scripts/annotation/cleanup_evidence.py --output "$OUT/cleanup_b_canary.json" || true
python3 scripts/annotation/server_lifecycle.py --model "$GLM" --revision "$GLM_REV" --port 8002 --runner scripts/annotation/run_vllm_annotator.py --log "$OUT/glm.server.log" --runner-args --model "$GLM" --revision "$GLM_REV" --annotator ANN-B --port 8002 --pilot data/dual_llm_benchmark_v1/manifests/a03_pilot_manifest.jsonl --output "$OUT/annotator_b" --cache "${A01_MODEL_CACHE:?}" --server-log "$OUT/glm.server.log"
log "GLM 40-record annotation complete"
python3 scripts/annotation/validate_annotations.py --schema schemas/annotation/model_annotation.schema.json --input "$OUT/annotator_b/raw.jsonl"
python3 scripts/annotation/cleanup_evidence.py --output "$OUT/cleanup_b.json" || true
log "computing agreement and building consolidated review packet"
python3 scripts/annotation/compute_agreement_full.py --a "$OUT/annotator_a/parsed.jsonl" --b "$OUT/annotator_b/parsed.jsonl" --pilot data/dual_llm_benchmark_v1/manifests/a03_pilot_manifest.json --output "$OUT/agreement.json"
python3 scripts/annotation/build_review_packet.py --a "$OUT/annotator_a" --b "$OUT/annotator_b" --pilot data/dual_llm_benchmark_v1/manifests/a03_pilot_manifest.json --agreement "$OUT/agreement.json" --output "$OUT/review_packet"
log "PASS_TO_HUMAN_REVIEW: pilot lifecycle and packet generation complete; full run remains unsubmitted"
