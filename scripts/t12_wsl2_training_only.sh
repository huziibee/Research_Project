#!/usr/bin/env bash
# T12 Slice 2 probe rerun — use after installing build-essential in WSL Ubuntu.
set -euo pipefail

export PATH="${HOME}/.local/bin:${PATH}"
REPO="/mnt/c/Users/huzii/Documents/University/Research Project"
INFERENCE_ENV="${HOME}/.local/t12-environments/t12-inference-wsl2"
TRAINING_ENV="${HOME}/.local/t12-environments/t12-training-wsl2"
BUILD_ESSENTIAL_INSTALL_CMD="sudo apt-get update && sudo apt-get install -y build-essential"

log() { printf '[t12-slice2] %s\n' "$*"; }

check_build_tools() {
  local missing=0
  for tool in gcc g++ make; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
      log "missing host compiler tool: ${tool}"
      missing=1
    fi
  done
  if [[ "${missing}" -eq 1 ]]; then
    log "bitsandbytes/Triton requires build-essential before probing."
    log "Run manually, then rerun this script:"
    log "  ${BUILD_ESSENTIAL_INSTALL_CMD}"
    return 1
  fi
  export CC="/usr/bin/gcc"
  export CXX="/usr/bin/g++"
  log "host compiler available: CC=${CC} CXX=${CXX}"
  return 0
}

main() {
  check_build_tools
  mkdir -p "${REPO}/outputs/environment_probes"
  CC="${CC:-/usr/bin/gcc}" CXX="${CXX:-/usr/bin/g++}" \
    "${INFERENCE_ENV}/bin/python" "${REPO}/scripts/t12_probe_environment.py" \
    --environment-id t12-inference-wsl2 \
    --role inference \
    --output-dir "${REPO}/outputs/environment_probes"
  CC="${CC:-/usr/bin/gcc}" CXX="${CXX:-/usr/bin/g++}" \
    "${TRAINING_ENV}/bin/python" "${REPO}/scripts/t12_probe_environment.py" \
    --environment-id t12-training-wsl2 \
    --role training \
    --output-dir "${REPO}/outputs/environment_probes"
}

main "$@"
