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


def main() -> int:
    register_path = ROOT / "configs/licences/dataset_licence_register.json"
    register = json.loads(register_path.read_text(encoding="utf-8"))
    errors = validate_dataset_licence_register(register)
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
    if errors:
        print("T28_R2 governance validation FAILED")
        print("\n".join(errors), file=sys.stderr)
        return 1
    unresolved = [entry["dataset_id"] for entry in register["entries"] if entry["dataset_id"] in {"ambik", "indirect_requests", "codraw_icr_v2", "vague", "clara"} and entry["verification_status"] != "verified"]
    print(json.dumps({"status": "WAITING_FOR_PERMISSION", "unresolved_primary_sources": unresolved, "training_allowed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
