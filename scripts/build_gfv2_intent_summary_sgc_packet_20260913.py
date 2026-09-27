#!/usr/bin/env python3
"""Build a prediction-blind SGC packet from v2 intent_summary (CPU only).

Does not run judges. Does not submit GPU jobs. Does not touch T39/T41.
Official two-judge SGC remains unrun until a later exclusive judge job.
"""
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
PULLS = ROOT / "outputs" / "cluster_pulls" / "r1_manager" / "predictions"
FULL_PRED = PULLS / "goal_first_manager_v2.predictions.jsonl"
BLIND_PRED = PULLS / "goal_first_context_blind_v2.predictions.jsonl"
OUT = ROOT / "outputs" / "gfv2_intent_summary_sgc_packet_20260913"
SEED = 20260913
COND_FULL = "GOAL_FIRST_V2_FULL"
COND_BLIND = "GOAL_FIRST_V2_BLIND"
# R1 salvage IDs from GOAL_FIRST_V2_ABLATION_PACKET_20260912.md (audit only; not in blind rows).
SALVAGE_FULL = (
    "CA-0105",
    "CA-0332",
    "CA-0360",
    "CA-0382",
    "CA-0648",
    "CA-0714",
    "CA-0762",
    "CA-0866",
)
SALVAGE_BLIND = ("CA-0805",)


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
    gold = load_jsonl(GOLD)
    full = load_jsonl(FULL_PRED)
    blind = load_jsonl(BLIND_PRED)
    ids = sorted(gold)
    if set(full) != set(ids) or set(blind) != set(ids):
        raise SystemExit("id_binding_failed")

    traces: list[dict] = []
    nonempty = 0
    verbatim_after = 0
    for rid in ids:
        cmd = ((gold[rid].get("source") or {}).get("command") or "")
        for cond, table in ((COND_FULL, full), (COND_BLIND, blind)):
            raw = intent_text(table[rid])
            if not raw:
                raise SystemExit(f"empty_intent_summary:{cond}:{rid}")
            excerpt = _strip_verbatim_source_command(raw, cmd).strip()
            if excerpt:
                nonempty += 1
            if cmd and cmd.lower() in excerpt.lower():
                verbatim_after += 1
            traces.append(
                {
                    "record_id": rid,
                    "analysis_condition": cond,
                    "intent_summary_sha256": sha256_text(raw),
                    "cleaned_observable_trace": excerpt,
                    "intent_candidate_text": excerpt,
                    "verbatim_command_omitted": bool(cmd and cmd.lower() in raw.lower()),
                    "trace_provenance": (
                        "goal_first_v2 R1 structured intent_summary; not leftover T39 think-trace"
                    ),
                }
            )

    rows: list[dict] = []
    rows_by_record: dict[str, list[tuple[str, dict]]] = {}
    for trace in traces:
        g = gold[trace["record_id"]]
        opaque = hashlib.sha256(
            f"gfv2-intent-sgc-v1|{trace['record_id']}|{trace['analysis_condition']}".encode()
        ).hexdigest()[:20]
        jr = {
            "evaluation_id": "GF-" + opaque,
            "source": g.get("source"),
            "gold_reference_A": g["reference_A_intent_text"],
            "gold_reference_B": g["reference_B_intent_text"],
            "candidate_observable_trace": trace["cleaned_observable_trace"],
            "candidate_intent_excerpt": trace["intent_candidate_text"],
            "verbatim_source_command_policy": (
                "Exact source-command copies are replaced and cannot by themselves "
                "earn semantic-goal credit."
            ),
            "instructions_scope": (
                "Judge semantic user-goal only. Ignore terminal route and CPC/slot correctness."
            ),
        }
        rows.append(jr)
        rows_by_record.setdefault(trace["record_id"], []).append((trace["analysis_condition"], jr))

    rng = random.Random(SEED)
    rng.shuffle(rows)
    pass1: list[dict] = []
    pass2: list[dict] = []
    assign = random.Random(SEED + 1)
    for rid in ids:
        pair = sorted(rows_by_record[rid], key=lambda item: item[0])
        if len(pair) != 2:
            raise SystemExit(f"pair_failure:{rid}")
        if assign.random() < 0.5:
            pass1.append(pair[0][1])
            pass2.append(pair[1][1])
        else:
            pass1.append(pair[1][1])
            pass2.append(pair[0][1])
    random.Random(SEED + 2).shuffle(pass1)
    random.Random(SEED + 3).shuffle(pass2)

    mapping = []
    for trace in traces:
        eid = (
            "GF-"
            + hashlib.sha256(
                f"gfv2-intent-sgc-v1|{trace['record_id']}|{trace['analysis_condition']}".encode()
            ).hexdigest()[:20]
        )
        mapping.append(
            {
                "evaluation_id": eid,
                "record_id": trace["record_id"],
                "analysis_condition": trace["analysis_condition"],
            }
        )

    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "intent_observable_traces_240.jsonl", traces)
    write_jsonl(OUT / "blind_semantic_goal_judge_packet_240.jsonl", rows)
    write_jsonl(OUT / "blind_judge_pass_1_120.jsonl", pass1)
    write_jsonl(OUT / "blind_judge_pass_2_120.jsonl", pass2)
    write_jsonl(OUT / "SEALED_evaluation_mapping.jsonl", mapping)

    audit = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "claim_boundary": (
            "CPU packet only. Judges not run. Not official SGC. "
            "Uses v2 structured intent_summary, not leftover T39 think-trace. "
            "Some R1 summaries are CPU-salvaged (rebuild_from_head_fields), not clean first-pass JSON. "
            "T39/T41 frozen. Adapter unofficial."
        ),
        "official_sgc_not_run": True,
        "gpu_judges_not_started": True,
        "n_records": len(ids),
        "n_traces": len(traces),
        "pass1": len(pass1),
        "pass2": len(pass2),
        "nonempty_excerpts": nonempty,
        "excerpts_still_containing_exact_source_command": verbatim_after,
        "seed": SEED,
        "systems": [COND_FULL, COND_BLIND],
        "replica": "R1",
        "full_predictions": str(FULL_PRED.relative_to(ROOT)).replace("\\", "/"),
        "blind_predictions": str(BLIND_PRED.relative_to(ROOT)).replace("\\", "/"),
        "gold": str(GOLD.relative_to(ROOT)).replace("\\", "/"),
        "full_predictions_sha256": sha256_text(FULL_PRED.read_text(encoding="utf-8")),
        "blind_predictions_sha256": sha256_text(BLIND_PRED.read_text(encoding="utf-8")),
        "gold_sha256": sha256_text(GOLD.read_text(encoding="utf-8")),
        "salvage_ids_full_context": list(SALVAGE_FULL),
        "salvage_ids_blind": list(SALVAGE_BLIND),
        "record_id_exposed_in_blind_packet": False,
        "protocol_reuse": (
            "pilot120_intent_evaluation_20260902 protocol/JUDGE_GUIDE.md and JUDGE_PROMPT.txt"
        ),
    }
    (OUT / "PACKET_AUDIT.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUT / "README.md").write_text(
        "# Goal-first v2 intent_summary SGC packet — 13 September 2026\n\n"
        "CPU packet only. **Judges were not run.** This is not official SGC.\n\n"
        "Candidate text is the structured `intent_summary` from R1 "
        "`goal_first_manager_v2` and `goal_first_context_blind_v2`, with exact "
        "source-command copies omitted. It is a different artifact from leftover "
        "T39 think-trace SGC (~113/120) and from the exploratory lexical proxy "
        "(112/120).\n\n"
        "Do not overwrite T39/T41. Do not flip the adapter official from this packet.\n\n"
        "To finish official two-judge SGC later: run the existing blind-judge "
        "protocol on `blind_judge_pass_1_120.jsonl` and `blind_judge_pass_2_120.jsonl` "
        "when an exclusive Blackwell node is free. Keep `SEALED_evaluation_mapping.jsonl` "
        "out of the judge submit directory.\n",
        encoding="utf-8",
    )
    print(json.dumps({"out": str(OUT), **audit}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
