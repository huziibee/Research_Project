#!/usr/bin/env python3
"""Run one frozen VAGUE goal-triplet system against a target-free packet."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


FIELDS = {"subject", "action", "object"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def post(port: int, body: dict) -> dict:
    request = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode())


def parse(content: str) -> dict:
    value = json.loads(content)
    if not isinstance(value, dict) or set(value) != FIELDS or any(not isinstance(value[key], str) or not value[key].strip() for key in FIELDS):
        raise ValueError("goal_triplet_schema_invalid")
    return {key: value[key].strip() for key in sorted(FIELDS)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if float(args.temperature) < 0:
        raise SystemExit("temperature_must_be_nonnegative")
    if args.out.exists() or args.manifest_out.exists():
        raise ValueError("output_or_manifest_exists")
    rows = [json.loads(line) for line in args.packet.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit is not None:
        rows = rows[:args.limit]
    if not rows or len({(row.get("record_id"), row.get("condition")) for row in rows}) != len(rows):
        raise ValueError("packet_coverage_or_duplicate_mismatch")
    prompt = args.prompt.read_text(encoding="utf-8")
    started = time.time(); predictions = []
    for index, row in enumerate(rows):
        user = "USER COMMAND:\n" + row["command"]
        if row["textual_caption"] is not None:
            user += "\n\nTEXTUAL SCENE DESCRIPTION:\n" + row["textual_caption"]
        body = {"model": args.model, "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": user}], "temperature": float(args.temperature), "top_p": 1.0, "seed": args.seed + index, "max_tokens": 96, "response_format": {"type": "json_object"}}
        error = None
        for _ in range(3):
            try:
                triplet = parse(post(args.port, body)["choices"][0]["message"]["content"]); error = None; break
            except Exception as exc:
                error = exc
                body["messages"].append({"role": "user", "content": "Technical retry: return exactly one valid JSON object with only non-empty string fields subject, action, and object for this same item."})
        if error is not None:
            raise SystemExit(f"prediction_failed:{row['record_id']}:{row['condition']}:{error!r}")
        predictions.append({"record_id": row["record_id"], "condition": row["condition"], "source_fingerprint_sha256": row["source_fingerprint_sha256"], "goal_triplet": triplet})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=args.out.parent, delete=False) as handle:
        for prediction in predictions:
            handle.write(json.dumps(prediction, ensure_ascii=False, sort_keys=True) + "\n")
        temporary = Path(handle.name)
    os.replace(temporary, args.out)
    manifest = {"status": "VAGUE_GOAL_TRIPLET_INFERENCE_COMPLETE", "model": args.model, "model_revision": args.revision, "packet_sha256": sha256(args.packet), "prompt_sha256": sha256(args.prompt), "output_sha256": sha256(args.out), "record_count": len(predictions), "decoder_parameters": {"temperature": float(args.temperature), "top_p": 1.0, "seed": args.seed, "max_tokens": 96, "technical_retries": 2}, "started_at_utc": datetime.fromtimestamp(started, timezone.utc).isoformat(), "elapsed_seconds": round(time.time() - started, 3)}
    args.manifest_out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"records": len(predictions), "output_sha256": manifest["output_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
