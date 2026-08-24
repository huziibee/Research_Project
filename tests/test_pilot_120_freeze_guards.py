"""Hard guards for Pilot-120 v1 evaluation-only freeze path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ambiguity_manager.evaluation import pilot_120 as p120

ROOT = Path(__file__).resolve().parents[1]


def test_preflight_passes_and_capability_distribution():
    report = p120.run_preflight()
    assert report["status"] == "preflight_pass"
    assert report["n_records"] == 120
    assert report["capability_counts"] == {"A": 99, "B": 21, "C": 0, "D": 0}
    assert report["one_path_true"] == 120
    assert report["failed_gates"] == []


def test_canonical_source_unique_ordered_hashed():
    paths = p120.default_paths()
    ids = p120.expected_record_ids(paths)
    rows = p120.load_jsonl(paths["canonical_jsonl"])
    assert [r["record_id"] for r in rows] == ids
    assert len(set(ids)) == 120
    sha1 = p120.sha256_file(paths["canonical_jsonl"])
    again = p120.materialize_canonical_source(paths)
    assert again["source_canonical_jsonl_sha256"] == sha1


def test_no_train_dev_leakage_gate():
    report = p120.run_preflight()
    gate = next(g for g in report["gates"] if g["name"] == "no_t28_train_dev_leakage")
    assert gate["ok"] is True


def test_blind_inputs_have_no_historical_or_private_labels():
    paths = p120.default_paths()
    for path in paths["inputs"].glob("CA-*.json"):
        obj = json.loads(path.read_text(encoding="utf-8"))
        assert not (set(obj) & p120.FORBIDDEN_VIEW_KEYS)


def test_evaluation_only_guard_blocks_training_purposes():
    p120.assert_evaluation_only("evaluate")
    with pytest.raises(p120.Pilot120Error):
        p120.assert_evaluation_only("train qlora adapter")
    with pytest.raises(p120.Pilot120Error):
        p120.assert_evaluation_only("model_selection on pilot")


def test_gold_policy_uses_pilot_adjudicated_gold():
    policy = p120.load_gold_policy()
    assert policy["decision"] == "use_existing_pilot_adjudicated_gold"
    assert policy["steve_ben_reannotation_required"] is False
    assert p120.uses_pilot_adjudicated_gold() is True


def test_pilot_adjudicated_gold_complete():
    check = p120.verify_pilot_adjudicated_gold()
    assert check["ok"] is True
    assert check["n"] == 120
    assert check["human_gate_required"] == []


def test_freeze_succeeds_under_pilot_gold_policy():
    # Idempotent: clear prior freeze if present with different claim
    freeze_dir = p120.default_paths()["freeze_dir"]
    manifest = freeze_dir / "FROZEN_MANIFEST.json"
    if manifest.exists():
        manifest.unlink()
    result = p120.freeze()
    assert result["n_records"] == 120
    assert result["evaluation_only"] is True
    assert "PILOT-ADJUDICATED GOLD" in result["claim"]
    assert "Steven James" not in result["claim"]
    assert result["agreement_label"] == "pilot_annotation_agreement"
    assert result["compare_to_pilot"]["n_changed"] == 0
    assert result["compare_to_pilot"]["n_unchanged"] == 120
    assert (ROOT / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl").exists()


def test_status_allows_freeze_claim_after_freeze():
    status = p120.write_status()
    assert status["claim_allowed"] is True
    assert status["steve_ben_reannotation_required"] is False
    assert status["agreement_used_for_freeze"] == "pilot_annotation_agreement"
    assert "PILOT-ADJUDICATED GOLD" in status["claim"]


def test_agreement_file_remains_not_started_without_steve_ben_submissions():
    # Final-protocol Steve/Ben agreement is intentionally unused under this policy
    report = p120.compute_final_protocol_agreement()
    assert report["status"] == "not_started"
    assert report["n_complete_pairs"] == 0
    assert report["label"] == "final_protocol_annotation_agreement"


def test_config_points_at_evaluation_only_paths():
    cfg = json.loads(
        (ROOT / "configs" / "evaluation" / "pilot_120_v1.json").read_text(encoding="utf-8")
    )
    assert cfg["role"] == "evaluation_only"
    assert cfg["must_not_use_for_training_or_model_selection"] is True
    assert cfg["n_records"] == 120
    assert cfg["gold_policy_decision"] == "use_existing_pilot_adjudicated_gold"
    assert cfg["gold_jsonl"] == "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl"
