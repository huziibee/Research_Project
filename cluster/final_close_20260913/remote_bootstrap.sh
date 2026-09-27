#!/usr/bin/env bash
set -euo pipefail
SRC=/home-mscluster/mbangie/t12-hpc/code/temp_sweep-20260913
DST=/home-mscluster/mbangie/t12-hpc/code/final_close-20260913
if [ ! -d "${DST}/scripts" ]; then
  cp -a "${SRC}" "${DST}"
fi
mkdir -p \
  "${DST}/scripts/semantic_intent" \
  "${DST}/scripts/annotation" \
  "${DST}/cluster/final_close_20260913" \
  "${DST}/outputs"
echo "bootstrap_ok ${DST}"
