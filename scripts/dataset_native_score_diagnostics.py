#!/usr/bin/env python3
"""Additive dataset-native scoring diagnostics.

These helpers never change a primary exact-match score, prompt, or source
label. They exist so majority-class, duplicate-input, and interval artefacts
cannot hide inside a headline rate.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


def wilson(k: int, n: int, z: float = 1.959963984540054) -> list[float] | None:
    if n <= 0:
        return None
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / den
    return [max(0.0, centre - half), min(1.0, centre + half)]


def proportion(k: int, n: int) -> dict[str, Any]:
    return {"correct": k, "n": n, "rate": (k / n) if n else None, "wilson95": wilson(k, n)}


def modal_joint_baseline(labels: Iterable[Any]) -> dict[str, Any]:
    encoded = [json.dumps(label, sort_keys=True, ensure_ascii=False) for label in labels]
    if not encoded:
        raise ValueError("modal_baseline_empty")
    counts = Counter(encoded)
    modal, count = counts.most_common(1)[0]
    n = len(encoded)
    return {
        "modal_label_json": modal,
        "modal_count": count,
        "n": n,
        "rate": count / n,
        "wilson95": wilson(count, n),
        "distinct_labels": len(counts),
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def unique_input_sensitivity(
    scored_rows: list[dict[str, Any]],
    ledger_rows: list[dict[str, Any]],
    *,
    record_id_field: str = "record_id",
    correct_field: str = "correct",
    condition: str | None = None,
) -> dict[str, Any]:
    """Collapse exact-input groups using the frozen ledger, never post-hoc exclusion."""
    by_id: dict[str, list[dict[str, Any]]] = {}
    for row in scored_rows:
        if condition is not None and row.get("condition") != condition:
            continue
        by_id.setdefault(str(row[record_id_field]), []).append(row)
    included = 0
    correct = 0
    excluded_inconsistent_groups = 0
    missing_groups = 0
    representatives: list[str] = []
    for group in ledger_rows:
        ids = [str(record_id) for record_id in group["record_ids"]]
        if group.get("source_target_consistency") != "CONSISTENT":
            excluded_inconsistent_groups += 1
            continue
        representative = sorted(ids)[0]
        rows = by_id.get(representative)
        if not rows:
            missing_groups += 1
            continue
        representatives.append(representative)
        for row in rows:
            included += 1
            correct += int(bool(row[correct_field]))
    return {
        "claim_boundary": "sensitivity only; primary result remains row-weighted",
        "ledger_groups": len(ledger_rows),
        "excluded_inconsistent_groups": excluded_inconsistent_groups,
        "missing_representative_groups": missing_groups,
        "representative_record_ids": len(representatives),
        "scored_rows": included,
        "correct": correct,
        "rate": (correct / included) if included else None,
        "wilson95": wilson(correct, included) if included else None,
    }
