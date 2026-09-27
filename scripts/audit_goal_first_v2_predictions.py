#!/usr/bin/env python3
"""CPU audit of goal-first v2 prediction directories. No model load. No retuning."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def audit_predictions(path: Path) -> dict:
    rows = load_jsonl(path)
    intent_nonnull = sum(bool(r.get("intent_summary")) for r in rows)
    failed = sum(bool(r.get("failed")) for r in rows)
    schema_valid = sum(bool(r.get("schema_valid")) for r in rows)
    routes: dict[str, int] = {}
    for r in rows:
        routes[str(r.get("terminal_strategy"))] = routes.get(str(r.get("terminal_strategy")), 0) + 1
    cpc_filled = 0
    for r in rows:
        parsed = r.get("parsed") or {}
        analysis = parsed.get("analysis") if isinstance(parsed, dict) else None
        cpc = None
        if isinstance(analysis, dict):
            cpc = analysis.get("cpc") or analysis.get("cpc_values")
        if isinstance(r.get("cpc"), dict):
            cpc = r["cpc"]
        if isinstance(cpc, dict) and any(v not in (None, "", [], {}) for v in cpc.values()):
            cpc_filled += 1
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "n_rows": len(rows),
        "failed": failed,
        "schema_valid": schema_valid,
        "intent_summary_nonnull": intent_nonnull,
        "cpc_any_filled": cpc_filled,
        "route_counts": routes,
        "record_ids_sorted_sha256": hashlib.sha256(
            ("\n".join(sorted(str(r.get("record_id")) for r in rows))).encode()
        ).hexdigest(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manager-dir", type=Path, required=True, help=".../manager with predictions/")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--expected-rows", type=int, default=120)
    args = ap.parse_args()

    pred_dir = args.manager_dir / "predictions"
    eval_dir = args.manager_dir / "evaluations"
    progress = args.manager_dir / "progress.json"
    report: dict = {
        "claim_boundary": "CPU hash/fill audit only; do not retune prompts from this file",
        "manager_dir": str(args.manager_dir),
        "expected_rows": args.expected_rows,
        "progress": json.loads(progress.read_text(encoding="utf-8")) if progress.exists() else None,
        "systems": {},
        "evaluations_present": {},
        "gates": {},
    }
    if not pred_dir.is_dir():
        raise SystemExit(f"missing_predictions_dir:{pred_dir}")
    for path in sorted(pred_dir.glob("*.predictions.jsonl")):
        sid = path.name.replace(".predictions.jsonl", "")
        report["systems"][sid] = audit_predictions(path)
    if eval_dir.is_dir():
        for path in sorted(eval_dir.glob("*.eval.json")):
            sid = path.name.replace(".eval.json", "")
            data = json.loads(path.read_text(encoding="utf-8"))
            term = data.get("terminal_strategy") or {}
            report["evaluations_present"][sid] = {
                "sha256": sha256_file(path),
                "route_accuracy": term.get("accuracy"),
                "n_gold": data.get("n_gold"),
                "n_predictions_rows": data.get("n_predictions_rows"),
            }
    systems = report["systems"]
    report["gates"] = {
        "all_systems_complete": bool(systems)
        and all(s["n_rows"] == args.expected_rows and s["failed"] == 0 for s in systems.values()),
        "intent_summary_full": bool(systems)
        and all(s["intent_summary_nonnull"] == args.expected_rows for s in systems.values()),
        "evaluations_written": bool(report["evaluations_present"]),
        "ready_for_hash_freeze_discussion": False,
    }
    report["gates"]["ready_for_hash_freeze_discussion"] = (
        report["gates"]["all_systems_complete"] and report["gates"]["evaluations_written"]
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "gates": report["gates"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
