"""Curated config loading, validation, and per-dataset audit specifications."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ambiguity_manager.data_audit.version import (
    AUDIT_SCHEMA_VERSION,
    LICENCE_MANIFEST_SCHEMA_VERSION,
    REGISTER_SCHEMA_VERSION,
)
from ambiguity_manager.paths import ProjectPaths

# Per-dataset technical audit specs. Paths come from the inclusion register.
DATASET_AUDIT_SPECS: dict[str, dict[str, Any]] = {
    "ambik": {
        "raw_root": "AmbiK",
        "entry_type": "git_submodule",
        "primary": {
            "relative_path": "AmbiK/AmbiK_data.csv",
            "file_type": "csv",
            "critical_fields": ["id", "ambiguous_task", "unambiguous_direct", "ambiguity_type"],
            "id_fields": ["id"],
            "component_name": "primary",
        },
        "auxiliary": [
            {
                "relative_path": "AmbiK/ambik_dataset/ambik_test_900.csv",
                "file_type": "csv",
                "critical_fields": ["ambiguous_task", "ambiguity_type"],
                "id_fields": [],
            },
            {
                "relative_path": "AmbiK/ambik_dataset/ambik_test_400.csv",
                "file_type": "csv",
                "critical_fields": ["ambiguous_task", "ambiguity_type"],
                "id_fields": [],
            },
            {
                "relative_path": "AmbiK/ambik_dataset/ambik_calib_100.csv",
                "file_type": "csv",
                "critical_fields": ["ambiguous_task", "ambiguity_type"],
                "id_fields": [],
            },
            {
                "relative_path": "AmbiK/ambik_knowno_data/knowno_data.csv",
                "file_type": "csv",
                "critical_fields": ["task", "ambiguity_type"],
                "id_fields": [],
            },
        ],
        "split_structure": "multiple_csv_subsets",
        "mapping_risks": [
            {
                "code": "TODO_VERIFY_LABEL_MAPPING",
                "field": "ambiguity_type",
                "note": "Map AmbiK ambiguity types to project taxonomy in T03",
            }
        ],
    },
    "clara": {
        "raw_root": "CLARA-Dataset",
        "entry_type": "git_submodule",
        "primary": {
            "relative_path": "CLARA-Dataset/data/agument.json",
            "file_type": "json_dict",
            "critical_fields": ["goal", "label", "task"],
            "id_fields": [],
            "record_key_is_id": True,
        },
        "auxiliary": [],
        "split_structure": "single_file",
        "mapping_risks": [
            {
                "code": "TODO_VERIFY_LABEL_MAPPING",
                "field": "label",
                "note": "CLARA labels 0-3 route mapping deferred to T07",
            }
        ],
    },
    "clariq": {
        "raw_root": "ClariQ",
        "entry_type": "git_submodule",
        "primary": {
            "relative_path": "ClariQ/data/train.tsv",
            "file_type": "tsv",
            "critical_fields": ["topic_id", "question_id", "initial_request"],
            "id_fields": ["question_id"],
            "split_name": "train",
        },
        "auxiliary": [
            {
                "relative_path": "ClariQ/data/dev.tsv",
                "file_type": "tsv",
                "critical_fields": ["topic_id", "question_id"],
                "id_fields": ["question_id"],
                "split_name": "dev",
            },
            {
                "relative_path": "ClariQ/data/test.tsv",
                "file_type": "tsv",
                "critical_fields": ["topic_id"],
                "id_fields": [],
                "split_name": "test",
            },
            {
                "relative_path": "ClariQ/data/test_with_labels.tsv",
                "file_type": "tsv",
                "critical_fields": ["topic_id", "question_id"],
                "id_fields": ["question_id"],
                "split_name": "test_with_labels",
            },
            {
                "relative_path": "ClariQ/data/question_bank.tsv",
                "file_type": "tsv",
                "critical_fields": ["question_id"],
                "id_fields": ["question_id"],
                "split_name": "question_bank",
            },
            {
                "relative_path": "ClariQ/data/multi_turn_human_generated_data.tsv",
                "file_type": "tsv",
                "critical_fields": ["topic_id"],
                "id_fields": [],
                "split_name": "multi_turn",
            },
        ],
        "split_structure": "official_tsv_splits",
        "split_overlap_checks": [
            {
                "files": ["ClariQ/data/train.tsv", "ClariQ/data/dev.tsv"],
                "id_fields": ["question_id"],
            }
        ],
        "mapping_risks": [],
    },
    "indirect_requests": {
        "raw_root": "IndirectRequests",
        "entry_type": "hf_dataset",
        "authoritative_components": [
            {
                "relative_path": "IndirectRequests/train/data-00000-of-00001.arrow",
                "file_type": "arrow",
                "metadata_path": "IndirectRequests/train/dataset_info.json",
                "critical_fields": ["utterance", "situation", "target_slot_value"],
                "id_fields": [],
                "component_name": "train",
            },
            {
                "relative_path": "IndirectRequests/validation/data-00000-of-00001.arrow",
                "file_type": "arrow",
                "metadata_path": "IndirectRequests/validation/dataset_info.json",
                "critical_fields": ["utterance", "situation"],
                "id_fields": [],
                "component_name": "validation",
            },
            {
                "relative_path": "IndirectRequests/test/data-00000-of-00001.arrow",
                "file_type": "arrow",
                "metadata_path": "IndirectRequests/test/dataset_info.json",
                "critical_fields": ["utterance", "situation"],
                "id_fields": [],
                "component_name": "test",
            },
        ],
        "split_structure": "official_hf_splits",
        "mapping_risks": [
            {
                "code": "TODO_VERIFY_LABEL_MAPPING",
                "field": "utterance",
                "note": "Field-to-canonical mapping deferred to T04",
            }
        ],
    },
    "safe_agent_bench": {
        "raw_root": "SafeAgentBench",
        "entry_type": "hf_dataset",
        "authoritative_components": [
            {
                "relative_path": "SafeAgentBench/abstract/train.arrow/data-00000-of-00001.arrow",
                "file_type": "arrow",
                "metadata_path": "SafeAgentBench/abstract/train.arrow/dataset_info.json",
                "critical_fields": ["instruction", "risk_category"],
                "id_fields": [],
                "component_name": "abstract",
            },
            {
                "relative_path": "SafeAgentBench/unsafe_detailed/train.arrow/data-00000-of-00001.arrow",
                "file_type": "arrow",
                "metadata_path": "SafeAgentBench/unsafe_detailed/train.arrow/dataset_info.json",
                "critical_fields": ["instruction", "risk_category"],
                "id_fields": [],
                "component_name": "unsafe_detailed",
            },
            {
                "relative_path": "SafeAgentBench/safe_detailed/train.arrow/data-00000-of-00001.arrow",
                "file_type": "arrow",
                "metadata_path": "SafeAgentBench/safe_detailed/train.arrow/dataset_info.json",
                "critical_fields": ["instruction", "risk_instruction"],
                "id_fields": [],
                "component_name": "safe_detailed",
            },
            {
                "relative_path": "SafeAgentBench/long_horizon/train.arrow/data-00000-of-00001.arrow",
                "file_type": "arrow",
                "metadata_path": "SafeAgentBench/long_horizon/train.arrow/dataset_info.json",
                "critical_fields": ["instruction", "scene_name"],
                "id_fields": [],
                "component_name": "long_horizon",
            },
        ],
        "split_structure": "config_subsets",
        "mapping_risks": [],
    },
    "codraw_icr_v2": {
        "raw_root": "codraw-icr-v2",
        "entry_type": "directory",
        "primary": {
            "relative_path": "codraw-icr-v2/codraw-icr-v2.tsv",
            "file_type": "tsv",
            "critical_fields": ["drawer", "game_name", "turn"],
            "id_fields": [],
        },
        "auxiliary": [
            {
                "relative_path": "codraw-icr-v2/codraw-icr-v2_raw.tsv",
                "file_type": "tsv",
                "critical_fields": ["drawer", "game_name"],
                "id_fields": [],
            }
        ],
        "split_structure": "single_file",
        "mapping_risks": [
            {
                "code": "TODO_VERIFY_LABEL_MAPPING",
                "field": "drawer",
                "note": "Clarification mapping deferred to T05",
            }
        ],
    },
    "vague": {
        "raw_root": "vague_bench",
        "entry_type": "hf_dataset",
        "primary": {
            "relative_path": "vague_bench/data/train-00000-of-00001.parquet",
            "file_type": "parquet",
            "critical_fields": ["direct", "indirect", "image_name"],
            "id_fields": ["image_name"],
            "split_name": "train",
        },
        "auxiliary": [],
        "split_structure": "single_split",
        "mapping_risks": [
            {
                "code": "TODO_VERIFY_LABEL_MAPPING",
                "field": "direct",
                "note": "Context-dependent mapping deferred to T06",
            }
        ],
    },
    "teach": {
        "raw_root": "TEACh",
        "entry_type": "git_submodule",
        "primary": None,
        "auxiliary": [],
        "split_structure": "game_json_files",
        "inventory_glob": "*.game.json",
        "mapping_risks": [],
    },
    "teach_tatc": {
        "raw_root": "teach_tatc",
        "entry_type": "git_submodule",
        "primary": None,
        "auxiliary": [],
        "split_structure": "none",
        "mapping_risks": [],
    },
}

MISSING_DATASETS = [
    {
        "dataset_id": "dynamic_rdmm",
        "status": "MISSING_NOT_BLOCKING",
        "planned_row_count": 19721,
        "standardized_glob": "dynamic_rdmm_standardized*.csv",
    },
    {
        "dataset_id": "refcoco",
        "status": "MISSING_NOT_BLOCKING",
        "planned_row_count": 378784,
        "standardized_glob": "refcoco_standardized*.csv",
    },
    {
        "dataset_id": "referit3d",
        "status": "MISSING_NOT_BLOCKING",
        "planned_row_count": 323177,
        "standardized_glob": "referit3d_standardized*.csv",
    },
    {
        "dataset_id": "cmc",
        "status": "MISSING_NOT_BLOCKING",
        "planned_row_count": 1571,
        "standardized_glob": "cmc_standardized*.csv",
    },
    {
        "dataset_id": "manual_compound",
        "status": "MISSING_NOT_BLOCKING",
        "planned_row_count": None,
        "standardized_glob": None,
        "note": "Required gold contribution; not yet created (T10)",
    },
]

EXCLUDED_ARTIFACTS = [
    {"relative_path": "data/raw/.venv", "reason": "accidental virtualenv, not a dataset"},
    {
        "relative_path": "data/raw/vague_bench/.cache",
        "reason": "HuggingFace download cache stubs, not authoritative payload",
    },
]


def default_register_path() -> Path:
    return ProjectPaths.from_repo_root().configs / "datasets" / "dataset_inclusion_register.json"


def default_licence_manifest_path() -> Path:
    return ProjectPaths.from_repo_root().configs / "datasets" / "licence_provenance_manifest.json"


def get_audit_spec(dataset_id: str) -> dict[str, Any] | None:
    return DATASET_AUDIT_SPECS.get(dataset_id)


def load_json_config(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    with source.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_inclusion_register(path: str | Path | None = None) -> dict[str, Any]:
    return load_json_config(path or default_register_path())


def load_licence_manifest(path: str | Path | None = None) -> dict[str, Any]:
    return load_json_config(path or default_licence_manifest_path())


def _has_licence_evidence(entry: dict[str, Any]) -> bool:
    if entry.get("licence_file_relpath"):
        return True
    if entry.get("licence_text_excerpt"):
        return True
    if entry.get("licence_url"):
        return True
    for citation in entry.get("citations", []):
        if citation.get("status") == "found" and (citation.get("url") or citation.get("title")):
            return True
    return False


def validate_inclusion_register(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("register_schema_version") != REGISTER_SCHEMA_VERSION:
        errors.append(f"register_schema_version must be {REGISTER_SCHEMA_VERSION}")
    entries = data.get("entries")
    if not isinstance(entries, list):
        return errors + ["entries must be a list"]
    for index, entry in enumerate(entries):
        prefix = f"entries[{index}]"
        decision = entry.get("decision")
        if decision not in {"include", "exclude", "conditional", "challenge_only", "auxiliary"}:
            errors.append(f"{prefix}.decision invalid: {decision!r}")
        if not entry.get("dataset_id"):
            errors.append(f"{prefix}.dataset_id is required")
        if not entry.get("expected_converter_ticket") and decision != "exclude":
            errors.append(f"{prefix}.expected_converter_ticket required for non-exclude")
        split = entry.get("split_eligibility")
        if not isinstance(split, dict):
            errors.append(f"{prefix}.split_eligibility must be an object")
    return errors


def validate_licence_manifest(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("manifest_schema_version") != LICENCE_MANIFEST_SCHEMA_VERSION:
        errors.append(f"manifest_schema_version must be {LICENCE_MANIFEST_SCHEMA_VERSION}")
    entries = data.get("entries")
    if not isinstance(entries, list):
        return errors + ["entries must be a list"]
    for index, entry in enumerate(entries):
        prefix = f"entries[{index}]"
        status = entry.get("licence_status")
        if status == "verified":
            if not _has_licence_evidence(entry):
                errors.append(f"{prefix}.verified requires recorded evidence location")
            if not entry.get("verified_by") or not entry.get("verified_at"):
                errors.append(f"{prefix}.verified requires verified_by and verified_at metadata")
        identifier = entry.get("licence_identifier")
        if identifier and not _has_licence_evidence(entry):
            errors.append(f"{prefix}.licence_identifier requires recorded evidence")
        for bool_field in ("redistribution_allowed", "commercial_use_allowed"):
            value = entry.get(bool_field)
            if value is not None and not _has_licence_evidence(entry):
                errors.append(f"{prefix}.{bool_field} requires recorded evidence")
    return errors


def validate_audit_result(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("audit_schema_version") != AUDIT_SCHEMA_VERSION:
        errors.append(f"audit_schema_version must be {AUDIT_SCHEMA_VERSION}")
    datasets = data.get("datasets")
    if datasets is not None and not isinstance(datasets, list):
        errors.append("datasets must be a list")
    elif isinstance(datasets, list):
        for index, dataset in enumerate(datasets):
            for field in (
                "payload_verification_status",
                "mapping_verification_status",
                "licence_status",
            ):
                value = dataset.get(field)
                if value is None:
                    errors.append(f"datasets[{index}].{field} is required")
            payload_status = dataset.get("payload_verification_status", dataset.get("verification_status"))
            if payload_status not in {
                "verified",
                "partially_verified",
                "metadata_only",
                "blocked",
                "excluded",
            }:
                errors.append(f"datasets[{index}].payload_verification_status invalid: {payload_status!r}")
            mapping_status = dataset.get("mapping_verification_status")
            if mapping_status not in {"verified", "TODO_VERIFY", "not_applicable"}:
                errors.append(f"datasets[{index}].mapping_verification_status invalid: {mapping_status!r}")
            blob = json.dumps(dataset)
            if "sample_rows" in blob:
                errors.append(f"datasets[{index}] must not contain sample_rows")
    return errors
