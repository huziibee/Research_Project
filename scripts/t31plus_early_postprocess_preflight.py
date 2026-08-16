#!/usr/bin/env python3
"""Create a hash-bound readiness record for non-protected T31+ post-processing."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"t31plus_preflight_not_object:{path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--early-gate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("t31plus_preflight_output_exists")
    gate = _read(args.early_gate)
    if gate.get("status") not in {"T29_T30_EARLY_PARTIAL", "T29_T30_EARLY_COMPLETE_NON_PROTECTED"}:
        raise SystemExit("t31plus_preflight_early_gate_unexpected_status")
    if gate.get("protected_data_accessed") is not False or gate.get("valid_for_official_use") is not False:
        raise SystemExit("t31plus_preflight_boundary_invalid")
    missing = gate.get("mandatory_t30_systems_still_missing")
    if not isinstance(missing, list):
        raise SystemExit("t31plus_preflight_missing_matrix_state_invalid")
    complete = gate.get("status") == "T29_T30_EARLY_COMPLETE_NON_PROTECTED"
    if complete != (not missing):
        raise SystemExit("t31plus_preflight_gate_completion_state_invalid")
    payload: dict[str, Any] = {
        "status": "READY_FOR_T31PLUS_EARLY_ANALYSIS" if complete else "WAITING_FOR_FULL_EARLY_T30_MATRIX",
        "scope": "non_protected_pilot120_only",
        "compute_location": "cluster_canonical_artifacts",
        "local_copy_policy": "retrieve_only_hash_verified_generated_report_package",
        "early_gate_sha256": _sha256(args.early_gate),
        "required_before_t31plus_analysis": {
            "complete_early_t30_matrix": True,
            "matrix_complete_at_preflight": complete,
            "missing_systems": sorted(missing),
            "frozen_early_cost_policy": True,
            "record_level_route_and_error_evidence": True,
            "aligned_all_system_prediction_matrix": True,
        },
        "analysis_order_after_matrix": [
            "T31_early_cost_sensitive_evaluation",
            "T32_early_paired_statistics",
            "T33_early_predeclared_ablations",
            "T36_early_layered_failure_analysis",
            "T37_early_report_and_reproducibility_package",
            "T38_early_integrity_audit",
        ],
        "official_claim_allowed": False,
        "protected_data_accessed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps({"status": payload["status"], "missing_systems": payload["required_before_t31plus_analysis"]["missing_systems"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
