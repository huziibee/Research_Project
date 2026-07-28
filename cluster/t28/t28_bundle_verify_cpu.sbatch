#!/bin/bash
# Independent CPU-only verification of the immutable T28 bundle.
#SBATCH --job-name=t28-bundle-verify
#SBATCH --partition=bigbatch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=t28-bundle-verify-%j.out
#SBATCH --error=t28-bundle-verify-%j.err
set -euo pipefail
: "${T28_BUNDLE_ROOT:?}"
: "${T28_ARCHIVE:?}"
: "${T28_MANIFEST:?}"
: "${T28_MANIFEST_SHA256:?}"
: "${T28_CODE_ROOT:?}"
: "${T28_EVIDENCE:?}"
export PYTHONPATH="${T28_CODE_ROOT}/src"
python3 "${T28_CODE_ROOT}/scripts/verify_t28_bundle_cpu.py" \
  --bundle-root "${T28_BUNDLE_ROOT}" --archive "${T28_ARCHIVE}" \
  --manifest "${T28_MANIFEST}" --manifest-sha256 "${T28_MANIFEST_SHA256}" \
  --output "${T28_EVIDENCE}"
