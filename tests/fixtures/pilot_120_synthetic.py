"""Shared synthetic Pilot-120 helpers for tests (never official gold)."""

from __future__ import annotations

import json
from pathlib import Path

from ambiguity_manager.annotation.final_protocol_v7 import PILOT_120_N, write_jsonl


def build_synthetic_pilot_120_tree(tmp_root: Path) -> Path:
  """Build a temporary Pilot-120 tree with synthetic labels (not official repo gold)."""
  art = tmp_root / "data" / "annotations" / "pilot_120_v1"
  art.mkdir(parents=True)
  (tmp_root / "configs" / "annotation").mkdir(parents=True)
  (tmp_root / "configs" / "evaluation").mkdir(parents=True)

  from ambiguity_manager.paths import ProjectPaths

  repo = ProjectPaths.from_repo_root().root
  for rel in (
    "configs/annotation/final_protocol_v7.json",
    "configs/evaluation/pilot_120_v1.json",
    "configs/annotation/annotation_roles_v1.json",
  ):
    src = repo / rel
    dst = tmp_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

  roles = json.loads((tmp_root / "configs/annotation/annotation_roles_v1.json").read_text(encoding="utf-8"))
  roles["roles"]["ADJ-01"]["status"] = "synthetic_test_only"
  roles["roles"]["ADJ-01"]["person_name"] = "SYN-ADJ"
  (tmp_root / "configs/annotation/annotation_roles_v1.json").write_text(
    json.dumps(roles, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
  )

  sources = []
  submissions_a = []
  submissions_b = []
  for i in range(PILOT_120_N):
    rid = f"pilot120:syn:{i:04d}"
    cap = (
      "Robot arm can reach table; gripper able to lift 500g; navigation permitted indoors."
      if i % 5
      else "Robot can grasp cups; unable to heat liquids; payload limit 400g."
    )
    sources.append(
      {
        "record_id": rid,
        "command": f"Please fetch item {i}",
        "scene_context": "Indoor lab",
        "dialogue_history": [],
        "capability_context": cap,
        "schema_version": "2.0.0",
        "group_id": f"g-{i // 10}",
        "capability_evidence_class": "A" if i % 5 else "B",
        "one_path_determinacy": True,
      }
    )
    base = {
      "record_id": rid,
      "speech_act": "directive_command",
      "terminal_strategy": "clarify" if i % 11 == 0 else "execute",
      "recommended_strategy": "clarify" if i % 11 == 0 else "execute",
      "ambiguity_types": ["referential"] if i % 3 else ["pragmatic", "spatial"],
      "capability_status": "capable",
      "capability_interpretation": "within_limits",
      "risk_level": "low",
      "ambiguity_present": True,
      "confidence": "high",
      "cpc": {},
    }
    submissions_a.append(dict(base, annotator_role="ANN-A"))
    b = dict(base, annotator_role="ANN-B")
    if i in {2, 7, 19}:
      b["terminal_strategy"] = "clarify"
      b["recommended_strategy"] = "clarify"
    submissions_b.append(b)

  write_jsonl(art / "source_canonical.jsonl", sources)
  (art / "annotations_raw").mkdir(parents=True, exist_ok=True)
  (art / "adjudication").mkdir(parents=True, exist_ok=True)
  (art / "blind_packages").mkdir(parents=True, exist_ok=True)
  (art / "reports").mkdir(parents=True, exist_ok=True)
  write_jsonl(art / "annotations_raw" / "ANN-A.jsonl", submissions_a)
  write_jsonl(art / "annotations_raw" / "ANN-B.jsonl", submissions_b)
  return tmp_root
