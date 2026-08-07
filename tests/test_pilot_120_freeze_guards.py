"""Additional Pilot-120 freeze / leakage / determinism tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ambiguity_manager.annotation.final_protocol_v7 import file_sha256, write_json, write_jsonl
from ambiguity_manager.evaluation.pilot_120 import (
  Pilot120FreezeError,
  compute_hashes,
  freeze_pilot_120_v1,
  write_eval_handoff,
)
from ambiguity_manager.paths import ProjectPaths
from tests.fixtures.pilot_120_synthetic import build_synthetic_pilot_120_tree


def test_eval_handoff_excludes_pilot_private_inputs(tmp_path: Path) -> None:
  root = build_synthetic_pilot_120_tree(tmp_path)
  # Minimal frozen-like hashes file for handoff writer
  p = root / "data/annotations/pilot_120_v1"
  write_json(
    p / "hashes.json",
    {
      "final_gold": "a" * 64,
      "manifest": "b" * 64,
      "eval_config": file_sha256(root / "configs/evaluation/pilot_120_v1.json"),
      "final_protocol_config": file_sha256(root / "configs/annotation/final_protocol_v7.json"),
    },
  )
  write_jsonl(p / "final_gold.jsonl", [{"record_id": "x"}])
  path = write_eval_handoff(root=root)
  handoff = json.loads(path.read_text(encoding="utf-8"))
  assert handoff["evaluation_only"] is True
  assert handoff["forbid_training_load"] is True
  excluded = " ".join(handoff["excluded_inputs"]).lower()
  assert "pilot" in excluded
  assert "private" in excluded
  assert "adjudication rationale" in excluded
  assert "python3 -m ambiguity_manager.evaluation.pilot_120_cli evaluate" in handoff["command"]


def test_leakage_blocks_freeze(tmp_path: Path) -> None:
  root = build_synthetic_pilot_120_tree(tmp_path)
  # Plant overlapping train id
  splits = root / "data/development/source_splits_v1"
  splits.mkdir(parents=True)
  write_jsonl(
    splits / "record_manifest.jsonl",
    [{"record_id": "pilot120:syn:0001", "split": "train"}],
  )
  # Prepare adjudication for disagreements
  from ambiguity_manager.evaluation.pilot_120 import run_agreement_and_queue

  run_agreement_and_queue(root=root)
  disag = root / "data/annotations/pilot_120_v1/adjudication/disagreements.jsonl"
  a_by = {
    json.loads(line)["record_id"]: json.loads(line)
    for line in (root / "data/annotations/pilot_120_v1/annotations_raw/ANN-A.jsonl").read_text().splitlines()
    if line.strip()
  }
  b_by = {
    json.loads(line)["record_id"]: json.loads(line)
    for line in (root / "data/annotations/pilot_120_v1/annotations_raw/ANN-B.jsonl").read_text().splitlines()
    if line.strip()
  }
  decisions = []
  for line in disag.read_text().splitlines():
    item = json.loads(line)
    rid = item["record_id"]
    decisions.append(
      {
        "record_id": rid,
        "status": "resolved",
        "adjudicator_role": "SYN-ADJ",
        "adjudication_decision": {
          "speech_act": a_by[rid]["speech_act"],
          "terminal_strategy": "clarify",
          "recommended_strategy": "clarify",
          "ambiguity_types": a_by[rid]["ambiguity_types"],
          "capability_status": a_by[rid]["capability_status"],
          "capability_interpretation": a_by[rid]["capability_interpretation"],
          "risk_level": a_by[rid]["risk_level"],
        },
        "ANN-A_original": a_by[rid],
        "ANN-B_original": b_by[rid],
        "retains_originals": True,
      }
    )
  write_jsonl(root / "data/annotations/pilot_120_v1/adjudication/decisions.jsonl", decisions)
  with pytest.raises(Pilot120FreezeError, match="train/dev leakage"):
    freeze_pilot_120_v1(root=root)


def test_compute_hashes_deterministic_for_protocol_configs() -> None:
  root = ProjectPaths.from_repo_root().root
  h1 = compute_hashes(root)
  h2 = compute_hashes(root)
  assert h1.get("final_protocol_config") == h2.get("final_protocol_config")
  assert h1.get("eval_config") == h2.get("eval_config")
  assert len(h1["final_protocol_config"]) == 64
