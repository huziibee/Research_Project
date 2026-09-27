#!/usr/bin/env python3
"""Prepare target-free AmbiK inference inputs and a separate mapped-type key."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_new(path: Path, rows: list[dict]) -> None:
    if path.exists(): raise ValueError(f"output_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--source", type=Path, required=True); parser.add_argument("--packet", type=Path, required=True); parser.add_argument("--key", type=Path, required=True); args = parser.parse_args()
    rows = [json.loads(line) for line in args.source.read_text(encoding="utf-8").splitlines() if line.strip()]
    packet, key = [], []
    for row in rows:
        record_id = row["id"]; fingerprint = digest(row)
        if not isinstance(row.get("ambiguity_types"), list) or not row["ambiguity_types"]: raise ValueError(f"missing_type:{record_id}")
        packet.append({"study_id": "ambik_ambiguity_type_v1", "record_id": record_id, "command": row["command"], "scene_context": row["scene_context"], "source_fingerprint_sha256": fingerprint})
        key.append({"record_id": record_id, "source_fingerprint_sha256": fingerprint, "ambiguity_types": row["ambiguity_types"], "label_status": "EXPLORATORY_WEAK_SOURCE_LABEL"})
    if len(packet) != 1000 or len({row["record_id"] for row in packet}) != 1000: raise ValueError("ambik_coverage_mismatch")
    write_new(args.packet, packet); write_new(args.key, key)
    print(json.dumps({"records": len(packet), "packet_sha256": hashlib.sha256(args.packet.read_bytes()).hexdigest(), "key_sha256": hashlib.sha256(args.key.read_bytes()).hexdigest()}, sort_keys=True))


if __name__ == "__main__": main()
