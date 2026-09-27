#!/usr/bin/env python3
"""Join two-judge decisions to the sealed map. Does not rewrite frozen T39/T41."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

FIELDS = (
    "primary_goal_match",
    "required_action_set_match",
    "polarity_match",
    "explicit_enough",
    "no_incompatible_goal",
)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sgc(row: dict) -> bool:
    return all(bool(row.get(field)) for field in FIELDS)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--judge-a", type=Path, required=True)
    parser.add_argument("--judge-b", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    mapping = {row["evaluation_id"]: row for row in load_jsonl(args.mapping)}
    by_judge = {
        "Judge_A": {row["evaluation_id"]: row for row in load_jsonl(args.judge_a)},
        "Judge_B": {row["evaluation_id"]: row for row in load_jsonl(args.judge_b)},
    }
    if set(by_judge["Judge_A"]) != set(mapping) or set(by_judge["Judge_B"]) != set(mapping):
        raise SystemExit("judgment_mapping_mismatch")

    rows = []
    both_yes = defaultdict(int)
    either_yes = defaultdict(int)
    n = defaultdict(int)
    agree = defaultdict(int)
    for eid, meta in mapping.items():
        a = sgc(by_judge["Judge_A"][eid])
        b = sgc(by_judge["Judge_B"][eid])
        cond = meta["analysis_condition"]
        n[cond] += 1
        if a and b:
            both_yes[cond] += 1
        if a or b:
            either_yes[cond] += 1
        if a == b:
            agree[cond] += 1
        rows.append(
            {
                "evaluation_id": eid,
                "record_id": meta["record_id"],
                "analysis_condition": cond,
                "judge_a_sgc": a,
                "judge_b_sgc": b,
                "both_sgc": a and b,
            }
        )
    summary = {
        "protocol": "same five-boolean AND as the older two-judge intent pass",
        "official_label": "two-judge intent correctness on the supplied box, not routing",
        "per_condition": {
            cond: {
                "n": n[cond],
                "both_judges_yes": both_yes[cond],
                "both_rate": both_yes[cond] / n[cond],
                "either_yes": either_yes[cond],
                "agree": agree[cond],
            }
            for cond in sorted(n)
        },
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "sgc_rows.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    (args.out / "sgc_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
