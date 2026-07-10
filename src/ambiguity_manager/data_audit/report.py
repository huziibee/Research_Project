"""Markdown report generation for dataset audit."""

from __future__ import annotations

import json
from typing import Any


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _format_component_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "—"
    return ", ".join(f"{name}={value}" for name, value in sorted(counts.items()))


def generate_audit_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Dataset Audit Report",
        "",
        f"- Audit schema: `{audit.get('audit_schema_version')}`",
        f"- Generated at: `{audit.get('generated_at')}`",
        f"- Tool version: `{audit.get('audit_tool_version')}`",
        f"- Git commit: `{audit.get('git_commit')}`",
        "",
        "Status fields are separated: payload verification (technical readability/counts), "
        "mapping verification (project taxonomy mapping), and licence status (evidence only).",
        "",
        "## Summary",
        "",
    ]
    summary = audit.get("summary", {})
    lines.append(
        _table(
            ["Metric", "Count"],
            [
                ["Datasets registered", str(summary.get("datasets_registered", 0))],
                ["Payload verified", str(summary.get("verified", 0))],
                ["Payload partially verified", str(summary.get("partially_verified", 0))],
                ["Payload metadata only", str(summary.get("metadata_only", 0))],
                ["Payload blocked", str(summary.get("blocked", 0))],
                ["Excluded", str(summary.get("excluded", 0))],
                ["Missing (not blocking)", str(summary.get("missing_not_blocking", 0))],
            ],
        )
    )
    lines.extend(["", "## Per-dataset outcomes", ""])
    for dataset in audit.get("datasets", []):
        lines.append(f"### {dataset.get('display_name')} (`{dataset.get('dataset_id')}`)")
        lines.append("")
        lines.append(
            _table(
                ["Field", "Value"],
                [
                    ["Payload verification", str(dataset.get("payload_verification_status"))],
                    ["Mapping verification", str(dataset.get("mapping_verification_status"))],
                    ["Licence status", str(dataset.get("licence_status"))],
                    ["Inclusion decision", str(dataset.get("inclusion_decision"))],
                    ["Role", str(dataset.get("intended_role"))],
                    ["Total authoritative rows", str(dataset.get("total_authoritative_record_count"))],
                    ["Component counts", _format_component_counts(dataset.get("authoritative_component_counts", {}))],
                    ["Filesystem present", str(dataset.get("filesystem_present"))],
                    ["Code only", str(dataset.get("code_only"))],
                    ["Submodule commit", str((dataset.get("provenance") or {}).get("submodule_commit"))],
                ],
            )
        )
        auth_rows = []
        for file_info in dataset.get("authoritative_files", []):
            auth_rows.append(
                [
                    file_info.get("relative_path", ""),
                    str(file_info.get("record_count")),
                    str(file_info.get("readable")),
                    str(file_info.get("sha256", ""))[:16] + "…" if file_info.get("sha256") else "",
                ]
            )
        if auth_rows:
            lines.extend(
                [
                    "",
                    "Authoritative files:",
                    "",
                    _table(["Path", "Rows", "Readable", "SHA-256 (prefix)"], auth_rows),
                ]
            )
        if dataset.get("warnings"):
            lines.append("")
            lines.append("Warnings:")
            for warning in dataset["warnings"]:
                lines.append(f"- `{warning.get('code')}`: {warning.get('message')}")
        if dataset.get("issues"):
            lines.append("")
            lines.append("Issues:")
            for issue in dataset["issues"]:
                lines.append(f"- `{issue.get('code')}`: {issue.get('message')}")
        if dataset.get("mapping_risks"):
            lines.append("")
            lines.append("Mapping risks:")
            for risk in dataset["mapping_risks"]:
                lines.append(f"- `{risk.get('code')}` field `{risk.get('field')}`: {risk.get('note')}")
        lines.append("")

    lines.extend(["## Missing datasets (not blocking)", ""])
    missing_rows = [
        [
            item.get("dataset_id", ""),
            item.get("status", ""),
            str(item.get("planned_row_count", "")),
        ]
        for item in audit.get("missing_datasets", [])
    ]
    lines.append(_table(["Dataset", "Status", "Planned rows"], missing_rows))
    lines.append("")
    lines.append("## Excluded artifacts")
    lines.append("")
    artifact_rows = [
        [item.get("relative_path", ""), item.get("reason", "")]
        for item in audit.get("excluded_artifacts", [])
    ]
    lines.append(_table(["Path", "Reason"], artifact_rows))
    lines.append("")
    return "\n".join(lines)


def generate_inclusion_markdown(register: dict[str, Any], audit: dict[str, Any]) -> str:
    audit_by_id = {item["dataset_id"]: item for item in audit.get("datasets", [])}
    rows = []
    for entry in register.get("entries", []):
        dataset_id = entry.get("dataset_id", "")
        audited = audit_by_id.get(dataset_id, {})
        rows.append(
            [
                dataset_id,
                entry.get("decision", ""),
                entry.get("role", ""),
                str(audited.get("payload_verification_status", "")),
                str(audited.get("mapping_verification_status", "")),
                str(audited.get("total_authoritative_record_count", "")),
                _format_component_counts(audited.get("authoritative_component_counts", {})),
                entry.get("expected_converter_ticket", "") or "—",
            ]
        )
    return "\n".join(
        [
            "# Dataset Inclusion Register",
            "",
            f"Register schema: `{register.get('register_schema_version')}`",
            f"Updated at (curated): `{register.get('updated_at')}`",
            "",
            "Computed payload verification and row counts come from the latest audit JSON.",
            "",
            _table(
                [
                    "Dataset",
                    "Decision",
                    "Role",
                    "Payload",
                    "Mapping",
                    "Total rows",
                    "Components",
                    "Converter",
                ],
                rows,
            ),
            "",
        ]
    )


def generate_licence_markdown(manifest: dict[str, Any], audit: dict[str, Any]) -> str:
    audit_by_id = {item["dataset_id"]: item for item in audit.get("datasets", [])}
    rows = []
    for entry in manifest.get("entries", []):
        dataset_id = entry.get("dataset_id", "")
        audited = audit_by_id.get(dataset_id, {})
        rows.append(
            [
                dataset_id,
                entry.get("licence_status", ""),
                str(audited.get("licence_status", "")),
                entry.get("licence_identifier") or "—",
                entry.get("licence_file_relpath") or "—",
                entry.get("acquisition_method", "") or "—",
                str((audited.get("provenance") or {}).get("submodule_commit") or "—"),
            ]
        )
    return "\n".join(
        [
            "# Source Licence and Provenance Manifest",
            "",
            f"Manifest schema: `{manifest.get('manifest_schema_version')}`",
            f"Updated at (curated): `{manifest.get('updated_at')}`",
            "",
            "This document records evidence locations only. It does not provide legal conclusions.",
            "",
            _table(
                [
                    "Dataset",
                    "Curated licence status",
                    "Audit licence status",
                    "Identifier",
                    "Licence file",
                    "Acquisition",
                    "Submodule commit",
                ],
                rows,
            ),
            "",
        ]
    )
