from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import pilot120_t45_historical_reconciliation as t45


ROOT = Path(__file__).resolve().parents[1]


def test_t45_sha256_streams_without_read_bytes(monkeypatch) -> None:
    path = ROOT / "scripts/pilot120_t45_historical_reconciliation.py"
    expected = hashlib.sha256(path.read_bytes()).hexdigest()

    def forbidden_read_bytes(_self):
        raise AssertionError("T45 provenance hashing must stream")

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    assert t45._sha256(path) == expected


def test_t45_base_adapter_disagreement_preserves_all_field_level_differences() -> None:
    ids = ["CA-1", "CA-2"]
    shared = {
        "schema_valid": True,
        "failed": False,
        "error": None,
        "raw_output": "{}",
    }
    matrix = {
        "direct_base_llm": {
            "CA-1": {**shared, "terminal_strategy": "execute", "ambiguity_types": ["scheduling"], "capability_status": "capable"},
            "CA-2": {**shared, "terminal_strategy": "clarify", "ambiguity_types": ["object_reference"], "capability_status": "capable"},
        },
        "t28_selected_adapter_llm": {
            "CA-1": {**shared, "raw_output": '{"different": true}', "terminal_strategy": "execute", "ambiguity_types": ["scheduling"], "capability_status": "capable"},
            "CA-2": {**shared, "terminal_strategy": "execute", "ambiguity_types": ["object_reference", "scheduling"], "capability_status": "conditionally_capable"},
        },
    }
    report = t45._base_adapter_disagreements(ids, matrix)
    assert report["n_core_prediction_signature_disagreements"] == 1
    assert report["n_raw_output_hash_disagreements"] == 1
    assert report["core_prediction_disagreement_rows"][0]["record_id"] == "CA-2"
    assert report["core_prediction_disagreement_rows"][0]["terminal_strategy_disagrees"] is True
    assert report["core_prediction_disagreement_rows"][0]["ambiguity_types_disagree"] is True
    assert report["core_prediction_disagreement_rows"][0]["capability_status_disagrees"] is True


def test_t45_reconciliation_reports_not_computed_when_historical_policy_bytes_do_not_match(monkeypatch) -> None:
    source, gold, manifest, frozen_paths = t45._frozen_inputs(ROOT)
    policy = ROOT / "configs/evaluation/pilot120_early_analysis_policy_v1.json"
    t31_path = ROOT / "data/annotations/pilot_120_v1/STATUS.json"
    run_manifest = ROOT / "data/annotations/pilot_120_v1/SOURCE_PROVENANCE.json"
    t31 = {
        "status": "T31_EARLY_COST_SENSITIVE_EVALUATION_COMPLETE",
        "scope": "non_protected_pilot120_early_analysis_only",
        "valid_for_official_use": False,
        "policy_sha256": "0" * 64,
        "prediction_sha256": {},
        "systems": {},
    }
    historical = {"freeze": {"source_sha256": manifest["hashes"]["source_canonical_jsonl"], "gold_sha256": manifest["hashes"]["final_gold_jsonl"], "n": 120}}
    original_load_json = t45._load_json

    def fake_load_json(path: Path):
        if path.resolve() == t31_path.resolve():
            return t31
        if path.resolve() == run_manifest.resolve():
            return historical
        return original_load_json(path)

    monkeypatch.setattr(t45, "_load_json", fake_load_json)
    original_sha256 = t45._sha256

    def fake_sha256(path: Path) -> str:
        if path.resolve() == t31_path.resolve():
            return "a" * 64
        if path.resolve() == run_manifest.resolve():
            return "b" * 64
        return original_sha256(path)

    monkeypatch.setattr(t45, "_sha256", fake_sha256)
    result = t45._reconciliation(
        source=source,
        gold=gold,
        manifest=manifest,
        frozen_paths=frozen_paths,
        policy_path=policy,
        t31_path=t31_path,
        run_manifest_path=run_manifest,
        predictions={},
    )
    assert result["status"] == "NOT_COMPUTED"
    assert "t31_policy_bytes_do_not_match_local_policy" in result["reconciliation"]["problems"]
