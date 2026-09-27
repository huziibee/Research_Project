#!/usr/bin/env python3
"""Build prediction-blind SGC packets for direct_base vs provisional adapter (R1).

CPU only. Does not run judges. Output is ready for a later GPU/CPU judge job.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0,
    str(ROOT / "pilot120_intent_evaluation_20260902" / "pilot120_intent_evaluation_20260902" / "scripts"),
)
from intent_eval_common import (  # type: ignore
    clean_observable_trace,
    extract_intent_candidate_text,
    sha256_text,
)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def by_id(rows: list[dict]) -> dict[str, dict]:
    out = {}
    for row in rows:
        rid = row["record_id"]
        if rid in out:
            raise SystemExit(f"duplicate:{rid}")
        out[rid] = row
    return out


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", type=Path, required=True, help="intent_gold_references_120.jsonl")
    ap.add_argument("--base-predictions", type=Path, required=True)
    ap.add_argument("--adapter-predictions", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=20260911)
    args = ap.parse_args()

    gold = by_id(load_jsonl(args.gold))
    base = by_id(load_jsonl(args.base_predictions))
    adapter = by_id(load_jsonl(args.adapter_predictions))
    ids = sorted(gold)
    if set(base) != set(ids) or set(adapter) != set(ids):
        raise SystemExit("id_binding_failed")

    traces = []
    for rid in ids:
        g = gold[rid]
        cmd = (g.get("source") or {}).get("command") or ""
        for cond, table in (("DIRECT_BASE", base), ("PROVISIONAL_ADAPTER", adapter)):
            raw = table[rid].get("raw_output") or ""
            clean = clean_observable_trace(raw, source_command=cmd)
            excerpt = extract_intent_candidate_text(raw, source_command=cmd)
            traces.append(
                {
                    "record_id": rid,
                    "analysis_condition": cond,
                    "raw_output_sha256": sha256_text(raw),
                    "cleaned_observable_trace": clean,
                    "intent_candidate_text": excerpt,
                    "verbatim_command_omitted": bool(cmd and cmd.lower() in raw.lower()),
                }
            )

    rows = []
    rows_by_record: dict[str, list[tuple[str, dict]]] = {}
    for t in traces:
        g = gold[t["record_id"]]
        opaque = hashlib.sha256(
            f"base-adapter-sgc-v1|{t['record_id']}|{t['analysis_condition']}".encode()
        ).hexdigest()[:20]
        jr = {
            "evaluation_id": "BA-" + opaque,
            "source": g.get("source"),
            "gold_reference_A": g["reference_A_intent_text"],
            "gold_reference_B": g["reference_B_intent_text"],
            "candidate_observable_trace": t["cleaned_observable_trace"],
            "candidate_intent_excerpt": t["intent_candidate_text"],
            "verbatim_source_command_policy": (
                "Exact source-command copies are replaced and cannot by themselves earn semantic-goal credit."
            ),
            "instructions_scope": "Judge semantic user-goal only. Ignore terminal route and CPC/slot correctness.",
        }
        rows.append(jr)
        rows_by_record.setdefault(t["record_id"], []).append((t["analysis_condition"], jr))

    rng = random.Random(args.seed)
    rng.shuffle(rows)
    pass1: list[dict] = []
    pass2: list[dict] = []
    assign = random.Random(args.seed + 1)
    for rid in ids:
        pair = sorted(rows_by_record[rid], key=lambda x: x[0])
        if len(pair) != 2:
            raise SystemExit(f"pair_failure:{rid}")
        if assign.random() < 0.5:
            pass1.append(pair[0][1])
            pass2.append(pair[1][1])
        else:
            pass1.append(pair[1][1])
            pass2.append(pair[0][1])
    random.Random(args.seed + 2).shuffle(pass1)
    random.Random(args.seed + 3).shuffle(pass2)

    mapping = []
    for t in traces:
        eid = (
            "BA-"
            + hashlib.sha256(
                f"base-adapter-sgc-v1|{t['record_id']}|{t['analysis_condition']}".encode()
            ).hexdigest()[:20]
        )
        mapping.append(
            {
                "evaluation_id": eid,
                "record_id": t["record_id"],
                "analysis_condition": t["analysis_condition"],
            }
        )

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "intent_observable_traces_240.jsonl", traces)
    write_jsonl(out / "blind_semantic_goal_judge_packet_240.jsonl", rows)
    write_jsonl(out / "blind_judge_pass_1_120.jsonl", pass1)
    write_jsonl(out / "blind_judge_pass_2_120.jsonl", pass2)
    write_jsonl(out / "SEALED_evaluation_mapping.jsonl", mapping)
    audit = {
        "n_records": len(ids),
        "n_traces": len(traces),
        "pass1": len(pass1),
        "pass2": len(pass2),
        "seed": args.seed,
        "systems": ["DIRECT_BASE", "PROVISIONAL_ADAPTER"],
        "claim_boundary": "Packet only; judges not run. Not official until two blind judges finalize.",
        "base_predictions_sha256": sha256_text(args.base_predictions.read_text(encoding="utf-8")),
        "adapter_predictions_sha256": sha256_text(args.adapter_predictions.read_text(encoding="utf-8")),
        "gold_sha256": sha256_text(args.gold.read_text(encoding="utf-8")),
    }
    (out / "PACKET_AUDIT.json").write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), **audit}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
