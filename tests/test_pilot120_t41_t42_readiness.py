from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import pilot120_t41_interpretation_readiness as t41
from scripts import pilot120_t42_single_ambiguity_readiness as t42


ROOT = Path(__file__).resolve().parents[1]
T41_CONTRACT = ROOT / "configs/evaluation/t41_interpretation_sidecar_contract_v1.json"
T42_SCAFFOLD = ROOT / "configs/evaluation/t42_single_ambiguity_study_scaffold_v1.json"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _span() -> dict[str, object]:
    return {"input_part": "command", "start": 0, "end": 4, "text_sha256": _sha256("move")}


def _gold() -> dict[str, object]:
    response_target = {
        "required": True,
        "targets": ["destination"],
        "wording_criteria": {"must_convey": ["ask destination"], "must_not_convey": [], "acceptable_paraphrase": True},
    }
    resolution = {"permitted": False, "values": {}, "evidence_spans": [_span()], "safety_rationale": "insufficient evidence"}
    return {
        "intent": {"label": "move", "evidence_spans": [_span()]},
        "cpc": {"slots": {"action": "move"}, "critical_slots": ["action"], "evidence_spans": [_span()]},
        "candidate_set": [],
        "resolution": resolution,
        "clarification": response_target,
        "rejection": {**response_target, "required": False, "targets": []},
        "silent_resolution": resolution,
    }


def test_t41_contract_is_a_non_result_readiness_contract() -> None:
    contract = json.loads(T41_CONTRACT.read_text(encoding="utf-8"))
    assert t41.validate_contract(contract) == []
    assert contract["current_state"]["annotations_present"] is False
    assert contract["current_state"]["all_interpretation_claims"] == "NOT_COMPUTED"


def test_t41_study_validator_requires_distinct_blind_reviews_and_all_fields() -> None:
    contract = json.loads(T41_CONTRACT.read_text(encoding="utf-8"))
    sidecar = [
        {
            "record_id": "t41-001",
            "source_study_id": "t41-new-source",
            "study_split": "development",
            "source_lineage_id": "source-lineage-1",
            "scenario_family_id": "family-1",
            "source_fingerprint_sha256": _sha256("source"),
            "input_fingerprint_sha256": _sha256("input"),
            "annotation_status": "adjudicated",
            "gold": _gold(),
        }
    ]
    review = {
        "record_id": "t41-001",
        "reviewer_pseudonym": "reviewer-A",
        "blinding": {"blind_to_system_identity": True, "blind_to_system_prediction": True, "blind_to_other_reviewer_labels": True},
        "schema_version": "1.0.0",
        "labels": _gold(),
    }
    review_a = [{**review, "review_assignment_id": "assignment-A"}]
    review_b = [{**review, "reviewer_pseudonym": "reviewer-B", "review_assignment_id": "assignment-B"}]
    adjudication = [{"record_id": "t41-001", "review_assignment_ids": ["assignment-A", "assignment-B"], "field_agreement": {field: "agree" for field in t41.REQUIRED_GOLD_FIELDS}, "adjudicated_gold": _gold(), "adjudicator_pseudonym": "adjudicator", "decision_rationale": "agreement"}]
    assert t41.validate_study(contract, sidecar, review_a, review_b, adjudication) == []

    invalid = t41.validate_study(contract, sidecar, review_a, review_a, adjudication)
    assert "adjudication:1:review_pair_invalid" in invalid


def test_t41_validator_rejects_review_visibility_of_system_outputs() -> None:
    contract = json.loads(T41_CONTRACT.read_text(encoding="utf-8"))
    sidecar = [{"record_id": "r", "source_study_id": "new", "study_split": "development", "source_lineage_id": "lineage", "scenario_family_id": "family", "source_fingerprint_sha256": _sha256("s"), "input_fingerprint_sha256": _sha256("i"), "annotation_status": "adjudicated", "gold": _gold()}]
    review = {"record_id": "r", "review_assignment_id": "A", "reviewer_pseudonym": "a", "blinding": {"blind_to_system_identity": True, "blind_to_system_prediction": True, "blind_to_other_reviewer_labels": True}, "schema_version": "1.0.0", "labels": _gold(), "raw_output": "must not be visible"}
    review_b = {**review, "review_assignment_id": "B", "reviewer_pseudonym": "b"}
    adjudication = [{"record_id": "r", "review_assignment_ids": ["A", "B"], "field_agreement": {field: "agree" for field in t41.REQUIRED_GOLD_FIELDS}, "adjudicated_gold": _gold(), "adjudicator_pseudonym": "adjudicator", "decision_rationale": "x"}]
    errors = t41.validate_study(contract, sidecar, [review], [review_b], adjudication)
    assert "review_A:1:system_visibility_forbidden" in errors
    assert "review_B:1:system_visibility_forbidden" in errors


