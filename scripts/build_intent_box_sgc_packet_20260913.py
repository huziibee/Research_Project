#!/usr/bin/env python3
"""CPU packet: prediction-blind SGC on new intent_summary boxes (raw + fine-tune)."""
from __future__ import annotations

import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0,
    str(ROOT / "pilot120_intent_evaluation_20260902" / "pilot120_intent_evaluation_20260902" / "scripts"),
)
from intent_eval_common import _strip_verbatim_source_command, sha256_text  # type: ignore

GOLD = (
    ROOT
    / "pilot120_intent_evaluation_20260902"
    / "pilot120_intent_evaluation_20260902"
    / "data"
    / "intent_gold_references_120.jsonl"
)


def load_jsonl(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["record_id"]] = row
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def intent_text(pred: dict) -> str:
    parsed = pred.get("parsed") or {}
    return str(pred.get("intent_summary") or parsed.get("intent_summary") or "").strip()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--fine-tune", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260913)
    args = parser.parse_args()

    gold = load_jsonl(GOLD)
    raw = load_jsonl(args.raw)
    fine = load_jsonl(args.fine_tune)
    ids = sorted(gold)
    if set(raw) != set(ids) or set(fine) != set(ids):
        raise SystemExit("id_binding_failed")
    traces = []
    for rid in ids:
        cmd = ((gold[rid].get("source") or {}).get("command") or "")
        for cond, table in (("RAW_INTENT_BOX", raw), ("FINE_TUNE_INTENT_BOX", fine)):
            raw_text = intent_text(table[rid])
            if not raw_text:
                raise SystemExit(f"empty_intent_summary:{cond}:{rid}")
            excerpt = _strip_verbatim_source_command(raw_text, cmd).strip()
            traces.append(
                {
                    "record_id": rid,
                    "analysis_condition": cond,
                    "cleaned_observable_trace": excerpt,
                    "intent_candidate_text": excerpt,
                }
            )

    rows_by_record: dict[str, list[tuple[str, dict]]] = {}
    rows = []
    for trace in traces:
        g = gold[trace["record_id"]]
        eid = "IB-" + hashlib.sha256(
            f"intent-box-sgc-v1|{trace['record_id']}|{trace['analysis_condition']}".encode()
        ).hexdigest()[:20]
        jr = {
            "evaluation_id": eid,
            "source": g.get("source"),
            "gold_reference_A": g["reference_A_intent_text"],
            "gold_reference_B": g["reference_B_intent_text"],
            "candidate_observable_trace": trace["cleaned_observable_trace"],
            "candidate_intent_excerpt": trace["intent_candidate_text"],
            "verbatim_source_command_policy": (
                "Exact source-command copies are replaced and cannot by themselves earn semantic-goal credit."
            ),
            "instructions_scope": "Judge semantic user-goal only. Ignore terminal route and CPC/slot correctness.",
        }
        rows.append(jr)
        rows_by_record.setdefault(trace["record_id"], []).append((trace["analysis_condition"], jr))

    assign = random.Random(args.seed + 1)
    pass1, pass2 = [], []
    for rid in ids:
        pair = sorted(rows_by_record[rid], key=lambda item: item[0])
        if assign.random() < 0.5:
            pass1.append(pair[0][1])
            pass2.append(pair[1][1])
        else:
            pass1.append(pair[1][1])
            pass2.append(pair[0][1])
    random.Random(args.seed + 2).shuffle(pass1)
    random.Random(args.seed + 3).shuffle(pass2)
    mapping = []
    for trace in traces:
        mapping.append(
            {
                "evaluation_id": "IB-"
                + hashlib.sha256(
                    f"intent-box-sgc-v1|{trace['record_id']}|{trace['analysis_condition']}".encode()
                ).hexdigest()[:20],
                "record_id": trace["record_id"],
                "analysis_condition": trace["analysis_condition"],
            }
        )
    args.out.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out / "blind_judge_pass_1_120.jsonl", pass1)
    write_jsonl(args.out / "blind_judge_pass_2_120.jsonl", pass2)
    write_jsonl(args.out / "SEALED_evaluation_mapping.jsonl", mapping)
    (args.out / "PACKET_AUDIT.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "official_sgc_not_run": True,
                "raw_sha256": sha256_text(args.raw.read_text(encoding="utf-8")),
                "fine_tune_sha256": sha256_text(args.fine_tune.read_text(encoding="utf-8")),
                "gold_sha256": sha256_text(GOLD.read_text(encoding="utf-8")),
                "seed": args.seed,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"out": str(args.out), "pass1": len(pass1), "pass2": len(pass2)}))


if __name__ == "__main__":
    main()
