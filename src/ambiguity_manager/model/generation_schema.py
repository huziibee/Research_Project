"""Authoritative LMFE-compatible model-generation schema layer.

The production registry remains the semantic source of truth.  This module
derives the smaller, non-null generation contract consumed by every training,
diagnostic, smoke, sealed, and future entry point.  Assemblers restore
production optional/null semantics deterministically after validation.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex

CONFIG_REL = "configs/model/t27f_schema_compatibility_v1.json"
PRODUCTION_REL = "configs/model/task_conditioned_prediction_tasks_v1.json"
GENERATION_SCHEMA_VERSION = "1.0.0"
AMBIGUITY_TYPES = [
    "referential", "spatial", "pragmatic", "temporal", "quantitative",
    "preference", "commonsense", "safety_precondition", "capability", "contextual",
]


def _root(root: Path | None) -> Path:
    return (root or Path(__file__).resolve().parents[3]).resolve()


def production_task_registry(root: Path | None = None) -> dict[str, Any]:
    return json.loads((_root(root) / PRODUCTION_REL).read_text(encoding="utf-8"))


def _minimal_ambiguity_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "t27f://predict_ambiguity_v1_generation",
        "type": "object", "additionalProperties": False,
        "required": ["ambiguity_present", "ambiguity_types"],
        "properties": {
            "ambiguity_present": {"type": "boolean"},
            "ambiguity_types": {"type": "array", "items": {"type": "string", "enum": AMBIGUITY_TYPES}},
        },
    }


def _remove_null(schema: dict[str, Any], *, enum: list[Any] | None = None) -> dict[str, Any]:
    result = dict(schema)
    types = result.get("type")
    if isinstance(types, list):
        non_null = [item for item in types if item != "null"]
        result["type"] = non_null[0] if len(non_null) == 1 else non_null
    if "enum" in result:
        result["enum"] = [item for item in result["enum"] if item is not None]
    if enum is not None:
        result["enum"] = enum
    return result


def _transform_interpretations(schema: dict[str, Any]) -> None:
    item = schema["properties"]["candidate_interpretations"]["items"]
    props = item["properties"]
    for name in ("text", "confidence", "safety_status", "cpc"):
        props[name] = _remove_null(props[name])
    props["safety_status"]["enum"] = ["safe", "unsafe", "unknown"]
    selected = schema["properties"]["selected_interpretation"]
    schema["properties"]["selected_interpretation"] = _remove_null(selected)
    evidence = selected["properties"]["supporting_evidence"]["items"]["properties"]
    evidence["span"] = _remove_null(evidence["span"])
    evidence["note"] = _remove_null(evidence["note"])


def effective_task_registry(root: Path | None = None) -> dict[str, Any]:
    root_path = _root(root)
    config = json.loads((root_path / CONFIG_REL).read_text(encoding="utf-8"))
    if config.get("generation_schema_version") != GENERATION_SCHEMA_VERSION:
        raise ValueError("generation_schema_version_mismatch")
    registry = copy.deepcopy(production_task_registry(root_path))
    registry["generation_schema_version"] = GENERATION_SCHEMA_VERSION
    registry["generation_schema_config_id"] = config["config_id"]
    for task in registry["tasks"]:
        # Keep the established prompt-contract family stable; schema authority
        # is versioned independently and is recorded in the registry.
        task["prompt_contract_identity"] = f"t27c_task_prompt_v1/{task['task_id']}"
        task_id = task["task_id"]
        if task_id == "predict_intent_v1":
            task["json_schema"]["properties"]["speech_act"] = _remove_null(task["json_schema"]["properties"]["speech_act"])
            task["optional_fields"] = ["speech_act"]
            task["unknown_handling"] = "omit speech_act when unsupported; assembler may restore production null"
        elif task_id == "predict_ambiguity_v1":
            task["json_schema"] = _minimal_ambiguity_schema()
            task["required_fields"] = ["ambiguity_present", "ambiguity_types"]
            task["optional_fields"] = []
            task["owned_production_fields"] = ["ambiguity_present", "ambiguity_types"]
            task["stable_field_order"] = ["ambiguity_present", "ambiguity_types"]
            task["maximum_output_tokens"] = 96
            task["unknown_handling"] = "missing task output remains production null; never derive false"
        elif task_id == "predict_interpretations_v1":
            _transform_interpretations(task["json_schema"])
            task["unknown_handling"] = "omit unsupported optional properties; selected_interpretation requires unique support"
        elif task_id == "predict_risk_capability_v1":
            props = task["json_schema"]["properties"]
            for name in ("risk_level", "capability_status"):
                props[name] = _remove_null(props[name])
            task["unknown_handling"] = "required unknown is the only safe unavailable prediction"
    validate_generation_schema_contract(registry)
    return registry


def generation_schema_hashes(registry: Mapping[str, Any]) -> dict[str, str]:
    return {str(task["task_id"]): sha256_hex(canonical_json_bytes(task["json_schema"])) for task in registry.get("tasks", [])}


def minimal_valid_instance(task: Mapping[str, Any]) -> dict[str, Any]:
    task_id = str(task["task_id"])
    if task_id == "predict_intent_v1": return {"intent_summary": "unknown intent"}
    if task_id == "predict_cpc_v1":
        return {"cpc": {name: {"value": None, "status": "unknown"} for name in task["json_schema"]["properties"]["cpc"]["properties"]}}
    if task_id == "predict_ambiguity_v1": return {"ambiguity_present": False, "ambiguity_types": []}
    if task_id == "predict_interpretations_v1": return {"candidate_interpretations": []}
    if task_id == "predict_risk_capability_v1": return {"risk_relevant": False, "risk_level": "unknown", "capability_status": "unknown"}
    raise ValueError(f"unknown_task:{task_id}")


def validate_generation_schema_contract(registry: Mapping[str, Any]) -> None:
    if registry.get("generation_schema_version") != GENERATION_SCHEMA_VERSION:
        raise ValueError("missing_generation_schema_version")
    for task in registry.get("tasks", []):
        schema_text = json.dumps(task["json_schema"])
        if "null" in (task["json_schema"].get("enum") or []):
            raise ValueError(f"nullable_enum:{task['task_id']}")
        if task["task_id"] == "predict_ambiguity_v1":
            if set(task["json_schema"]["properties"]) != {"ambiguity_present", "ambiguity_types"} or task.get("maximum_output_tokens") != 96:
                raise ValueError("ambiguity_contract_drift")
        if task["task_id"] == "predict_cpc_v1" and not schema_text:
            raise ValueError("empty_cpc_schema")