def _t42_record() -> dict[str, object]:
    return {
        "record_id": "t42-001",
        "source_record_id": "source-001",
        "source_corpus_id": "licensed-new-corpus",
        "source_license_id": "license-record-001",
        "source_lineage_id": "lineage-001",
        "scenario_family_id": "family-001",
        "source_fingerprint_sha256": _sha256("source-001"),
        "input_fingerprint_sha256": _sha256("input-001"),
        "annotation_status": "adjudicated",
        "unresolved_ambiguity_instances": [{"ambiguity_instance_id": "a1", "ambiguity_type": "object_reference", "resolution_status": "unresolved", "evidence_spans": ["it"]}],
        "secondary_ambiguity_instances": [],
        "eligibility_assertions": {"exactly_one_unresolved_ambiguity": True, "exactly_one_ambiguity_type": True, "no_secondary_ambiguity": True},
        "adjudication": {"status": "adjudicated", "blind_review_assignment_ids": ["blind-A", "blind-B"]},
    }


def test_t42_scaffold_stays_unfrozen_until_new_source_material_exists() -> None:
    scaffold = json.loads(T42_SCAFFOLD.read_text(encoding="utf-8"))
    assert t42.validate_scaffold(scaffold) == []
    assert scaffold["current_state"]["frozen_manifest"] == "NOT_COMPUTED"


def test_t42_record_validator_proves_exactly_one_unresolved_type_and_no_secondary() -> None:
    assert t42.validate_record(_t42_record()) == []
    invalid = _t42_record()
    invalid["unresolved_ambiguity_instances"] = [
        {"ambiguity_instance_id": "a1", "ambiguity_type": "object_reference", "resolution_status": "unresolved", "evidence_spans": ["it"]},
        {"ambiguity_instance_id": "a2", "ambiguity_type": "temporal", "resolution_status": "unresolved", "evidence_spans": ["later"]},
    ]
    invalid["secondary_ambiguity_instances"] = [{"ambiguity_type": "temporal"}]
    errors = t42.validate_record(invalid)
    assert "unresolved_ambiguity_instances_must_have_exactly_one" in errors
    assert "secondary_ambiguity_present" in errors


def test_t42_freeze_validator_requires_all_three_family_disjoint_ledgers() -> None:
    scaffold = json.loads(T42_SCAFFOLD.read_text(encoding="utf-8"))
    record = _t42_record()
    # The validator hashes supplied future files.  Static contract files are
    # sufficient stand-ins here, so this unit test has no filesystem writes.
    records_path = T42_SCAFFOLD
    ledger = {
        "record_id": record["record_id"],
        "source_lineage_id": record["source_lineage_id"],
        "scenario_family_id": record["scenario_family_id"],
        "input_fingerprint_sha256": record["input_fingerprint_sha256"],
        "comparators": {"pilot_120_v1": "no_overlap", "t41_interpretation_sidecar": "no_overlap", "t44_independent_confirmation": "no_overlap"},
    }
    ledger_path = T41_CONTRACT
    manifest = {
        "status": "T42_STUDY_FROZEN_MANIFEST",
        "freeze_id": "t42-freeze",
        "records_sha256": t42._sha256(records_path),
        "record_ids": ["t42-001"],
        "source_audit_sha256": "a" * 64,
        "exclusion_ledger_sha256": t42._sha256(ledger_path),
        "protocol_sha256": "b" * 64,
        "fixed_inference_configuration_sha256": "c" * 64,
        "eligibility_validation_status": "T42_SINGLE_AMBIGUITY_ELIGIBILITY_PASSED",
    }
    assert t42.validate_freeze(scaffold, [record], [ledger], manifest, records_path, ledger_path) == []
    ledger["comparators"]["t44_independent_confirmation"] = "unresolved"
    errors = t42.validate_freeze(scaffold, [record], [ledger], manifest, records_path, ledger_path)
    assert "ledger:t42-001:comparison_not_proven" in errors
