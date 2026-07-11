"""Canonical JSON hashing and contract sidecar helpers."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

CONTRACT_SIDECAR_REL_PATH = "configs/research/research_contract_v1.json"
_SIDECAR_LINE_RE = re.compile(
    r"^([0-9a-f]{64})  configs/research/research_contract_v1\.json\n$"
)


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_sidecar_line(line: str) -> tuple[str, str]:
    match = _SIDECAR_LINE_RE.match(line)
    if not match:
        raise ValueError(f"invalid contract sidecar line format: {line!r}")
    return match.group(1), CONTRACT_SIDECAR_REL_PATH


def format_sidecar_line(digest: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("digest must be 64-character lowercase hex SHA-256")
    return f"{digest}  {CONTRACT_SIDECAR_REL_PATH}\n"


def write_contract_sidecar(json_path: Path, sidecar_path: Path) -> str:
    payload_bytes = json_path.read_bytes()
    digest = sha256_hex(payload_bytes)
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text(format_sidecar_line(digest), encoding="utf-8")
    return digest


def verify_contract_sidecar(json_path: Path, sidecar_path: Path) -> bool:
    if not json_path.is_file() or not sidecar_path.is_file():
        return False
    try:
        digest, _ = parse_sidecar_line(sidecar_path.read_text(encoding="utf-8"))
    except ValueError:
        return False
    return sha256_hex(json_path.read_bytes()) == digest
