"""Streaming file readers and hashing for dataset audit."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from ambiguity_manager.data_audit.models import ReaderResult

_PYARROW_AVAILABLE: bool | None = None


def _pyarrow_available() -> bool:
    global _PYARROW_AVAILABLE
    if _PYARROW_AVAILABLE is not None:
        return _PYARROW_AVAILABLE
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        _PYARROW_AVAILABLE = False
    else:
        _PYARROW_AVAILABLE = True
    return _PYARROW_AVAILABLE


def streaming_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_magic_bytes(path: Path, length: int = 8) -> str:
    with path.open("rb") as handle:
        return handle.read(length).hex()


def _missing_count(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _count_nulls_in_row(row: dict[str, str], critical_fields: list[str]) -> dict[str, int]:
    counts = {field: 0 for field in critical_fields}
    for field in critical_fields:
        if field not in row:
            counts[field] += 1
        elif _missing_count(row.get(field)):
            counts[field] += 1
    return counts


def read_csv_audit(path: Path, critical_fields: list[str]) -> ReaderResult:
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            reader = csv.reader(handle)
            try:
                header_row = next(reader)
            except StopIteration:
                return ReaderResult(
                    ok=False,
                    error_kind="unexpected_schema",
                    error_message="missing header row",
                )
            if not header_row:
                return ReaderResult(
                    ok=False,
                    error_kind="unexpected_schema",
                    error_message="missing header row",
                )
            header_fields = header_row
            expected_width = len(header_fields)
            missing_headers = [field for field in critical_fields if field not in header_fields]
            if missing_headers:
                return ReaderResult(
                    ok=False,
                    header_fields=header_fields,
                    error_kind="unexpected_schema",
                    error_message=f"missing critical fields: {', '.join(missing_headers)}",
                )
            null_counts = {field: 0 for field in critical_fields}
            header_index = {name: index for index, name in enumerate(header_fields)}
            record_count = 0
            for row_number, row in enumerate(reader, start=2):
                if len(row) != expected_width:
                    return ReaderResult(
                        ok=False,
                        record_count=record_count,
                        header_fields=header_fields,
                        error_kind="inconsistent_row_width",
                        error_message=f"row {row_number} has {len(row)} fields, expected {expected_width}",
                    )
                record_count += 1
                row_dict = {header_fields[index]: row[index] for index in range(expected_width)}
                for field, count in _count_nulls_in_row(row_dict, critical_fields).items():
                    null_counts[field] += count
        return ReaderResult(
            ok=True,
            record_count=record_count,
            header_fields=header_fields,
            null_counts=null_counts,
            container_kind="csv",
        )
    except csv.Error as exc:
        return ReaderResult(ok=False, error_kind="syntax_error", error_message=str(exc))


def read_tsv_audit(path: Path, critical_fields: list[str]) -> ReaderResult:
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not reader.fieldnames:
                return ReaderResult(
                    ok=False,
                    error_kind="unexpected_schema",
                    error_message="missing header row",
                )
            header_fields = list(reader.fieldnames)
            expected_width = len(header_fields)
            missing_headers = [field for field in critical_fields if field not in header_fields]
            if missing_headers:
                return ReaderResult(
                    ok=False,
                    header_fields=header_fields,
                    error_kind="unexpected_schema",
                    error_message=f"missing critical fields: {', '.join(missing_headers)}",
                )
            null_counts = {field: 0 for field in critical_fields}
            record_count = 0
            for row_number, row in enumerate(reader, start=2):
                if len(row) != expected_width:
                    return ReaderResult(
                        ok=False,
                        record_count=record_count,
                        header_fields=header_fields,
                        error_kind="inconsistent_row_width",
                        error_message=f"row {row_number} has {len(row)} fields, expected {expected_width}",
                    )
                record_count += 1
                for field, count in _count_nulls_in_row(row, critical_fields).items():
                    null_counts[field] += count
        return ReaderResult(
            ok=True,
            record_count=record_count,
            header_fields=header_fields,
            null_counts=null_counts,
            container_kind="tsv",
        )
    except csv.Error as exc:
        return ReaderResult(ok=False, error_kind="syntax_error", error_message=str(exc))


def read_json_audit(path: Path, critical_fields: list[str] | None = None) -> ReaderResult:
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        return ReaderResult(ok=False, error_kind="syntax_error", error_message=str(exc))

    null_counts = {field: 0 for field in (critical_fields or [])}
    if isinstance(data, list):
        record_count = len(data)
        container_kind = "json_array"
        if critical_fields:
            for item in data:
                if not isinstance(item, dict):
                    continue
                for field in critical_fields:
                    if field not in item or _missing_count(item.get(field)):
                        null_counts[field] += 1
        return ReaderResult(
            ok=True,
            record_count=record_count,
            container_kind=container_kind,
            null_counts=null_counts,
        )
    if isinstance(data, dict):
        record_count = len(data)
        if critical_fields:
            for item in data.values():
                if not isinstance(item, dict):
                    continue
                for field in critical_fields:
                    if field not in item or _missing_count(item.get(field)):
                        null_counts[field] += 1
        return ReaderResult(
            ok=True,
            record_count=record_count,
            container_kind="json_dict",
            null_counts=null_counts,
        )
    return ReaderResult(
        ok=False,
        error_kind="unexpected_schema",
        error_message=f"unsupported JSON top-level type: {type(data).__name__}",
    )


def read_jsonl_audit(path: Path, critical_fields: list[str]) -> ReaderResult:
    null_counts = {field: 0 for field in critical_fields}
    record_count = 0
    header_fields: set[str] = set()
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    item = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    return ReaderResult(
                        ok=False,
                        error_kind="syntax_error",
                        error_message=f"line {line_number}: {exc}",
                    )
                if not isinstance(item, dict):
                    return ReaderResult(
                        ok=False,
                        error_kind="unexpected_schema",
                        error_message=f"line {line_number}: expected object",
                    )
                header_fields.update(item.keys())
                record_count += 1
                for field in critical_fields:
                    if field not in item or _missing_count(item.get(field)):
                        null_counts[field] += 1
    except OSError as exc:
        return ReaderResult(ok=False, error_kind="syntax_error", error_message=str(exc))
    missing_headers = [field for field in critical_fields if field not in header_fields and record_count > 0]
    if missing_headers:
        return ReaderResult(
            ok=False,
            header_fields=sorted(header_fields),
            error_kind="unexpected_schema",
            error_message=f"missing critical fields: {', '.join(missing_headers)}",
        )
    return ReaderResult(
        ok=True,
        record_count=record_count,
        header_fields=sorted(header_fields),
        null_counts=null_counts,
        container_kind="jsonl",
    )


def read_arrow_stream_audit(path: Path, critical_fields: list[str] | None = None) -> ReaderResult:
    if not _pyarrow_available():
        return ReaderResult(
            ok=False,
            error_kind="pyarrow_not_installed",
            error_message="pyarrow is required to audit Arrow IPC stream files",
        )
    import pyarrow as pa

    try:
        with path.open("rb") as handle:
            reader = pa.ipc.open_stream(handle)
            table = reader.read_all()
    except Exception as exc:  # noqa: BLE001 - surface parse failures to audit
        return ReaderResult(ok=False, error_kind="syntax_error", error_message=str(exc))

    header_fields = list(table.schema.names)
    null_counts = {field: 0 for field in (critical_fields or []) if field in header_fields}
    for field in list(null_counts):
        if field not in table.column_names:
            null_counts[field] = table.num_rows
            continue
        column = table.column(field)
        null_counts[field] = int(column.null_count) + sum(
            1 for value in column.to_pylist() if isinstance(value, str) and not value.strip()
        )
    missing = [field for field in (critical_fields or []) if field not in header_fields]
    if missing:
        return ReaderResult(
            ok=False,
            record_count=table.num_rows,
            header_fields=header_fields,
            null_counts=null_counts,
            error_kind="unexpected_schema",
            error_message=f"missing critical fields: {', '.join(missing)}",
        )
    return ReaderResult(
        ok=True,
        record_count=table.num_rows,
        header_fields=header_fields,
        null_counts=null_counts,
        container_kind="arrow_ipc_stream",
    )


def read_parquet_audit(path: Path, critical_fields: list[str] | None = None) -> ReaderResult:
    if not _pyarrow_available():
        return ReaderResult(
            ok=False,
            error_kind="pyarrow_not_installed",
            error_message="pyarrow is required to audit Parquet files",
        )
    import pyarrow.parquet as pq

    try:
        parquet_file = pq.ParquetFile(path)
    except Exception as exc:  # noqa: BLE001
        return ReaderResult(ok=False, error_kind="syntax_error", error_message=str(exc))

    schema = parquet_file.schema_arrow
    header_fields = list(schema.names)
    record_count = parquet_file.metadata.num_rows if parquet_file.metadata else 0
    missing = [field for field in (critical_fields or []) if field not in header_fields]
    if missing:
        return ReaderResult(
            ok=False,
            record_count=record_count,
            header_fields=header_fields,
            error_kind="unexpected_schema",
            error_message=f"missing critical fields: {', '.join(missing)}",
        )
    null_counts = {field: 0 for field in (critical_fields or [])}
    if critical_fields and record_count > 0:
        table = parquet_file.read(columns=[field for field in critical_fields if field in header_fields])
        for field in null_counts:
            if field not in table.column_names:
                null_counts[field] = record_count
                continue
            column = table.column(field)
            null_counts[field] = int(column.null_count) + sum(
                1 for value in column.to_pylist() if isinstance(value, str) and not value.strip()
            )
    return ReaderResult(
        ok=True,
        record_count=record_count,
        header_fields=header_fields,
        null_counts=null_counts,
        container_kind="parquet",
    )


def audit_file_payload(path: Path, file_spec: dict[str, Any]) -> ReaderResult:
    file_type = file_spec.get("file_type", "")
    critical_fields = list(file_spec.get("critical_fields", []))
    if file_type == "csv":
        return read_csv_audit(path, critical_fields)
    if file_type == "tsv":
        return read_tsv_audit(path, critical_fields)
    if file_type == "json_dict":
        return read_json_audit(path, critical_fields)
    if file_type == "json_array":
        return read_json_audit(path, critical_fields)
    if file_type == "jsonl":
        return read_jsonl_audit(path, critical_fields)
    if file_type == "arrow":
        return read_arrow_stream_audit(path, critical_fields)
    if file_type == "parquet":
        return read_parquet_audit(path, critical_fields)
    return ReaderResult(
        ok=False,
        error_kind="unexpected_schema",
        error_message=f"unsupported file_type: {file_type}",
    )
