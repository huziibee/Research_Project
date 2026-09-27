#!/usr/bin/env python3
"""Build prediction-blind SGC packet for T0.7 Goal-First + Context-Blind intents.

Mirrors build_gfv2_intent_summary_sgc_packet_20260913.py but accepts CLI paths so
repaired T0.7 artifacts can be judged without rewriting the T0 packet.
"""
from __future__ import annotations

import argparse
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
from intent_eval_common import _strip_verbatim_source_command  # type: ignore

GOLD = (
    ROOT
    / "pilot120_intent_evaluation_20260902"
    / "pilot120_intent_evaluation_20260902"
    / "data"
    / "intent_gold_references_120.jsonl"
)
COND_FULL = "GOAL_FIRST_V2_FULL_T07"
COND_BLIND = "GOAL_FIRST_V2_BLIND_T07"


def load_jsonl(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rid = row["record_id"]
        if rid in rows:
            raise SystemExit(f"duplicate:{path}:{rid}")
        rows[rid] = row
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def intent_text(pred: dict) -> str:
    parsed = (pred.get("parsed") or {}).get("analysis") or {}
    text = pred.get("intent_summary") or parsed.get("intent_summary") or ""
    return str(text).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal-first", type=Path, required=True)
    parser.add_argument("--context-blind", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260913)
    args = parser.parse_args()

    gold = load_jsonl(GOLD)
    full = load_jsonl(args.goal_first)
    blind = load_jsonl(args.context_blind)
    ids = sorted(gold)
    if set(full) != set(ids) or set(blind) != set(ids):
        raise SystemExit("id_binding_failed")

    traces: list[dict] = []
    for rid in ids:
        cmd = ((gold[rid].get("source") or {}).get("command") or "")
        for cond, table in ((COND_FULL, full), (COND_BLIND, blind)):
            raw = intent_text(table[rid])
            if not raw:
                raise SystemExit(f"empty_intent_summary:{cond}:{rid}")
            excerpt = _strip_verbatim_source_command(raw, cmd).strip()
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
        eid = "T07M-" + hashlib.sha256(
            f"t07-manager-sgc-v1|{trace['record_id']}|{trace['analysis_condition']}".encode()
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
                "evaluation_id": "T07M-"
                + hashlib.sha256(
                    f"t07-manager-sgc-v1|{trace['record_id']}|{trace['analysis_condition']}".encode()
                ).hexdigest()[:20],
                "record_id": trace["record_id"],
                "analysis_condition": trace["analysis_condition"],
            }
        )

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "blind_judge_pass_1_120.jsonl", pass1)
    write_jsonl(out / "blind_judge_pass_2_120.jsonl", pass2)
    write_jsonl(out / "SEALED_evaluation_mapping.jsonl", mapping)
    write_jsonl(out / "intent_observable_traces_240.jsonl", traces)
    (out / "PACKET_AUDIT.json").write_text(
        json.dumps(
            {
                "built_at_utc": datetime.now(timezone.utc).isoformat(),
                "n_pass1": len(pass1),
                "n_pass2": len(pass2),
                "n_mapping": len(mapping),
                "conditions": [COND_FULL, COND_BLIND],
                "degree_timid_share_goal_first_intent": True,
                "seed": args.seed,
                "goal_first": str(args.goal_first),
                "context_blind": str(args.context_blind),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "out": str(out), "n": len(ids)}, indent=2))


if __name__ == "__main__":
    main()
