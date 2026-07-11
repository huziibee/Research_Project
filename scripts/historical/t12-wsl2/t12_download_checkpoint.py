#!/usr/bin/env python3
"""T12 Slice 3B deterministic checkpoint download controller."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.model.checkpoint_download import (  # noqa: E402
    AUTHORIZED_CANDIDATE_ENTRY_ID,
    AUTHORIZED_REPOSITORY_ID,
    AUTHORIZED_REVISION_SHA,
    EXCLUDE_PATTERNS,
    INCLUDE_PATTERNS,
    MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES,
    CheckpointDownloadPaths,
    build_cache_accounting,
    build_scaffold_manifest,
    free_disk_bytes,
    is_wsl_linux_runtime,
    load_register,
    manifest_from_dry_run,
    perform_dry_run,
    perform_preflight,
    physical_cache_bytes,
    repo_contains_checkpoint_weights,
    resolve_download_paths,
    resolve_hub_cache_dir,
    snapshot_cache_path,
    utc_now_iso,
    validate_checkpoint_download_evidence,
    validate_download_approval,
    validate_dry_run_before_download,
    verify_downloaded_snapshot,
)


def _repo_root() -> Path:
    start = Path(__file__).resolve().parent
    for directory in [start, *start.parents]:
        if (directory / "pyproject.toml").is_file():
            return directory
    raise FileNotFoundError("could not locate repository root")


def _runtime(paths: CheckpointDownloadPaths | None) -> CheckpointDownloadPaths:
    return paths or resolve_download_paths(_repo_root())


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return build_scaffold_manifest()
    return json.loads(path.read_text(encoding="utf-8"))


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_raw_log(raw_log_dir: Path, command: str, payload: dict[str, Any]) -> Path:
    raw_log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = raw_log_dir / f"{command}_{timestamp}.json"
    log_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return log_path


def _build_hub_client(token: str | None):
    from huggingface_hub import HfApi

    return HfApi(token=token)


def _file_size_lookup(hub, repo_id: str, revision: str):
    siblings: dict[str, int] = {}

    def lookup(relpath: str) -> int:
        if relpath in siblings:
            return siblings[relpath]
        info = hub.repo_info(repo_id, revision=revision, files_metadata=True)
        for sibling in getattr(info, "siblings", []) or []:
            name = getattr(sibling, "rfilename", None) or getattr(sibling, "path", None)
            size = getattr(sibling, "size", 0) or 0
            if isinstance(name, str):
                siblings[name] = int(size)
        return siblings.get(relpath, 0)

    return lookup


def _cached_file_lookup(cache_dir: Path, repo_id: str, revision: str):
    from huggingface_hub import try_to_load_from_cache

    def lookup(relpath: str) -> bool:
        cached = try_to_load_from_cache(
            repo_id=repo_id,
            filename=relpath,
            revision=revision,
            cache_dir=str(cache_dir),
        )
        return isinstance(cached, str)

    return lookup


def cmd_preflight(
    args: argparse.Namespace,
    paths: CheckpointDownloadPaths | None = None,
) -> int:
    runtime = _runtime(paths)
    cache_dir = runtime.hub_cache_dir
    token = args.token
    hub = None if args.offline else _build_hub_client(token)

    result = perform_preflight(
        runtime.repo_root,
        repo_id=AUTHORIZED_REPOSITORY_ID,
        revision=AUTHORIZED_REVISION_SHA,
        cache_dir=cache_dir,
        register_path=runtime.register_path,
        token=token,
        hub=hub,
    )
    payload = {
        "command": "preflight",
        "candidate_entry_id": AUTHORIZED_CANDIDATE_ENTRY_ID,
        "repository_id": AUTHORIZED_REPOSITORY_ID,
        "revision": AUTHORIZED_REVISION_SHA,
        "checks": result.checks,
        "errors": result.errors,
        "wsl_runtime": is_wsl_linux_runtime(),
        "cache_policy": "single_wsl_cache",
        "free_disk_bytes": free_disk_bytes(cache_dir.parent),
        "physical_cache_bytes": physical_cache_bytes(cache_dir),
        "repo_weight_violations": repo_contains_checkpoint_weights(runtime.repo_root),
    }
    log_path = _write_raw_log(runtime.raw_log_dir, "preflight", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"raw_log={log_path.relative_to(runtime.repo_root).as_posix()}", file=sys.stderr)
    return 1 if result.errors else 0


def cmd_dry_run(
    args: argparse.Namespace,
    paths: CheckpointDownloadPaths | None = None,
) -> int:
    runtime = _runtime(paths)
    cache_dir = runtime.hub_cache_dir
    token = args.token
    hub = _build_hub_client(token)

    preflight = perform_preflight(
        runtime.repo_root,
        repo_id=AUTHORIZED_REPOSITORY_ID,
        revision=AUTHORIZED_REVISION_SHA,
        cache_dir=cache_dir,
        register_path=runtime.register_path,
        token=token,
        hub=hub,
    )
    if preflight.errors:
        print(json.dumps({"errors": preflight.errors}, indent=2), file=sys.stderr)
        return 1

    size_lookup = _file_size_lookup(hub, AUTHORIZED_REPOSITORY_ID, AUTHORIZED_REVISION_SHA)
    cached_lookup = _cached_file_lookup(cache_dir, AUTHORIZED_REPOSITORY_ID, AUTHORIZED_REVISION_SHA)
    free_before = free_disk_bytes(cache_dir.parent)

    try:
        dry_run = perform_dry_run(
            hub,
            repo_id=AUTHORIZED_REPOSITORY_ID,
            revision=AUTHORIZED_REVISION_SHA,
            cache_dir=cache_dir,
            file_size_lookup=size_lookup,
            cached_file_lookup=cached_lookup,
        )
    except ValueError as exc:
        print(json.dumps({"errors": [str(exc)]}, indent=2), file=sys.stderr)
        return 1

    manifest = manifest_from_dry_run(dry_run, free_disk_before_bytes=free_before)
    _write_manifest(runtime.manifest_path, manifest)

    payload = {
        "command": "dry-run",
        "repository_id": AUTHORIZED_REPOSITORY_ID,
        "revision": AUTHORIZED_REVISION_SHA,
        "files_already_cached": dry_run.files_already_cached,
        "files_requiring_download": dry_run.files_requiring_download,
        "total_required_bytes": dry_run.total_required_bytes,
        "pre_existing_cached_bytes": dry_run.pre_existing_cached_bytes,
        "projected_physical_cache_bytes": dry_run.cumulative_cache_bytes,
        "resolved_commit_sha": dry_run.resolved_commit_sha,
        "inventory": [
            {"relpath": entry.relpath, "size_bytes": entry.size_bytes}
            for entry in dry_run.inventory
        ],
    }
    log_path = _write_raw_log(runtime.raw_log_dir, "dry_run", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"manifest={runtime.manifest_relpath()}", file=sys.stderr)
    print(f"raw_log={log_path.relative_to(runtime.repo_root).as_posix()}", file=sys.stderr)
    return 0


def cmd_download(
    args: argparse.Namespace,
    paths: CheckpointDownloadPaths | None = None,
) -> int:
    runtime = _runtime(paths)
    manifest_path = runtime.manifest_path
    manifest = _load_manifest(manifest_path)
    approval_errors = validate_download_approval(approve=args.approve_dry_run)
    dry_run_errors = validate_dry_run_before_download(manifest)
    errors = approval_errors + dry_run_errors
    if errors:
        print(json.dumps({"errors": errors}, indent=2), file=sys.stderr)
        return 1

    token = args.token
    if token:
        print(
            json.dumps(
                {"errors": ["access token must not be supplied for ungated checkpoint download"]},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1

    cache_dir = runtime.hub_cache_dir
    preflight = perform_preflight(
        runtime.repo_root,
        repo_id=AUTHORIZED_REPOSITORY_ID,
        revision=AUTHORIZED_REVISION_SHA,
        cache_dir=cache_dir,
        register_path=runtime.register_path,
        token=None,
        hub=_build_hub_client(None),
    )
    if preflight.errors:
        print(json.dumps({"errors": preflight.errors}, indent=2), file=sys.stderr)
        return 1

    from huggingface_hub import snapshot_download

    free_before = free_disk_bytes(cache_dir.parent)
    pre_existing_physical = manifest.get("pre_existing_physical_cache_bytes")
    if not isinstance(pre_existing_physical, int):
        pre_existing_physical = physical_cache_bytes(cache_dir)

    path = snapshot_download(
        repo_id=AUTHORIZED_REPOSITORY_ID,
        revision=AUTHORIZED_REVISION_SHA,
        cache_dir=str(cache_dir),
        allow_patterns=list(INCLUDE_PATTERNS),
        ignore_patterns=list(EXCLUDE_PATTERNS),
        token=None,
    )

    downloaded_payload = int(manifest.get("download_required_bytes", 0))
    physical_after = physical_cache_bytes(cache_dir)
    manifest.update(
        {
            "download_status": "completed",
            "verification_status": "pending",
            "verification_errors": [],
            "downloaded_payload_bytes": downloaded_payload,
            "logical_snapshot_bytes": downloaded_payload,
            "pre_existing_physical_cache_bytes": pre_existing_physical,
            "physical_cache_bytes": physical_after,
            "physical_cache_growth_bytes": max(physical_after - pre_existing_physical, 0),
            "remaining_cap_headroom_bytes": MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES - physical_after,
            "free_disk_before_bytes": free_before,
            "free_disk_after_bytes": free_disk_bytes(cache_dir.parent),
            "overall_status": "download_complete_unverified",
            "download_snapshot_path_hint": "hub_cache_only",
        }
    )
    _write_manifest(manifest_path, manifest)

    payload = {
        "command": "download",
        "repository_id": AUTHORIZED_REPOSITORY_ID,
        "revision": AUTHORIZED_REVISION_SHA,
        "snapshot_hint": "hub_cache_only",
        "actual_downloaded_bytes": manifest["downloaded_payload_bytes"],
        "physical_cache_bytes": manifest["physical_cache_bytes"],
        "physical_cache_growth_bytes": manifest["physical_cache_growth_bytes"],
        "cache_dir_policy": "single_wsl_cache",
        "resolved_path_marker": bool(path),
    }
    log_path = _write_raw_log(runtime.raw_log_dir, "download", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"raw_log={log_path.relative_to(runtime.repo_root).as_posix()}", file=sys.stderr)
    return 0


def cmd_verify(
    args: argparse.Namespace,
    paths: CheckpointDownloadPaths | None = None,
) -> int:
    runtime = _runtime(paths)
    manifest_path = runtime.manifest_path
    manifest = _load_manifest(manifest_path)
    dry_run_errors = validate_dry_run_before_download(manifest)
    if dry_run_errors:
        print(json.dumps({"errors": dry_run_errors}, indent=2), file=sys.stderr)
        return 1

    cache_dir = runtime.hub_cache_dir
    snapshot_dir = snapshot_cache_path(
        cache_dir,
        repo_id=AUTHORIZED_REPOSITORY_ID,
        revision=AUTHORIZED_REVISION_SHA,
    )
    if not snapshot_dir.is_dir():
        print(json.dumps({"errors": ["snapshot directory not found"]}, indent=2), file=sys.stderr)
        return 1

    try:
        verification = verify_downloaded_snapshot(
            snapshot_dir,
            dry_run_inventory=manifest["dry_run_file_inventory"],
        )
        accounting = build_cache_accounting(
            snapshot_dir=snapshot_dir,
            dry_run_inventory=manifest["dry_run_file_inventory"],
            cache_dir=cache_dir,
            pre_existing_physical_cache_bytes=manifest.get("pre_existing_physical_cache_bytes"),
        )
    except (ValueError, NameError) as exc:
        failure_event = {
            "event_type": "verification_failure",
            "retrospective": False,
            "recorded_at": utc_now_iso(),
            "error_class": type(exc).__name__,
            "error_message": str(exc),
        }
        events = list(manifest.get("verification_events", []))
        events.append(failure_event)
        manifest.update(
            {
                "verification_status": "failed",
                "verification_errors": [str(exc)],
                "verification_events": events,
                "overall_status": "verification_failed",
                "no_model_load": True,
                "no_gpu_allocation": True,
                "checkpoint_load_verified": False,
                "selected_model": None,
            }
        )
        _write_manifest(manifest_path, manifest)
        print(json.dumps({"errors": [str(exc)]}, indent=2), file=sys.stderr)
        return 1

    if accounting.physical_cache_bytes > MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES:
        error = "physical cache exceeds 30 GiB cap"
        print(json.dumps({"errors": [error]}, indent=2), file=sys.stderr)
        return 1

    manifest.update(
        {
            **verification,
            "downloaded_payload_bytes": accounting.downloaded_payload_bytes,
            "logical_snapshot_bytes": accounting.logical_snapshot_bytes,
            "physical_cache_bytes": accounting.physical_cache_bytes,
            "physical_cache_growth_bytes": accounting.physical_cache_growth_bytes,
            "pre_existing_physical_cache_bytes": accounting.pre_existing_physical_cache_bytes,
            "remaining_cap_headroom_bytes": accounting.remaining_cap_headroom_bytes,
            "download_status": "completed",
            "verification_status": "completed",
            "verification_errors": [],
            "overall_status": "verification_complete",
            "no_model_load": True,
            "no_gpu_allocation": True,
            "checkpoint_load_verified": False,
            "selected_model": None,
        }
    )
    _write_manifest(manifest_path, manifest)

    payload = {
        "command": "verify",
        "repository_id": AUTHORIZED_REPOSITORY_ID,
        "revision": AUTHORIZED_REVISION_SHA,
        "overall_status": manifest["overall_status"],
        "required_file_checks": verification["required_file_checks"],
        "excluded_file_checks": verification["excluded_file_checks"],
        "file_count": len(verification["files"]),
        "logical_snapshot_bytes": verification["logical_snapshot_bytes"],
        "physical_cache_bytes": accounting.physical_cache_bytes,
        "physical_cache_growth_bytes": accounting.physical_cache_growth_bytes,
        "remaining_cap_headroom_bytes": accounting.remaining_cap_headroom_bytes,
    }
    log_path = _write_raw_log(runtime.raw_log_dir, "verify", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"manifest={runtime.manifest_relpath()}", file=sys.stderr)
    print(f"raw_log={log_path.relative_to(runtime.repo_root).as_posix()}", file=sys.stderr)
    return 0


def cmd_report(
    args: argparse.Namespace,
    paths: CheckpointDownloadPaths | None = None,
) -> int:
    runtime = _runtime(paths)
    manifest_path = runtime.manifest_path
    manifest = _load_manifest(manifest_path)
    register = load_register(runtime.register_path)
    errors = validate_checkpoint_download_evidence(manifest, register=register)
    payload = {
        "command": "report",
        "manifest_path": runtime.manifest_relpath(),
        "validation_errors": errors,
        "manifest": manifest,
        "register_selected_model": register.get("selected_model"),
        "candidate_status": next(
            (
                entry.get("verification_status")
                for entry in register.get("entries", [])
                if entry.get("entry_id") == AUTHORIZED_CANDIDATE_ENTRY_ID
            ),
            None,
        ),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight", help="Run pre-download checks")
    preflight.add_argument("--offline", action="store_true", help="Skip Hub metadata resolution")
    preflight.add_argument("--token", default=None, help="Must remain unset for ungated model")

    dry_run = subparsers.add_parser("dry-run", help="Inventory files and bytes without downloading")
    dry_run.add_argument("--token", default=None, help="Must remain unset for ungated model")

    download = subparsers.add_parser("download", help="Download allowlisted checkpoint files")
    download.add_argument(
        "--approve-dry-run",
        action="store_true",
        help="Explicit human approval after reviewing dry-run evidence",
    )
    download.add_argument("--token", default=None, help="Must remain unset for ungated model")

    subparsers.add_parser("verify", help="Verify downloaded snapshot integrity")
    subparsers.add_parser("report", help="Print tracked evidence manifest and validation")
    return parser


def main(
    argv: list[str] | None = None,
    paths: CheckpointDownloadPaths | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "preflight": cmd_preflight,
        "dry-run": cmd_dry_run,
        "download": cmd_download,
        "verify": cmd_verify,
        "report": cmd_report,
    }
    return handlers[args.command](args, paths=paths)


if __name__ == "__main__":
    raise SystemExit(main())
