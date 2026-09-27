#!/usr/bin/env python3
"""CPU reparse of failed goal-first v2 rows using improved JSON selection.

No model load. Uses stored raw_output + routers. Rewrites ordered prediction
files and re-runs deterministic evaluations.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ambiguity_manager.evaluation import pilot_120 as p120  # noqa: E402
from ambiguity_manager.systems.contracts import SystemInput  # noqa: E402
from ambiguity_manager.systems.goal_first_analysis_v2 import (  # noqa: E402
    extract_analysis_json,
    normalise_analysis_output,
)
from ambiguity_manager.systems.manager import FullManager, GoalFirstManagerV2  # noqa: E402
from ambiguity_manager.systems.variants import DegreeBasedRouterSystem  # noqa: E402
from evaluate_goal_first_manager_v2 import (  # noqa: E402
    SYSTEMS,
    _prediction_row,
    _rewrite_predictions,
    _sha256,
)
from evaluate_pilot_120_direct_base import verify_freeze  # noqa: E402

FULL_CONTEXT = ("goal_first_manager_v2", "rich_conservative_manager_v2", "degree_based_router_v2")


def _system_input(row: dict[str, Any]) -> SystemInput:
    return SystemInput(
        record_id=str(row["record_id"]),
        command=str(row["command"]),
        dialogue_history=tuple(str(item) for item in row.get("dialogue_history") or []),
        scene_context=row.get("scene_context"),
        capability_context=row.get("capability_context"),
        protected_data=False,
    )


def _load_by_id(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        rows[str(item["record_id"])] = item
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manager-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.manager_dir.resolve()
    freeze = verify_freeze(root)
    source = {
        str(row["record_id"]): row
        for row in p120.load_jsonl(root / "data/annotations/pilot_120_v1/source_canonical.jsonl")
    }
    expected_ids = list(source)
    paths = {sid: output / "predictions" / f"{sid}.predictions.jsonl" for sid in SYSTEMS}
    existing = {sid: _load_by_id(path) for sid, path in paths.items()}
    routers = {
        "goal_first_manager_v2": GoalFirstManagerV2(),
        "rich_conservative_manager_v2": FullManager(),
        "degree_based_router_v2": DegreeBasedRouterSystem(),
    }
    repaired: dict[str, list[str]] = {sid: [] for sid in SYSTEMS}
    still_failed: dict[str, list[str]] = {sid: [] for sid in SYSTEMS}

    # Full-context systems share the same raw analysis on failures.
    full_failed_ids = sorted(
        {
            rid
            for sid in FULL_CONTEXT
            for rid, row in existing[sid].items()
            if row.get("failed") is True
        }
    )
    for rid in full_failed_ids:
        record = _system_input(source[rid])
        donor = next(existing[sid][rid] for sid in FULL_CONTEXT if rid in existing[sid])
        raw = donor.get("raw_output") or ""
        analysis, meta, error = normalise_analysis_output(
            extract_analysis_json(raw), system_input=record, provider_id="goal_first_v2_full_context_reparse"
        )
        for sid in FULL_CONTEXT:
            if rid not in existing[sid] or existing[sid][rid].get("failed") is not True:
                continue
            if error is not None or analysis is None or meta is None:
                still_failed[sid].append(rid)
                continue
            try:
                result = routers[sid].run(record, cached_analysis=analysis)
                err = None
            except Exception as exc:  # noqa: BLE001
                result = None
                err = f"system_exception:{type(exc).__name__}:{exc}"
            existing[sid][rid] = _prediction_row(
                record_id=rid,
                system_id=sid,
                result=result,
                meta=meta,
                raw_output=raw,
                latency_ms=float(donor.get("latency_ms") or 0.0),
                error=err,
                analysis_attempts=list(donor.get("analysis_attempts") or [])
                + [{"attempt": "cpu_reparse", "validation_error": None if err is None else err}],
            )
            if err is None and existing[sid][rid].get("failed") is not True:
                repaired[sid].append(rid)
            else:
                still_failed[sid].append(rid)

    # Context-blind failures are independent.
    sid = "goal_first_context_blind_v2"
    for rid, row in list(existing[sid].items()):
        if row.get("failed") is not True:
            continue
        record = _system_input(source[rid]).without_context()
        raw = row.get("raw_output") or ""
        analysis, meta, error = normalise_analysis_output(
            extract_analysis_json(raw), system_input=record, provider_id="goal_first_v2_context_blind_reparse"
        )
        if error is not None or analysis is None or meta is None:
            still_failed[sid].append(rid)
            continue
        try:
            result = GoalFirstManagerV2().run(record, cached_analysis=analysis)
            err = None
        except Exception as exc:  # noqa: BLE001
            result = None
            err = f"system_exception:{type(exc).__name__}:{exc}"
        existing[sid][rid] = _prediction_row(
            record_id=rid,
            system_id=sid,
            result=result,
            meta=meta,
            raw_output=raw,
            latency_ms=float(row.get("latency_ms") or 0.0),
            error=err,
            analysis_attempts=list(row.get("analysis_attempts") or [])
            + [{"attempt": "cpu_reparse", "validation_error": None if err is None else err}],
        )
        if err is None and existing[sid][rid].get("failed") is not True:
            repaired[sid].append(rid)
        else:
            still_failed[sid].append(rid)

    for sid, path in paths.items():
        _rewrite_predictions(path, existing[sid], expected_ids)

    reports = {}
    validation = {}
    for sid, path in paths.items():
        rows = p120.load_jsonl(path)
        ids = [str(row.get("record_id") or "") for row in rows]
        validation[sid] = {"n_rows": len(rows), "ordered_complete": ids == expected_ids}
        reports[sid] = p120.evaluate_predictions(
            path, config_path=root / "configs/evaluation/pilot_120_v1.json", paths=p120.default_paths(root)
        )
        (output / "evaluations" / f"{sid}.eval.json").write_text(
            json.dumps(reports[sid], indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    failed_any = any(row.get("failed") is True for sid in SYSTEMS for row in existing[sid].values())
    status = "VERIFY_PASSED" if all(v["ordered_complete"] for v in validation.values()) and not failed_any else "VERIFY_FAILED"
    manifest = {
        "status": status,
        "system_family": "goal_first_manager_v2",
        "claim_boundary": "separately_versioned_from_frozen_t39",
        "systems": list(SYSTEMS),
        "freeze": freeze,
        "cpu_reparse": True,
        "repaired": repaired,
        "still_failed": still_failed,
        "prediction_sha256": {sid: _sha256(path) for sid, path in paths.items()},
        "validation": validation,
        "updated_at_epoch": time.time(),
    }
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "progress.json").write_text(
        json.dumps(
            {
                "status": status,
                "current_record_id": None,
                "records_completed": len(expected_ids),
                "records_expected": len(expected_ids),
                "updated_at_epoch": time.time(),
                "elapsed_seconds": 0,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    summary = {
        "status": status,
        "repaired_counts": {sid: len(ids) for sid, ids in repaired.items()},
        "still_failed_counts": {sid: len(ids) for sid, ids in still_failed.items()},
        "route_accuracy": {
            sid: (reports[sid].get("terminal_strategy") or {}).get("accuracy") for sid in SYSTEMS
        },
    }
    (output / "cpu_reparse_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if status == "VERIFY_PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
