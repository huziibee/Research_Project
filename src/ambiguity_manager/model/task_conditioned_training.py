"""T27C task-conditioned training example construction (CPU-safe).

Contract: task_conditioned_training_example_v1

Creates one training example per (source_record, task) only when the source
record honestly supports that task. Within a task, every example uses the same
small JSON schema with complete target supervision (no filler masking).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.task_prediction_contract import (
    STRONG_ELIGIBILITY,
    build_task_prompt,
    validate_task_schema,
    validate_task_semantics,
)
from ambiguity_manager.model.token_loss_masking import (
    IGNORE_INDEX,
    SEPARATOR,
    MaskedTrainingSequence,
    TokenSpanMask,
    TokenizerLike,
)
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES

TRAINING_EXAMPLE_SCHEMA = "task_conditioned_training_example_v1"
TRAINING_EXAMPLE_VERSION = "1.0.0"


class TaskConditionedTrainingError(RuntimeError):
    """Raised when a task-conditioned training example cannot be built."""


def _encode(tokenizer: TokenizerLike, text: str, *, add_special_tokens: bool) -> list[int]:
    ids = list(tokenizer.encode(text, add_special_tokens=add_special_tokens))
    return [int(x) for x in ids]


def build_fully_supervised_task_sequence(
    *,
    prompt_text: str,
    target_json: str,
    tokenizer: TokenizerLike,
    max_seq_len: int,
    pad_token_id: int,
) -> MaskedTrainingSequence:
    """Mask prompt+padding; supervise the entire compact task JSON target."""
    if not prompt_text:
        raise TaskConditionedTrainingError("prompt_text_required")
    if not target_json:
        raise TaskConditionedTrainingError("target_json_required")

    prompt_ids = _encode(tokenizer, prompt_text, add_special_tokens=True)
    sep_ids = _encode(tokenizer, SEPARATOR, add_special_tokens=False)
    target_ids = _encode(tokenizer, target_json, add_special_tokens=False)
    if not target_ids:
        raise TaskConditionedTrainingError("empty_target_tokenisation")

    spans = [
        TokenSpanMask("prompt", "prompt", 0, len(prompt_ids), "mask"),
        TokenSpanMask(
            "separator",
            "separator",
            len(prompt_ids),
            len(prompt_ids) + len(sep_ids),
            "mask",
        ),
        TokenSpanMask(
            "task_target",
            "target_supervised",
            len(prompt_ids) + len(sep_ids),
            len(prompt_ids) + len(sep_ids) + len(target_ids),
            "supervise",
        ),
    ]
    input_ids = prompt_ids + sep_ids + target_ids
    labels = [IGNORE_INDEX] * (len(prompt_ids) + len(sep_ids)) + list(target_ids)
    attention = [1] * len(input_ids)

    if len(input_ids) > max_seq_len:
        overflow = len(input_ids) - max_seq_len
        if overflow >= len(prompt_ids):
            raise TaskConditionedTrainingError("sequence_too_long_even_after_prompt_trim")
        input_ids = input_ids[overflow:]
        labels = labels[overflow:]
        attention = attention[overflow:]
        spans = [
            TokenSpanMask(
                span.name,
                span.kind,
                max(0, span.token_start - overflow),
                max(0, span.token_end - overflow),
                span.label_mode,
            )
            for span in spans
            if span.token_end > overflow
        ]

    pad_count = 0
    if len(input_ids) < max_seq_len:
        pad_count = max_seq_len - len(input_ids)
        pad_start = len(input_ids)
        input_ids = input_ids + [pad_token_id] * pad_count
        labels = labels + [IGNORE_INDEX] * pad_count
        attention = attention + [0] * pad_count
        spans.append(
            TokenSpanMask("padding", "padding", pad_start, pad_start + pad_count, "mask")
        )

    supervised = sum(1 for label in labels if label != IGNORE_INDEX)
    if supervised <= 0:
        raise TaskConditionedTrainingError("zero_supervised_target_tokens")

    diagnostics = {
        "total_tokens": len(input_ids),
        "prompt_masked_tokens": sum(
            1 for span in spans if span.kind == "prompt" for _ in range(span.token_end - span.token_start)
        ),
        "target_supervised_tokens": supervised,
        "unavailable_field_masked_tokens": 0,
        "padding_masked_tokens": pad_count,
        "supervised_token_percentage": round(100.0 * supervised / max(1, len(input_ids)), 4),
        "command_reconstruction": False,
        "full_task_target_supervised": True,
    }
    return MaskedTrainingSequence(
        input_ids=tuple(input_ids),
        labels=tuple(labels),
        attention_mask=tuple(attention),
        spans=tuple(spans),
        diagnostics=diagnostics,
    )

@dataclass(frozen=True)
class TaskConditionedTrainingExample:
    payload: dict[str, Any]

    @property
    def training_example_id(self) -> str:
        return str(self.payload["training_example_id"])

    @property
    def task_id(self) -> str:
        return str(self.payload["task_id"])

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


def _canonical_target(fields: Mapping[str, Any], field_order: Sequence[str]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}
    for key in field_order:
        if key in fields:
            ordered[key] = fields[key]
    for key in sorted(fields):
        if key not in ordered:
            ordered[key] = fields[key]
    return ordered


def _normalize_cpc(raw: Any) -> dict[str, Any] | None:
    """Map source cpc/slots into the production 13-slot CPC object.

    Source datasets often emit flat slot maps (action/object/subject). Map
    ``subject`` → ``actor`` and treat bare string values as filled.
    """
    if not isinstance(raw, dict) or not raw:
        return None
    alias = {"subject": "actor"}
    out: dict[str, Any] = {
        name: {"value": None, "status": "unknown"} for name in CPC_SLOT_NAMES
    }
    filled_count = 0
    for key, slot in raw.items():
        name = alias.get(str(key), str(key))
        if name not in CPC_SLOT_NAMES:
            continue
        if isinstance(slot, dict):
            status = slot.get("status") or "unknown"
            value = slot.get("value")
            if status not in {"filled", "missing", "unknown", "not_applicable"}:
                status = "unknown"
            if status == "filled" or value not in (None, ""):
                if status == "unknown" and value not in (None, ""):
                    status = "filled"
                filled_count += 1 if status == "filled" or value not in (None, "") else 0
            out[name] = {"value": value, "status": status}
        elif slot is not None and slot != "":
            out[name] = {"value": str(slot), "status": "filled"}
            filled_count += 1
    if filled_count <= 0:
        return None
    return out


def _normalize_candidates(raw: Any) -> list[dict[str, Any]] | None:
    if not isinstance(raw, list) or not raw:
        return None
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("summary")
        frame_id = item.get("frame_id") or item.get("interpretation_id")
        if not frame_id:
            # Deterministic synthetic id from stable content — not a semantic label.
            digest = sha256_hex(str(text or idx).encode("utf-8"))[:12]
            frame_id = f"cand_{idx}_{digest}"
        entry: dict[str, Any] = {"frame_id": str(frame_id)}
        if isinstance(text, str) and text.strip():
            entry["text"] = text.strip()
        if item.get("confidence") is not None:
            entry["confidence"] = item.get("confidence")
        safety_status = item.get("safety_status")
        if safety_status in {"safe", "unsafe", "unknown"}:
            entry["safety_status"] = safety_status
        if isinstance(item.get("cpc"), dict):
            entry["cpc"] = item.get("cpc")
        out.append(entry)
    return out or None


def _extract_task_fields(
    task_id: str,
    record: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, str]] | None:
    """Return (fields, supervision_status) or None if task unsupported."""
    supervision: dict[str, str] = {}
    if task_id == "predict_intent_v1":
        # Required: intent_summary (or intent alias). speech_act is optional and
        # never fabricated — include only when present in the source record.
        summary = record.get("intent_summary") or record.get("intent")
        if not (isinstance(summary, str) and summary.strip()):
            return None
        fields: dict[str, Any] = {"intent_summary": summary.strip()}
        supervision["intent_summary"] = (
            "strong" if record.get("intent_summary") else "weak"
        )
        speech = record.get("speech_act")
        if isinstance(speech, str) and speech.strip():
            fields["speech_act"] = speech.strip()
            supervision["speech_act"] = "strong"
        else:
            # Optional generation properties are omitted when unsupported.
            # The production assembler may restore null after validation.
            supervision["speech_act"] = "missing"
        return fields, supervision

    if task_id == "predict_cpc_v1":
        cpc = _normalize_cpc(record.get("cpc") or record.get("slots"))
        if cpc is None:
            return None
        return {"cpc": cpc}, {"cpc": "strong"}

    if task_id == "predict_ambiguity_v1":
        if "ambiguity_present" not in record or record.get("ambiguity_present") is None:
            return None
        types = list(record.get("ambiguity_types") or [])
        fields = {
            "ambiguity_present": bool(record.get("ambiguity_present")),
            "ambiguity_types": types,
        }
        supervision = {
            "ambiguity_present": "strong",
            "ambiguity_types": "strong",
        }
        # primary_ambiguity_type and unresolved_slots remain production-owned
        # fields and are intentionally excluded from model generation.
        return fields, supervision

    if task_id == "predict_interpretations_v1":
        cands = _normalize_candidates(record.get("candidate_interpretations"))
        if not cands:
            return None
        fields = {"candidate_interpretations": cands}
        supervision = {"candidate_interpretations": "strong"}
        selected = record.get("selected_interpretation") or record.get("resolved_interpretation")
        if isinstance(selected, dict):
            fid = selected.get("frame_id") or selected.get("interpretation_id")
            if not fid and cands:
                fid = cands[0]["frame_id"]
            if fid:
                evidence = []
                for evidence_item in list(selected.get("supporting_evidence") or []):
                    if not isinstance(evidence_item, dict):
                        continue
                    cleaned = {}
                    for key in ("span", "note"):
                        value = evidence_item.get(key)
                        if isinstance(value, str) and value.strip():
                            cleaned[key] = value.strip()
                    if cleaned:
                        evidence.append(cleaned)
                fields["selected_interpretation"] = {
                    "frame_id": str(fid),
                    "supporting_evidence": evidence,
                }
                supervision["selected_interpretation"] = "weak"
        elif isinstance(selected, str) and selected.strip() and cands:
            # Free-text resolved interpretation: bind to first candidate id weakly.
            fields["selected_interpretation"] = {
                "frame_id": cands[0]["frame_id"],
                "supporting_evidence": [],
            }
            supervision["selected_interpretation"] = "weak"
        return fields, supervision

    if task_id == "predict_risk_capability_v1":
        if record.get("risk_level") is None and record.get("capability_status") is None:
            return None
        fields = {
            "risk_relevant": bool(
                record.get("risk_relevant", record.get("risk_level") not in (None, "none"))
            ),
            "risk_level": record.get("risk_level")
            if record.get("risk_level") is not None
            else "unknown",
            "capability_status": record.get("capability_status")
            if record.get("capability_status") is not None
            else "unknown",
        }
        return fields, {
            "risk_relevant": "strong",
            "risk_level": "strong" if record.get("risk_level") is not None else "weak",
            "capability_status": "strong"
            if record.get("capability_status") is not None
            else "weak",
        }

    raise TaskConditionedTrainingError(f"unsupported_task_id:{task_id}")


def task_is_eligible(
    task_spec: Mapping[str, Any],
    eligibility: Mapping[str, str],
) -> bool:
    primary = str(task_spec.get("eligibility_task"))
    status = eligibility.get(primary)
    if status in STRONG_ELIGIBILITY:
        return True
    secondary = task_spec.get("secondary_eligibility_task")
    if secondary and eligibility.get(str(secondary)) in STRONG_ELIGIBILITY:
        return True
    # Manifest CPC/speech statuses can be stale relative to alias fields (slots/intent).
    # Allow weakly_eligible or unavailable when the extractor can still build an honest target.
    if status in {"weakly_eligible", "unavailable"}:
        return True
    return False


def build_task_conditioned_training_example(
    *,
    record: Mapping[str, Any],
    eligibility: Mapping[str, str],
    task_spec: Mapping[str, Any],
    source_dataset: str,
    split: str = "source_train",
    tokenizer: Any | None = None,
    max_seq_len: int = 1024,
    pad_token_id: int = 0,
) -> TaskConditionedTrainingExample | None:
    """Build one example or return None when the record cannot support the task."""
    task_id = str(task_spec["task_id"])
    if split != "source_train":
        raise TaskConditionedTrainingError("training_examples_require_source_train")
    if not task_is_eligible(task_spec, eligibility):
        return None

    extracted = _extract_task_fields(task_id, record)
    if extracted is None:
        return None
    fields, supervision = extracted
    order = list(task_spec.get("stable_field_order") or sorted(fields))
    target = _canonical_target(fields, order)

    schema_errors = validate_task_schema(task_spec, target)
    if schema_errors:
        return None
    semantic_errors = validate_task_semantics(task_spec, target)
    if semantic_errors:
        return None

    # Require at least one strong or approved weak semantic target.
    if not any(v in {"strong", "weak"} for v in supervision.values()):
        return None

    record_id = str(record.get("id") or record.get("record_id"))
    prompt = build_task_prompt(
        task_spec=task_spec,
        command=str(record.get("command") or ""),
        scene_context=record.get("scene_context"),
        dialogue_history=record.get("dialogue_history") or [],
        capability_context=record.get("capability_context"),
        analysis_variant="full_context",
    )
    target_json = json.dumps(target, ensure_ascii=False, sort_keys=False)
    # Stable serialization: use canonical bytes for hash, readable dump for training.
    target_json = canonical_json_bytes(target).decode("utf-8")

    if tokenizer is None:
        from ambiguity_manager.model.full_schema_token_masking import DeterministicCharTokenizer

        tokenizer = DeterministicCharTokenizer()
        pad_token_id = int(tokenizer.pad_token_id)
        # Char tokenizer needs headroom for diagnostic builds.
        max_seq_len = max(max_seq_len, len(prompt) + len(target_json) + 8)

    masked = build_fully_supervised_task_sequence(
        prompt_text=prompt,
        target_json=target_json,
        tokenizer=tokenizer,
        max_seq_len=max_seq_len,
        pad_token_id=pad_token_id,
    )
    labels = list(masked.labels)
    if not any(x != IGNORE_INDEX for x in labels):
        raise TaskConditionedTrainingError(f"zero_supervision:{record_id}:{task_id}")

    example_id = f"{record_id}::{task_id}"
    payload = {
        "schema": TRAINING_EXAMPLE_SCHEMA,
        "schema_version": TRAINING_EXAMPLE_VERSION,
        "training_example_id": example_id,
        "source_record_id": record_id,
        "source_dataset": source_dataset,
        "split": split,
        "task_id": task_id,
        "task_version": str(task_spec.get("task_version") or "1.0.0"),
        "task_instruction_prompt": prompt,
        "canonical_task_target": target,
        "canonical_task_target_json": target_json,
        "field_supervision_status": supervision,
        "weak_label_status": {
            k: (v == "weak") for k, v in supervision.items()
        },
        "prompt_token_mask_rule": "all_prompt_tokens_-100",
        "target_token_mask_rule": "all_task_target_tokens_supervised",
        "padding_mask_rule": "padding_-100",
        "input_ids": list(masked.input_ids),
        "labels": labels,
        "attention_mask": list(masked.attention_mask),
        "mask_diagnostics": dict(masked.diagnostics),
        "source_provenance": {
            "record_id": record_id,
            "source_dataset": source_dataset,
            "group_id": record.get("group_id"),
            "eligibility": dict(eligibility),
        },
        "schema_identity": {
            "task_schema_id": task_spec.get("json_schema", {}).get("$id"),
            "task_schema_hash": sha256_hex(
                canonical_json_bytes(task_spec["json_schema"])
            ),
        },
        "prompt_identity": str(task_spec.get("prompt_contract_identity")),
        "canonical_example_hash": None,
    }
    payload["canonical_example_hash"] = sha256_hex(
        canonical_json_bytes(
            {
                k: v
                for k, v in payload.items()
                if k
                not in {
                    "input_ids",
                    "labels",
                    "attention_mask",
                    "mask_diagnostics",
                    "canonical_example_hash",
                }
            }
        )
    )
    return TaskConditionedTrainingExample(payload=payload)


def build_examples_for_record(
    *,
    record: Mapping[str, Any],
    eligibility: Mapping[str, str],
    task_registry: Mapping[str, Any],
    source_dataset: str,
    split: str = "source_train",
) -> list[TaskConditionedTrainingExample]:
    out: list[TaskConditionedTrainingExample] = []
    for task in task_registry.get("tasks") or []:
        example = build_task_conditioned_training_example(
            record=record,
            eligibility=eligibility,
            task_spec=task,
            source_dataset=source_dataset,
            split=split,
        )
        if example is not None:
            out.append(example)
    return out
