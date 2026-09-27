#!/usr/bin/env python3
"""Create a target-free VAGUE inference packet from the prepared gold-bound file."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError(f"output_exists:{args.out}")
    packet = []
    for line in args.prepared.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        source = json.loads(line)
        packet.append({key: source[key] for key in ("study_id", "record_id", "condition", "command", "textual_caption", "source_fingerprint_sha256")})
    if len(packet) != 3354 or len({(row["record_id"], row["condition"]) for row in packet}) != 3354:
        raise ValueError("inference_packet_coverage_mismatch")
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in packet), encoding="utf-8", newline="\n")
    print(json.dumps({"records": len(packet), "prepared_sha256": sha256(args.prepared), "packet_sha256": sha256(args.out)}, sort_keys=True))


if __name__ == "__main__":
    main()
