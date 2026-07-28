#!/usr/bin/env python3
"""Validate T28-R2 artefacts without training or changing data."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.governance.dataset_licence import validate_dataset_licence_register
from ambiguity_manager.governance.protected_data import validate_protected_data_policy
from ambiguity_manager.governance.t28_r2 import training_allowed, validate_internal_research_gate
from ambiguity_manager.model.structured_target import StructuredTargetError, build_structured_target
from ambiguity_manager.model.training_target_packaging import load_training_target_policy_strict


def main() -> int:
    register_path = ROOT / "configs/licences/dataset_licence_register.json"
    register = json.loads(register_path.read_text(encoding="utf-8"))
    errors = validate_dataset_licence_register(register)
    errors.extend(validate_internal_research_gate(register, repo_root=ROOT))
    for entry in register["entries"]:
        path = entry.get("evidence_url_or_path")
        expected = entry.get("evidence_hash")
        if path and path.startswith("docs/"):
            actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            if actual != expected:
                errors.append(f"{entry['dataset_id']}: evidence hash mismatch")
    manifest = json.loads((ROOT / "data/processed/weak_pool/weak_pool_canonical.manifest.json").read_text(encoding="utf-8"))
    if manifest["canonical_sha256"] != "1e51cac046e014a6b890b10a155d22e32e01aa276d4507a10ad4f86abcf9942a":
        errors.append("canonical hash changed")
    if manifest["permitted_view_sha256"] != "34b551c37c8f97c24c1263a2cc12a9497e65f754924f1404c47055999f04ea22":
        errors.append("permitted view hash changed")
    policy = json.loads((ROOT / "configs/governance/protected_data_policy.json").read_text(encoding="utf-8"))
    errors.extend(validate_protected_data_policy(policy))
    view = ROOT / "data/processed/weak_pool/t28_permitted_train_dev.jsonl"
    rows = [json.loads(line) for line in view.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(row.get("protected_data") is True for row in rows):
        errors.append("protected data present in permitted view")
    target_policy = load_training_target_policy_strict(ROOT / "configs/data/training_target_policy_v1.json")
    valid_targets = 0
    for row in rows:
        try:
            build_structured_target(row["record"], row["eligibility"], policy=target_policy)
        except StructuredTargetError:
            continue
        valid_targets += 1
    if valid_targets != 13058:
        errors.append(f"CPU target canary expected 13058, got {valid_targets}")
    if errors:
        print("T28_R2 governance validation FAILED")
        print("\n".join(errors), file=sys.stderr)
        return 1
    allowed, gate_errors = training_allowed(register, repo_root=ROOT)
    if gate_errors and register["internal_academic_research_use_gate"]["decision"] in {"approved", "approved_with_conditions"}:
        print(json.dumps({"status": "BLOCKED", "training_allowed": False, "errors": gate_errors}, sort_keys=True))
        return 1
    status = "PASS" if allowed else "WAITING_FOR_APPROVAL"
    unresolved = [entry["dataset_id"] for entry in register["entries"] if entry["dataset_id"] in {"ambik", "indirect_requests", "codraw_icr_v2", "vague", "clara"} and entry["verification_status"] != "verified"]
    print(json.dumps({"status": status, "unresolved_primary_sources": unresolved, "training_allowed": allowed, "adapter_release_allowed": False, "raw_data_redistribution_allowed": False, "valid_targets": valid_targets}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
