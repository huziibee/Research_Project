#!/usr/bin/env python3
"""Exploratory, read-only Pilot-120 capability-status probe with GLiNER2.5-Decide.

The model receives source fields only. Gold is loaded after predictions and is
used solely for scoring. This does not replace the project's frozen pipeline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/annotations/pilot_120_v1/source_canonical.jsonl"
GOLD = ROOT / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl"
SOURCE_SHA256 = "f33b1e29f1e8aa256a475f07213aa07247def47d8e2148d54a472a40b71b05c9"
GOLD_SHA256 = "5e23ad1a92ff1873c8f039a8ce560a111dd6fb6b8ae8c11d6cf34dbfa1c360db"
MODEL_ID = "fastino/GLiNER2.5-Decide"
MODEL_REVISION = "5a7adf72a23b4d311abae6ce050d7f0012bb3416"
MODEL_SHA256 = "40a5a23ff860dc3dff426cecd1048cacdd29c648c96db209dad818e9686dc997"
MODEL_MANIFEST = (ROOT / "research/pilot120/gliner25_decide_capability_probe_v1"
                  / "model_snapshot_sha256.json")
LABELS = {
    "capable": "The robot can do the requested task within its stated abilities.",
    "conditionally_capable": "The robot can do the task only if a stated condition is met.",
    "incapable": "The robot lacks the ability, tool, reach, or access to do the task.",
    "unauthorized": "The robot can physically do the task but permission is missing or denied.",
    "unsafe": "Doing the task presents an unacceptable safety risk.",
}
SCHEMA = {"capability_status": {"labels": LABELS}}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rows(path: Path, expected_hash: str) -> list[dict]:
    actual = digest(path)
    if actual != expected_hash:
        raise ValueError(f"frozen_hash_mismatch: {path}: {actual}")
    result = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    ids = [row["record_id"] for row in result]
    if len(result) != 120 or len(set(ids)) != 120:
        raise ValueError(f"frozen_coverage_mismatch: {path}")
    return result


def render_source(row: dict) -> str:
    dialogue = row.get("dialogue_history") or []
    return "\n".join(
        (
            f"Command: {row.get('command') or ''}",
            "Dialogue history: " + json.dumps(dialogue, ensure_ascii=False),
            f"Scene context: {row.get('scene_context') or ''}",
            f"Robot capability context: {row.get('capability_context') or ''}",
        )
    )


def verify_model_snapshot(model_dir: Path) -> None:
    manifest = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    if manifest["model_id"] != MODEL_ID or manifest["revision"] != MODEL_REVISION:
        raise ValueError("model_manifest_identity_mismatch")
    files = manifest["files"]
    if files.get("model.safetensors") != MODEL_SHA256:
        raise ValueError("model_weight_manifest_mismatch")
    actual_names = {
        path.relative_to(model_dir).as_posix()
        for path in model_dir.rglob("*")
        if path.is_file() and ".cache" not in path.relative_to(model_dir).parts
    }
    if actual_names != set(files):
        raise ValueError("model_snapshot_file_set_mismatch")
    for name, expected_hash in files.items():
        if digest(model_dir / name) != expected_hash:
            raise ValueError(f"model_snapshot_hash_mismatch: {name}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--record-id", action="append", default=[])
    args = parser.parse_args()

    source = rows(SOURCE, SOURCE_SHA256)
    selected = [row for row in source if not args.record_id or row["record_id"] in args.record_id]
    if (not selected or len(args.record_id) != len(set(args.record_id))
            or (args.record_id and len(selected) != len(args.record_id))):
        raise ValueError("unknown_or_duplicate_record_id")
    verify_model_snapshot(args.model_dir)

    from gliner2 import AutoExtractor, __version__ as gliner_version
    import torch

    model = AutoExtractor.from_pretrained(str(args.model_dir))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    prediction_path = args.output_dir / "predictions.jsonl"
    predictions: list[dict] = []
    with prediction_path.open("w", encoding="utf-8") as out:
        for index, row in enumerate(selected, 1):
            result = {"record_id": row["record_id"], "prediction": None, "confidence": None,
                      "error": None}
            try:
                response = model.classify_text(render_source(row), SCHEMA,
                                               include_confidence=True)
                status = response["capability_status"]
                result["prediction"] = status["label"] if isinstance(status, dict) else status
                result["confidence"] = status.get("confidence") if isinstance(status, dict) else None
                if result["prediction"] not in LABELS:
                    raise ValueError("out_of_schema_prediction")
            except Exception as exc:
                result["error"] = f"{type(exc).__name__}: {exc}"
                result["prediction"] = None
                result["confidence"] = None
            predictions.append(result)
            out.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
            out.flush()
            print(f"GLINER_ROW {index}/{len(selected)} {row['record_id']} "
                  f"pred={result['prediction']} failed={result['error'] is not None}", flush=True)

    gold = {row["record_id"]: row for row in rows(GOLD, GOLD_SHA256)}
    if {row["record_id"] for row in source} != set(gold):
        raise ValueError("source_gold_id_set_mismatch")
    correct = sum(p["prediction"] == gold[p["record_id"]]["capability_status"]
                  for p in predictions)
    confusion = Counter(
        (gold[p["record_id"]]["capability_status"], p["prediction"] or "FAILED")
        for p in predictions
    )
    summary = {
        "status": "exploratory_source_seen_in_prior_project_development",
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "model_weight_sha256": MODEL_SHA256,
        "gliner2_version": gliner_version,
        "torch_version": torch.__version__,
        "source_sha256": SOURCE_SHA256,
        "gold_sha256": GOLD_SHA256,
        "schema": SCHEMA,
        "selected_record_ids": [row["record_id"] for row in selected],
        "n": len(predictions),
        "failed": sum(p["error"] is not None for p in predictions),
        "exact": correct,
        "accuracy": correct / len(predictions),
        "confusion": [
            {"gold": label, "predicted": predicted, "n": count}
            for (label, predicted), count in sorted(confusion.items())
        ],
        "prediction_sha256": digest(prediction_path),
        "claim_limit": "Capability status includes authorization and safety; this is not a "
                       "five-gate or physical-robot capability score.",
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"GLINER_DONE exact={correct}/{len(predictions)} failed={summary['failed']} "
          f"output={args.output_dir}")


if __name__ == "__main__":
    main()
