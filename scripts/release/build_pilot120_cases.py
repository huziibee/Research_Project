"""Build browsable Pilot-120 case records from frozen, hash-checked sources.

The output reproduces source-derived text. Review dataset rights before making
the repository public. This script never modifies the frozen input artifacts.
"""
from __future__ import annotations

import csv
import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data/annotations/pilot_120_v1"
RELEASE = ROOT / "research/pilot120"
T07 = RELEASE / "artifacts/t07_matched_baseline_completion_20260927_FINAL.zip"
FULL = RELEASE / "artifacts/p120_full_analysis_20260923.zip"
EXPECTED = {
    PILOT / "source_canonical.jsonl": "f33b1e29f1e8aa256a475f07213aa07247def47d8e2148d54a472a40b71b05c9",
    PILOT / "pilot_120_final_gold.jsonl": "5e23ad1a92ff1873c8f039a8ce560a111dd6fb6b8ae8c11d6cf34dbfa1c360db",
    PILOT / "GOLD_POLICY.json": "3c1f0a4d43c29996062a4a2ecd321e4023a38f5fad950801f96e07e23aac4a34",
    PILOT / "frozen/FROZEN_MANIFEST.json": "c61489101bfbc6cf0222538107abd272b50ce59c2f2a4292e95773f686d60230",
    T07: "34ca50e034ca37b617068bb50c734d12fa26282fb5eec563c11ead700163e491",
    FULL: "0305b1e9ab062876ee6ee89778cc6028d2eaf01718b7dd0295944e7d9cb81a01",
}


def verify(path: Path, expected: str) -> None:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch: {path.relative_to(ROOT)}")


def rows_by_id(lines: list[str], label: str) -> dict[str, dict]:
    rows = [json.loads(line) for line in lines if line.strip()]
    ids = [row["record_id"] for row in rows]
    if len(rows) != 120 or len(set(ids)) != 120:
        raise ValueError(f"{label}: expected 120 unique record IDs")
    return dict(zip(ids, rows))


def zip_jsonl(archive: zipfile.ZipFile, suffix: str) -> dict[str, dict]:
    matches = [name for name in archive.namelist() if name.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"expected one {suffix} in archive")
    lines = archive.read(matches[0]).decode("utf-8-sig").splitlines()
    return rows_by_id(lines, suffix)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Verify generated files without writing")
    args = parser.parse_args()
    for path, digest in EXPECTED.items():
        verify(path, digest)
    source = rows_by_id(
        (PILOT / "source_canonical.jsonl").read_text(encoding="utf-8").splitlines(),
        "source",
    )
    gold = rows_by_id(
        (PILOT / "pilot_120_final_gold.jsonl").read_text(encoding="utf-8").splitlines(),
        "gold",
    )
    if set(source) != set(gold):
        raise ValueError("source and gold IDs differ")

    with zipfile.ZipFile(T07) as t07, zipfile.ZipFile(FULL) as full:
        if t07.testzip() or full.testzip():
            raise ValueError("ZIP CRC check failed")
        raw = zip_jsonl(t07, "/06_raw_qwen_t07.predictions.jsonl")
        finetune = zip_jsonl(t07, "/07_finetune_t07.predictions.jsonl")
        official = zip_jsonl(t07, "/13_t07_official_intent_results.jsonl")
        compare_name = next(
            name for name in t07.namelist() if name.endswith("/17_t07_case_level_comparison.csv")
        )
        comparison = {
            row["record_id"]: row
            for row in csv.DictReader(io.StringIO(t07.read(compare_name).decode("utf-8-sig")))
        }
        inherited = {}
        for label, slug in {
            "goal_first": "goal_first_manager_v2",
            "degree": "degree_based_router_v2",
            "timid": "rich_conservative_manager_v2",
            "context_blind": "goal_first_context_blind_v2",
        }.items():
            inherited[label] = zip_jsonl(
                full, f"/T0.7/predictions/{slug}.predictions.jsonl"
            )

        all_tables = [raw, finetune, official, comparison, *inherited.values()]
        if any(set(table) != set(source) for table in all_tables):
            raise ValueError("case IDs differ between frozen inputs and output tables")

        out = RELEASE / "cases"
        if not args.check:
            out.mkdir(parents=True, exist_ok=True)
        expected_files = {f"{case_id}.json" for case_id in source}
        extras = {path.name for path in out.glob("*.json")} - expected_files
        if extras:
            raise ValueError(f"unexpected stale case files: {sorted(extras)[:3]}")
        for case_id in source:
            record = {
                "record_id": case_id,
                "frozen_source": source[case_id],
                "frozen_gold": gold[case_id],
                "t07_comparison": comparison[case_id],
                "t07_official_intent": official[case_id],
                "t07_predictions": {
                    "raw_qwen": raw[case_id],
                    "finetune": finetune[case_id],
                    **{key: table[case_id] for key, table in inherited.items()},
                },
                "provenance": {
                    "source_sha256": EXPECTED[PILOT / "source_canonical.jsonl"],
                    "gold_sha256": EXPECTED[PILOT / "pilot_120_final_gold.jsonl"],
                    "t07_final_zip_sha256": EXPECTED[T07],
                    "inherited_t07_zip_sha256": EXPECTED[FULL],
                    "note": "Goal-First, Degree, Timid, and Context-Blind predictions are inherited from the earlier T0.7 run; official intent and comparison come from the final T0.7 archive.",
                },
            }
            target = out / f"{case_id}.json"
            expected_text = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
            if args.check:
                if not target.is_file() or target.read_text(encoding="utf-8") != expected_text:
                    raise ValueError(f"case content differs from frozen inputs: {case_id}")
            else:
                target.write_text(expected_text, encoding="utf-8")

    index = ["# Pilot-120 case index", "", "120 frozen records; select a case to see its source, gold, and T0.7 outputs.", ""]
    index += [f"- [{case_id}](cases/{case_id}.json)" for case_id in source]
    index_path = RELEASE / "INDEX.md"
    index_text = "\n".join(index) + "\n"
    if args.check:
        if not index_path.is_file() or index_path.read_text(encoding="utf-8") != index_text:
            raise ValueError("case index differs from frozen ID set")
    else:
        index_path.write_text(index_text, encoding="utf-8")
    print(f"PILOT120_CASE_INDEX_OK cases={len(source)} mode={'check' if args.check else 'build'}")


if __name__ == "__main__":
    main()
