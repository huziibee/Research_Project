#!/usr/bin/env bash
# Quick-start repair script for goal-first v2 R1 failures
# Run this from the cluster login node after reviewing the plan.

set -euo pipefail

echo "=== Goal-first v2 R1 Failure Repair Quick-Start ==="
echo ""
echo "Current failures: 33 rows (9+9+9+6 across 4 systems)"
echo "Target: <5 residual failures"
echo ""
echo "This script will:"
echo "  1. Run CPU salvage (10 min, no GPU)"
echo "  2. Check if GPU available for repair"
echo "  3. Display status and next steps"
echo ""

# Verify we're on the cluster
if [[ ! -d "/home-mscluster/mbangie/t12-hpc" ]]; then
    echo "ERROR: Must run on mscluster. Current dir: $(pwd)"
    exit 1
fi

cd /home-mscluster/mbangie/t12-hpc

# Set required environment variables
export GFV2_CODE_ROOT=/home-mscluster/mbangie/t12-hpc
export GFV2_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911

echo "Environment:"
echo "  GFV2_CODE_ROOT: ${GFV2_CODE_ROOT}"
echo "  GFV2_OUTPUT: ${GFV2_OUTPUT}"
echo ""

# Phase 1: CPU Salvage
echo "=== Phase 1: CPU Salvage (no GPU) ==="
echo "Submitting CPU salvage job..."

CPU_JOB=$(sbatch --parsable cluster/goal_first_v2/cpu_salvage.sbatch)
echo "Submitted job ${CPU_JOB}"
echo ""
echo "Monitor with:"
echo "  tail -f logs/gf-v2-cpu-salvage-${CPU_JOB}.out"
echo ""
echo "Waiting for completion (max 1h)..."

# Wait for CPU job to complete
while true; do
    STATUS=$(squeue -j ${CPU_JOB} -h -o %T 2>/dev/null || echo "DONE")
    if [[ "${STATUS}" == "DONE" ]]; then
        break
    fi
    echo "  Job ${CPU_JOB} status: ${STATUS}"
    sleep 30
done

echo ""
echo "=== CPU Salvage Complete ==="
echo ""

# Check salvage results
if [[ -f "${GFV2_OUTPUT}/manager/cpu_salvage_summary.json" ]]; then
    echo "Salvage results:"
    cat "${GFV2_OUTPUT}/manager/cpu_salvage_summary.json" | python3 -m json.tool
    echo ""
    
    STILL_FAILED=$(cat "${GFV2_OUTPUT}/manager/cpu_salvage_summary.json" | \
        python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(d['still_failed_counts'].values()))")
    
    echo "Remaining failures: ${STILL_FAILED}/33"
    echo ""
    
    if [[ ${STILL_FAILED} -lt 5 ]]; then
        echo "✓ SUCCESS: Reduced to <5 failures via CPU salvage alone!"
        echo "  GPU repair optional for further polish."
    elif [[ ${STILL_FAILED} -lt 15 ]]; then
        echo "✓ GOOD: Salvaged $(( 33 - STILL_FAILED ))/33 rows."
        echo "  Recommend GPU repair for remaining failures."
    else
        echo "⚠ PARTIAL: Only salvaged $(( 33 - STILL_FAILED ))/33 rows."
        echo "  GPU repair required."
    fi
else
    echo "ERROR: Salvage summary not found. Check logs:"
    echo "  cat logs/gf-v2-cpu-salvage-${CPU_JOB}.out"
    exit 1
fi

# Phase 2: Check GPU availability
echo ""
echo "=== Phase 2: GPU Repair Status ==="
echo ""

# Check if job 53188 is still running
JOB_53188_STATUS=$(squeue -j 53188 -h -o %T 2>/dev/null || echo "NOT_FOUND")
if [[ "${JOB_53188_STATUS}" == "NOT_FOUND" ]]; then
    echo "Job 53188 (follow-on): Complete or not found"
else
    echo "Job 53188 (follow-on): ${JOB_53188_STATUS}"
    echo "  Wait for completion before GPU repair."
fi

# Check biggpu availability
BIGGPU_BUSY=$(squeue -p biggpu -h | wc -l)
if [[ ${BIGGPU_BUSY} -eq 0 ]]; then
    echo "biggpu partition: AVAILABLE"
    echo ""
    echo "Ready to submit GPU repair. Run:"
    echo "  sbatch cluster/goal_first_v2/repair_failed_now.sbatch"
else
    echo "biggpu partition: BUSY (${BIGGPU_BUSY} jobs)"
    echo "  Check status: squeue -p biggpu"
fi

echo ""
echo "=== Next Steps ==="
echo ""
echo "1. Review salvage results above"
echo "2. If still_failed < 5: DONE (optional GPU polish)"
echo "3. If still_failed >= 5:"
echo "   a. Wait for biggpu availability"
echo "   b. Set GPU environment variables (see repair_failed_now.sbatch)"
echo "   c. Run: sbatch cluster/goal_first_v2/repair_failed_now.sbatch"
echo "4. Verify final state:"
echo "   cat ${GFV2_OUTPUT}/manager/run_manifest.json | jq '{status, row_failure_total}'"
echo ""
echo "Full documentation:"
echo "  docs/reports/GOAL_FIRST_V2_FAILURE_REPAIR_PLAN_20260912.md"
echo ""
