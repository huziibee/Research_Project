#!/usr/bin/env python3
"""Lightweight CPU-only T12 cluster canary (no model / GPU / ML imports)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path


FORBIDDEN_IMPORTS = ("torch", "transformers", "vllm")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _count_jsonl_rows(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")


def _assert_no_ml_imports() -> None:
    for name in FORBIDDEN_IMPORTS:
        if name in sys.modules:
            raise RuntimeError(f"forbidden_import_loaded:{name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="T12 CPU-only cluster canary")
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-archive-sha256", required=True)
    parser.add_argument(
        "--source-identity-manifest",
        type=Path,
        help="Optional path to retained source-identity manifest to copy into results.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _assert_no_ml_imports()
    args = build_parser().parse_args(argv)
    started = _utc_now()
    result_dir = args.result_dir.resolve()
    result_dir.mkdir(parents=True, exist_ok=True)

    records_path = result_dir / "canary_records.jsonl"
    result_path = result_dir / "canary_result.json"
    manifest_path = result_dir / "run_manifest.json"

    if any(path.exists() for path in (records_path, result_path, manifest_path)):
        raise RuntimeError(f"result_dir_not_empty:{result_dir}")

    record = {
        "record_id": "canary-001",
        "run_id": args.run_id,
        "message": "t12_cluster_operator_canary_ok",
        "timestamp_utc": started,
    }
    records_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")

    if args.source_identity_manifest is not None:
        src = args.source_identity_manifest
        if not src.is_file():
            raise RuntimeError(f"source_identity_manifest_missing:{src}")
        dest = result_dir / "source_identity_manifest.json"
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    ended = _utc_now()
    result = {
        "schema_version": "1.0.0",
        "profile": "canary",
        "success": True,
        "run_id": args.run_id,
        "source_commit_sha": args.source_commit,
        "source_archive_sha256": args.source_archive_sha256,
        "hostname": socket.gethostname(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "slurm_job_partition": os.environ.get("SLURM_JOB_PARTITION"),
        "slurm_nodelist": os.environ.get("SLURM_NODELIST"),
        "python_version": platform.python_version(),
        "start_timestamp_utc": started,
        "end_timestamp_utc": ended,
        "gpus_required": False,
        "model_loaded": False,
        "protected_data_used": False,
        "forbidden_imports_present": [name for name in FORBIDDEN_IMPORTS if name in sys.modules],
    }
    _write_json(result_path, result)

    files = sorted(path for path in result_dir.iterdir() if path.is_file())
    file_entries = []
    for path in files:
        entry: dict = {
            "relative_path": path.name,
            "sha256": _sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        if path.suffix == ".jsonl":
            entry["row_count"] = _count_jsonl_rows(path)
        file_entries.append(entry)

    manifest = {
        "schema_version": "1.0.0",
        "run_id": args.run_id,
        "profile": "canary",
        "source_commit_sha": args.source_commit,
        "source_archive_sha256": args.source_archive_sha256,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "hostname": socket.gethostname(),
        "start_timestamp_utc": started,
        "end_timestamp_utc": ended,
        "success": True,
        "files": file_entries,
    }
    _write_json(manifest_path, manifest)

    # Recompute after writing manifest itself is already included before this write;
    # rewrite manifest to include its own hash after a finalisation pass.
    files = sorted(path for path in result_dir.iterdir() if path.is_file())
    file_entries = []
    for path in files:
        if path.name == "run_manifest.json":
            continue
        entry = {
            "relative_path": path.name,
            "sha256": _sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        if path.suffix == ".jsonl":
            entry["row_count"] = _count_jsonl_rows(path)
        file_entries.append(entry)
    manifest["files"] = file_entries
    manifest["finalised"] = True
    _write_json(manifest_path, manifest)

    _assert_no_ml_imports()
    print(f"CANARY_OK run_id={args.run_id} result_dir={result_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
