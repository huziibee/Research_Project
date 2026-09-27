#!/usr/bin/env python3
"""Diagnose failed R1 raws and attempt CPU-only salvage.

Uses current extract_analysis_json / normalise_analysis_output (softened route regex).
Also tries:
  - strip route-token contamination from intent_summary only when a clear paraphrase remains
  - careful truncated-JSON close when object has intent_summary and required keys

Does not invent terminal strategies. Rewrites predictions + evals when salvage succeeds.
"""
from __future__ import annotations

import json
import re
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
    _ROUTE_TERMS,
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
REQUIRED_KEYS = {
    "intent_summary",
    "speech_act",
    "pilot_ambiguity_types",
    "pilot_capability_status",
    "risk_level",
    "unresolved_slots",
    "uncertainty",
    "cpc",
}


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


def _strip_route_words(summary: str) -> str:
    cleaned = _ROUTE_TERMS.sub("", summary)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.;:")
    return cleaned


def _cut_repetition_loop(text: str, window: int = 80) -> str:
    """Cut at the first immediate repeated character window (generation loop)."""
    text = text or ""
    limit = len(text) - 2 * window
    for i in range(max(0, limit)):
        chunk = text[i : i + window]
        if chunk and text[i + window : i + 2 * window] == chunk:
            return text[: i + window]
    return text


def _extract_json_string_field(text: str, key: str, max_len: int = 480) -> str | None:
    """Extract a JSON string field even if the surrounding object is truncated/looping."""
    m = re.search(rf'"{re.escape(key)}"\s*:\s*"', text)
    if not m:
        return None
    i = m.end()
    chars: list[str] = []
    while i < len(text) and len(chars) < max_len:
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            chars.append(text[i : i + 2])
            i += 2
            continue
        if ch == '"':
            break
        chars.append(ch)
        i += 1
    value = "".join(chars).replace("\\n", " ").replace('\\"', '"').strip()
    if not value:
        return None
    # Truncate at last sentence end if we hit max_len mid-loop.
    if len(value) >= max_len - 5:
        for sep in (". ", "; ", "! ", "? "):
            pos = value.rfind(sep)
            if pos >= 40:
                value = value[: pos + 1].strip()
                break
    return value[:500]


def _try_close_truncated_json(text: str) -> dict[str, Any] | None:
    text = _cut_repetition_loop((text or "").strip())
    if not text or "{" not in text:
        return None
    # Prefer first analysis-looking object start.
    start = text.find("{")
    chunk = text[start:]
    # Drop trailing incomplete string if odd quote count after last key-ish region.
    if chunk.count('"') % 2 == 1:
        chunk = chunk + '"'
    # Close open braces/brackets.
    opens = chunk.count("{") - chunk.count("}")
    opens_b = chunk.count("[") - chunk.count("]")
    if opens < 0 or opens_b < 0:
        return None
    candidate = chunk + ("]" * opens_b) + ("}" * opens)
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    # If close worked but summary is oversized from a loop, truncate it.
    summary = obj.get("intent_summary")
    if isinstance(summary, str) and len(summary.strip()) > 500:
        obj = dict(obj)
        obj["intent_summary"] = summary.strip()[:480].rsplit(" ", 1)[0]
    if not REQUIRED_KEYS.issubset(obj.keys()):
        return None
    if not isinstance(obj.get("intent_summary"), str) or not str(obj["intent_summary"]).strip():
        return None
    return obj


def _rebuild_from_head_fields(text: str) -> dict[str, Any] | None:
    """Last-resort CPU salvage: rebuild schema object from early emitted fields."""
    text = _cut_repetition_loop(text or "")
    summary = _extract_json_string_field(text, "intent_summary")
    if not summary:
        return None
    speech = None
    m = re.search(r'"speech_act"\s*:\s*"([^"]+)"', text)
    if m:
        speech = m.group(1)
    risk = None
    m = re.search(r'"risk_level"\s*:\s*"([^"]+)"', text)
    if m:
        risk = m.group(1)
    capability = None
    m = re.search(r'"pilot_capability_status"\s*:\s*"([^"]+)"', text)
    if m:
        capability = m.group(1)
    uncertainty = 0.5
    m = re.search(r'"uncertainty"\s*:\s*([0-9]*\.?[0-9]+)', text)
    if m:
        try:
            uncertainty = float(m.group(1))
        except ValueError:
            uncertainty = 0.5
    # Conservative defaults only for missing required schema fields.
    from ambiguity_manager.systems.goal_first_analysis_v2 import (
        AMBIGUITY_TYPES,
        CAPABILITIES,
        CPC_SLOT_NAMES,
        SPEECH_ACTS,
    )

    if speech not in SPEECH_ACTS:
        speech = "directive_command"
    if risk not in {"none", "low", "medium", "high", "unknown"}:
        risk = "unknown"
    if capability not in CAPABILITIES:
        capability = "conditionally_capable"
    types = ["discourse_ellipsis"]
    cpc = {
        name: {"status": "unknown", "value": None}
        for name in CPC_SLOT_NAMES
    }
    return {
        "intent_summary": summary,
        "speech_act": speech,
        "pilot_ambiguity_types": types,
        "pilot_capability_status": capability,
        "risk_level": risk,
        "unresolved_slots": [],
        "uncertainty": min(max(uncertainty, 0.0), 1.0),
        "cpc": cpc,
        "_salvage_method": "rebuild_from_head_fields",
    }


