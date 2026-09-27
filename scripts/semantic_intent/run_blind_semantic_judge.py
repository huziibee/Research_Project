#!/usr/bin/env python3
"""Prediction-blind runner for one semantic-intent judging pass.

This runner deliberately accepts only the sanitized blind packet and judge
materials.  It has no argument for a system identity, mapping, terminal route,
or any T39 score.  Model provenance is recorded in a separate run manifest,
not in the prompt supplied to the judge.
"""
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


REQUIRED = {
    "evaluation_id",
    "primary_goal_match",
    "required_action_set_match",
    "polarity_match",
    "explicit_enough",
    "no_incompatible_goal",
    "rationale",
    "prediction_blind_attestation",
}
BOOL_FIELDS = REQUIRED - {"evaluation_id", "rationale"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError(f"non_object_packet_row:{line_no}")
            rows.append(obj)
    return rows


def post(url: str, body: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_decision(content: str, expected_id: str) -> dict:
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("decision_not_object")
    if REQUIRED - set(value):
        for nested in value.values():
            if isinstance(nested, dict) and REQUIRED <= set(nested):
                value = nested
                break
    missing = REQUIRED - set(value)
    if missing:
        raise ValueError(f"decision_keys_missing:{sorted(missing)}")
    # GLM sometimes echoes packet fields into the JSON. Keep the official
    # five-boolean schema only; do not treat extra keys as a new protocol.
    value = {key: value[key] for key in REQUIRED}
    # The opaque ID is a transport key, not a semantic judgment. Gemma copied
    # a calibration ID in job 50868 despite sequential single-row prompts.
    # Bind a validated response to the one packet row just sent instead of
    # requiring the model to reproduce an arbitrary hash token.
    if not isinstance(value["evaluation_id"], str):
        raise ValueError("decision_id_not_string")
    if any(not isinstance(value[field], bool) for field in BOOL_FIELDS):
        raise ValueError("decision_bool_field_invalid")
    if value["prediction_blind_attestation"] is not True:
        raise ValueError("blind_attestation_not_true")
    if not isinstance(value["rationale"], str) or not value["rationale"].strip():
        raise ValueError("decision_rationale_missing")
    value["evaluation_id"] = expected_id
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", required=True)
    parser.add_argument("--guide", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--calibration", required=True)
    parser.add_argument("--judge-id", required=True, choices=["Judge_A", "Judge_B"])
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--out", required=True)
    parser.add_argument("--manifest-out", required=True)
    parser.add_argument("--seed", required=True, type=int)
    args = parser.parse_args()

    packet_path = Path(args.packet)
    rows = load_jsonl(packet_path)
    if len(rows) != 120 or len({row.get("evaluation_id") for row in rows}) != 120:
        raise SystemExit("blind_pass_must_contain_exactly_120_unique_evaluation_ids")
    forbidden = {"system_id", "model", "route", "terminal", "cpc_correct", "ambiguity_correct", "record_id"}
    if any(any(token in key.lower() for token in forbidden) for row in rows for key in row):
        raise SystemExit("forbidden_blind_packet_key")

    guide = Path(args.guide).read_text(encoding="utf-8")
    prompt = Path(args.prompt).read_text(encoding="utf-8")
    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    calibration = Path(args.calibration).read_text(encoding="utf-8")
    system = "\n\n".join((prompt, "JUDGE GUIDE:\n" + guide, "OUTPUT SCHEMA:\n" + json.dumps(schema, sort_keys=True), "SYNTHETIC CALIBRATION (not Pilot results):\n" + calibration))
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    decisions: list[dict] = []
    started = time.time()
    for index, row in enumerate(rows, 1):
        body = {
            "model": args.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": "Judge this one blinded item. Return JSON only.\n" + json.dumps(row, ensure_ascii=False, sort_keys=True)},
            ],
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": args.seed + index,
            "max_tokens": 2048,
            "response_format": {"type": "json_object"},
        }
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                response = post(f"http://127.0.0.1:{args.port}/v1/chat/completions", body)
                content = response["choices"][0]["message"]["content"]
                decisions.append(parse_decision(content, row["evaluation_id"]))
                last_error = None
                break
            except Exception as error:  # Transport and JSON schema retries only.
                last_error = error
                body["messages"] = body["messages"] + [{
                    "role": "user",
                    "content": (
                        "Technical retry: return exactly one JSON object with ONLY these keys: "
                        "evaluation_id, primary_goal_match, required_action_set_match, polarity_match, "
                        "explicit_enough, no_incompatible_goal, rationale, prediction_blind_attestation. "
                        "Do not echo the packet, gold text, or any other field. "
                        f"evaluation_id MUST be exactly {row['evaluation_id']}."
                    ),
                }]
        if last_error is not None:
            raise SystemExit(f"judge_decision_failed:{row['evaluation_id']}:{last_error!r}")

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=output_path.parent, delete=False) as handle:
        for decision in decisions:
            handle.write(json.dumps(decision, ensure_ascii=False, sort_keys=True) + "\n")
        temp_name = handle.name
    os.replace(temp_name, output_path)
    manifest = {
        "judge_id": args.judge_id,
        "model": args.model,
        "revision": args.revision,
        "packet_sha256": sha256_file(packet_path),
        "guide_sha256": sha256_file(Path(args.guide)),
        "prompt_sha256": sha256_file(Path(args.prompt)),
        "schema_sha256": sha256_file(Path(args.schema)),
        "calibration_sha256": sha256_file(Path(args.calibration)),
        "output_sha256": sha256_file(output_path),
        "record_count": len(decisions),
        "fresh_context": True,
        "prediction_blind_inputs_only": True,
        "started_at_utc": datetime.fromtimestamp(started, timezone.utc).isoformat(),
        "elapsed_seconds": round(time.time() - started, 3),
    }
    Path(args.manifest_out).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"judge_id": args.judge_id, "record_count": len(decisions), "output_sha256": manifest["output_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
