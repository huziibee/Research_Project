"""Guards for Pilot-120 local-systems evaluation artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ambiguity_manager.evaluation import pilot_120 as p120

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "pilot_120" / "local_systems"
PREDICTIONS = OUT / "predictions"
SYSTEMS = ("always_execute", "always_clarify", "always_silently_resolve")


@pytest.fixture(scope="module")
def expected_ids() -> list[str]:
    return p120.expected_record_ids()


def test_frozen_hashes_still_match_manifest():
    manifest = p120.load_json(
        ROOT / "data" / "annotations" / "pilot_120_v1" / "frozen" / "FROZEN_MANIFEST.json"
    )
    checks = {
        "source_canonical_jsonl": ROOT
        / "data"
        / "annotations"
        / "pilot_120_v1"
        / "source_canonical.jsonl",
        "final_gold_jsonl": ROOT
        / "data"
        / "annotations"
        / "pilot_120_v1"
        / "pilot_120_final_gold.jsonl",
        "gold_policy": ROOT / "data" / "annotations" / "pilot_120_v1" / "GOLD_POLICY.json",
        "config_pilot_120_v1": ROOT / "configs" / "evaluation" / "pilot_120_v1.json",
    }
    for key, path in checks.items():
        assert p120.sha256_file(path) == manifest["hashes"][key]
    assert manifest["evaluation_only"] is True
    assert manifest["n_records"] == 120


@pytest.mark.parametrize("system_id", SYSTEMS)
def test_local_prediction_contract(system_id: str, expected_ids: list[str]):
    path = PREDICTIONS / f"{system_id}.predictions.jsonl"
    if not path.exists():
        pytest.skip("local prediction artifact not generated yet")
    rows = p120.load_jsonl(path)
    ids = [str(r["record_id"]) for r in rows]
    assert len(rows) == 120
    assert len(set(ids)) == 120
    assert ids == expected_ids
    for row in rows:
        assert row["system_id"] == system_id
        assert row.get("terminal_strategy")
        assert row.get("supports_ambiguity_prediction") is False
        assert row.get("supports_capability_prediction") is False
        assert row.get("ambiguity_types") is None
        assert row.get("capability_status") is None
        assert "tokens" not in row or row["tokens"] is not None


@pytest.mark.parametrize("system_id", SYSTEMS)
def test_local_eval_scores_full_denominator(system_id: str):
    path = OUT / "evaluations" / f"{system_id}.eval.json"
    if not path.exists():
        pytest.skip("local eval artifact not generated yet")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["n_gold"] == 120
    assert report["operational"]["denominator"] == 120
    assert 0.0 <= report["terminal_strategy"]["accuracy"] <= 1.0


def test_cluster_handoff_exists_and_excludes_unselected_t28():
    path = ROOT / "outputs" / "pilot_120" / "cluster_systems_pending.json"
    if not path.exists():
        pytest.skip("cluster handoff not generated yet")
    handoff = json.loads(path.read_text(encoding="utf-8"))
    deferred = {s["system_id"] for s in handoff["deferred_systems"]}
    assert "degree_based_router" in deferred
    assert "full_type_risk_aware_manager" in deferred
    excluded = {s["system_id"] for s in handoff["explicitly_excluded_until_ready"]}
    assert "t28_full_type_risk_aware_manager_qlora_r5_retry5" in excluded


def test_training_loader_still_blocked():
    with pytest.raises(p120.Pilot120Error):
        p120.assert_evaluation_only("train on pilot_120")
