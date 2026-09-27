#!/usr/bin/env bash
# Resume the five cancelled ABLE IX temperature jobs in their existing outputs.
# Keep the original submission.tsv and all partial prediction rows intact.
set -euo pipefail
umask 077

T03_CODE_ROOT=/home-mscluster/mbangie/t12-hpc/code/pilot120_t03_gf_ablation-20260923
ABLE_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/able_ix_five_seed-20260923
PRIO_OUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915
GFV2_CONTAINER=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif
GFV2_HF_HOME=/home-mscluster/mbangie/t12-hpc/hf-cache
GFV2_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-hpc/training-site-packages
SBATCH_SCRIPT="${T03_CODE_ROOT}/cluster/pilot120_t03_gf_ablation_20260923/able_ix_temp.sbatch"
export T03_CODE_ROOT ABLE_OUTPUT PRIO_OUT GFV2_CONTAINER GFV2_HF_HOME GFV2_TRAINING_SITE_PACKAGES
unset ABLE_SEEDS  # The launcher default is exactly seeds 1, 2, 3, 4.

test -f "${SBATCH_SCRIPT}"
test -f "${T03_CODE_ROOT}/scripts/evaluate_goal_first_manager_v2.py"
test -d "${ABLE_OUTPUT}"
test -f "${GFV2_CONTAINER}"
test -d "${GFV2_HF_HOME}"
test -d "${GFV2_TRAINING_SITE_PACKAGES}"

if [[ -n "$(squeue -u mbangie -h -n p120-able-t00,p120-able-t03,p120-able-t05,p120-able-t07,p120-able-t10)" ]]; then
  echo 'able_ix_jobs_already_queued' >&2
  exit 2
fi

for temp in 0.0 0.3 0.5 0.7 1.0; do
  source_pred="${PRIO_OUT}/T${temp}/predictions/goal_first_manager_v2.predictions.jsonl"
  test -f "${source_pred}"
  test "$(wc -l < "${source_pred}")" -eq 120
done

python3 - "${ABLE_OUTPUT}" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
for temp in ('0.0', '0.3', '0.5', '0.7', '1.0'):
    for path in sorted((root / f'T{temp}').glob('seed_*/predictions/*.jsonl')):
        seen = set()
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            row = json.loads(line)
            record_id = str(row.get('record_id') or '')
            if not record_id or record_id in seen:
                raise ValueError(f'duplicate_or_missing_id:{path}:{number}')
            seen.add(record_id)
        if len(seen) > 120:
            raise ValueError(f'too_many_rows:{path}:{len(seen)}')
        print(f'CHECKPOINT_OK {path} {len(seen)}/120', flush=True)
PY

ledger="${ABLE_OUTPUT}/resubmission_20260927_$(date -u +%H%M%S).tsv"
set -o noclobber
printf 'temperature\tjob_id\tdependency\toutput_root\n' > "${ledger}"
set +o noclobber

temps=(0.0 0.3 0.5 0.7 1.0)
names=(p120-able-t00 p120-able-t03 p120-able-t05 p120-able-t07 p120-able-t10)
previous=''
for i in "${!temps[@]}"; do
  export ABLE_TEMP="${temps[$i]}"
  dependency=()
  if [[ -n "${previous}" ]]; then
    dependency=(--dependency="afterok:${previous}")
  fi
  job_id="$(sbatch --parsable --job-name="${names[$i]}" "${dependency[@]}" \
    --export=ALL "${SBATCH_SCRIPT}")"
  printf '%s\t%s\t%s\t%s\n' "${ABLE_TEMP}" "${job_id}" "${previous:-none}" "${ABLE_OUTPUT}/T${ABLE_TEMP}" | tee -a "${ledger}"
  previous="${job_id}"
done

echo "RESUBMISSION_LEDGER ${ledger}"
squeue -u mbangie
