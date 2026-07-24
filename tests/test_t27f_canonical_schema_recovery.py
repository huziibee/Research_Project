from __future__ import annotations

import json
from pathlib import Path

import pytest

from ambiguity_manager.model.generation_schema import (
    GENERATION_SCHEMA_VERSION,
    effective_task_registry,
    generation_schema_hashes,
    minimal_valid_instance,
    validate_generation_schema_contract,
)
from ambiguity_manager.model.schema_preflight import run_schema_preflight
from ambiguity_manager.model.cluster.job_operator import ClusterJobOperator, JobStatus, get_profile

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_registry_removes_nullable_prediction_enums_and_unions() -> None:
    registry = effective_task_registry(ROOT)
    tasks = {task["task_id"]: task for task in registry["tasks"]}
    intent = tasks["predict_intent_v1"]["json_schema"]["properties"]["speech_act"]
    assert intent == {"type": "string", "enum": [
        "directive_command", "indirect_request", "information_question",
        "permission_request", "prohibition", "conditional_directive",
        "multi_intent", "other_non_actionable",
    ]}
    ambiguity = tasks["predict_ambiguity_v1"]["json_schema"]
    assert set(ambiguity["properties"]) == {"ambiguity_present", "ambiguity_types"}
    risk = tasks["predict_risk_capability_v1"]["json_schema"]["properties"]
    assert risk["risk_level"]["type"] == "string"
    assert risk["capability_status"]["type"] == "string"
    assert None not in risk["risk_level"]["enum"]
    assert None not in risk["capability_status"]["enum"]


def test_optional_interpretation_fields_are_omitted_not_null() -> None:
    task = {t["task_id"]: t for t in effective_task_registry(ROOT)["tasks"]}["predict_interpretations_v1"]
    props = task["json_schema"]["properties"]["candidate_interpretations"]["items"]["properties"]
    assert props["safety_status"] == {"type": "string", "enum": ["safe", "unsafe", "unknown"]}
    assert props["text"] == {"type": "string"}
    assert props["confidence"] == {"type": "number"}
    assert "selected_interpretation" not in task["json_schema"]["required"]


def test_required_unknown_semantics_and_minimal_ambiguity_bound_are_frozen() -> None:
    registry = effective_task_registry(ROOT)
    tasks = {task["task_id"]: task for task in registry["tasks"]}
    risk = tasks["predict_risk_capability_v1"]["json_schema"]["properties"]
    assert "unknown" in risk["risk_level"]["enum"]
    assert "unknown" in risk["capability_status"]["enum"]
    assert tasks["predict_ambiguity_v1"]["maximum_output_tokens"] == 96
    assert tasks["predict_ambiguity_v1"]["json_schema"]["required"] == ["ambiguity_present", "ambiguity_types"]


def test_production_registry_is_preserved_and_cpc_hash_is_unchanged() -> None:
    production = json.loads((ROOT / "configs/model/task_conditioned_prediction_tasks_v1.json").read_text())
    effective = effective_task_registry(ROOT)
    production_tasks = {t["task_id"]: t for t in production["tasks"]}
    effective_tasks = {t["task_id"]: t for t in effective["tasks"]}
    assert production_tasks["predict_cpc_v1"]["json_schema"] == effective_tasks["predict_cpc_v1"]["json_schema"]
    assert production_tasks["predict_ambiguity_v1"]["json_schema"] != effective_tasks["predict_ambiguity_v1"]["json_schema"]


def test_all_entry_points_resolve_one_version_and_hash_set() -> None:
    registry = effective_task_registry(ROOT)
    validate_generation_schema_contract(registry)
    hashes = generation_schema_hashes(registry)
    assert registry["generation_schema_version"] == GENERATION_SCHEMA_VERSION
    assert set(hashes) == {task["task_id"] for task in registry["tasks"]}
    assert all(len(value) == 64 for value in hashes.values())


def test_minimal_valid_instances_are_non_null_and_schema_valid() -> None:
    from jsonschema import Draft202012Validator

    for task in effective_task_registry(ROOT)["tasks"]:
        schema = task["json_schema"]
        instance = minimal_valid_instance(task)
        errors = list(Draft202012Validator(schema).iter_errors(instance))
        assert not errors, (task["task_id"], errors)


def test_exact_runtime_preflight_is_fail_fast_and_records_all_tasks() -> None:
    evidence = run_schema_preflight(ROOT)
    assert evidence["passed"] is True
    assert evidence["model_loading_permitted"] is True
    assert {item["task_id"] for item in evidence["tasks"]} == set(generation_schema_hashes(effective_task_registry(ROOT)))
    assert all(item["compile_result"] == "passed" for item in evidence["tasks"])


def test_slurm_completed_with_nonzero_exit_is_not_success() -> None:
    assert JobStatus(job_id="1", state="COMPLETED", exit_code="1:0").success is False
    assert JobStatus(job_id="1", state="COMPLETED", exit_code="0:0").success is True


def test_non_strict_sbatch_template_propagates_failure_and_writes_artifact() -> None:
    operator = ClusterJobOperator(repo_root=ROOT, dry_run=True)
    profile = get_profile(operator.profiles_doc, "t27f_all_task_canary")
    rendered = operator._render_sbatch(
        profile=profile, run_id="t27f-test-failure", head_sha="a" * 40,
        archive_sha="b" * 64, archive_filename="source.tar.gz",
    )
    assert "exit ${JOB_STATUS:-0}" in rendered
    assert "runtime_failure.json" in rendered
    assert "T12_JOB_FAILED" in rendered
    assert "JOB_STATUS=${SCRIPT_RC}" in rendered
