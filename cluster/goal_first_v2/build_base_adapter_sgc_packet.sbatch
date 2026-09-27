#!/usr/bin/env bash
# CPU-only: build base vs adapter blind SGC packets from frozen Pilot R1 traces.
# Can run now; does not need GPU and does not touch 53074/53081.
#SBATCH --job-name=ba-sgc-packet
#SBATCH --partition=bigbatch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/home-mscluster/mbangie/t12-hpc/logs/ba-sgc-packet-%j.out
#SBATCH --error=/home-mscluster/mbangie/t12-hpc/logs/ba-sgc-packet-%j.err

set -euo pipefail
umask 077
: "${PACKET_CODE_ROOT:?}"
: "${PACKET_OUT:?}"

cd "${PACKET_CODE_ROOT}"
mkdir -p "${PACKET_OUT}"

python3 scripts/build_base_adapter_sgc_packet_20260911.py \
  --gold "${PACKET_GOLD}" \
  --base-predictions "${PACKET_BASE_PRED}" \
  --adapter-predictions "${PACKET_ADAPTER_PRED}" \
  --out "${PACKET_OUT}"
