"""Versioned task-aligned QLoRA training-example contract (T27)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.structured_target import (
    PROMPT_CONTRACT_VERSION,
    TRAINING_EXAMPLE_SCHEMA_VERSION,
    TRAINING_TARGET_SCHEMA,
    StructuredTarget,
    build_structured_target,
)
from ambiguity_manager.model.token_loss_masking import (
    DeterministicCharTokenizer,
    MaskedTrainingSequence,
    build_masked_sequence,
)
from ambiguity_manager.model.training_target_packaging import load_training_target_policy_strict

TRAINING_EXAMPLE_CONTRACT_ID = "qlora_training_example_v1"


class TrainingExampleError(RuntimeError):
    """Raised when a training example violates the task-aligned contract."""


def build_inference_time_prompt(record: Mapping[str, Any]) -> str:
    """Build a prompt using only inference-time information.

    Must not expose source gold metadata, split assignments, design-cell labels,
    eligibility labels, or future manual labels.
    """
    forbidden_keys = {
        "eligibility",
        "label_eligibility",
        "split",
        "split_status",
        "original_split",
        "design_cell",
        "annotation_status",
        "label_confidence",
        "source_metadata",
        "mapping_notes",
        "gold_clarification_question",
    }
    for key in forbidden_keys:
        # Presence on the record is fine; we simply must not copy them into the prompt.
        del key

    command = str(record.get("command") or "").strip()
    if not command:
        raise TrainingExampleError("command_required_for_prompt")

    sections: list[str] = [
        "You are a structured semantic analyzer for compound ambiguous robot commands.",
        "Return exactly one JSON object and nothing else.",
        "Output only authorised semantic fields as compact JSON.",
        "Do not invent unavailable fields as negatives.",
        "",
        "[ORIGINAL_COMMAND]",
        command,
    ]
    scene = record.get("scene_context")
    if isinstance(scene, str) and scene.strip():
        sections.extend(["", "[SCENE_CONTEXT]", scene.strip()])
    history = record.get("dialogue_history")
    if isinstance(history, list) and history:
        sections.extend(["", "[DIALOGUE_HISTORY]"])
        for line in history:
            if isinstance(line, str) and line.strip():
                sections.append(f"- {line.strip()}")
    capability = record.get("capability_context")
    if isinstance(capability, str) and capability.strip():
        sections.extend(["", "[CAPABILITY_CONTEXT]", capability.strip()])
    sections.extend(
        [
            "",
            "[OUTPUT_SCHEMA_INSTRUCTIONS]",
            f"Emit a single JSON object compatible with {TRAINING_TARGET_SCHEMA}.",
            "Use stable field names and canonical enum spellings.",
            "Do not include runner-owned or administrative metadata.",
        ]
    )
    prompt = "\n".join(sections)
    for leaked in (
        "source_train",
        "source_dev",
        "source_holdout",
        "label_eligibility",
        "design_cell",
        "weakly_eligible",
        "eligible",
        "unavailable",
    ):
        # Eligibility vocabulary may coincidentally appear in commands; only reject
        # when we ourselves injected administrative sections (checked via markers).
        if f"[ELIGIBILITY" in prompt or f"split=" in prompt:
            raise TrainingExampleError(f"prompt_leaked_admin_marker:{leaked}")
    return prompt


@dataclass(frozen=True)
class TrainingExample:
    training_example_id: str
    source_record_id: str
    source_dataset: str
    split: str
    input_prompt: str
    canonical_structured_target: dict[str, Any]
    target_field_eligibility: dict[str, str]
    weak_label_status: str
    per_field_supervision_status: dict[str, str]
    prompt_token_mask_note: str
    target_token_mask_note: str
    unavailable_field_token_masks: tuple[str, ...]
    source_provenance: dict[str, Any]
    schema_version: str
    prompt_contract_version: str
    canonical_example_hash: str
    structured_target: StructuredTarget
    masked_sequence: MaskedTrainingSequence | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "contract_id": TRAINING_EXAMPLE_CONTRACT_ID,
            "training_example_id": self.training_example_id,
            "source_record_id": self.source_record_id,
            "source_dataset": self.source_dataset,
            "split": self.split,
            "input_prompt": self.input_prompt,
            "canonical_structured_target": dict(self.canonical_structured_target),
            "target_field_eligibility": dict(self.target_field_eligibility),
            "weak_label_status": self.weak_label_status,
            "per_field_supervision_status": dict(self.per_field_supervision_status),
            "prompt_token_mask": self.prompt_token_mask_note,
            "target_token_mask": self.target_token_mask_note,
            "unavailable_field_token_masks": list(self.unavailable_field_token_masks),
            "source_provenance": dict(self.source_provenance),
            "schema_version": self.schema_version,
            "prompt_contract_version": self.prompt_contract_version,
            "canonical_example_hash": self.canonical_example_hash,
            "target_hash": self.structured_target.target_hash,
            "supervised_fields": list(self.structured_target.supervised_fields),
        }
        if self.masked_sequence is not None:
            payload["loss_mask_diagnostics"] = dict(self.masked_sequence.diagnostics)
        return payload


def build_training_example(
    *,
    record: Mapping[str, Any],
    eligibility: Mapping[str, str],
    source_dataset: str,
    group_key: str,
    split: str = "source_train",
    policy: Mapping[str, Any] | None = None,
    tokenizer: Any | None = None,
    max_seq_len: int = 512,
    attach_masks: bool = True,
) -> TrainingExample:
    if split != "source_train":
        raise TrainingExampleError(f"training_examples_must_be_source_train:{split}")
    record_id = str(record.get("id") or "")
    if not record_id:
        raise TrainingExampleError("source_record_id_required")

    resolved_policy = dict(policy) if policy is not None else load_training_target_policy_strict()
    target = build_structured_target(record, eligibility, policy=resolved_policy)
    prompt = build_inference_time_prompt(record)

    weak_status = str(eligibility.get("structured_training_target") or "unknown")
    per_field: dict[str, str] = {}
    for name in target.supervised_fields:
        per_field[name] = "weakly_supervised" if name in target.weakly_eligible_fields else "supervised"
    for name in target.unavailable_fields:
        per_field[name] = "unavailable_masked"

    masked: MaskedTrainingSequence | None = None
    if attach_masks:
        tok = tokenizer or DeterministicCharTokenizer()
        pad_id = int(getattr(tok, "pad_token_id", 0) or 0)
        masked = build_masked_sequence(
            prompt_text=prompt,
            target_json=target.canonical_json,
            field_spans=[span.to_dict() for span in target.field_spans],
            unavailable_field_names=target.unavailable_fields,
            tokenizer=tok,
            max_seq_len=max_seq_len,
            pad_token_id=pad_id,
        )
        if masked.diagnostics["target_supervised_tokens"] <= 0:
            raise TrainingExampleError(f"zero_supervised_target_tokens:{record_id}")

    example_id = f"tex:{record_id}"
    provenance = {
        "source_record_id": record_id,
        "source_dataset": source_dataset,
        "group_key": group_key,
        "split": split,
        "training_target_schema": TRAINING_TARGET_SCHEMA,
    }
    hash_payload = {
        "training_example_id": example_id,
        "source_record_id": record_id,
        "split": split,
        "input_prompt": prompt,
        "target_hash": target.target_hash,
        "schema_version": TRAINING_EXAMPLE_SCHEMA_VERSION,
        "prompt_contract_version": PROMPT_CONTRACT_VERSION,
    }
    example_hash = sha256_hex(canonical_json_bytes(hash_payload))
    return TrainingExample(
        training_example_id=example_id,
        source_record_id=record_id,
        source_dataset=source_dataset,
        split=split,
        input_prompt=prompt,
        canonical_structured_target={
            "schema": target.schema,
            "fields": dict(target.fields),
        },
        target_field_eligibility=dict(eligibility),
        weak_label_status=weak_status,
        per_field_supervision_status=per_field,
        prompt_token_mask_note="all_prompt_tokens_label_-100",
        target_token_mask_note="supervised_field_token_ids_retained",
        unavailable_field_token_masks=tuple(target.unavailable_fields),
        source_provenance=provenance,
        schema_version=TRAINING_EXAMPLE_SCHEMA_VERSION,
        prompt_contract_version=PROMPT_CONTRACT_VERSION,
        canonical_example_hash=example_hash,
        structured_target=target,
        masked_sequence=masked,
    )
