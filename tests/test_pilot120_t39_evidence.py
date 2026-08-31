from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scripts import pilot120_t39_evidence as t39
from scripts.pilot120_t39_evidence import _evidence_payload, _metric_eligibility, _route_code, _route_code_second_pass, _strata


ROOT = Path(__file__).resolve().parents[1]


def test_route_double_code_covers_all_terminal_pairs() -> None:
    terminals = ("execute", "clarify", "face_preserving_rejection")
    for gold in terminals:
        for predicted in terminals:
            assert _route_code(gold, predicted) == _route_code_second_pass(gold, predicted)


def test_structural_strata_marks_thin_types_and_pairs_count_only() -> None:
    source = [
        {"record_id": "r1", "dialogue_history": [], "scene_context": "s", "capability_context": "c"},
        {"record_id": "r2", "dialogue_history": ["d"], "scene_context": "s", "capability_context": "c"},
    ]
    gold = {
        "r1": {"ambiguity_types": ["object_reference", "temporal_reference"], "terminal_strategy": "execute", "capability_status": "capable", "gold_status": "auto_agree"},
        "r2": {"ambiguity_types": ["object_reference", "temporal_reference"], "terminal_strategy": "clarify", "capability_status": "capable", "gold_status": "auto_agree"},
    }
    index = {(row["family"], row["label"]): row for row in _strata(source, gold)}
    assert index[("compound_depth", "depth_2")]["n"] == 2
    assert index[("dialogue_presence", "dialogue_present")]["n"] == 1
    assert index[("ambiguity_type", "object_reference")]["count_only"] is True
    assert index[("ambiguity_pair", "object_reference+temporal_reference")]["count_only"] is True


def test_interpretation_gold_is_missing_required_fields() -> None:
    rows = [json.loads(line) for line in (ROOT / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl").read_text(encoding="utf-8").splitlines() if line]
    fields = {key for row in rows for key in row}
    assert "intent" not in fields
    assert "cpc" not in fields
    assert "candidate_set" not in fields


def test_evidence_payload_scores_all_five_systems_from_frozen_predictions(monkeypatch) -> None:
    gold = [json.loads(line) for line in (ROOT / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl").read_text(encoding="utf-8").splitlines() if line]
    by_id = {
        row["record_id"]: {
            "record_id": row["record_id"],
            "terminal_strategy": row["terminal_strategy"],
            "ambiguity_types": row["ambiguity_types"],
            "capability_status": row["capability_status"],
            "schema_valid": True,
            "failed": False,
            "error": None,
            "latency_ms": 1.0,
            "raw_output": "{}",
        }
        for row in gold
    }
    expected_record_ids = [row["record_id"] for row in gold]

    def fake_load_prediction(_path, *, system_id, expected_ids):
        assert expected_ids == expected_record_ids
        return {record_id: {**row, "system_id": system_id} for record_id, row in by_id.items()}

    monkeypatch.setattr(t39, "_load_prediction", fake_load_prediction)
    predictions = []
    for system_id in (
        "direct_base_llm",
        "t28_selected_adapter_llm",
        "degree_based_router",
        "full_type_risk_aware_manager",
        "context_blind_manager",
    ):
        predictions.append((system_id, ROOT / "configs/evaluation/pilot_120_v1.json"))
    payload = _evidence_payload(
        root=ROOT,
        policy_path=ROOT / "configs/evaluation/pilot120_early_analysis_policy_v1.json",
        analysis_policy_path=ROOT / "configs/evaluation/pilot120_t39_evidence_policy_v1.json",
        prediction_args=predictions,
        allow_missing=False,
    )
    assert payload["status"] == "T39_EVIDENCE_ATLAS_COMPLETE"
    assert payload["systems"]["direct_base_llm"]["terminal_strategy"]["accuracy"] == 1.0
    assert payload["context_ablation"]["status"] == "DESCRIPTIVE_ALL_CONTEXT_ABLATION_ONLY"


def test_metric_eligibility_never_treats_missing_saved_fields_as_wrong_labels() -> None:
    rows = {
        "r1": {"terminal_strategy": "execute", "ambiguity_types": ["object_reference"], "capability_status": "capable", "latency_ms": 1.0},
        "r2": {"terminal_strategy": "clarify", "capability_status": "capable", "latency_ms": "unknown"},
    }
    eligibility = _metric_eligibility(["r1", "r2"], rows)
    assert eligibility["terminal_strategy"]["status"] == "ELIGIBLE"
    assert eligibility["ambiguity_types"]["status"] == "NOT_COMPUTED"
    assert eligibility["capability_status"]["status"] == "ELIGIBLE"
    assert eligibility["latency_ms"]["status"] == "NOT_COMPUTED"


def test_reproducibility_drift_names_changed_records_and_runtime(monkeypatch) -> None:
    reference_prediction = ROOT / "reference.jsonl"
    changed_prediction = ROOT / "changed.jsonl"
    evidences = {}
    evidence_paths = []
    for replicate in ("R1", "R2", "R3", "R4", "R5"):
        evidence_path = ROOT / f"{replicate}.json"
        prediction = changed_prediction if replicate == "R2" else reference_prediction
        evidences[str(evidence_path)] = {
            "status": "T39_EVIDENCE_ATLAS_COMPLETE",
            "prediction_sha256": {"direct_base_llm": "changed" if replicate == "R2" else "reference"},
            "prediction_paths": {"direct_base_llm": str(prediction)},
            "runtime_provenance": {"status": "COMPLETE", "records": {"direct_base_llm": [{"slurm": {"job_id": replicate}}]}},
        }
        evidence_paths.append((replicate, evidence_path))
    predictions = {
        str(reference_prediction): [{"record_id": "r1", "terminal_strategy": "execute", "ambiguity_types": ["object_reference"], "capability_status": "capable", "schema_valid": True, "failed": False, "raw_output": "a"}],
        str(changed_prediction): [{"record_id": "r1", "terminal_strategy": "clarify", "ambiguity_types": ["object_reference"], "capability_status": "capable", "schema_valid": True, "failed": False, "raw_output": "b"}],
    }
    captured = {}
    monkeypatch.setattr(t39, "_load_json", lambda path: evidences[str(path)])
    monkeypatch.setattr(t39.p120, "load_jsonl", lambda path: predictions[str(path)])
    monkeypatch.setattr(t39, "_write_json", lambda _path, payload: captured.update(payload))
    t39.run_reproducibility(SimpleNamespace(replica_evidence=evidence_paths, output=ROOT / "audit.json"))
    audit = captured
    assert audit["status"] == "VERIFY_FAILED"
    changed = audit["drift_report"]["per_replica"]["R2"]["direct_base_llm"]["changed_records"]
    assert changed == [{"record_id": "r1", "changed_fields": ["raw_output_sha256", "terminal_strategy"]}]
    assert audit["drift_report"]["runtime_conditions"]["R2"]["status"] == "COMPLETE"
