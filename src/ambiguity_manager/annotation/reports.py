"""Report builders for T13 annotation programme."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ambiguity_manager.annotation.canonical import sha256_hex
from ambiguity_manager.annotation.contamination import find_source_overlaps
from ambiguity_manager.annotation.coverage import summarise_coverage
from ambiguity_manager.annotation.duplicates import find_duplicates


def build_quality_report(
  records: list[dict[str, Any]],
  *,
  root: Path | None = None,
) -> dict[str, Any]:
  duplicates = find_duplicates(records)
  overlaps = find_source_overlaps(records, root=root)
  coverage = summarise_coverage(records)
  exclusions = []
  for kind, clusters in duplicates.items():
    for cluster in clusters:
      exclusions.append({"reason": f"duplicate_{kind}", "record_ids": cluster})
  for overlap in overlaps:
    exclusions.append(
      {
        "reason": "source_command_overlap",
        "record_id": overlap["record_id"],
        "source_hits": overlap["source_hits"],
      }
    )
  return {
    "n_records": len(records),
    "duplicates": duplicates,
    "contamination_overlaps": overlaps,
    "coverage": coverage,
    "exclusion_report": exclusions,
    "contains_gold_labels": False,
  }


def write_json_report(path: Path, payload: dict[str, Any], *, overwrite: bool = True) -> str:
  path.parent.mkdir(parents=True, exist_ok=True)
  if path.exists() and not overwrite:
    raise FileExistsError(f"refusing to overwrite report: {path}")
  text = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
  path.write_text(text, encoding="utf-8")
  return sha256_hex(text.encode("utf-8"))
