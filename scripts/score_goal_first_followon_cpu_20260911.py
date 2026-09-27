#!/usr/bin/env python3
"""CPU score follow-on natives + audit v2 R2/R3. No model load. No retuning."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code-root", type=Path, required=True)
    ap.add_argument("--followon-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    code = args.code_root
    root = args.followon_root
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(code / "scripts"))

    summary: dict = {"followon_root": str(root), "audits": {}, "native_scores": {}, "errors": []}

    for replica in ("R2", "R3"):
        manager = root / replica / "manager"
        if not manager.exists():
            summary["errors"].append(f"missing:{manager}")
            continue
        dest = out / f"{replica}_audit.json"
        run(
            [
                sys.executable,
                str(code / "scripts/audit_goal_first_v2_predictions.py"),
                "--manager-dir",
                str(manager),
                "--out",
                str(dest),
                "--expected-rows",
                "120",
            ]
        )
        summary["audits"][replica] = str(dest)

    # Native scorers if prediction files exist
    score_map = [
        (
            "vague",
            "scripts/score_vague_goal_intent.py",
            "vague_inference_packet.jsonl",
        ),
        (
            "ambik",
            "scripts/score_ambik_ambiguity_type.py",
            "ambik_packet.jsonl",
        ),
        (
            "indirect",
            "scripts/score_native_context.py",
            "indirect.jsonl",
        ),
        (
            "clara",
            "scripts/score_native_context.py",
            "clara.jsonl",
        ),
    ]
    native_root = Path(
        "/home-mscluster/mbangie/t12-hpc/code/followon-native-20260911"
    )
    for system in ("gemma4", "glm47"):
        for task, script, packet_name in score_map:
            pred = root / "native" / system / task / "predictions.jsonl"
            if not pred.exists():
                summary["errors"].append(f"missing_pred:{pred}")
                continue
            packet = native_root / "inputs" / packet_name
            dest = out / "native" / system / f"{task}_score.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            cmd = [
                sys.executable,
                str(code / script if (code / script).exists() else native_root / script),
                "--predictions",
                str(pred),
                "--packet",
                str(packet),
                "--out",
                str(dest),
            ]
            # scorers have slightly different CLIs; try common forms
            try:
                run(cmd)
                summary["native_scores"][f"{system}/{task}"] = str(dest)
            except Exception as exc:  # noqa: BLE001
                # fallback without --packet if scorer only needs predictions
                alt = [
                    sys.executable,
                    str(code / script if (code / script).exists() else native_root / script),
                    "--predictions",
                    str(pred),
                    "--out",
                    str(dest),
                ]
                try:
                    run(alt)
                    summary["native_scores"][f"{system}/{task}"] = str(dest)
                except Exception as exc2:  # noqa: BLE001
                    summary["errors"].append(f"score_failed:{system}/{task}:{exc!r}|{exc2!r}")

    (out / "followon_cpu_score_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
