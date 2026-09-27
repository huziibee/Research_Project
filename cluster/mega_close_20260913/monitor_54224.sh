#!/usr/bin/env bash
set -u
LOG=/home-mscluster/mbangie/t12-hpc/logs/mega-close-54224.monitor.log
OUT=/home-mscluster/mbangie/t12-hpc/logs/mega-close-54224.out
JOB=54224
{
  echo "monitor_start $(date -Is)"
  while true; do
    date -Is
    squeue -j "$JOB" -o "%.18i %.2t %.10M %.20R" || true
    if ! squeue -j "$JOB" -h | grep -q .; then
      echo JOB_DONE
      sacct -j "$JOB" --format=JobID,State,ExitCode,Elapsed -P || true
      break
    fi
    echo ---OUT---
    tail -n 20 "$OUT" || true
    ls /home-mscluster/mbangie/t12-hpc/results/final_close-20260913/SMOKE_OK.json \
       /home-mscluster/mbangie/t12-hpc/results/final_close-20260913/MEGA_STATUS.json 2>&1 || true
    echo ====
    sleep 900
  done
} >>"$LOG" 2>&1
