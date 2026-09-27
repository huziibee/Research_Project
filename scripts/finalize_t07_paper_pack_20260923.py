#!/usr/bin/env python3
"""Write the paper-facing T0.7 completion files and package the experiment dir."""
from __future__ import annotations

import csv
import hashlib
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from score_t07_matched_baseline_20260922 import wilson

FIELDS = (
    "primary_goal_match",
    "required_action_set_match",
    "polarity_match",
    "explicit_enough",
    "no_incompatible_goal",
)
COND_RAW = "RAW_INTENT_BOX"
COND_FT = "FINE_TUNE_INTENT_BOX"
COND_GF = "GOAL_FIRST_V2_FULL_T07"
COND_BLIND = "GOAL_FIRST_V2_BLIND_T07"


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _judge_index(path: Path) -> dict[str, dict]:
    return {row["evaluation_id"]: row for row in _load_jsonl(path)}


def write_paper_pack(exp: Path) -> Path:
    exp = exp.resolve()
    ids = [line.strip() for line in (exp / "02_input_case_ids.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(ids) == 120 and len(set(ids)) == 120

    box_rows = _load_jsonl(exp / "judges/intent_box_raw_ft/final/sgc_rows.jsonl")
    mgr_rows = _load_jsonl(exp / "judges/gfv2_intent_summary_t07/final/sgc_rows.jsonl")
    box_map = {(r["record_id"], r["analysis_condition"]): r for r in box_rows}
    mgr_map = {(r["record_id"], r["analysis_condition"]): r for r in mgr_rows}

    def count(mp: dict, cond: str) -> int:
        return sum(1 for rid in ids if (mp.get((rid, cond)) or {}).get("both_sgc") is True)

    raw_intent = count(box_map, COND_RAW)
    ft_intent = count(box_map, COND_FT)
    gf_intent = count(mgr_map, COND_GF)
    blind_intent = count(mgr_map, COND_BLIND)

    routing = {
        "Raw Qwen": 96,
        "Fine-Tune": 92,
        "Goal-First": 56,
        "Degree": 57,
        "Timid": 29,
        "Context-Blind": 21,
    }
    official = {
        "Raw Qwen": raw_intent,
        "Fine-Tune": ft_intent,
        "Goal-First": gf_intent,
        "Degree": gf_intent,
        "Timid": gf_intent,
        "Context-Blind": blind_intent,
    }
    notes = {
        "Raw Qwen": "official two-judge on T0.7 intent box",
        "Fine-Tune": "official two-judge on T0.7 intent box",
        "Goal-First": "official two-judge on repaired T0.7 intent_summary",
        "Degree": "inherits Goal-First official intent (shared generation; not re-judged)",
        "Timid": "inherits Goal-First official intent (shared generation; not re-judged)",
        "Context-Blind": "official two-judge on T0.7 context-blind intent_summary",
    }

    systems_official = {
        "raw_qwen": (exp / "10_raw_qwen_t07_official_intent.json", COND_RAW, box_map, "Raw Qwen"),
        "finetune": (exp / "11_finetune_t07_official_intent.json", COND_FT, box_map, "Fine-Tune"),
        "goal_first": (exp / "12_goal_first_t07_official_intent.json", COND_GF, mgr_map, "Goal-First"),
        "context_blind": (exp / "13_context_blind_t07_official_intent.json", COND_BLIND, mgr_map, "Context-Blind"),
    }
    for _key, (path, cond, mp, label) in systems_official.items():
        k = official[label]
        path.write_text(
            json.dumps(
                {
                    "system": label,
                    "official_intent": k,
                    "n": 120,
                    "failed_in_denominator": True,
                    "pass_rule": "both judges five-boolean AND",
                    "condition": cond,
                    "degree_timid_inherit_goal_first": label == "Goal-First",
                    "wilson_95ci": wilson(k, 120),
                    "T0.3_included": False,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    judge_a_box = _judge_index(exp / "judges/intent_box_raw_ft/Judge_A_combined.jsonl")
    judge_b_box = _judge_index(exp / "judges/intent_box_raw_ft/Judge_B_combined.jsonl")
    judge_a_mgr = _judge_index(exp / "judges/gfv2_intent_summary_t07/Judge_A_combined.jsonl")
    judge_b_mgr = _judge_index(exp / "judges/gfv2_intent_summary_t07/Judge_B_combined.jsonl")

    excerpts: dict[tuple[str, str], str] = {}
    for packet in (
        exp / "packets/intent_box_sgc_t07/SEALED_evaluation_mapping.jsonl",
        exp / "packets/manager_sgc_t07/SEALED_evaluation_mapping.jsonl",
    ):
        for row in _load_jsonl(packet):
            excerpts[(row["record_id"], row["analysis_condition"])] = str(
                row.get("candidate_intent_excerpt") or row.get("intent_candidate_text") or ""
            )
    for packet in (
        exp / "packets/intent_box_sgc_t07/blind_judge_pass_1_120.jsonl",
        exp / "packets/manager_sgc_t07/blind_judge_pass_1_120.jsonl",
    ):
        for row in _load_jsonl(packet):
            # blind packets are keyed by evaluation_id only; skip if no record
            pass

    mapping_rows = _load_jsonl(exp / "packets/intent_box_sgc_t07/SEALED_evaluation_mapping.jsonl") + _load_jsonl(
        exp / "packets/manager_sgc_t07/SEALED_evaluation_mapping.jsonl"
    )
    mapping_by_eid = {row["evaluation_id"]: row for row in mapping_rows}

    case_path = exp / "14_official_intent_case_level.csv"
    with case_path.open("w", encoding="utf-8", newline="") as fh:
        fields = [
            "record_id",
            "system",
            "analysis_condition",
            "candidate_intent_text",
            "official_both_judges",
            *[f"judge_a_{f}" for f in FIELDS],
            "judge_a_overall",
            "judge_a_rationale",
            *[f"judge_b_{f}" for f in FIELDS],
            "judge_b_overall",
            "judge_b_rationale",
        ]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for label, cond, mp, ja, jb in (
            ("Raw Qwen", COND_RAW, box_map, judge_a_box, judge_b_box),
            ("Fine-Tune", COND_FT, box_map, judge_a_box, judge_b_box),
            ("Goal-First", COND_GF, mgr_map, judge_a_mgr, judge_b_mgr),
            ("Context-Blind", COND_BLIND, mgr_map, judge_a_mgr, judge_b_mgr),
        ):
            for rid in ids:
                official_row = mp.get((rid, cond)) or {}
                eid = official_row.get("evaluation_id")
                if not eid:
                    for ev, meta in mapping_by_eid.items():
                        if meta.get("record_id") == rid and meta.get("analysis_condition") == cond:
                            eid = ev
                            break
                a = ja.get(eid or "") or {}
                b = jb.get(eid or "") or {}
                w.writerow(
                    {
                        "record_id": rid,
                        "system": label,
                        "analysis_condition": cond,
                        "candidate_intent_text": excerpts.get((rid, cond), ""),
                        "official_both_judges": official_row.get("both_sgc"),
                        **{f"judge_a_{f}": a.get(f) for f in FIELDS},
                        "judge_a_overall": official_row.get("judge_a_sgc"),
                        "judge_a_rationale": a.get("rationale"),
                        **{f"judge_b_{f}": b.get(f) for f in FIELDS},
                        "judge_b_overall": official_row.get("judge_b_sgc"),
                        "judge_b_rationale": b.get("rationale"),
                    }
                )

    scoreboard_rows = [
        {
            "system": name,
            "official_intent": official[name],
            "exact_routing": routing[name],
            "note": notes[name],
        }
        for name in ("Raw Qwen", "Fine-Tune", "Goal-First", "Degree", "Timid", "Context-Blind")
    ]
    (exp / "15_final_t07_scoreboard.json").write_text(
        json.dumps(
            {
                "title": "Pilot-120 T0.7 matched baseline (study default)",
                "n": 120,
                "T0.3_included": False,
                "degree_timid_share_goal_first_intent": True,
                "historical_T0_preserved": True,
                "rows": scoreboard_rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with (exp / "16_final_t07_scoreboard.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["system", "official_intent", "exact_routing", "note"])
        w.writeheader()
        w.writerows(scoreboard_rows)
    md = [
        "# T0.7 matched baseline scoreboard",
        "",
        "| System | Official intent /120 | Exact routing /120 |",
        "|---|---:|---:|",
    ]
    for row in scoreboard_rows:
        md.append(f"| {row['system']} | {row['official_intent']} | {row['exact_routing']} |")
    md.extend(
        [
            "",
            "Degree and Timid inherit Goal-First official intent (shared written generation).",
            "T0.3 is not included. Historical T0 official intent (Raw 113 / Fine-Tune 107 / Goal-First 113) is preserved.",
            "",
        ]
    )
    (exp / "17_final_t07_scoreboard.md").write_text("\n".join(md), encoding="utf-8")
    (exp / "FINAL_T07_SCOREBOARD.json").write_text((exp / "15_final_t07_scoreboard.json").read_text(encoding="utf-8"), encoding="utf-8")
    (exp / "FINAL_T07_SCOREBOARD.csv").write_text((exp / "16_final_t07_scoreboard.csv").read_text(encoding="utf-8"), encoding="utf-8")
    (exp / "FINAL_T07_SCOREBOARD.md").write_text((exp / "17_final_t07_scoreboard.md").read_text(encoding="utf-8"), encoding="utf-8")
    (exp / "T07_OFFICIAL_INTENT_CASES.csv").write_text(case_path.read_text(encoding="utf-8"), encoding="utf-8")

    summary = json.loads((exp / "FINAL_T07_MATCHED_BASELINE_SUMMARY.json").read_text(encoding="utf-8"))
    paired_stats = summary["paired_statistics"]
    (exp / "18_paired_statistics.json").write_text(json.dumps(paired_stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def fmt_pair(name: str, block: dict) -> str:
        m = block["mcnemar_exact"]
        return (
            f"### {name}\n"
            f"- both correct: {block['both_correct']}\n"
            f"- {block['a']} only: {block['a_only_correct']}\n"
            f"- {block['b']} only: {block['b_only_correct']}\n"
            f"- both wrong: {block['both_wrong']}\n"
            f"- exact McNemar p = {m['p_value']}\n"
        )

    wilson_md = ["## Wilson 95% CI\n"]
    for name in official:
        wi = wilson(official[name], 120)
        wr = wilson(routing[name], 120)
        wilson_md.append(
            f"- {name}: intent {official[name]}/120 ({wi['low']:.3f}–{wi['high']:.3f}); "
            f"routing {routing[name]}/120 ({wr['low']:.3f}–{wr['high']:.3f})"
        )
    (exp / "19_paired_statistics.md").write_text(
        "# Paired analyses (same 120 cases)\n\n"
        + "\n".join(fmt_pair(k, v) for k, v in paired_stats.items())
        + "\n"
        + "\n".join(wilson_md)
        + "\n",
        encoding="utf-8",
    )

    provenance = exp / "20_ADAPTER_PROVENANCE_NOTE.md"
    if not provenance.exists():
        raise SystemExit("missing_adapter_provenance_note")

    status = {
        "RAW_T07_ROUTING": "96/120",
        "FINETUNE_T07_ROUTING": "92/120",
        "RAW_T07_OFFICIAL_INTENT": f"{raw_intent}/120",
        "FINETUNE_T07_OFFICIAL_INTENT": f"{ft_intent}/120",
        "GOAL_FIRST_T07_OFFICIAL_INTENT": f"{gf_intent}/120",
        "CONTEXT_BLIND_T07_OFFICIAL_INTENT": f"{blind_intent}/120",
        "DEGREE_T07_OFFICIAL_INTENT": f"{gf_intent}/120 (shared Goal-First)",
        "TIMID_T07_OFFICIAL_INTENT": f"{gf_intent}/120 (shared Goal-First)",
        "OFFICIAL_TWO_JUDGE_COMPLETE": "YES",
        "MATCHED_DEPTH5_CONTROL": "NOT_RUN",
        "T0.3_INCLUDED": "NO",
        "n": 120,
        "unique_ids": 120,
        "failed_rows_in_denominator": True,
        "degree_timid_independently_judged": False,
        "completed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (exp / "21_FINAL_STATUS.md").write_text(
        "# FINAL STATUS — T0.7 matched baseline\n\n"
        + "\n".join(f"{k} = {v}" for k, v in status.items())
        + "\n",
        encoding="utf-8",
    )
    (exp / "21_FINAL_STATUS.json").write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    hash_targets = sorted(
        p
        for p in exp.rglob("*")
        if p.is_file()
        and "T0.3" not in str(p)
        and "t03" not in str(p).lower()
        and p.suffix in {".json", ".jsonl", ".md", ".csv", ".txt"}
    )
    hashes = {str(p.relative_to(exp)).replace("\\", "/"): _sha256(p) for p in hash_targets}
    (exp / "SHA256_FINAL.json").write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    archive = exp.parent / "t07_matched_baseline_completion_20260922_FINAL.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(exp, arcname="t07_matched_baseline_completion_20260922")
    print(json.dumps({"archive": str(archive), **status}, indent=2, sort_keys=True))
    return archive


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", type=Path, required=True)
    args = parser.parse_args()
    write_paper_pack(args.experiment_dir)
