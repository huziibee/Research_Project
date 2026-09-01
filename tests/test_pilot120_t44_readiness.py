from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import pilot120_t44_readiness as t44


ROOT = Path(__file__).resolve().parents[1]


def _sha(character: str = "a") -> str:
    return character * 64


def _complete_artifacts() -> tuple[dict, dict, dict]:
    candidate_id = "T44-0001"
    record_hash = _sha("b")
    provenance = {
        "schema_version": t44.SCHEMA_VERSION,
        "status": "FROZEN",
        "source": {
            "corpus_id": "independent-corpus",
            "source_version": "v1",
            "retrieval": {
                "source_uri": "https://example.invalid/source",
                "retrieved_at": "2026-09-01T00:00:00Z",
                "source_manifest_sha256": _sha("c"),
            },
            "licence": {
                "decision": "APPROVED_FOR_THIS_STUDY",
                "licence_identifier": "CC-BY-4.0",
                "reviewer_id": "rights-reviewer",
                "reviewed_at": "2026-09-01T00:00:00Z",
                "evidence": [{"evidence_id": "licence-pdf", "sha256": _sha("d")}],
            },
        },
        "records": [{"candidate_id": candidate_id, "source_record_sha256": record_hash, "upstream_source_id": "source-1"}],
    }
    axis = {
        "decision": "NO_MATCH",
        "method_id": "frozen-review-v1",
        "evidence_ref": "review-log-1",
        "reviewer_id": "reviewer-1",
        "reviewed_at": "2026-09-01T00:00:00Z",
    }
    comparisons = {
        reference: {
            "exact_record": dict(axis),
            "paraphrase_or_derivation": {**axis, "human_review": True},
            "scenario_family": {**axis, "human_review": True},
        }
        for reference in t44.REQUIRED_REFERENCE_CORPORA
    }
    exclusion = {
        "schema_version": t44.SCHEMA_VERSION,
        "status": "FROZEN",
        "reference_corpora": [
            {"reference_id": reference, "state": "FROZEN_REFERENCE", "reference_manifest_sha256": _sha(str(index + 1))}
            for index, reference in enumerate(t44.REQUIRED_REFERENCE_CORPORA)
        ],
        "records": [{"candidate_id": candidate_id, "source_record_sha256": record_hash, "disposition": "ELIGIBLE", "comparisons": comparisons}],
    }
    review_packet = {
        "schema_version": t44.SCHEMA_VERSION,
        "status": "FROZEN",
        "packet_id": "t44-review-v1",
        "candidate_ids": [candidate_id],
        "blinding": {"system_identity_blinded": True, "annotators_blinded_to_each_other": True},
        "annotators": {"annotator_a_id": "ANN-A", "annotator_b_id": "ANN-B"},
        "adjudication_protocol_id": "t44-adjudication-v1",
        "t41_interpretation_field_coverage": {
            field: {"status": "NOT_COMPUTED", "reason": "No T41 measurement contract is frozen."}
            for field in t44.REQUIRED_T41_FIELDS
        },
        "denominator_and_eligibility": {"pre_registered_rule_id": "t44-eligibility-v1"},
        "evaluator": {"version": "t39-fixed-v1", "sha256": _sha("e")},
    }
    return provenance, exclusion, review_packet


def test_t44_templates_are_explicitly_not_computed() -> None:
    provenance = json.loads((ROOT / "configs/evaluation/pilot120_t44_source_provenance_template.json").read_text(encoding="utf-8"))
    exclusion = json.loads((ROOT / "configs/evaluation/pilot120_t44_three_axis_exclusion_template.json").read_text(encoding="utf-8"))
    review_packet = json.loads((ROOT / "configs/evaluation/pilot120_t44_review_packet_template.json").read_text(encoding="utf-8"))
    pilot_template = json.loads((ROOT / "configs/evaluation/pilot120_t44_pilot_provenance_recovery_template.json").read_text(encoding="utf-8"))
    result = t44.validate_readiness(provenance, exclusion, review_packet, pilot_template, root=ROOT)
    assert result["status"] == "NOT_COMPUTED"
    assert result["confirmation_status"] == "NOT_COMPUTED"
    assert any("template_not_evidence" in problem for problem in result["problems"])


def test_pilot_reference_recovery_binds_current_immutable_source() -> None:
    payload = t44.build_pilot_reference(ROOT)
    manifest = json.loads((ROOT / "data/annotations/pilot_120_v1/frozen/FROZEN_MANIFEST.json").read_text(encoding="utf-8"))
    assert payload["status"] == t44.PILOT_REFERENCE_STATUS
    assert payload["pilot_freeze"]["n_records"] == 120
    assert payload["pilot_freeze"]["source_sha256"] == manifest["hashes"]["source_canonical_jsonl"]
    assert len(payload["record_fingerprints"]) == 120
    assert t44.validate_pilot_reference(payload, root=ROOT) == []


def test_t44_ready_ledger_requires_all_three_human_reviewed_axes() -> None:
    provenance, exclusion, review_packet = _complete_artifacts()
    pilot_reference = t44.build_pilot_reference(ROOT)
    complete = t44.validate_readiness(provenance, exclusion, review_packet, pilot_reference, root=ROOT)
    assert complete["status"] == "T44_READINESS_VERIFY_PASSED"
    assert complete["confirmation_status"] == "NOT_COMPUTED"

    incomplete = copy.deepcopy(exclusion)
    del incomplete["records"][0]["comparisons"]["pilot_120_v1"]["scenario_family"]["human_review"]
    result = t44.validate_readiness(provenance, incomplete, review_packet, pilot_reference, root=ROOT)
    assert result["status"] == "NOT_COMPUTED"
    assert "exclusion:T44-0001:pilot_120_v1:scenario_family:human_review_required" in result["problems"]


def test_t44_artifact_writer_refuses_existing_path(monkeypatch) -> None:
    monkeypatch.setattr(Path, "exists", lambda _self: True)
    with pytest.raises(FileExistsError, match="refusing_to_replace_t44_artifact"):
        t44._write_json(Path("already-frozen.json"), {"status": "second"})
