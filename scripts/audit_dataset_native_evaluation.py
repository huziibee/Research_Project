#!/usr/bin/env python3
"""Audit source-native metric eligibility for the future exploratory study.

This script is read-only over source data. It neither runs a model nor rewrites
T39/T41 evidence. A metric may be proposed only when every required source
field is actually present on the inspected rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_not_object:{path}")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"jsonl_row_not_object:{path}:{number}")
        rows.append(value)
    return rows


def present(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def audit(protocol: dict[str, Any], root: Path) -> dict[str, Any]:
    datasets: dict[str, Any] = {}
    errors: list[str] = []
    for name, spec in (protocol.get("datasets") or {}).items():
        path = root / str(spec.get("path") or "")
        if not path.is_file():
            errors.append(f"missing_dataset:{name}:{path}")
            continue
        rows = load_jsonl(path)
        required = [str(field) for field in spec.get("required_nonempty_fields") or []]
        coverage = {field: sum(present(row.get(field)) for row in rows) for field in required}
        datasets[name] = {
            "path": str(path).replace("\\", "/"),
            "sha256": sha256(path),
            "records": len(rows),
            "required_field_coverage": coverage,
            "all_required_fields_present_on_all_rows": all(count == len(rows) for count in coverage.values()),
            "metrics": spec.get("metrics") or {},
            "conditions": spec.get("conditions") or [],
        }
    return {
        "status": "DATASET_NATIVE_ELIGIBILITY_AUDIT_PASSED" if not errors else "VERIFY_FAILED",
        "protocol_id": protocol.get("protocol_id"),
        "protocol_sha256": None,
        "inference_run": False,
        "frozen_artifacts_modified": False,
        "errors": errors,
        "datasets": datasets,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError(f"output_exists:{args.output}")
    protocol = load_json(args.protocol)
    result = audit(protocol, args.root)
    result["protocol_sha256"] = sha256(args.protocol)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "datasets": len(result["datasets"]), "errors": len(result["errors"])}, sort_keys=True))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
