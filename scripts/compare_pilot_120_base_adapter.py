#!/usr/bin/env python3
"""Emit a fail-closed, evaluation-only paired Pilot-120 comparison."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.evaluation import pilot_120 as p120  # noqa: E402
from evaluate_pilot_120_direct_base import (  # noqa: E402
    SELECTED_ADAPTER_SYSTEM_ID,
    SYSTEM_ID,
    verify_freeze,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"pilot_paired_json_unreadable:{path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"pilot_paired_json_not_object:{path}")
    return value


def _load_predictions(path: Path, *, expected_ids: set[str], system_id: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        record_id = str(row.get("record_id") or "")
        if not record_id or record_id in rows:
            raise ValueError(f"pilot_paired_duplicate_or_missing_record_id:{path}:{number}")
        if row.get("system_id") != system_id:
            raise ValueError(f"pilot_paired_system_id_mismatch:{path}:{number}")
        if row.get("failed") is not False or row.get("schema_valid") is not True:
            raise ValueError(f"pilot_paired_invalid_prediction:{path}:{record_id}")
        rows[record_id] = row
    if set(rows) != expected_ids:
        raise ValueError(f"pilot_paired_record_set_mismatch:{path}")
    return rows


def _metric(report: Mapping[str, Any], section: str, name: str) -> float:
    try:
        value = float(report[section][name])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"pilot_paired_metric_missing:{section}.{name}") from exc
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"pilot_paired_metric_out_of_range:{section}.{name}")
    return value


def _validate_report(report: Mapping[str, Any], *, system_id: str, freeze: Mapping[str, Any]) -> None:
    if report.get("gold_sha256") != freeze["gold_sha256"]:
        raise ValueError("pilot_paired_gold_hash_mismatch")
    if report.get("n_gold") != freeze["n"] or report.get("n_predictions_rows") != freeze["n"]:
        raise ValueError("pilot_paired_denominator_mismatch")
    operational = report.get("operational")
    if not isinstance(operational, Mapping):
        raise ValueError("pilot_paired_operational_missing")
    if operational.get("denominator") != freeze["n"]:
        raise ValueError("pilot_paired_operational_denominator_mismatch")
    if float(operational.get("schema_valid_rate", -1.0)) != 1.0:
        raise ValueError("pilot_paired_schema_valid_rate_not_one")
    if float(operational.get("failure_error_rate", -1.0)) != 0.0:
        raise ValueError("pilot_paired_failure_rate_not_zero")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--base-evaluation", type=Path, required=True)
    parser.add_argument("--adapter-evaluation", type=Path, required=True)
    parser.add_argument("--base-predictions", type=Path, required=True)
    parser.add_argument("--adapter-predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("pilot_paired_output_exists")

    freeze = verify_freeze(args.root.resolve())
    paths = p120.default_paths(args.root.resolve())
    config = p120.load_json(paths["config"])
    source = args.root.resolve() / config["source_canonical_jsonl"]
    expected_ids = {str(row["record_id"]) for row in p120.load_jsonl(source)}
    if len(expected_ids) != freeze["n"]:
        raise SystemExit("pilot_paired_freeze_id_count_mismatch")
    base = _load_json(args.base_evaluation)
    adapter = _load_json(args.adapter_evaluation)
    _validate_report(base, system_id=SYSTEM_ID, freeze=freeze)
    _validate_report(adapter, system_id=SELECTED_ADAPTER_SYSTEM_ID, freeze=freeze)
    base_rows = _load_predictions(args.base_predictions, expected_ids=expected_ids, system_id=SYSTEM_ID)
    adapter_rows = _load_predictions(args.adapter_predictions, expected_ids=expected_ids, system_id=SELECTED_ADAPTER_SYSTEM_ID)
    adapter_ids = {str(row.get("adapter_id") or "") for row in adapter_rows.values()}
    if len(adapter_ids) != 1 or not next(iter(adapter_ids)):
        raise SystemExit("pilot_paired_adapter_identity_inconsistent")

    metrics = (("terminal_strategy", "accuracy"), ("terminal_strategy", "macro_f1"), ("capability_status", "macro_f1"), ("ambiguity_types", "macro_f1"))
    deltas = {
        f"{section}.{name}": _metric(adapter, section, name) - _metric(base, section, name)
        for section, name in metrics
    }
    changed_terminal = sum(
        base_rows[record_id]["terminal_strategy"] != adapter_rows[record_id]["terminal_strategy"]
        for record_id in expected_ids
    )
    payload = {
        "status": "VERIFY_PASSED",
        "claim": "evaluation_only_paired_pilot_120_early_results",
        "valid_for_official_use": False,
        "may_influence_t28_selection": False,
        "may_influence_threshold_tuning": False,
        "protected_data_accessed": False,
        "frozen_gold_sha256": freeze["gold_sha256"],
        "denominator": freeze["n"],
        "base": {"system_id": SYSTEM_ID, "evaluation_sha256": _sha256(args.base_evaluation), "predictions_sha256": _sha256(args.base_predictions)},
        "adapter": {"system_id": SELECTED_ADAPTER_SYSTEM_ID, "evaluation_sha256": _sha256(args.adapter_evaluation), "predictions_sha256": _sha256(args.adapter_predictions), "adapter_id": next(iter(adapter_ids))},
        "metric_deltas_adapter_minus_base": deltas,
        "terminal_strategy_changed_n": changed_terminal,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps({"status": payload["status"], "denominator": payload["denominator"], "terminal_strategy_changed_n": changed_terminal}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
