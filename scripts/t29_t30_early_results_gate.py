#!/usr/bin/env python3
"""Record the non-protected Pilot-120 T29/T30 early-results readiness state."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


CONSTANT_SYSTEMS = {"always_execute", "always_clarify", "always_silently_resolve"}
MANAGER_SYSTEMS = {
    "degree_based_router",
    "context_blind_manager",
    "full_type_risk_aware_manager",
}


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"early_gate_not_object:{path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paired-comparison", type=Path, required=True)
    parser.add_argument("--constant-summary", type=Path, required=True)
    parser.add_argument("--manager-summary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("t29_t30_early_gate_output_exists")
    paired = _read(args.paired_comparison)
    constants = _read(args.constant_summary)
    if paired.get("status") != "VERIFY_PASSED" or paired.get("denominator") != 120:
        raise SystemExit("t29_t30_early_gate_paired_pilot_not_verified")
    if paired.get("valid_for_official_use") is not False or paired.get("protected_data_accessed") is not False:
        raise SystemExit("t29_t30_early_gate_pilot_boundary_invalid")
    ran = set(constants.get("systems_run") or [])
    if ran != CONSTANT_SYSTEMS:
        raise SystemExit("t29_t30_early_gate_constant_system_set_mismatch")
    manager_summary: dict[str, Any] | None = None
    missing = sorted(MANAGER_SYSTEMS)
    if args.manager_summary is not None:
        manager_summary = _read(args.manager_summary)
        ran_manager = set(manager_summary.get("systems") or [])
        if manager_summary.get("status") != "VERIFY_PASSED" or ran_manager != MANAGER_SYSTEMS:
            raise SystemExit("t29_t30_early_gate_manager_system_set_or_status_invalid")
        validation = manager_summary.get("validation") or {}
        if any(not (validation.get(sid) or {}).get("ordered_complete") for sid in MANAGER_SYSTEMS):
            raise SystemExit("t29_t30_early_gate_manager_denominator_invalid")
        missing = []
    complete = not missing
    payload = {
        "status": "T29_T30_EARLY_COMPLETE_NON_PROTECTED" if complete else "T29_T30_EARLY_PARTIAL",
        "claim": "non_protected_pilot120_end_to_end_readiness",
        "valid_for_official_use": False,
        "protected_data_accessed": False,
        "pilot120_denominator": 120,
        "evidence": {
            "paired_base_adapter_sha256": _sha256(args.paired_comparison),
            "constant_baselines_sha256": _sha256(args.constant_summary),
            "manager_systems_sha256": _sha256(args.manager_summary) if args.manager_summary else None,
        },
        "systems_with_completed_pilot_evidence": sorted(
            CONSTANT_SYSTEMS | {"direct_base_llm", "t28_selected_adapter_llm"} | (MANAGER_SYSTEMS if complete else set())
        ),
        "mandatory_t30_systems_still_missing": missing,
        "next_gate": "T31plus_early_analysis" if complete else "implement_and_run_remaining_three_pilot_systems_before_T29_T30_EARLY_RESULTS_PASS",
        "official_t29_t30_blocked_by": [
            "Pilot-120 is not the protected official dataset",
            "full-1000 semantic QA remains deferred",
            "formal T29 protocol and protected-access approval are not satisfied",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps({"status": payload["status"], "missing": payload["mandatory_t30_systems_still_missing"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
