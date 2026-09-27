#!/usr/bin/env bash
set -u
echo "=== ERR 54231 ==="
tail -n 80 /home-mscluster/mbangie/t12-hpc/logs/mega-official-54231.err
echo
echo "=== OUT 54231 MARKERS ==="
grep -nE 'phase:|missing_|refusing_|Error|Traceback|FAILED|failed|prove|PROVE|mega_official|exit|temp_sweep' /home-mscluster/mbangie/t12-hpc/logs/mega-official-54231.out | tail -n 80
echo
echo "=== OUT TAIL ==="
tail -n 60 /home-mscluster/mbangie/t12-hpc/logs/mega-official-54231.out
echo
echo "=== CLOSE DIR ==="
ls -la /home-mscluster/mbangie/t12-hpc/results/final_close-20260913 | head -n 40
echo
echo "=== SBATCH HEAD ==="
head -n 30 /home-mscluster/mbangie/t12-hpc/code/mega_close-20260913/cluster/mega_close_20260913/mega_official.sbatch
