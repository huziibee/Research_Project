#!/usr/bin/env bash
# One-shot mega-official status. Run from Git Bash / WSL:
#   bash cluster/mega_close_20260913/check_mega_official.sh
# Or on the cluster:
#   bash /home-mscluster/mbangie/t12-hpc/code/mega_close-20260913/cluster/mega_close_20260913/check_mega_official.sh
set -u
JOB="${1:-54259}"
REMOTE=0
if [[ -d /home-mscluster/mbangie/t12-hpc ]]; then
  REMOTE=1
fi

remote_body() {
  local job="$1"
  echo "=== QUEUE ==="
  squeue -u mbangie -o '%.18i %.12P %.16j %.8u %.2t %.10M %.6D %R' || true
  echo
  if [[ -z "$job" ]]; then
    job=$(awk -F'\t' '$1=="job_id"{print $2}' /home-mscluster/mbangie/t12-hpc/results/final_close-20260913/mega_official_submission.tsv 2>/dev/null | tail -n 1)
  fi
  echo "=== JOB ${job:-unknown} ==="
  if [[ -n "$job" ]]; then
    sacct -j "$job" --format=JobID,JobName%18,State,ExitCode,Elapsed,NodeList,End -P -X || true
  fi
  echo
  echo "=== MARKERS ==="
  ls -la \
    /home-mscluster/mbangie/t12-hpc/results/final_close-20260913/PROVE_OK.json \
    /home-mscluster/mbangie/t12-hpc/results/final_close-20260913/MEGA_STATUS.json \
    /home-mscluster/mbangie/t12-hpc/results/final_close-20260913/MEGA_LEDGER.json \
    /home-mscluster/mbangie/t12-hpc/results/final_close-20260913/mega_official_submission.tsv \
    2>&1 || true
  echo
  echo "=== SUBMISSION ==="
  cat /home-mscluster/mbangie/t12-hpc/results/final_close-20260913/mega_official_submission.tsv 2>/dev/null || true
  echo
  echo "=== PROVE / STATUS ==="
  python3 - <<'PY'
from pathlib import Path
base = Path("/home-mscluster/mbangie/t12-hpc/results/final_close-20260913")
for name in ("PROVE_OK.json", "MEGA_STATUS.json", "MEGA_LEDGER.json"):
    p = base / name
    print("---", name, "---")
    print(p.read_text(encoding="utf-8") if p.exists() else "missing")
PY
  echo
  echo "=== OUT TAIL ==="
  if [[ -n "$job" && -f "/home-mscluster/mbangie/t12-hpc/logs/mega-official-${job}.out" ]]; then
    tail -n 40 "/home-mscluster/mbangie/t12-hpc/logs/mega-official-${job}.out"
  else
    ls -lt /home-mscluster/mbangie/t12-hpc/logs/mega-official-*.out 2>/dev/null | head -n 5
    tail -n 40 /home-mscluster/mbangie/t12-hpc/logs/mega-official-*.out 2>/dev/null | tail -n 40
  fi
  echo
  echo "=== ERR TAIL (non-progress) ==="
  if [[ -n "$job" && -f "/home-mscluster/mbangie/t12-hpc/logs/mega-official-${job}.err" ]]; then
    grep -vE 'Loading weights|FutureWarning|_check_is_size|bitsandbytes' \
      "/home-mscluster/mbangie/t12-hpc/logs/mega-official-${job}.err" | tail -n 30 || true
  fi
}

if [[ "$REMOTE" -eq 1 ]]; then
  remote_body "$JOB"
else
  ssh -o BatchMode=yes -o ConnectTimeout=20 wits-mscluster "$(declare -f remote_body); remote_body '${JOB}'"
fi
