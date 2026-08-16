#!/usr/bin/env python3
"""Create a deliberately non-official T28 identity with one disclosed exclusion."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

BASE_MODEL = "Qwen/Qwen3-8B"
BASE_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"early_pilot_identity_not_object:{path}")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter-identity", type=Path, required=True)
    parser.add_argument("--repair-evaluation-dir", type=Path, required=True)
    parser.add_argument("--excluded-call-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("early_pilot_identity_output_exists")
    source = _load(args.adapter_identity)
    if source.get("base_model") != f"{BASE_MODEL}@{BASE_REVISION}":
        raise SystemExit("early_pilot_identity_base_mismatch")
    if source.get("selection_candidate") is not True or source.get("technical_smoke_only") is not False:
        raise SystemExit("early_pilot_identity_adapter_not_eligible_candidate")
    manifest_path = args.repair_evaluation_dir / "evaluation_progress.json"
    results_path = args.repair_evaluation_dir / "dev_raw_and_parsed.jsonl"
    manifest = _load(manifest_path)
    rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 1 or rows[0].get("call_id") != args.excluded_call_id:
        raise SystemExit("early_pilot_identity_repair_call_mismatch")
    row = rows[0]
    if (row.get("adapter_parsed") or {}).get("accepted") is True:
        raise SystemExit("early_pilot_identity_exclusion_not_required")
    if (row.get("base_parsed") or {}).get("accepted") is not True:
        raise SystemExit("early_pilot_identity_base_repair_not_valid")
    scale = float(manifest.get("adapter_scale"))
    if scale <= 0:
        raise SystemExit("early_pilot_identity_invalid_scale")
    payload = {
        "selection_contract": "t28_early_pilot_exclusion_v1",
        "selected_adapter": True,
        "adapter_id": source["adapter_id"],
        "adapter_scale": scale,
        "base_model": BASE_MODEL,
        "base_revision": BASE_REVISION,
        "selection_status": "provisional_for_pilot_early_evaluation_only",
        "valid_for_official_use": False,
        "pilot120_used_for_selection": False,
        "official_t28_selection_completed": False,
        "explicit_exclusion": {
            "call_id": args.excluded_call_id,
            "reason": "adapter_no_json_after_v4_exact_repair",
            "repair_manifest_sha256": _sha256(manifest_path),
            "repair_results_sha256": _sha256(results_path),
            "paired_routing_denominator_excludes_call": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps({"status": payload["selection_status"], "excluded_call_id": args.excluded_call_id}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
