"""Bounded regeneration repair-prompt builder for T12 Stage D1C1."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.prediction_contract import model_semantic_output_schema_hash
from ambiguity_manager.model.prompt_builder import PromptBuildRequest

DEFAULT_PIPELINE_CONTRACT_REL = Path("configs") / "model" / "t12_generation_pipeline_contract.json"
PIPELINE_CONTRACT_HASH_METHOD = "canonical_json_sha256_v1"


@dataclass(frozen=True)
class RepairPromptRequest:
    original_request: PromptBuildRequest
    attempt_number: int
    validation_failures: tuple[str, ...]
    prior_raw_output: str | None = None


@dataclass(frozen=True)
class RepairPromptResult:
    repair_user_content: str
    repair_prompt_hash: str
    prior_raw_output_included: bool
    prior_raw_output_truncated: bool
    schema_hash: str


def load_pipeline_contract(path: Path | None = None) -> dict[str, object]:
    from ambiguity_manager.paths import repo_root

    target = path or (repo_root() / DEFAULT_PIPELINE_CONTRACT_REL)
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("pipeline contract must be a JSON object")
    return payload


def generation_pipeline_contract_hash(
    contract_or_path: Path | dict[str, object] | None = None,
) -> str:
    if contract_or_path is None:
        contract = load_pipeline_contract()
    elif isinstance(contract_or_path, Path):
        contract = load_pipeline_contract(contract_or_path)
    elif isinstance(contract_or_path, dict):
        contract = contract_or_path
    else:
        raise TypeError("contract_or_path must be a Path, dict, or None")
    if not isinstance(contract, dict):
        raise ValueError("pipeline contract must be a JSON object")
    return sha256_hex(canonical_json_bytes(contract))


def build_repair_prompt(
    request: RepairPromptRequest,
    *,
    contract: dict[str, object] | None = None,
) -> RepairPromptResult:
    policy = contract or load_pipeline_contract()
    max_chars = int(policy["repair_prompt_max_prior_raw_output_chars"])
    include_prior = bool(policy["include_prior_raw_output_in_repair_prompt"])
    schema_hash = model_semantic_output_schema_hash()

    original = request.original_request
    sections: list[str] = [
        "[REPAIR_ATTEMPT]",
        f"attempt_number={request.attempt_number}",
        "previous_output_status=invalid",
        f"semantic_schema_hash={schema_hash}",
        "",
        "[ORIGINAL_COMMAND]",
        original.command,
    ]
    if original.scene_context is not None:
        sections.extend(["", "[SCENE_CONTEXT]", original.scene_context])
    if original.dialogue_history:
        sections.extend(["", "[DIALOGUE_HISTORY]"])
        for line in original.dialogue_history:
            sections.append(f"- {line}")
    if original.capability_context is not None:
        sections.extend(["", "[CAPABILITY_CONTEXT]", original.capability_context])

    sections.extend(
        [
            "",
            "[VALIDATION_FAILURES]",
            *request.validation_failures,
            "",
            "[REPAIR_REQUIREMENTS]",
            "Return one complete replacement semantic JSON object only.",
            "Do not emit prose, Markdown fences, omitted required fields, enum coercion, or command changes.",
            "Do not invent a corrected semantic answer locally; regenerate the full object.",
        ]
    )

    prior_included = False
    prior_truncated = False
    if include_prior and request.prior_raw_output:
        prior_included = True
        prior_text = request.prior_raw_output
        if len(prior_text) > max_chars:
            prior_text = prior_text[:max_chars]
            prior_truncated = True
        sections.extend(
            [
                "",
                "[PRIOR_INVALID_OUTPUT_BEGIN]",
                prior_text,
                "[PRIOR_INVALID_OUTPUT_END]",
            ]
        )

    repair_content = "\n".join(sections)
    payload = {
        "attempt_number": request.attempt_number,
        "schema_hash": schema_hash,
        "validation_failures": list(request.validation_failures),
        "repair_user_content": repair_content,
        "prior_raw_output_included": prior_included,
        "prior_raw_output_truncated": prior_truncated,
    }
    return RepairPromptResult(
        repair_user_content=repair_content,
        repair_prompt_hash=sha256_hex(canonical_json_bytes(payload)),
        prior_raw_output_included=prior_included,
        prior_raw_output_truncated=prior_truncated,
        schema_hash=schema_hash,
    )


def build_repair_messages(
    system_message: str,
    original_request: PromptBuildRequest,
    repair_result: RepairPromptResult,
) -> list[dict[str, str]]:
    """Build abstract messages for a regeneration attempt without mutating caller input."""
    request_copy = copy.deepcopy(original_request)
    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": repair_result.repair_user_content},
    ]
