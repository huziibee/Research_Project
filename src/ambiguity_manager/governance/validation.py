"""Repository-wide governance validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ambiguity_manager.governance.ai_use import (
    AI_USE_LOG_SCHEMA_VERSION,
    load_ai_use_log,
    validate_ai_use_log,
    validate_ai_use_log_path,
)
from ambiguity_manager.governance.core_stretch import validate_core_stretch_policy
from ambiguity_manager.governance.dataset_licence import validate_dataset_licence_register
from ambiguity_manager.governance.deviations import (
    DEVIATION_RECORD_SCHEMA_VERSION,
    load_deviation_log,
    validate_deviation_log,
    validate_deviation_log_path,
)
from ambiguity_manager.governance.ethics import (
    derive_ticket_verdict,
    validate_ethics_determination,
)
from ambiguity_manager.governance.hashing import verify_contract_sidecar
from ambiguity_manager.governance.model_licence import validate_model_licence_register
from ambiguity_manager.governance.protected_data import validate_protected_data_policy
from ambiguity_manager.governance.research_contract import validate_research_contract


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_repository_governance(repo_root: Path) -> list[str]:
    errors: list[str] = []

    contract_path = repo_root / "configs" / "research" / "research_contract_v1.json"
    sidecar_path = repo_root / "configs" / "research" / "research_contract_v1.sha256"
    if not contract_path.is_file():
        errors.append("missing configs/research/research_contract_v1.json")
    else:
        contract = _load_json(contract_path)
        errors.extend(validate_research_contract(contract))
        if sidecar_path.is_file():
            if not verify_contract_sidecar(contract_path, sidecar_path):
                errors.append("research contract sidecar verification failed")
        else:
            errors.append("missing configs/research/research_contract_v1.sha256")

    ethics_path = repo_root / "configs" / "governance" / "human_annotation_governance.json"
    if ethics_path.is_file():
        ethics = _load_json(ethics_path)
        errors.extend(validate_ethics_determination(ethics, repo_root=repo_root))
        _ = derive_ticket_verdict(ethics)
    else:
        errors.append("missing configs/governance/human_annotation_governance.json")

    ai_use_rel = "docs/governance/logs/generative_ai_use_log.jsonl"
    errors.extend(validate_ai_use_log_path(ai_use_rel))
    ai_use_entries = load_ai_use_log(repo_root / ai_use_rel)
    errors.extend(validate_ai_use_log(ai_use_entries))

    deviation_rel = "docs/governance/logs/deviation_log.jsonl"
    errors.extend(validate_deviation_log_path(deviation_rel))
    deviation_entries, deviation_parse_errors = load_deviation_log(repo_root / deviation_rel)
    errors.extend(
        validate_deviation_log(
            deviation_entries,
            repo_root=repo_root,
            parse_errors=deviation_parse_errors,
        )
    )

    for rel_path in (
        "configs/governance/core_stretch_policy.json",
        "configs/licences/dataset_licence_register.json",
        "configs/licences/model_licence_register.json",
        "configs/governance/protected_data_policy.json",
    ):
        path = repo_root / rel_path
        if not path.is_file():
            errors.append(f"missing {rel_path}")
            continue
        data = _load_json(path)
        if rel_path.endswith("core_stretch_policy.json"):
            errors.extend(validate_core_stretch_policy(data))
        elif rel_path.endswith("dataset_licence_register.json"):
            errors.extend(validate_dataset_licence_register(data))
        elif rel_path.endswith("model_licence_register.json"):
            errors.extend(validate_model_licence_register(data))
        elif rel_path.endswith("protected_data_policy.json"):
            errors.extend(validate_protected_data_policy(data))

    for log_name in (
        "decision_log.jsonl",
        "deviation_log.jsonl",
        "protected_access_log.jsonl",
        "role_overlap_log.jsonl",
    ):
        rel = f"docs/governance/logs/{log_name}"
        if not (repo_root / rel).is_file():
            errors.append(f"missing tracked governance log {rel}")

    schema_path = repo_root / "configs" / "governance" / "ai_use_log_schema.json"
    if schema_path.is_file():
        schema = _load_json(schema_path)
        if schema.get("schema_version") != AI_USE_LOG_SCHEMA_VERSION:
            errors.append("ai_use_log_schema.json version mismatch")

    deviation_schema_path = repo_root / "configs" / "governance" / "deviation_record_schema.json"
    if deviation_schema_path.is_file():
        deviation_schema = _load_json(deviation_schema_path)
        if deviation_schema.get("schema_version") != DEVIATION_RECORD_SCHEMA_VERSION:
            errors.append("deviation_record_schema.json version mismatch")

    return errors
