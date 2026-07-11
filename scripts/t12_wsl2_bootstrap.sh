#!/usr/bin/env bash
# T12 Slice 2 WSL2 environment bootstrap — run inside Ubuntu WSL2 only.
set -euo pipefail

REPO="/mnt/c/Users/huzii/Documents/University/Research Project"
ENV_ROOT="${HOME}/.local/t12-environments"
INFERENCE_ENV="${ENV_ROOT}/t12-inference-wsl2"
TRAINING_ENV="${ENV_ROOT}/t12-training-wsl2"
PYTORCH_INDEX="https://download.pytorch.org/whl/cu118"
INDEX_STRATEGY="unsafe-best-match"
BUILD_ESSENTIAL_INSTALL_CMD="sudo apt-get update && sudo apt-get install -y build-essential"

log() { printf '[t12-slice2] %s\n' "$*"; }

record_resources() {
  local label="$1"
  local out="$2"
  {
    echo "=== ${label} ==="
    date -u +"%Y-%m-%dT%H:%M:%SZ"
    free -m
    swapon --show 2>/dev/null || true
    df -h /
    nvidia-smi --query-gpu=name,memory.total,memory.free,memory.used --format=csv,noheader 2>/dev/null || true
  } >> "${out}"
}

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    uv --version
    return
  fi
  log "installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
  uv --version
}

check_build_tools() {
  local missing=0
  for tool in gcc g++ make; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
      log "missing host compiler tool: ${tool}"
      missing=1
    fi
  done
  if [[ "${missing}" -eq 1 ]]; then
    log "bitsandbytes/Triton requires a host C/C++ toolchain (build-essential)."
    log "Run this command manually in WSL Ubuntu, then rerun this bootstrap:"
    log "  ${BUILD_ESSENTIAL_INSTALL_CMD}"
    log "Do not store or automate sudo passwords."
    return 1
  fi
  export CC="/usr/bin/gcc"
  export CXX="/usr/bin/g++"
  log "host compiler available: CC=${CC} CXX=${CXX}"
  gcc --version | head -1
  return 0
}

setup_env() {
  local env_id="$1"
  local role="$2"
  local req_in="$3"
  local lock_rel="$4"
  local venv_path="$5"

  log "setting up ${env_id}"
  uv python install 3.11
  uv venv "${venv_path}" --python 3.11 --clear
  uv pip compile \
    "${REPO}/${req_in}" \
    -o "${REPO}/${lock_rel}" \
    --python-version 3.11 \
    --python-platform x86_64-manylinux_2_28 \
    --extra-index-url "${PYTORCH_INDEX}" \
    --index-strategy "${INDEX_STRATEGY}"
  uv pip sync "${REPO}/${lock_rel}" \
    --python "${venv_path}/bin/python" \
    --extra-index-url "${PYTORCH_INDEX}" \
    --index-strategy "${INDEX_STRATEGY}"
  CC="${CC:-/usr/bin/gcc}" CXX="${CXX:-/usr/bin/g++}" \
    "${venv_path}/bin/python" "${REPO}/scripts/t12_probe_environment.py" \
    --environment-id "${env_id}" \
    --role "${role}" \
    --output-dir "${REPO}/outputs/environment_probes"
}

main() {
  export PATH="${HOME}/.local/bin:${PATH}"
  cd "${REPO}"
  mkdir -p "${ENV_ROOT}" "${REPO}/requirements/locks" "${REPO}/outputs/environment_probes"
  RESOURCE_LOG="${REPO}/outputs/environment_probes/resource_measurements.txt"
  : > "${RESOURCE_LOG}"

  record_resources "before_installation" "${RESOURCE_LOG}"
  ensure_uv
  check_build_tools

  setup_env \
    "t12-inference-wsl2" \
    "inference" \
    "requirements/t12-inference.in" \
    "requirements/locks/t12-inference-wsl2.lock" \
    "${INFERENCE_ENV}"

  setup_env \
    "t12-training-wsl2" \
    "training" \
    "requirements/t12-training.in" \
    "requirements/locks/t12-training-wsl2.lock" \
    "${TRAINING_ENV}"

  record_resources "after_probes" "${RESOURCE_LOG}"

  log "inference probe:"
  cat "${REPO}/outputs/environment_probes/t12-inference-wsl2.json"
  log "training probe:"
  cat "${REPO}/outputs/environment_probes/t12-training-wsl2.json"
}

main "$@"
