#!/usr/bin/env bash
# Five ABLE IX jobs: one temperature each. Seeds 1-4 emitted; seed 0 imported.
# Queue the five temperatures after the separate T0.7 completion.
set -euo pipefail
umask 077

: "${T03_CODE_ROOT:=/home-mscluster/mbangie/t12-hpc/code/pilot120_t03_gf_ablation-20260923}"
: "${ABLE_OUTPUT:=/home-mscluster/mbangie/t12-hpc/results/able_ix_five_seed-20260923}"
: "${GFV2_TRAINING_SITE_PACKAGES:=/home-mscluster/mbangie/t12-hpc/training-site-packages}"
: "${GFV2_HF_HOME:=/home-mscluster/mbangie/t12-hpc/hf-cache}"
: "${GFV2_CONTAINER:=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif}"
: "${PRIO_OUT:=/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915}"
: "${AFTER_FIRST:=0}"
: "${ABLE_SEEDS:=1 2 3 4}"

HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "${ABLE_OUTPUT}" /home-mscluster/mbangie/t12-hpc/logs
export T03_CODE_ROOT ABLE_OUTPUT GFV2_TRAINING_SITE_PACKAGES GFV2_HF_HOME GFV2_CONTAINER PRIO_OUT ABLE_SEEDS

if squeue -u mbangie -h -n p120-able-t00,p120-able-t03,p120-able-t05,p120-able-t07,p120-able-t10 | grep -q .; then
  echo "able_jobs_already_queued" >&2
  exit 2
fi

TEMPS=(0.0 0.3 0.5 0.7 1.0)
NAMES=(p120-able-t00 p120-able-t03 p120-able-t05 p120-able-t07 p120-able-t10)
prev="${AFTER_FIRST}"
dep_kind="afterany"
: > "${ABLE_OUTPUT}/submission.tsv"

for i in "${!TEMPS[@]}"; do
  temp="${TEMPS[$i]}"
  name="${NAMES[$i]}"
  EXTRA=(--job-name="${name}")
  if [[ -n "${prev}" && "${prev}" != "0" ]]; then
    EXTRA+=(--dependency="${dep_kind}:${prev}")
  fi
  export ABLE_TEMP="${temp}"
  jid=$(sbatch --parsable "${EXTRA[@]}" --export=ALL "${HERE}/able_ix_temp.sbatch")
  echo "submitted ${name} ${jid} temp=${temp} ${dep_kind}=${prev} seeds=${ABLE_SEEDS}"
  printf '%s\t%s\ttemp\t%s\t%s\t%s\tseeds\t%s\n' \
    "${name}" "${jid}" "${temp}" "${dep_kind}" "${prev}" "${ABLE_SEEDS}" \
    | tee -a "${ABLE_OUTPUT}/submission.tsv"
  prev="${jid}"
  dep_kind="afterany"
done

squeue -u mbangie
