"""T27C task-conditioned prediction contracts (CPU-safe at import).

Defines TaskPredictionRequest / TaskPredictionResult, task-registry loading,
prompt construction, and task-output validation. Heavy JSON-schema validation
uses jsonschema only inside functions (already a project dependency).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES

TASK_REGISTRY_REL = "configs/model/task_conditioned_prediction_tasks_v1.json"
FIELD_REGISTRY_REL = "configs/model/t27c_field_responsibility_registry_v1.json"
PROMPT_CONTRACT_FAMILY = "t27c_task_prompt_v1"
ASSEMBLER_VERSION = "structured_analysis_assembler_v1"

STRONG_ELIGIBILITY = frozenset({"eligible", "weakly_eligible"})


class TaskPredictionContractError(RuntimeError):
    """Raised when a task prediction contract cannot be satisfied."""


@dataclass(frozen=True)
class TaskPredictionRequest:
    record_id: str
    task_id: str
    task_version: str
    model_input: str
    input_hash: str
    prompt_contract: str
    base_model_identity: str
    adapter_identity: str | None
    generation_config: dict[str, Any]
    prompt_hash: str
    schema_hash: str
    generation_config_hash: str

    def cache_identity(self, *, output_hash: str | None = None) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "task_id": self.task_id,
            "input_hash": self.input_hash,
            "prompt_hash": self.prompt_hash,
            "schema_hash": self.schema_hash,
            "base_model_identity": self.base_model_identity,
            "adapter_identity": self.adapter_identity,
            "generation_config_hash": self.generation_config_hash,
            "output_hash": output_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "task_id": self.task_id,
            "task_version": self.task_version,
            "model_input": self.model_input,
            "input_hash": self.input_hash,
            "prompt_contract": self.prompt_contract,
            "base_model_identity": self.base_model_identity,
            "adapter_identity": self.adapter_identity,
            "generation_config": dict(self.generation_config),
            "prompt_hash": self.prompt_hash,
            "schema_hash": self.schema_hash,
            "generation_config_hash": self.generation_config_hash,
        }


@dataclass(frozen=True)
class TaskPredictionResult:
    record_id: str
    task_id: str
    task_version: str
    raw_attempts: tuple[str, ...]
    parsed_output: dict[str, Any] | None
    transport_status: str
    parse_status: str
    schema_status: str
    semantic_status: str
    safety_status: str
    final_status: str
    task_provenance: dict[str, Any]
    output_hash: str | None
    failure_details: tuple[str, ...] = ()
    constraint_initialised: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "task_id": self.task_id,
            "task_version": self.task_version,
            "raw_attempts": list(self.raw_attempts),
            "parsed_output": self.parsed_output,
            "transport_status": self.transport_status,
            "parse_status": self.parse_status,
            "schema_status": self.schema_status,
            "semantic_status": self.semantic_status,
            "safety_status": self.safety_status,
            "final_status": self.final_status,
            "task_provenance": dict(self.task_provenance),
            "output_hash": self.output_hash,
            "failure_details": list(self.failure_details),
            "constraint_initialised": self.constraint_initialised,
        }

    @property
    def accepted(self) -> bool:
        return self.final_status == "accepted"


def _root(root: Path | None) -> Path:
    return (root or ProjectPaths.from_repo_root().root).resolve()


def load_task_registry(root: Path | None = None) -> dict[str, Any]:
    path = _root(root) / TASK_REGISTRY_REL
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_task_registry(payload)
    return payload


def load_field_responsibility_registry(root: Path | None = None) -> dict[str, Any]:
    path = _root(root) / FIELD_REGISTRY_REL
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_field_responsibility_registry(payload)
    return payload


def registry_hash(payload: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(dict(payload)))


def validate_task_registry(payload: Mapping[str, Any]) -> None:
    errors: list[str] = []
    if payload.get("registry_id") != "task_conditioned_prediction_tasks_v1":
        errors.append("registry_id mismatch")
    if payload.get("shared_adapter_only") is not True:
        errors.append("shared_adapter_only must be true")
    if payload.get("task_specific_adapter_search_permitted") is not False:
        errors.append("task_specific_adapter_search_permitted must be false")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("tasks must be a non-empty list")
        raise TaskPredictionContractError("; ".join(errors))
    seen: set[str] = set()
    for task in tasks:
        tid = str(task.get("task_id"))
        if tid in seen:
            errors.append(f"duplicate_task_id:{tid}")
        seen.add(tid)
        if not isinstance(task.get("json_schema"), dict):
            errors.append(f"{tid}: missing json_schema")
        if not task.get("prompt_contract_identity"):
            errors.append(f"{tid}: missing prompt_contract_identity")
        if not isinstance(task.get("owned_production_fields"), list):
            errors.append(f"{tid}: owned_production_fields required")
    if errors:
        raise TaskPredictionContractError(
            "invalid task registry:\n- " + "\n- ".join(errors)
        )


def validate_field_responsibility_registry(payload: Mapping[str, Any]) -> None:
    errors: list[str] = []
    if payload.get("registry_id") != "t27c_field_responsibility_registry_v1":
        errors.append("registry_id mismatch")
    if payload.get("assembler_version") != ASSEMBLER_VERSION:
        errors.append("assembler_version mismatch")
    fields = payload.get("fields")
    if not isinstance(fields, list) or not fields:
        errors.append("fields must be a non-empty list")
    model_owners: dict[str, str] = {}
    for item in fields or []:
        path = str(item.get("field_path"))
        owner = str(item.get("owner"))
        if owner == "model_task_output":
            task = item.get("required_task_id")
            if not task:
                errors.append(f"{path}: model_task_output requires required_task_id")
            prior = model_owners.get(path)
            if prior and prior != task:
                conflict = item.get("conflict_rule")
                if conflict in (None, "", "reject_duplicate_or_mismatch"):
                    # allowed if conflict rule present; still track
                    pass
                else:
                    errors.append(f"{path}: dual model owners {prior} vs {task}")
            model_owners[path] = str(task)
        if owner in {
            "deterministic_derived",
            "runner_owned",
            "provider_provenance",
            "unsupported_for_t27c",
            "forbidden_to_fabricate",
        }:
            if item.get("required_task_id") not in (None, ""):
                errors.append(f"{path}: non-model owner must not set required_task_id")
    forbidden = set(payload.get("model_must_not_emit") or [])
    for path, task in model_owners.items():
        if path in forbidden:
            errors.append(f"{path}: listed in model_must_not_emit but owned by {task}")
    if errors:
        raise TaskPredictionContractError(
            "invalid field responsibility registry:\n- " + "\n- ".join(errors)
        )


def get_task_spec(registry: Mapping[str, Any], task_id: str) -> dict[str, Any]:
    for task in registry.get("tasks") or []:
        if task.get("task_id") == task_id:
            return dict(task)
    raise TaskPredictionContractError(f"unknown_task_id:{task_id}")


def task_schema_hash(task_spec: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(task_spec["json_schema"]))


def build_task_prompt(
    *,
    task_spec: Mapping[str, Any],
    command: str,
    scene_context: str | None = None,
    dialogue_history: Sequence[str] | None = None,
    capability_context: str | None = None,
    analysis_variant: str = "full_context",
) -> str:
    """Build a pinned task prompt that clearly identifies the task ID."""
    task_id = str(task_spec["task_id"])
    purpose = str(task_spec.get("purpose") or "")
    schema = task_spec["json_schema"]
    schema_text = json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2)
    history = list(dialogue_history or [])
    lines = [
        f"TASK_ID={task_id}",
        f"PROMPT_CONTRACT={task_spec.get('prompt_contract_identity')}",
        f"ANALYSIS_VARIANT={analysis_variant}",
        f"PURPOSE={purpose}",
        "Emit ONLY a single JSON object matching the task schema.",
        "Do not emit prose, markdown, or fields outside the task schema.",
        "Do not emit routing, provenance, runner, or other production-envelope fields.",
        "TASK_JSON_SCHEMA=",
        schema_text,
        "COMMAND=",
        command.strip(),
    ]
    if analysis_variant == "full_context":
        if scene_context:
            lines.extend(["SCENE_CONTEXT=", str(scene_context)])
        if history:
            lines.append("DIALOGUE_HISTORY=")
            lines.extend(f"- {h}" for h in history)
        if capability_context:
            lines.extend(["CAPABILITY_CONTEXT=", str(capability_context)])
    else:
        lines.append("CONTEXT_MODE=context_blind")
    lines.append("JSON_OUTPUT=")
    return "\n".join(lines)


def render_qwen_task_prompt(tokenizer: Any, task_prompt: str) -> str:
    """Render the frozen task prompt with the pinned Qwen3 chat contract."""
    if not callable(getattr(tokenizer, "apply_chat_template", None)):
        raise TaskPredictionContractError("qwen_chat_template_unavailable")
    rendered = tokenizer.apply_chat_template(
        [{"role": "user", "content": str(task_prompt)}],
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    if not isinstance(rendered, str) or not rendered:
        raise TaskPredictionContractError("qwen_chat_template_empty")
    return rendered


def build_task_prediction_request(
    *,
    record_id: str,
    task_spec: Mapping[str, Any],
    command: str,
    base_model_identity: str,
    adapter_identity: str | None,
    generation_config: Mapping[str, Any],
    scene_context: str | None = None,
    dialogue_history: Sequence[str] | None = None,
    capability_context: str | None = None,
    analysis_variant: str = "full_context",
) -> TaskPredictionRequest:
    prompt = build_task_prompt(
        task_spec=task_spec,
        command=command,
        scene_context=scene_context,
        dialogue_history=dialogue_history,
        capability_context=capability_context,
        analysis_variant=analysis_variant,
    )
    input_payload = {
        "record_id": record_id,
        "command": command,
        "scene_context": scene_context,
        "dialogue_history": list(dialogue_history or []),
        "capability_context": capability_context,
        "analysis_variant": analysis_variant,
    }
    gen = dict(generation_config)
    return TaskPredictionRequest(
        record_id=record_id,
        task_id=str(task_spec["task_id"]),
        task_version=str(task_spec.get("task_version") or "1.0.0"),
        model_input=prompt,
        input_hash=sha256_hex(canonical_json_bytes(input_payload)),
        prompt_contract=str(task_spec.get("prompt_contract_identity")),
        base_model_identity=base_model_identity,
        adapter_identity=adapter_identity,
        generation_config=gen,
        prompt_hash=sha256_hex(prompt.encode("utf-8")),
        schema_hash=task_schema_hash(task_spec),
        generation_config_hash=sha256_hex(canonical_json_bytes(gen)),
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    if not raw:
        return None
    # Prefer fenced or first object.
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        return None
    snippet = raw[start : end + 1]
    try:
        payload = json.loads(snippet)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def validate_task_schema(
    task_spec: Mapping[str, Any], parsed: Mapping[str, Any]
) -> list[str]:
    """Validate parsed output against the task JSON schema."""
    from jsonschema import Draft202012Validator

    schema = task_spec["json_schema"]
    validator = Draft202012Validator(schema)
    return [
        f"{'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
        for err in sorted(validator.iter_errors(dict(parsed)), key=lambda e: list(e.path))
    ]


def validate_task_semantics(
    task_spec: Mapping[str, Any], parsed: Mapping[str, Any]
) -> list[str]:
    """Semantic checks beyond JSON Schema (enums already covered by schema)."""
    errors: list[str] = []
    task_id = str(task_spec["task_id"])
    owned = set(task_spec.get("owned_production_fields") or [])
    extra = set(parsed) - owned - set(task_spec.get("optional_fields") or []) - set(
        task_spec.get("required_fields") or []
    )
    # Allow only keys declared in schema properties.
    schema_props = set((task_spec.get("json_schema") or {}).get("properties") or {})
    extra = set(parsed) - schema_props
    if extra:
        errors.append(f"unexpected_fields:{sorted(extra)}")

    if task_id == "predict_cpc_v1":
        cpc = parsed.get("cpc")
        if not isinstance(cpc, dict):
            errors.append("cpc_must_be_object")
        else:
            missing = [n for n in CPC_SLOT_NAMES if n not in cpc]
            if missing:
                errors.append(f"cpc_missing_slots:{missing}")
            unknown = [k for k in cpc if k not in CPC_SLOT_NAMES]
            if unknown:
                errors.append(f"cpc_unknown_slots:{unknown}")
            for name, slot in cpc.items():
                if not isinstance(slot, dict):
                    errors.append(f"cpc.{name}_not_object")
                    continue
                status = slot.get("status")
                value = slot.get("value")
                if status == "filled" and (value is None or value == ""):
                    errors.append(f"cpc.{name}_filled_without_value")

    if task_id == "predict_ambiguity_v1":
        present = parsed.get("ambiguity_present")
        types = parsed.get("ambiguity_types") or []
        primary = parsed.get("primary_ambiguity_type")
        if present is False and types:
            errors.append("ambiguity_present_false_with_types")
        if present is True and not types:
            errors.append("ambiguity_present_true_without_types")
        if primary is not None and primary not in types:
            errors.append("primary_ambiguity_type_not_in_types")

    if task_id == "predict_interpretations_v1":
        cands = parsed.get("candidate_interpretations") or []
        selected = parsed.get("selected_interpretation")
        ids = {
            c.get("frame_id")
            for c in cands
            if isinstance(c, dict) and isinstance(c.get("frame_id"), str)
        }
        if selected is not None:
            if not isinstance(selected, dict):
                errors.append("selected_interpretation_not_object")
            else:
                fid = selected.get("frame_id")
                if fid not in ids:
                    errors.append("selected_interpretation_not_in_candidates")

    if task_id == "predict_risk_capability_v1":
        # Missing must not become fabricated safe/capable at this layer; values
        # are checked by assembler defaults. Here only require keys present.
        for key in ("risk_relevant", "risk_level", "capability_status"):
            if key not in parsed:
                errors.append(f"missing_{key}")

    # Safety: task must not emit forbidden production fields.
    forbidden_hits = sorted(
        k
        for k in parsed
        if k
        in {
            "recommended_strategy",
            "strategy_sequence",
            "compound_ambiguity",
            "compound_ambiguity_count",
            "analysis_provenance",
            "execution_status",
            "result_hash",
            "run_mode",
        }
    )
    if forbidden_hits:
        errors.append(f"forbidden_fields_emitted:{forbidden_hits}")
    return errors


def evaluate_task_output(
    *,
    request: TaskPredictionRequest,
    task_spec: Mapping[str, Any],
    raw_text: str,
    constraint_initialised: bool,
    transport_status: str = "generated",
) -> TaskPredictionResult:
    failures: list[str] = []
    if not constraint_initialised:
        failures.append("constraint_not_initialised")
        return TaskPredictionResult(
            record_id=request.record_id,
            task_id=request.task_id,
            task_version=request.task_version,
            raw_attempts=(raw_text,),
            parsed_output=None,
            transport_status=transport_status,
            parse_status="not_attempted",
            schema_status="not_attempted",
            semantic_status="not_attempted",
            safety_status="rejected",
            final_status="rejected",
            task_provenance={
                "prompt_hash": request.prompt_hash,
                "schema_hash": request.schema_hash,
                "cache_identity": request.cache_identity(),
            },
            output_hash=None,
            failure_details=tuple(failures),
            constraint_initialised=False,
        )

    parsed = _extract_json_object(raw_text)
    if parsed is None:
        return TaskPredictionResult(
            record_id=request.record_id,
            task_id=request.task_id,
            task_version=request.task_version,
            raw_attempts=(raw_text,),
            parsed_output=None,
            transport_status=transport_status,
            parse_status="failed",
            schema_status="not_attempted",
            semantic_status="not_attempted",
            safety_status="rejected",
            final_status="rejected",
            task_provenance={
                "prompt_hash": request.prompt_hash,
                "schema_hash": request.schema_hash,
                "cache_identity": request.cache_identity(),
            },
            output_hash=None,
            failure_details=("no_json_or_parse_failure",),
            constraint_initialised=True,
        )

    schema_errors = validate_task_schema(task_spec, parsed)
    semantic_errors = validate_task_semantics(task_spec, parsed)
    schema_status = "valid" if not schema_errors else "invalid"
    semantic_status = "valid" if not semantic_errors else "invalid"
    safety_status = "accepted" if not schema_errors and not semantic_errors else "rejected"
    final = "accepted" if safety_status == "accepted" else "rejected"
    output_hash = sha256_hex(canonical_json_bytes(parsed))
    return TaskPredictionResult(
        record_id=request.record_id,
        task_id=request.task_id,
        task_version=request.task_version,
        raw_attempts=(raw_text,),
        parsed_output=parsed,
        transport_status=transport_status,
        parse_status="valid",
        schema_status=schema_status,
        semantic_status=semantic_status,
        safety_status=safety_status,
        final_status=final,
        task_provenance={
            "prompt_hash": request.prompt_hash,
            "schema_hash": request.schema_hash,
            "cache_identity": request.cache_identity(output_hash=output_hash),
            "base_model_identity": request.base_model_identity,
            "adapter_identity": request.adapter_identity,
        },
        output_hash=output_hash,
        failure_details=tuple(schema_errors + semantic_errors),
        constraint_initialised=True,
    )


def assert_task_results_not_cross_reused(
    results: Sequence[TaskPredictionResult],
) -> None:
    """Guard: never treat a successful prediction as valid for another task ID."""
    by_key: dict[tuple[str, str], TaskPredictionResult] = {}
    for result in results:
        key = (result.record_id, result.task_id)
        if key in by_key:
            raise TaskPredictionContractError(
                f"duplicate_task_result:{result.record_id}:{result.task_id}"
            )
        by_key[key] = result
