#!/usr/bin/env python3
"""T12 Slice 4 synthetic fixture evaluation CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.model.checkpoint_download import resolve_hub_cache_dir
from ambiguity_manager.model.synthetic_evaluation import (
    SyntheticEvaluationError,
    atomic_write_json,
    build_evidence_scaffold,
    load_fixture_manifest,
    load_json,
    refresh_evidence_hashes,
    render_report_markdown,
    resolve_evaluation_paths,
    run_fixtures,
    validate_pre_run_gates,
    validate_synthetic_evaluation_evidence,
)
from ambiguity_manager.paths import ProjectPaths


def _ensure_offline_env() -> None:
    from ambiguity_manager.model.checkpoint_download import is_wsl_linux_runtime

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    native_hf = Path.home() / ".cache" / "huggingface"
    if is_wsl_linux_runtime():
        os.environ["HF_HOME"] = str(native_hf)
        os.environ["HF_HUB_CACHE"] = str(native_hf / "hub")
    elif "HF_HOME" not in os.environ:
        os.environ["HF_HOME"] = str(native_hf)
        os.environ["HF_HUB_CACHE"] = str(native_hf / "hub")


def _load_context(repo_root: Path) -> dict:
    paths = resolve_evaluation_paths(repo_root)
    manifest = load_fixture_manifest(paths["fixture_path"])
    download_evidence = load_json(paths["download_evidence"])
    load_evidence = load_json(paths["load_evidence"])
    register = load_json(paths["register"])
    if paths["evidence_path"].is_file():
        evidence = load_json(paths["evidence_path"])
    else:
        evidence = build_evidence_scaffold(fixture_file_sha256=manifest.fixture_file_sha256)
    return {
        "paths": paths,
        "manifest": manifest,
        "download_evidence": download_evidence,
        "load_evidence": load_evidence,
        "register": register,
        "evidence": evidence,
    }


def cmd_preflight(repo_root: Path) -> int:
    _ensure_offline_env()
    ctx = _load_context(repo_root)
    cache_dir = resolve_hub_cache_dir()
    errors = validate_pre_run_gates(
        download_evidence=ctx["download_evidence"],
        register=ctx["register"],
        load_evidence=ctx["load_evidence"],
        cache_dir=cache_dir,
    )
    try:
        load_fixture_manifest(
            ctx["paths"]["fixture_path"],
            expected_sha256=ctx["manifest"].fixture_file_sha256,
        )
    except SyntheticEvaluationError as exc:
        errors.append(str(exc))

    refresh_evidence_hashes(ctx)
    ctx["evidence"]["fixture_file_sha256"] = ctx["manifest"].fixture_file_sha256
    ctx["evidence"]["run_status"] = "preflight_passed" if not errors else "preflight_failed"
    atomic_write_json(ctx["paths"]["evidence_path"], ctx["evidence"])

    report = {
        "preflight_status": "passed" if not errors else "failed",
        "fixture_count": len(ctx["manifest"].fixtures),
        "fixture_file_sha256": ctx["manifest"].fixture_file_sha256,
        "errors": errors,
        "selected_model": ctx["register"].get("selected_model"),
    }
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


def cmd_run(repo_root: Path, *, regenerate: bool) -> int:
    _ensure_offline_env()
    ctx = _load_context(repo_root)
    cache_dir = resolve_hub_cache_dir()
    errors = validate_pre_run_gates(
        download_evidence=ctx["download_evidence"],
        register=ctx["register"],
        load_evidence=ctx["load_evidence"],
        cache_dir=cache_dir,
    )
    if errors:
        raise SystemExit("pre-run gate failure:\n" + "\n".join(errors))

    ctx["evidence"] = run_fixtures(
        repo_root=repo_root,
        manifest=ctx["manifest"],
        evidence=ctx["evidence"],
        regenerate=regenerate,
    )
    refresh_evidence_hashes(ctx)
    atomic_write_json(ctx["paths"]["evidence_path"], ctx["evidence"])

    summary = {
        "run_status": ctx["evidence"]["run_status"],
        "attempted_count": ctx["evidence"]["aggregate_metrics"]["attempted_count"],
        "completed_generation_count": ctx["evidence"]["aggregate_metrics"]["completed_generation_count"],
        "schema_valid_count": ctx["evidence"]["aggregate_metrics"]["schema_valid_count"],
        "outcome_classification": ctx["evidence"]["outcome_classification"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if ctx["evidence"]["run_status"] == "completed" else 1


def cmd_verify(repo_root: Path) -> int:
    ctx = _load_context(repo_root)
    errors = validate_synthetic_evaluation_evidence(
        ctx["evidence"],
        register=ctx["register"],
        expected_fixture_sha256=ctx["manifest"].fixture_file_sha256,
    )
    report = {
        "verification_status": "passed" if not errors else "failed",
        "errors": errors,
        "run_status": ctx["evidence"].get("run_status"),
        "aggregate_reconciliation": ctx["evidence"].get("aggregate_reconciliation"),
    }
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


def cmd_report(repo_root: Path) -> int:
    ctx = _load_context(repo_root)
    errors = validate_synthetic_evaluation_evidence(
        ctx["evidence"],
        register=ctx["register"],
        expected_fixture_sha256=ctx["manifest"].fixture_file_sha256,
    )
    markdown = render_report_markdown(ctx["evidence"])
    ctx["paths"]["report_path"].parent.mkdir(parents=True, exist_ok=True)
    ctx["paths"]["report_path"].write_text(markdown + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "report_relpath": "docs/reports/ticket_T12_synthetic_evaluation.md",
                "validation_errors": errors,
                "outcome_classification": ctx["evidence"].get("outcome_classification"),
            },
            indent=2,
        )
    )
    return 0 if not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="T12 Slice 4 synthetic evaluation")
    parser.add_argument("mode", choices=("preflight", "run", "verify", "report"))
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Regenerate all fixture outputs even when prior results exist",
    )
    args = parser.parse_args()
    repo_root = ProjectPaths.from_repo_root().root

    if args.mode == "preflight":
        return cmd_preflight(repo_root)
    if args.mode == "run":
        return cmd_run(repo_root, regenerate=args.regenerate)
    if args.mode == "verify":
        return cmd_verify(repo_root)
    return cmd_report(repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
