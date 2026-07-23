"""Deterministic structured training-target serialisation (T27 task-aligned).

Produces a versioned training-target representation containing only fields
authorised by the training-target policy for a given record. Unavailable and
ineligible field groups are omitted from the learned target (never fabricated
as null/empty/negative labels). Provenance and eligibility stay outside the
target object.

Mapping to the production model-facing semantic schema is documented in
``TRAINING_TO_PRODUCTION_MAPPING``: supervised fields map 1:1 by name; omitted
fields must not be treated as negatives during training; at inference the
full production schema is required and is validated separately.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.prediction_contract import (
    MODEL_OUTPUT_REQUIRED_FIELDS,
    runner_owned_prediction_fields,
)
from ambiguity_manager.model.training_target_packaging import (
    TrainingTargetPackage,
    build_training_target_package,
    load_training_target_policy_strict,
)

TRAINING_TARGET_SCHEMA = "training_semantic_target_v1"
PROMPT_CONTRACT_VERSION = "t27_task_aligned_prompt_v1"
TRAINING_EXAMPLE_SCHEMA_VERSION = "1.0.0"

# Field groups whose source values may live under alternate record keys.
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "intent_summary": ("intent_summary", "intent"),
    "clarification_question": ("clarification_question", "gold_clarification_question"),
    "cpc": ("cpc", "slots"),
}

TRAINING_TO_PRODUCTION_MAPPING: dict[str, Any] = {
    "training_schema": TRAINING_TARGET_SCHEMA,
    "production_schema": "t12_model_semantic_output",
    "rule": (
        "Each supervised key in training_semantic_target_v1.fields maps by exact "
        "name into the production model-owned semantic payload. Fields omitted "
        "from the training target because they are unavailable/ineligible are "
        "not negatives and must not appear in the causal-LM loss. At inference "
        "the model must emit the full production schema; validation uses "
        "validate_semantic_payload, not the partial training representation."
    ),
    "omitted_field_policy": "exclude_from_target_and_loss",
    "fabricated_nulls_forbidden": True,
    "runner_owned_forbidden_in_target": True,
    "label_eligibility_forbidden_in_target": True,
}


class StructuredTargetError(RuntimeError):
    """Raised when a structured training target cannot be built safely."""


@dataclass(frozen=True)
class FieldSpan:
    field_name: str
    field_group: str
    supervision: str  # supervised | unavailable_masked | omitted
    char_start: int
    char_end: int
    json_fragment: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "field_group": self.field_group,
            "supervision": self.supervision,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "json_fragment": self.json_fragment,
        }


@dataclass(frozen=True)
class StructuredTarget:
    schema: str
    fields: dict[str, Any]
    supervised_fields: tuple[str, ...]
    unavailable_fields: tuple[str, ...]
    weakly_eligible_fields: tuple[str, ...]
    field_spans: tuple[FieldSpan, ...]
    canonical_json: str
    target_hash: str
    field_group_status: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "fields": dict(self.fields),
            "supervised_fields": list(self.supervised_fields),
            "unavailable_fields": list(self.unavailable_fields),
            "weakly_eligible_fields": list(self.weakly_eligible_fields),
            "field_spans": [span.to_dict() for span in self.field_spans],
            "canonical_json": self.canonical_json,
            "target_hash": self.target_hash,
            "field_group_status": dict(self.field_group_status),
            "training_to_production_mapping": TRAINING_TO_PRODUCTION_MAPPING,
        }


def _resolve_field_value(record: Mapping[str, Any], field_name: str) -> Any:
    if field_name.endswith(".*"):
        base = field_name[:-2]
        aliases = _FIELD_ALIASES.get(base, (base,))
        for alias in aliases:
            if alias in record:
                return record.get(alias)
        return None
    aliases = _FIELD_ALIASES.get(field_name, (field_name,))
    for alias in aliases:
        if alias in record:
            return record.get(alias)
    return None


def _canonical_enum_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        # Preserve semantic order for ordered lists; sort only free-form string sets
        # when the list is a multi-label type bag (ambiguity_types).
        return list(value)
    return value


def _assert_no_runner_owned(fields: Mapping[str, Any]) -> None:
    forbidden = sorted(set(fields) & runner_owned_prediction_fields())
    if forbidden:
        raise StructuredTargetError(f"runner_owned_fields_in_target:{forbidden}")
    if "label_eligibility" in fields:
        raise StructuredTargetError("label_eligibility_forbidden_in_target")


def _serialize_field_fragment(name: str, value: Any) -> str:
    return json.dumps({name: _canonical_enum_value(value)}, ensure_ascii=False, sort_keys=True)[1:-1]


def build_structured_target(
    record: Mapping[str, Any],
    eligibility: Mapping[str, str],
    *,
    policy: Mapping[str, Any] | None = None,
    package: TrainingTargetPackage | None = None,
) -> StructuredTarget:
    """Build a canonical partial training target from authorised field groups only."""
    resolved_policy = dict(policy) if policy is not None else load_training_target_policy_strict()
    resolved_package = package or build_training_target_package(
        dict(record), dict(eligibility), policy=resolved_policy
    )

    supervised: dict[str, Any] = {}
    supervised_names: list[str] = []
    weakly: list[str] = []
    unavailable: list[str] = []
    group_status: dict[str, str] = {}
    spans: list[FieldSpan] = []

    # Emit as compact canonical object with stable key ordering across supervised fields.
    fragments: list[str] = []
    # Opening brace
    body_parts: list[tuple[str, str, str, str]] = []  # name, group, status, fragment

    source_fields_by_group = {
        str(spec["field_group"]): list(spec["source_fields"])
        for spec in resolved_policy["field_groups"]
    }
    for group in resolved_package.field_groups:
        group_status[group.field_group] = group.eligibility_status
        for source_field in source_fields_by_group.get(group.field_group, []):
            field_name = source_field[:-2] if source_field.endswith(".*") else source_field
            if group.masked or group.loss_weight <= 0.0:
                unavailable.append(field_name)
                continue
            value = _resolve_field_value(record, source_field)
            # Do not fabricate values when the authorised group has no usable value.
            if value is None:
                unavailable.append(field_name)
                continue
            if isinstance(value, list) and len(value) == 0 and group.eligibility_status == "unavailable":
                unavailable.append(field_name)
                continue
            supervised[field_name] = _canonical_enum_value(value)
            supervised_names.append(field_name)
            if group.eligibility_status == "weakly_eligible":
                weakly.append(field_name)
            fragment = _serialize_field_fragment(field_name, supervised[field_name])
            body_parts.append((field_name, group.field_group, "supervised", fragment))

    if not supervised:
        raise StructuredTargetError(
            f"zero_supervised_target_fields:{resolved_package.record_id}"
        )

    _assert_no_runner_owned(supervised)

    # Stable field order by sorted field name for deterministic hashing.
    body_parts.sort(key=lambda item: item[0])
    ordered_fields = {name: supervised[name] for name, _, _, _ in body_parts}

    # Rebuild fragments in sorted order and track character spans inside the full JSON.
    pieces: list[str] = []
    for name, _group, _status, fragment in body_parts:
        pieces.append(fragment)
    inner = ", ".join(pieces)
    canonical_json = "{" + inner + "}"

    # Recompute spans against the final string.
    cursor = 1  # after '{'
    for index, (name, group_name, status, fragment) in enumerate(body_parts):
        if index > 0:
            # account for ", " separator
            cursor += 2
        start = cursor
        end = start + len(fragment)
        spans.append(
            FieldSpan(
                field_name=name,
                field_group=group_name,
                supervision=status,
                char_start=start,
                char_end=end,
                json_fragment=fragment,
            )
        )
        cursor = end

    # Verify reconstruction.
    rebuilt = json.loads(canonical_json)
    if rebuilt != ordered_fields:
        raise StructuredTargetError("canonical_target_reconstruction_mismatch")

    target_hash = sha256_hex(canonical_json_bytes({"schema": TRAINING_TARGET_SCHEMA, "fields": ordered_fields}))
    return StructuredTarget(
        schema=TRAINING_TARGET_SCHEMA,
        fields=ordered_fields,
        supervised_fields=tuple(sorted(ordered_fields)),
        unavailable_fields=tuple(sorted(set(unavailable))),
        weakly_eligible_fields=tuple(sorted(set(weakly))),
        field_spans=tuple(spans),
        canonical_json=canonical_json,
        target_hash=target_hash,
        field_group_status=group_status,
    )


def expand_training_target_to_production_skeleton(target: StructuredTarget) -> dict[str, Any]:
    """Map supervised training fields into a production-shaped dict (documentation/helper).

    Omitted production-required keys are left absent (not null-filled) so callers
    cannot mistake silence for a negative label. This helper is not used as a
    training loss target.
    """
    payload = {name: target.fields[name] for name in target.supervised_fields}
    for name in sorted(MODEL_OUTPUT_REQUIRED_FIELDS):
        if name not in payload:
            continue
    return payload


def validate_training_target_object(payload: Mapping[str, Any]) -> None:
    if payload.get("schema") != TRAINING_TARGET_SCHEMA:
        raise StructuredTargetError("invalid_training_target_schema")
    fields = payload.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise StructuredTargetError("training_target_fields_required")
    _assert_no_runner_owned(fields)
