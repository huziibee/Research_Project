#!/usr/bin/env bash
set -u
JOB=54230
LOG=/home-mscluster/mbangie/t12-hpc/logs/mega-official-${JOB}.monitor.log
OUT=/home-mscluster/mbangie/t12-hpc/logs/mega-official-${JOB}.out
ERR=/home-mscluster/mbangie/t12-hpc/logs/mega-official-${JOB}.err
# fallback glob if named differently
{
  echo "monitor_start $(date -Is) job=$JOB"
  while true; do
    date -Is
    squeue -j "$JOB" -o "%.18i %.2t %.10M %.20R" || true
    if ! squeue -j "$JOB" -h | grep -q .; then
      echo JOB_DONE
      sacct -j "$JOB" --format=JobID,State,ExitCode,Elapsed -P || true
      break
    fi
    echo ---OUT---
    tail -n 25 "$OUT" 2>/dev/null || tail -n 25 /home-mscluster/mbangie/t12-hpc/logs/mega-official-*.out 2>/dev/null | tail -n 25 || true
    echo ---MARKERS---
    ls /home-mscluster/mbangie/t12-hpc/results/final_close-20260913/PROVE_OK.json \
       /home-mscluster/mbangie/t12-hpc/results/final_close-20260913/MEGA_STATUS.json \
       /home-mscluster/mbangie/t12-hpc/results/final_close-20260913/MEGA_LEDGER.json 2>&1 || true
    echo ====
    sleep 900
  done
} >>"$LOG" 2>&1
