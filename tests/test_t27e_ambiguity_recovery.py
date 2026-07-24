from __future__ import annotations

import json
from pathlib import Path

import pytest

from ambiguity_manager.model.t27e_ambiguity_recovery import (
    ambiguity_forensic_summary,
    build_minimal_ambiguity_schema,
    effective_ambiguity_task_spec,
    validate_t27e_policy,
)


ROOT = Path(__file__).resolve().parents[1]


def test_minimal_ambiguity_contract_has_only_required_model_fields() -> None:
    schema = build_minimal_ambiguity_schema()
    assert schema["required"] == ["ambiguity_present", "ambiguity_types"]
    assert set(schema["properties"]) == {"ambiguity_present", "ambiguity_types"}
    assert schema["additionalProperties"] is False


def test_effective_ambiguity_task_spec_uses_minimal_contract_without_fabrication() -> None:
    registry = json.loads(
        (ROOT / "configs/model/task_conditioned_prediction_tasks_v1.json").read_text()
    )
    task = effective_ambiguity_task_spec(registry)
    assert task["task_id"] == "predict_ambiguity_v1"
    assert task["json_schema"]["required"] == ["ambiguity_present", "ambiguity_types"]
    assert task["optional_fields"] == []
    assert task["owned_production_fields"] == ["ambiguity_present", "ambiguity_types"]


def test_forensic_summary_classifies_bounded_unterminated_attempt() -> None:
    summary = ambiguity_forensic_summary(
        raw_text='{"ambiguity_present":true,"ambiguity_types":["referential"]',
        maximum_output_tokens=192,
        generated_token_count=192,
        termination_reason="length",
    )
    assert summary["termination_class"] == "bounded_maximum_token_unterminated_json"
    assert summary["json_complete"] is False
    assert summary["generated_token_count"] == 192


def test_t27e_policy_is_frozen_before_sealed_execution() -> None:
    policy = json.loads(
        (ROOT / "configs/model/t27e_ambiguity_recovery_v1.json").read_text()
    )
    validate_t27e_policy(policy)
    assert policy["sealed"]["frozen_before_execution"] is True
    assert policy["sealed"]["record_count"] == 12
    assert policy["diagnostic"]["record_count"] == 16
    assert policy["data_isolation"]["protected_access_permitted"] is False


def test_ambiguity_training_schedule_requires_full_traversal() -> None:
    policy = json.loads(
        (ROOT / "configs/model/t27e_ambiguity_recovery_v1.json").read_text()
    )
    assert policy["repair"]["ambiguity_training"]["minimum_full_traversals"] == 1
    assert policy["repair"]["ambiguity_training"]["other_tasks_enabled"] is False


def test_cluster_profile_is_allowlisted_and_forensic_run_is_diagnostic_only() -> None:
    profiles = json.loads((ROOT / "configs/cluster/t12_job_profiles.json").read_text())
    profile = profiles["profiles"]["t27e_ambiguity_diagnostic"]
    assert profile["entry_point"] == "scripts/t27e_ambiguity_diagnostic.py"
    assert "t27e" in profile["run_id_prefix"]
    assert "sealed" not in profile["description"].lower()
    assert "unconstrained" not in profile["entry_args"].lower()


def test_sealed_profile_uses_frozen_manifest_and_minimal_schema_runner() -> None:
    profiles = json.loads((ROOT / "configs/cluster/t12_job_profiles.json").read_text())
    profile = profiles["profiles"]["t27e_ambiguity_sealed"]
    assert profile["entry_point"] == "scripts/t27e_ambiguity_sealed.py"
    assert "t27e_final_smoke_v1/manifest.json" in profile["entry_args"]
    assert "required_task_matrix.json" in profile["entry_args"]
    assert profile["expected_result_files"][-1] == "prediction_journal.jsonl"
