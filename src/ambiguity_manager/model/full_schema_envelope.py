"""Full production-schema training envelope (T27B).

CPU-only. Does not import torch, transformers, peft, bitsandbytes, accelerate,
vllm, or requests at module import time.

Every training target uses the same complete production-compatible structural
envelope (``full_schema_envelope_v1``). Structural tokens are supervised;
strong/weak semantic values are supervised per eligibility; unavailable
semantic value tokens are masked later (-100). No fabricated supervised labels.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.prediction_contract import (
    MODEL_OUTPUT_REQUIRED_FIELDS,
    SemanticPayloadError,
    runner_owned_prediction_fields,
    validate_semantic_payload,
)
from ambiguity_manager.model.training_target_packaging import (
    TrainingTargetPackage,
    build_training_target_package,
    load_training_target_policy_strict,
)
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES, CPCSlotStatus, RouteLabel

FULL_SCHEMA_ENVELOPE_ID = "full_schema_envelope_v1"
PROMPT_CONTRACT_VERSION = "t27b_full_schema_prompt_v1"
ENVELOPE_POLICY_REL = "configs/model/full_schema_envelope_policy_v1.json"

SEGMENT_KINDS = frozenset(
    {
        "structural",
        "field_name",
        "supervised_value",
        "weak_value",
        "unavailable_value",
        "separator",
    }
)

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "intent_summary": ("intent_summary", "intent"),
    "clarification_question": ("clarification_question", "gold_clarification_question"),
    "cpc": ("cpc", "slots"),
}

_ALWAYS_MASKED = frozenset(
    {
        "unresolved_slots",
        "supporting_evidence",
        "resolved_slots",
        "resolution_method",
        "resolution_evidence",
        "context_sampling_uncertainty",
    }
)

TRAINING_TO_PRODUCTION_MAPPING: dict[str, Any] = {
    "training_envelope": FULL_SCHEMA_ENVELOPE_ID,
    "production_schema": "t12_model_semantic_output",
    "rule": (
        "Every training target is a complete 25-field production-shaped JSON object. "
        "Structural and field-name tokens are supervised. Eligible/weakly_eligible "
        "semantic value tokens retain IDs. Unavailable semantic value tokens are "
        "present as schema-valid fillers but masked from the loss (-100). "
        "Inference uses the same production schema via validate_semantic_payload."
    ),
    "omitted_field_policy": "never_omit_keys_mask_unavailable_values",
    "fabricated_nulls_forbidden_as_supervised_labels": True,
    "runner_owned_forbidden_in_target": True,
    "label_eligibility_forbidden_in_target": True,
    "prompt_contract_version": PROMPT_CONTRACT_VERSION,
}


class FullSchemaEnvelopeError(RuntimeError):
    """Raised when a full-schema envelope cannot be built safely."""


@dataclass(frozen=True)
class FieldSpan:
    field_path: str
    field_group: str | None
    supervision: str  # supervised | weak | unavailable_masked
    char_start: int
    char_end: int
    json_fragment: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "field_group": self.field_group,
            "supervision": self.supervision,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "json_fragment": self.json_fragment,
        }


@dataclass(frozen=True)
class EnvelopeSegment:
    kind: str
    text: str
    char_start: int
    char_end: int
    field_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "text": self.text,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "field_path": self.field_path,
        }


@dataclass(frozen=True)
class FullSchemaEnvelope:
    envelope_id: str
    fields: dict[str, Any]
    supervised_fields: tuple[str, ...]
    weakly_eligible_fields: tuple[str, ...]
    unavailable_fields: tuple[str, ...]
    field_spans: tuple[FieldSpan, ...]
    segments: tuple[EnvelopeSegment, ...]
    canonical_json: str
    target_hash: str
    field_group_status: dict[str, str]
    per_field_supervision: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "fields": dict(self.fields),
            "supervised_fields": list(self.supervised_fields),
            "weakly_eligible_fields": list(self.weakly_eligible_fields),
            "unavailable_fields": list(self.unavailable_fields),
            "field_spans": [span.to_dict() for span in self.field_spans],
            "segments": [seg.to_dict() for seg in self.segments],
            "canonical_json": self.canonical_json,
            "target_hash": self.target_hash,
            "field_group_status": dict(self.field_group_status),
            "per_field_supervision": dict(self.per_field_supervision),
            "training_to_production_mapping": TRAINING_TO_PRODUCTION_MAPPING,
        }


def load_envelope_policy(path: Path | None = None) -> dict[str, Any]:
    target = path
    if target is None:
        target = ProjectPaths.from_repo_root().root / ENVELOPE_POLICY_REL
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("envelope_id") != FULL_SCHEMA_ENVELOPE_ID:
        raise FullSchemaEnvelopeError("envelope_policy_id_mismatch")
    return payload


def _empty_cpc() -> dict[str, Any]:
    slot = {"status": CPCSlotStatus.UNKNOWN.value, "value": None}
    return {name: dict(slot) for name in CPC_SLOT_NAMES}


def _unavailable_baseline() -> dict[str, Any]:
    """Schema-valid production-shaped filler (mirrors test_t12_prediction_contract)."""
    return {
        "cpc": _empty_cpc(),
        "speech_act": None,
        "intent_summary": None,
        "candidate_interpretations": [],
        "selected_interpretation": None,
        "unresolved_slots": [],
        "supporting_evidence": [],
        "ambiguity_present": False,
        "ambiguity_types": [],
        "primary_ambiguity_type": None,
        "compound_ambiguity": False,
        "compound_ambiguity_count": 0,
        "risk_relevant": False,
        "risk_level": None,
        "capability_status": None,
        "recommended_strategy": RouteLabel.EXECUTE.value,
        "strategy_sequence": [],
        "clarification_question": None,
        "clarification_subtype": None,
        "clarification_targets": [],
        "rejection_reason": None,
        "resolved_slots": [],
        "resolution_method": None,
        "resolution_evidence": [],
        "context_sampling_uncertainty": None,
    }


def _resolve_field_value(record: Mapping[str, Any], field_name: str) -> Any:
    aliases = _FIELD_ALIASES.get(field_name, (field_name,))
    for alias in aliases:
        if alias in record:
            return record.get(alias)
    return None


def _normalise_cpc(value: Any) -> dict[str, Any]:
    base = _empty_cpc()
    if not isinstance(value, dict):
        return base
    for name in CPC_SLOT_NAMES:
        raw = value.get(name)
        if isinstance(raw, dict):
            status = raw.get("status", CPCSlotStatus.UNKNOWN.value)
            if status not in {s.value for s in CPCSlotStatus}:
                status = CPCSlotStatus.UNKNOWN.value
            slot_value = raw.get("value", None)
            base[name] = {"status": status, "value": slot_value}
        elif raw is not None:
            base[name] = {"status": CPCSlotStatus.FILLED.value, "value": raw}
    return base


def _canonical_candidate_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    items = list(value)

    def _key(item: Any) -> str:
        return json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    return sorted(items, key=_key)


def _field_group_for(field_name: str, training_policy: Mapping[str, Any]) -> str | None:
    for spec in training_policy.get("field_groups", []):
        sources = [str(x) for x in spec.get("source_fields", [])]
        for source in sources:
            base = source[:-2] if source.endswith(".*") else source
            if base == field_name:
                return str(spec["field_group"])
    return None


def _group_status_map(package: TrainingTargetPackage) -> dict[str, str]:
    return {group.field_group: group.eligibility_status for group in package.field_groups}


def _is_usable_value(field_name: str, value: Any) -> bool:
    if value is None:
        return False
    if field_name == "cpc":
        if not isinstance(value, dict) or not value:
            return False
        return any(
            isinstance(slot, dict)
            and (
                slot.get("status") == CPCSlotStatus.FILLED.value
                or slot.get("value") not in (None, "")
            )
            for slot in value.values()
        )
    return True


def _assert_no_admin(fields: Mapping[str, Any]) -> None:
    forbidden = sorted(set(fields) & runner_owned_prediction_fields())
    if forbidden:
        raise FullSchemaEnvelopeError(f"runner_owned_fields_in_target:{forbidden}")
    if "label_eligibility" in fields:
        raise FullSchemaEnvelopeError("label_eligibility_forbidden_in_target")
    for key in ("id", "source_dataset", "source_id", "group_id", "split", "eligibility"):
        if key in fields:
            raise FullSchemaEnvelopeError(f"admin_key_in_target:{key}")


class _SegmentWriter:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.segments: list[EnvelopeSegment] = []
        self.cursor = 0

    def add(self, kind: str, text: str, *, field_path: str | None = None) -> None:
        if kind not in SEGMENT_KINDS:
            raise FullSchemaEnvelopeError(f"unknown_segment_kind:{kind}")
        start = self.cursor
        end = start + len(text)
        self.parts.append(text)
        self.segments.append(
            EnvelopeSegment(
                kind=kind,
                text=text,
                char_start=start,
                char_end=end,
                field_path=field_path,
            )
        )
        self.cursor = end

    def text(self) -> str:
        return "".join(self.parts)


def _json_dump_leaf(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _emit_value(
    writer: _SegmentWriter,
    value: Any,
    *,
    value_kind: str,
    field_path: str,
) -> None:
    if isinstance(value, dict):
        writer.add("structural", "{", field_path=field_path)
        items = sorted(value.items(), key=lambda item: item[0])
        for index, (key, child) in enumerate(items):
            if index > 0:
                writer.add("structural", ", ", field_path=field_path)
            writer.add("field_name", _json_dump_leaf(key), field_path=f"{field_path}.{key}")
            writer.add("structural", ": ", field_path=field_path)
            _emit_value(writer, child, value_kind=value_kind, field_path=f"{field_path}.{key}")
        writer.add("structural", "}", field_path=field_path)
        return
    if isinstance(value, list):
        writer.add("structural", "[", field_path=field_path)
        for index, child in enumerate(value):
            if index > 0:
                writer.add("structural", ", ", field_path=field_path)
            _emit_value(writer, child, value_kind=value_kind, field_path=f"{field_path}[{index}]")
        writer.add("structural", "]", field_path=field_path)
        return
    writer.add(value_kind, _json_dump_leaf(value), field_path=field_path)


def _value_kind_for(supervision: str) -> str:
    if supervision == "supervised":
        return "supervised_value"
    if supervision == "weak":
        return "weak_value"
    return "unavailable_value"


def _serialize_envelope(
    fields: Mapping[str, Any],
    per_field_supervision: Mapping[str, str],
) -> tuple[str, tuple[EnvelopeSegment, ...], tuple[FieldSpan, ...]]:
    writer = _SegmentWriter()
    spans: list[FieldSpan] = []
    ordered_names = sorted(MODEL_OUTPUT_REQUIRED_FIELDS)
    writer.add("structural", "{")
    for index, name in enumerate(ordered_names):
        if index > 0:
            writer.add("structural", ", ")
        field_start = writer.cursor
        writer.add("field_name", _json_dump_leaf(name), field_path=name)
        writer.add("structural", ": ")
        supervision = per_field_supervision[name]
        _emit_value(
            writer,
            fields[name],
            value_kind=_value_kind_for(supervision),
            field_path=name,
        )
        value_end = writer.cursor
        fragment = writer.text()[field_start:value_end]
        spans.append(
            FieldSpan(
                field_path=name,
                field_group=None,
                supervision=(
                    "supervised"
                    if supervision == "supervised"
                    else ("weak" if supervision == "weak" else "unavailable_masked")
                ),
                char_start=field_start,
                char_end=value_end,
                json_fragment=fragment,
            )
        )
    writer.add("structural", "}")
    canonical = writer.text()
    reference = json.dumps(dict(fields), ensure_ascii=False, sort_keys=True)
    if canonical != reference:
        raise FullSchemaEnvelopeError(
            f"canonical_json_mismatch: expected={reference!r} got={canonical!r}"
        )
    rebuilt = "".join(seg.text for seg in writer.segments)
    if rebuilt != canonical:
        raise FullSchemaEnvelopeError("segment_reconstruction_mismatch")
    return canonical, tuple(writer.segments), tuple(spans)


def _reject_unsafe_route_overlay(fields: Mapping[str, Any], supervised: Mapping[str, str]) -> None:
    route = fields.get("recommended_strategy")
    route_sup = supervised.get("recommended_strategy")
    if route_sup not in {"supervised", "weak"}:
        return
    if route == RouteLabel.CLARIFY.value:
        q_ok = supervised.get("clarification_question") in {"supervised", "weak"} and bool(
            fields.get("clarification_question")
        )
        t_ok = supervised.get("clarification_targets") in {"supervised", "weak"} and bool(
            fields.get("clarification_targets")
        )
        if not (q_ok and t_ok):
            raise FullSchemaEnvelopeError("unsafe_route_overlay:clarify_missing_clarification")
    if route == RouteLabel.FACE_PRESERVING_REJECTION.value:
        if supervised.get("rejection_reason") not in {"supervised", "weak"} or not fields.get(
            "rejection_reason"
        ):
            raise FullSchemaEnvelopeError("unsafe_route_overlay:rejection_missing_reason")
    if route == RouteLabel.SILENTLY_RESOLVE.value:
        raise FullSchemaEnvelopeError("unsafe_route_overlay:silently_resolve_unsupported")
    if route == RouteLabel.MULTI_STEP.value:
        seq = fields.get("strategy_sequence")
        if supervised.get("strategy_sequence") not in {"supervised", "weak"} or not (
            isinstance(seq, list) and len(seq) >= 2
        ):
            raise FullSchemaEnvelopeError("unsafe_route_overlay:multi_step_missing_sequence")


def build_full_schema_envelope(
    record: Mapping[str, Any],
    eligibility: Mapping[str, str],
    *,
    policy: Mapping[str, Any] | None = None,
    training_policy: Mapping[str, Any] | None = None,
    package: TrainingTargetPackage | None = None,
    require_production_validation: bool = True,
    emit_segments: bool = True,
) -> FullSchemaEnvelope:
    """Build a complete production-shaped envelope with typed segments."""
    envelope_policy = dict(policy) if policy is not None else load_envelope_policy()
    resolved_training = (
        dict(training_policy)
        if training_policy is not None
        else load_training_target_policy_strict()
    )
    resolved_package = package or build_training_target_package(
        dict(record), dict(eligibility), policy=resolved_training
    )
    group_status = _group_status_map(resolved_package)
    decisions = envelope_policy.get("field_decisions") or {}

    fields = _unavailable_baseline()
    per_field_supervision: dict[str, str] = {
        name: "unavailable" for name in sorted(MODEL_OUTPUT_REQUIRED_FIELDS)
    }
    supervised_names: list[str] = []
    weakly_names: list[str] = []
    unavailable_names: list[str] = []

    for name in sorted(MODEL_OUTPUT_REQUIRED_FIELDS):
        decision = decisions.get(name) or {}
        treatment = str(decision.get("treatment") or "masked_unavailable_envelope")
        group = _field_group_for(name, resolved_training) or decision.get("field_group")
        status = group_status.get(str(group)) if group else None

        if name in _ALWAYS_MASKED or treatment == "masked_unavailable_envelope":
            unavailable_names.append(name)
            per_field_supervision[name] = "unavailable"
            continue

        if status not in {"eligible", "weakly_eligible"}:
            unavailable_names.append(name)
            per_field_supervision[name] = "unavailable"
            continue

        raw = _resolve_field_value(record, name)
        if name == "cpc":
            raw = _normalise_cpc(raw) if raw is not None else None
        if name == "candidate_interpretations" and raw is not None:
            raw = _canonical_candidate_list(raw)
        if not _is_usable_value(name, raw):
            unavailable_names.append(name)
            per_field_supervision[name] = "unavailable"
            continue

        fields[name] = raw if name != "cpc" else _normalise_cpc(raw)
        if status == "weakly_eligible":
            per_field_supervision[name] = "weak"
            weakly_names.append(name)
            supervised_names.append(name)
        else:
            per_field_supervision[name] = "supervised"
            supervised_names.append(name)

    if (
        per_field_supervision.get("compound_ambiguity") in {"supervised", "weak"}
        and fields.get("compound_ambiguity") is True
    ):
        types = fields.get("ambiguity_types") or []
        count = int(fields.get("compound_ambiguity_count") or 0)
        if not (isinstance(types, list) and len(types) >= 2 and count >= 2):
            raise FullSchemaEnvelopeError("unsafe_compound_overlay")

    if not supervised_names:
        raise FullSchemaEnvelopeError(
            f"zero_semantic_supervised_fields:{resolved_package.record_id}"
        )

    _reject_unsafe_route_overlay(fields, per_field_supervision)
    _assert_no_admin(fields)

    if require_production_validation:
        try:
            validate_semantic_payload(dict(fields))
        except SemanticPayloadError as exc:
            raise FullSchemaEnvelopeError(f"envelope_not_production_compatible:{exc}") from exc

    ordered_fields = {name: fields[name] for name in sorted(MODEL_OUTPUT_REQUIRED_FIELDS)}
    if emit_segments:
        canonical_json, segments, spans = _serialize_envelope(fields, per_field_supervision)
        enriched_spans: list[FieldSpan] = []
        for span in spans:
            group = _field_group_for(span.field_path, resolved_training)
            enriched_spans.append(
                FieldSpan(
                    field_path=span.field_path,
                    field_group=group,
                    supervision=span.supervision,
                    char_start=span.char_start,
                    char_end=span.char_end,
                    json_fragment=span.json_fragment,
                )
            )
    else:
        canonical_json = json.dumps(ordered_fields, ensure_ascii=False, sort_keys=True)
        segments = tuple()
        enriched_spans = []

    target_hash = sha256_hex(
        canonical_json_bytes(
            {
                "envelope_id": FULL_SCHEMA_ENVELOPE_ID,
                "fields": ordered_fields,
            }
        )
    )
    return FullSchemaEnvelope(
        envelope_id=FULL_SCHEMA_ENVELOPE_ID,
        fields=ordered_fields,
        supervised_fields=tuple(sorted(set(supervised_names))),
        weakly_eligible_fields=tuple(sorted(set(weakly_names))),
        unavailable_fields=tuple(sorted(set(unavailable_names))),
        field_spans=tuple(enriched_spans),
        segments=segments,
        canonical_json=canonical_json,
        target_hash=target_hash,
        field_group_status=group_status,
        per_field_supervision={
            name: (
                "supervised"
                if per_field_supervision[name] == "supervised"
                else (
                    "weakly_supervised"
                    if per_field_supervision[name] == "weak"
                    else "unavailable_masked"
                )
            )
            for name in sorted(MODEL_OUTPUT_REQUIRED_FIELDS)
        },
    )


def validate_envelope_against_production_shape(payload: Mapping[str, Any] | str) -> dict[str, Any]:
    """Parse envelope JSON and require all model-owned keys; prefer full semantic validity."""
    if isinstance(payload, str):
        parsed = json.loads(payload)
    else:
        parsed = dict(payload)
    if not isinstance(parsed, dict):
        raise FullSchemaEnvelopeError("envelope_must_be_object")
    missing = sorted(MODEL_OUTPUT_REQUIRED_FIELDS - set(parsed))
    if missing:
        raise FullSchemaEnvelopeError(f"missing_required_fields:{missing}")
    extra = sorted(set(parsed) - MODEL_OUTPUT_REQUIRED_FIELDS)
    if extra:
        raise FullSchemaEnvelopeError(f"unknown_fields:{extra}")
    cpc = parsed.get("cpc")
    if not isinstance(cpc, dict) or set(cpc) != set(CPC_SLOT_NAMES):
        raise FullSchemaEnvelopeError("invalid_cpc_shape")
    validate_semantic_payload(parsed)
    return parsed