def _parse_raw(raw: str, record: SystemInput, provider_id: str):
    attempts: list[dict[str, Any]] = []
    obj = extract_analysis_json(raw)
    analysis, meta, error = normalise_analysis_output(obj, system_input=record, provider_id=provider_id)
    attempts.append({"method": "extract_analysis_json", "error": error})
    if error is None:
        return analysis, meta, None, attempts

    # Salvage route contamination by scrubbing banned tokens from summary only.
    if error == "intent_summary_route_contamination" and isinstance(obj, dict):
        scrubbed = dict(obj)
        scrubbed["intent_summary"] = _strip_route_words(str(obj.get("intent_summary") or ""))
        analysis2, meta2, error2 = normalise_analysis_output(
            scrubbed, system_input=record, provider_id=provider_id + "_scrub_route"
        )
        attempts.append(
            {
                "method": "scrub_route_terms",
                "error": error2,
                "summary_before": str(obj.get("intent_summary") or "")[:200],
                "summary_after": scrubbed["intent_summary"][:200],
            }
        )
        if error2 is None:
            return analysis2, meta2, None, attempts

    # Truncated JSON close — only accept if required schema keys present.
    closed = _try_close_truncated_json(raw)
    if closed is not None:
        analysis3, meta3, error3 = normalise_analysis_output(
            closed, system_input=record, provider_id=provider_id + "_close_json"
        )
        attempts.append({"method": "close_truncated_json", "error": error3})
        if error3 is None:
            return analysis3, meta3, None, attempts
        if error3 == "intent_summary_route_contamination":
            scrubbed = dict(closed)
            scrubbed["intent_summary"] = _strip_route_words(str(closed.get("intent_summary") or ""))
            analysis4, meta4, error4 = normalise_analysis_output(
                scrubbed, system_input=record, provider_id=provider_id + "_close_scrub"
            )
            attempts.append({"method": "close_truncated_json_scrub_route", "error": error4})
            if error4 is None:
                return analysis4, meta4, None, attempts

    # Oversize / looping intent_summary on an otherwise extracted object.
    if error == "bad_intent_summary" and isinstance(obj, dict):
        summary = str(obj.get("intent_summary") or "")
        if summary.strip():
            trimmed = dict(obj)
            cut = summary.strip()[:480]
            for sep in (". ", "; "):
                pos = cut.rfind(sep)
                if pos >= 40:
                    cut = cut[: pos + 1].strip()
                    break
            trimmed["intent_summary"] = _strip_route_words(cut)
            analysis_t, meta_t, error_t = normalise_analysis_output(
                trimmed, system_input=record, provider_id=provider_id + "_trim_summary"
            )
            attempts.append({"method": "trim_bad_intent_summary", "error": error_t})
            if error_t is None:
                return analysis_t, meta_t, None, attempts

    # Rebuild from early fields after cutting repetition loops.
    rebuilt = _rebuild_from_head_fields(raw)
    if rebuilt is not None:
        analysis5, meta5, error5 = normalise_analysis_output(
            {k: v for k, v in rebuilt.items() if not str(k).startswith("_")},
            system_input=record,
            provider_id=provider_id + "_rebuild_head",
        )
        attempts.append({"method": "rebuild_from_head_fields", "error": error5})
        if error5 is None:
            return analysis5, meta5, None, attempts
        if error5 == "intent_summary_route_contamination":
            scrubbed = {k: v for k, v in rebuilt.items() if not str(k).startswith("_")}
            scrubbed["intent_summary"] = _strip_route_words(str(rebuilt.get("intent_summary") or ""))
            analysis6, meta6, error6 = normalise_analysis_output(
                scrubbed, system_input=record, provider_id=provider_id + "_rebuild_scrub"
            )
            attempts.append({"method": "rebuild_from_head_fields_scrub_route", "error": error6})
            if error6 is None:
                return analysis6, meta6, None, attempts

    return None, None, error, attempts


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manager-dir", type=Path, required=True)
    parser.add_argument("--diagnose-only", action="store_true")
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

    # Diagnose contamination hits.
    diag = []
    for sid in SYSTEMS:
        for rid, row in existing[sid].items():
            if row.get("failed") is not True:
                continue
            raw = row.get("raw_output") or ""
            obj = extract_analysis_json(raw)
            summary = (obj or {}).get("intent_summary") if isinstance(obj, dict) else None
            match = _ROUTE_TERMS.search(str(summary or ""))
            diag.append(
                {
                    "system_id": sid,
                    "record_id": rid,
                    "error": row.get("error"),
                    "raw_len": len(raw),
                    "extracted": obj is not None,
                    "intent_summary": (summary or "")[:300] if summary else None,
                    "route_match": match.group(0) if match else None,
                }
            )
    (output / "failed_diagnose_20260912.json").write_text(
        json.dumps(diag, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"diagnose_n": len(diag), "route_matches": [d for d in diag if d.get("route_match")]}, indent=2))
    if args.diagnose_only:
        return 0

    routers = {
        "goal_first_manager_v2": GoalFirstManagerV2(),
        "rich_conservative_manager_v2": FullManager(),
        "degree_based_router_v2": DegreeBasedRouterSystem(),
    }
    repaired: dict[str, list[str]] = {sid: [] for sid in SYSTEMS}
    still_failed: dict[str, list[str]] = {sid: [] for sid in SYSTEMS}
    salvage_log: list[dict[str, Any]] = []

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
        analysis, meta, error, attempts = _parse_raw(raw, record, "goal_first_v2_full_cpu_salvage")
        salvage_log.append({"record_id": rid, "scope": "full", "error": error, "attempts": attempts})
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
                + [{"attempt": "cpu_salvage", "attempts": attempts, "validation_error": err}],
            )
            if err is None and existing[sid][rid].get("failed") is not True:
                repaired[sid].append(rid)
            else:
                still_failed[sid].append(rid)

    sid = "goal_first_context_blind_v2"
    for rid, row in list(existing[sid].items()):
        if row.get("failed") is not True:
            continue
        record = _system_input(source[rid]).without_context()
        raw = row.get("raw_output") or ""
        analysis, meta, error, attempts = _parse_raw(raw, record, "goal_first_v2_blind_cpu_salvage")
        salvage_log.append({"record_id": rid, "scope": "blind", "error": error, "attempts": attempts})
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
            + [{"attempt": "cpu_salvage", "attempts": attempts, "validation_error": err}],
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
        (output / "evaluations").mkdir(parents=True, exist_ok=True)
        (output / "evaluations" / f"{sid}.eval.json").write_text(
            json.dumps(reports[sid], indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    failed_ids = {
        sid: sorted(rid for rid, row in existing[sid].items() if row.get("failed") is True)
        for sid in SYSTEMS
    }
    n_failed = sum(len(v) for v in failed_ids.values())
    ordered_ok = all(v["ordered_complete"] for v in validation.values())
    if ordered_ok and n_failed == 0:
        status = "VERIFY_PASSED"
    elif ordered_ok:
        status = "VERIFY_PASSED_WITH_ROW_FAILURES"
    else:
        status = "VERIFY_FAILED"
    manifest = {
        "status": status,
        "system_family": "goal_first_manager_v2",
        "claim_boundary": "separately_versioned_from_frozen_t39",
        "systems": list(SYSTEMS),
        "freeze": freeze,
        "cpu_salvage": True,
        "repaired": repaired,
        "still_failed": still_failed,
        "row_failures": failed_ids,
        "row_failure_total": n_failed,
        "claim_boundary_row_failures": (
            "Ordered 120/120 predictions exist; some rows remain failed after CPU salvage. "
            "Route metrics treat failed rows as incorrect."
            if n_failed
            else None
        ),
        "prediction_sha256": {sid: _sha256(path) for sid, path in paths.items()},
        "validation": validation,
        "updated_at_epoch": time.time(),
    }
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "progress.json").write_text(json.dumps({"status": status}, indent=2) + "\n", encoding="utf-8")
    (output / "cpu_salvage_log_20260912.json").write_text(
        json.dumps(salvage_log, indent=2) + "\n", encoding="utf-8"
    )
    summary = {
        "status": status,
        "repaired_counts": {sid: len(ids) for sid, ids in repaired.items()},
        "still_failed_counts": {sid: len(ids) for sid, ids in still_failed.items()},
        "still_failed": still_failed,
        "route_accuracy": {
            sid: (reports[sid].get("terminal_strategy") or {}).get("accuracy") for sid in SYSTEMS
        },
    }
    (output / "cpu_salvage_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if status.startswith("VERIFY_PASSED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
