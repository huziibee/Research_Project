"""Dataset audit orchestration."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ambiguity_manager.data_audit.checks import (
    check_duplicate_ids_csv,
    check_split_overlap_tsv,
    classify_mapping_verification_status,
    classify_payload_verification_status,
    is_code_only_tree,
    is_lfs_pointer,
    is_metadata_only_tree,
    load_dataset_info_num_examples,
    read_submodule_commit,
)
from ambiguity_manager.data_audit.config import (
    DATASET_AUDIT_SPECS,
    EXCLUDED_ARTIFACTS,
    MISSING_DATASETS,
    get_audit_spec,
    load_inclusion_register,
    load_licence_manifest,
    validate_inclusion_register,
    validate_licence_manifest,
)
from ambiguity_manager.data_audit.readers import audit_file_payload, read_magic_bytes, streaming_sha256
from ambiguity_manager.data_audit.version import AUDIT_SCHEMA_VERSION, AUDIT_TOOL_VERSION
from ambiguity_manager.paths import ProjectPaths


def _repo_relative(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _resolve_raw_path(repo_root: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    if path.parts[:2] == ("data", "raw"):
        return repo_root / path
    return repo_root / "data" / "raw" / path


def _audit_single_file(
    repo_root: Path,
    file_spec: dict[str, Any],
    *,
    authoritative: bool,
) -> dict[str, Any]:
    relative_path = file_spec["relative_path"]
    absolute_path = _resolve_raw_path(repo_root, relative_path)

    result: dict[str, Any] = {
        "relative_path": relative_path,
        "authoritative": authoritative,
        "file_type": file_spec.get("file_type"),
        "exists": absolute_path.is_file(),
        "readable": False,
        "empty": False,
        "size_bytes": None,
        "sha256": None,
        "magic_bytes": None,
        "parser": file_spec.get("file_type"),
        "record_count": None,
        "header_fields": [],
        "field_types": {},
        "null_or_missing_counts": {},
        "metadata_path": file_spec.get("metadata_path"),
        "metadata_record_count": None,
        "metadata_count_matches_parser": None,
        "issues": [],
    }

    if not result["exists"]:
        result["issues"].append({"code": "missing_file", "message": "authoritative file not found"})
        return result

    size_bytes = absolute_path.stat().st_size
    result["size_bytes"] = size_bytes
    result["empty"] = size_bytes == 0
    if result["empty"]:
        result["issues"].append({"code": "empty_payload", "message": "file exists but is empty"})
        return result

    if is_lfs_pointer(absolute_path):
        result["issues"].append({"code": "lfs_pointer", "message": "file is a Git LFS pointer stub"})
        return result

    result["magic_bytes"] = read_magic_bytes(absolute_path)
    result["sha256"] = streaming_sha256(absolute_path)

    metadata_path = file_spec.get("metadata_path")
    if metadata_path:
        metadata_abs = _resolve_raw_path(repo_root, metadata_path)
        split_name = file_spec.get("component_name") or file_spec.get("split_name")
        result["metadata_record_count"] = load_dataset_info_num_examples(metadata_abs, split_name)

    payload = audit_file_payload(absolute_path, file_spec)
    if not payload.ok:
        result["issues"].append(
            {
                "code": payload.error_kind or "parse_error",
                "message": payload.error_message or "failed to parse payload",
            }
        )
        if payload.error_kind == "pyarrow_not_installed":
            result["issues"].append({"code": "pyarrow_not_installed", "message": payload.error_message})
        return result

    result["readable"] = True
    result["record_count"] = payload.record_count
    result["header_fields"] = payload.header_fields
    result["field_types"] = payload.field_types
    result["null_or_missing_counts"] = payload.null_counts

    if result["metadata_record_count"] is not None:
        result["metadata_count_matches_parser"] = result["metadata_record_count"] == payload.record_count
        if not result["metadata_count_matches_parser"]:
            result["issues"].append(
                {
                    "code": "metadata_count_mismatch",
                    "message": (
                        f"metadata count {result['metadata_record_count']} != "
                        f"parser count {payload.record_count}"
                    ),
                }
            )
    return result


def _authoritative_specs(spec: dict[str, Any]) -> list[dict[str, Any]]:
    components = spec.get("authoritative_components")
    if components:
        return list(components)
    primary = spec.get("primary")
    return [primary] if primary else []


def _dataset_status_fields(
    *,
    decision: str,
    excluded: bool,
    blocked: bool,
    payload_readable: bool,
    metadata_only: bool,
    has_warnings: bool,
    mapping_risks: list[dict[str, str]],
    licence_entry: dict[str, Any] | None,
) -> dict[str, str]:
    payload_status = classify_payload_verification_status(
        decision=decision,
        excluded=excluded,
        blocked=blocked,
        payload_readable=payload_readable,
        metadata_only=metadata_only,
        has_warnings=has_warnings,
    )
    if excluded or decision == "exclude":
        mapping_status = "not_applicable"
    else:
        mapping_status = classify_mapping_verification_status(mapping_risks)
    return {
        "payload_verification_status": payload_status,
        "mapping_verification_status": mapping_status,
        "licence_status": (licence_entry or {}).get("licence_status", "unresolved"),
        "verification_status": payload_status,
    }


def audit_dataset_entry(
    *,
    repo_root: Path,
    entry: dict[str, Any],
    spec: dict[str, Any] | None,
    licence_entry: dict[str, Any] | None,
) -> dict[str, Any]:
    dataset_id = entry["dataset_id"]
    decision = entry.get("decision", "")
    spec = spec or {}
    raw_root_name = spec.get("raw_root", "")
    raw_root = repo_root / "data" / "raw" / raw_root_name if raw_root_name else None

    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    authoritative_files: list[dict[str, Any]] = []
    auxiliary_files: list[dict[str, Any]] = []
    duplicate_checks: list[dict[str, Any]] = []
    overlap_checks: list[dict[str, Any]] = []
    has_warnings = False
    blocked = False
    payload_readable = False
    metadata_only = False
    parser_row_count: int | None = None
    parser_row_count_notes = "no authoritative payload configured"

    code_only = bool(raw_root and raw_root.is_dir() and is_code_only_tree(raw_root))
    if code_only:
        warnings.append({"code": "code_only_tree", "message": "directory appears code-only without data payloads"})

    if decision == "exclude":
        inventory_count = None
        if raw_root and raw_root.is_dir() and spec.get("inventory_glob"):
            inventory_count = len(list(raw_root.rglob(spec["inventory_glob"])))
        status_fields = _dataset_status_fields(
            decision=decision,
            excluded=True,
            blocked=False,
            payload_readable=False,
            metadata_only=False,
            has_warnings=False,
            mapping_risks=[],
            licence_entry=licence_entry,
        )
        return {
            "dataset_id": dataset_id,
            "display_name": entry.get("display_name", dataset_id),
            "raw_root_relative": raw_root_name,
            "entry_type": spec.get("entry_type"),
            "filesystem_present": bool(raw_root and raw_root.is_dir()),
            "code_only": code_only,
            **status_fields,
            "inclusion_decision": decision,
            "intended_role": entry.get("role"),
            "expected_converter_ticket": entry.get("expected_converter_ticket"),
            "parser_row_count": inventory_count,
            "total_authoritative_record_count": inventory_count,
            "authoritative_component_counts": {},
            "parser_row_count_notes": (
                "inventory count only for excluded dataset"
                if inventory_count is not None
                else "code-only repository without local episode payload"
                if code_only
                else "excluded dataset"
            ),
            "authoritative_files": [],
            "auxiliary_files": [],
            "splits": {"structure": spec.get("split_structure"), "splits_found": [], "overlap_checks": []},
            "duplicate_checks": [],
            "provenance": {
                "source_urls": (licence_entry or {}).get("source_urls", []),
                "submodule_commit": read_submodule_commit(raw_root) if raw_root else None,
            },
            "mapping_risks": spec.get("mapping_risks", []),
            "issues": issues,
            "warnings": warnings,
        }

    authoritative_specs = _authoritative_specs(spec)
    authoritative_component_counts: dict[str, int] = {}
    total_authoritative_record_count = 0

    for file_spec in authoritative_specs:
        audited = _audit_single_file(repo_root, file_spec, authoritative=True)
        authoritative_files.append(audited)
        component_name = (
            file_spec.get("component_name")
            or file_spec.get("split_name")
            or Path(file_spec["relative_path"]).name
        )
        if audited.get("readable") and audited.get("record_count") is not None:
            payload_readable = True
            authoritative_component_counts[component_name] = audited["record_count"]
            total_authoritative_record_count += audited["record_count"]
        if audited.get("issues"):
            if any(
                issue["code"] in {"pyarrow_not_installed", "missing_file", "empty_payload", "lfs_pointer"}
                for issue in audited["issues"]
            ):
                blocked = True
            if any(issue["code"] in {"metadata_count_mismatch"} for issue in audited["issues"]):
                has_warnings = True
            issues.extend(audited["issues"])
        id_fields = file_spec.get("id_fields", [])
        if id_fields and audited.get("exists") and audited.get("readable"):
            abs_path = _resolve_raw_path(repo_root, file_spec["relative_path"])
            if file_spec.get("file_type") == "csv":
                duplicate_checks.append(check_duplicate_ids_csv(abs_path, id_fields).to_dict())

    if authoritative_specs:
        parser_row_count = total_authoritative_record_count or None
        if len(authoritative_component_counts) == 1:
            parser_row_count_notes = "single authoritative file"
        else:
            parser_row_count_notes = "sum of authoritative components"
    elif raw_root and raw_root.is_dir():
        metadata_only = is_metadata_only_tree(raw_root)
        if metadata_only:
            blocked = True
            issues.append({"code": "metadata_only", "message": "only metadata files found, no payload"})
        elif code_only:
            blocked = True
            issues.append({"code": "no_payload", "message": "no authoritative payload configured or present"})

    for aux_spec in spec.get("auxiliary", []):
        audited = _audit_single_file(repo_root, aux_spec, authoritative=False)
        auxiliary_files.append(audited)
        if audited.get("issues"):
            issues.extend(
                [{**issue, "scope": aux_spec["relative_path"]} for issue in audited["issues"]]
            )

    for overlap_spec in spec.get("split_overlap_checks", []):
        paths = [_resolve_raw_path(repo_root, rel) for rel in overlap_spec["files"]]
        overlap = check_split_overlap_tsv(paths, overlap_spec["id_fields"])
        overlap_checks.append(overlap.to_dict())
        if overlap.status == "warning":
            has_warnings = True
            warnings.append(
                {
                    "code": "split_overlap",
                    "message": (
                        f"{overlap.overlap_count} overlapping IDs across "
                        f"{', '.join(overlap_spec['files'])} on {overlap.id_fields}"
                    ),
                }
            )

    splits_found = list(authoritative_component_counts.keys())
    if not splits_found:
        for file_spec in spec.get("auxiliary", []):
            if file_spec.get("split_name"):
                splits_found.append(file_spec["split_name"])

    mapping_risks = list(spec.get("mapping_risks", []))
    status_fields = _dataset_status_fields(
        decision=decision,
        excluded=False,
        blocked=blocked,
        payload_readable=payload_readable,
        metadata_only=metadata_only,
        has_warnings=has_warnings,
        mapping_risks=mapping_risks,
        licence_entry=licence_entry,
    )

    return {
        "dataset_id": dataset_id,
        "display_name": entry.get("display_name", dataset_id),
        "raw_root_relative": raw_root_name,
        "entry_type": spec.get("entry_type"),
        "filesystem_present": bool(raw_root and raw_root.is_dir()),
        "code_only": code_only,
        **status_fields,
        "inclusion_decision": decision,
        "intended_role": entry.get("role"),
        "expected_converter_ticket": entry.get("expected_converter_ticket"),
        "parser_row_count": parser_row_count,
        "total_authoritative_record_count": total_authoritative_record_count or parser_row_count,
        "authoritative_component_counts": authoritative_component_counts,
        "parser_row_count_notes": parser_row_count_notes,
        "authoritative_files": authoritative_files,
        "auxiliary_files": auxiliary_files,
        "splits": {
            "structure": spec.get("split_structure"),
            "splits_found": splits_found,
            "overlap_checks": overlap_checks,
        },
        "duplicate_checks": duplicate_checks,
        "provenance": {
            "source_urls": (licence_entry or {}).get("source_urls", []),
            "submodule_commit": read_submodule_commit(raw_root) if raw_root else None,
            "acquisition_method": (licence_entry or {}).get("acquisition_method"),
            "source_version": (licence_entry or {}).get("source_version"),
        },
        "mapping_risks": mapping_risks,
        "issues": issues,
        "warnings": warnings,
    }


def _git_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def run_audit(
    *,
    repo_root: Path | None = None,
    generated_at: str | None = None,
    register_path: Path | None = None,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    paths = ProjectPaths.from_repo_root(repo_root)
    repo_root = paths.root
    register = load_inclusion_register(register_path)
    manifest = load_licence_manifest(manifest_path)
    register_errors = validate_inclusion_register(register)
    manifest_errors = validate_licence_manifest(manifest)
    if register_errors:
        raise ValueError("invalid inclusion register: " + "; ".join(register_errors))
    if manifest_errors:
        raise ValueError("invalid licence manifest: " + "; ".join(manifest_errors))

    licence_by_id = {entry["dataset_id"]: entry for entry in manifest.get("entries", [])}
    datasets: list[dict[str, Any]] = []
    summary = {
        "verified": 0,
        "partially_verified": 0,
        "metadata_only": 0,
        "blocked": 0,
        "excluded": 0,
        "TODO_VERIFY": 0,
    }

    for entry in register.get("entries", []):
        dataset_id = entry["dataset_id"]
        spec = get_audit_spec(dataset_id)
        audited = audit_dataset_entry(
            repo_root=repo_root,
            entry=entry,
            spec=spec,
            licence_entry=licence_by_id.get(dataset_id),
        )
        datasets.append(audited)
        status = audited.get("payload_verification_status", audited.get("verification_status"))
        if status in summary:
            summary[status] += 1

    datasets.sort(key=lambda item: item["dataset_id"])
    payload = {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "generated_at": generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "audit_tool_version": AUDIT_TOOL_VERSION,
        "repo_marker": "pyproject.toml",
        "git_commit": _git_commit(repo_root),
        "summary": {
            "datasets_registered": len(datasets),
            **summary,
            "missing_not_blocking": len(MISSING_DATASETS),
        },
        "excluded_artifacts": EXCLUDED_ARTIFACTS,
        "datasets": datasets,
        "missing_datasets": MISSING_DATASETS,
    }
    return payload
