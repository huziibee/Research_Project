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
    assert JobStatus(job_id="1", state="COMPLETED", exit_code=None).success is False


def test_verification_rejects_durable_failure_markers(tmp_path) -> None:
    operator = ClusterJobOperator(repo_root=ROOT, dry_run=True)
    run_id = "t27f-failure-marker"
    operator.state_dir = tmp_path / "state"
    pull_dir = operator.state_dir / run_id / "pulled"
    pull_dir.mkdir(parents=True)
    (pull_dir / "runtime_failure.json").write_text('{"status":"failed"}\n')
    (pull_dir / "heartbeat.json").write_text('{"status":"failed"}\n')
    (pull_dir / "run_manifest.json").write_text('{"status":"failed","files":[]}\n')
    operator.state_dir.joinpath("state.json").write_text(json.dumps({"runs": {run_id: {
        "run_id": run_id, "job_id": "1", "profile": "t27f_all_task_canary",
        "local_pull_path": str(pull_dir),
    }}}))
    with pytest.raises(Exception):
        operator.verify(run_id)


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


def test_rendered_non_strict_sbatch_failing_entrypoint_is_retrievable(tmp_path) -> None:
    operator = ClusterJobOperator(repo_root=ROOT, dry_run=True)
    profile = {
        "partition": "stampede", "time_limit": "00:01:00", "memory_mb": 100,
        "cpus": 1, "gpus_required": False, "sbatch_strict_mode": False,
        "job_name": "t27f-dummy-failure", "entry_point": "scripts/fail.py",
        "remote_result_root_template": "${T12_CLUSTER_ROOT}/runs/t27f-dummy-failure",
    }
    run_id = "t27f-dummy-failure"
    prep = tmp_path / "runs" / "t27f-dummy-failure" / f".prep-{run_id}" / "source" / "t12-src" / "scripts"
    prep.mkdir(parents=True)
    (prep / "fail.py").write_text("raise SystemExit(23)\n")
    rendered = operator._render_sbatch(
        profile=profile, run_id=run_id, head_sha="a" * 40,
        archive_sha="b" * 64, archive_filename="source.tar.gz",
        cluster_root_absolute=str(tmp_path),
    )
    sbatch = tmp_path / "submit.sbatch"
    # Preserve LF line endings because the rendered artifact is a Linux
    # sbatch script and this test may execute it through WSL on Windows.
    sbatch.write_bytes(rendered.encode("utf-8"))
    import os
    import subprocess
    if os.name == "nt":
        # The managed Windows runner resolves ``bash`` through WSL.  Convert
        # pytest's Windows temp path so the same rendered sbatch is executable
        # there as it is on the cluster's Linux shell.
        drive = sbatch.drive.rstrip(":").lower()
        wsl_sbatch = f"/mnt/{drive}/" + "/".join(sbatch.parts[1:])
        wsl_root = f"/mnt/{tmp_path.drive.rstrip(':').lower()}/" + "/".join(tmp_path.parts[1:])
        result = subprocess.run(
            [
                "wsl.exe", "--", "env", f"T12_CLUSTER_ROOT={wsl_root}",
                "SLURM_JOB_ID=1234", "bash", wsl_sbatch,
            ],
            env=os.environ.copy(), text=True, capture_output=True,
        )
    else:
        env = dict(os.environ, T12_CLUSTER_ROOT=str(tmp_path), SLURM_JOB_ID="1234")
        result = subprocess.run(["bash", str(sbatch)], env=env, text=True, capture_output=True)
    result_dir = tmp_path / "runs" / "t27f-dummy-failure" / run_id
    assert result.returncode == 23
    assert "T12_JOB_FAILED" in result.stdout
    assert json.loads((result_dir / "runtime_failure.json").read_text())["status"] == "failed"
    assert json.loads((result_dir / "heartbeat.json").read_text())["status"] == "failed"
