#!/usr/bin/env python3
"""Verify goal-first v2 R1 repair completion and report final metrics."""

import json
import sys
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_repair_completion.py <manager_dir>")
        print("Example: python verify_repair_completion.py /home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911/manager")
        return 1
    
    manager_dir = Path(sys.argv[1])
    manifest_path = manager_dir / "run_manifest.json"
    
    if not manifest_path.exists():
        print(f"ERROR: Manifest not found at {manifest_path}")
        return 1
    
    manifest = json.loads(manifest_path.read_text())
    
    print("=" * 70)
    print("Goal-first v2 R1 Repair Verification")
    print("=" * 70)
    print()
    
    # Overall status
    status = manifest.get("status", "UNKNOWN")
    print(f"Status: {status}")
    print()
    
    # Failure counts
    row_failures = manifest.get("row_failures", {})
    row_failure_total = manifest.get("row_failure_total", 0)
    
    print("Failed Row Counts:")
    for system, failed_ids in sorted(row_failures.items()):
        print(f"  {system:40s} {len(failed_ids):3d} failures")
    print(f"  {'TOTAL':40s} {row_failure_total:3d} failures")
    print()
    
    # Initial state comparison
    INITIAL_FAILURES = 33
    reduction = INITIAL_FAILURES - row_failure_total
    reduction_pct = (reduction / INITIAL_FAILURES) * 100 if INITIAL_FAILURES > 0 else 0
    
    print(f"Repair Progress:")
    print(f"  Initial failures:  {INITIAL_FAILURES}")
    print(f"  Current failures:  {row_failure_total}")
    print(f"  Repaired:          {reduction} ({reduction_pct:.1f}% reduction)")
    print()
    
    # Route accuracy by system
    print("Route Accuracy by System:")
    eval_dir = manager_dir / "evaluations"
    for system in ["goal_first_manager_v2", "rich_conservative_manager_v2", 
                   "degree_based_router_v2", "goal_first_context_blind_v2"]:
        eval_path = eval_dir / f"{system}.eval.json"
        if eval_path.exists():
            eval_data = json.loads(eval_path.read_text())
            terminal_strategy = eval_data.get("terminal_strategy", {})
            accuracy = terminal_strategy.get("accuracy")
            if accuracy is not None:
                print(f"  {system:40s} {accuracy:.3f}")
            else:
                print(f"  {system:40s} N/A")
        else:
            print(f"  {system:40s} (eval not found)")
    print()
    
    # Success criteria
    print("Success Criteria:")
    print(f"  ✓ Status VERIFY_PASSED*:        {'✓' if status.startswith('VERIFY_PASSED') else '✗'}")
    print(f"  ✓ Failures reduced by >50%:     {'✓' if reduction_pct > 50 else '✗'}")
    print(f"  ✓ Residual failures <15:        {'✓' if row_failure_total < 15 else '✗'}")
    print()
    
    # Overall verdict
    if status.startswith("VERIFY_PASSED") and row_failure_total < 15:
        verdict = "SUCCESS"
        color = "\033[92m"  # Green
    elif status.startswith("VERIFY_PASSED") and row_failure_total < 20:
        verdict = "ACCEPTABLE"
        color = "\033[93m"  # Yellow
    else:
        verdict = "NEEDS_WORK"
        color = "\033[91m"  # Red
    reset = "\033[0m"
    
    print(f"Overall Verdict: {color}{verdict}{reset}")
    print()
    
    # Specific failed IDs for follow-up
    if row_failure_total > 0 and row_failure_total < 10:
        print("Remaining Failed IDs (for targeted repair):")
        for system, failed_ids in sorted(row_failures.items()):
            if failed_ids:
                print(f"  {system}:")
                for fid in sorted(failed_ids):
                    print(f"    - {fid}")
        print()
    
    # Recommendations
    print("Recommendations:")
    if row_failure_total == 0:
        print("  ✓ All failures resolved! Mark as VERIFY_PASSED.")
    elif row_failure_total < 5:
        print("  ✓ Excellent result. Consider optional one-ID sampling for residuals.")
    elif row_failure_total < 15:
        print("  ✓ Good result. GPU repair recommended for remaining failures.")
    elif row_failure_total < 25:
        print("  ⚠ Partial success. Apply GPU patches (A+B) and retry repair.")
    else:
        print("  ✗ Insufficient progress. Review salvage logs and consider Phase 3 sampling.")
    print()
    
    # Next steps
    if row_failure_total > 5:
        print("Next Steps:")
        print("  1. Review failed IDs in prediction files (raw_output field)")
        print("  2. Check salvage log: cpu_salvage_log_20260912.json")
        print("  3. If CPU salvage complete, apply GPU patches and run repair_failed_now.sbatch")
        print("  4. For hard cases, use --target-ids for one-ID sampling")
        print()
    
    return 0 if verdict in ("SUCCESS", "ACCEPTABLE") else 1

if __name__ == "__main__":
    sys.exit(main())
