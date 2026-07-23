"""Segment-aware token loss masking for full-schema envelopes (T27B).

CPU-only. Does not import torch/transformers/peft/bitsandbytes/accelerate/vllm/requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from ambiguity_manager.model.full_schema_envelope import EnvelopeSegment, FullSchemaEnvelope
from ambiguity_manager.model.token_loss_masking import (
    DeterministicCharTokenizer,
    IGNORE_INDEX,
    SEPARATOR,
)

__all__ = [
    "IGNORE_INDEX",
    "DeterministicCharTokenizer",
    "FullSchemaTokenMaskError",
    "MaskedEnvelopeSequence",
    "build_masked_sequence_from_envelope",
]


class FullSchemaTokenMaskError(RuntimeError):
    """Raised when envelope token masks cannot be built safely."""


class TokenizerLike(Protocol):
    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]: ...

    def decode(self, ids: Sequence[int], skip_special_tokens: bool = True) -> str: ...


@dataclass(frozen=True)
class MaskedEnvelopeSequence:
    input_ids: tuple[int, ...]
    labels: tuple[int, ...]
    attention_mask: tuple[int, ...]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_ids": list(self.input_ids),
            "labels": list(self.labels),
            "attention_mask": list(self.attention_mask),
            "diagnostics": dict(self.diagnostics),
        }


def _encode(tokenizer: TokenizerLike, text: str, *, add_special_tokens: bool) -> list[int]:
    ids = list(tokenizer.encode(text, add_special_tokens=add_special_tokens))
    return [int(x) for x in ids]


def _supervise_kind(kind: str, *, exclude_weak: bool) -> bool:
    if kind in {"structural", "field_name", "supervised_value"}:
        return True
    if kind == "weak_value":
        return not exclude_weak
    return False


def build_masked_sequence_from_envelope(
    *,
    prompt: str,
    envelope: FullSchemaEnvelope,
    tokenizer: TokenizerLike,
    max_seq_len: int,
    pad_token_id: int,
    exclude_weak: bool = False,
) -> MaskedEnvelopeSequence:
    """Tokenise prompt + envelope segments with full-schema supervision rules."""
    if not prompt:
        raise FullSchemaTokenMaskError("prompt_required")
    if not envelope.canonical_json:
        raise FullSchemaTokenMaskError("envelope_canonical_json_required")

    rebuilt = "".join(seg.text for seg in envelope.segments)
    if rebuilt != envelope.canonical_json:
        raise FullSchemaTokenMaskError("envelope_segment_rebuild_mismatch")

    prompt_ids = _encode(tokenizer, prompt, add_special_tokens=True)
    sep_ids = _encode(tokenizer, SEPARATOR, add_special_tokens=False)

    target_ids: list[int] = []
    target_labels: list[int] = []
    structural_supervised = 0
    semantic_supervised = 0
    weak_supervised = 0
    unavailable_masked = 0
    supervised_field_paths: set[str] = set()
    masked_field_paths: set[str] = set()

    def _append(seg: EnvelopeSegment) -> None:
        nonlocal structural_supervised, semantic_supervised, weak_supervised, unavailable_masked
        ids = _encode(tokenizer, seg.text, add_special_tokens=False)
        if not ids and seg.text:
            raise FullSchemaTokenMaskError(f"empty_tokenisation:{seg.kind}:{seg.field_path}")
        target_ids.extend(ids)
        supervise = _supervise_kind(seg.kind, exclude_weak=exclude_weak)
        if supervise:
            target_labels.extend(ids)
            if seg.kind in {"structural", "field_name"}:
                structural_supervised += len(ids)
            elif seg.kind == "supervised_value":
                semantic_supervised += len(ids)
                if seg.field_path:
                    supervised_field_paths.add(seg.field_path.split("[", 1)[0].split(".", 1)[0])
            elif seg.kind == "weak_value":
                weak_supervised += len(ids)
                semantic_supervised += len(ids)
                if seg.field_path:
                    supervised_field_paths.add(seg.field_path.split("[", 1)[0].split(".", 1)[0])
        else:
            target_labels.extend([IGNORE_INDEX] * len(ids))
            if seg.kind in {"unavailable_value", "weak_value"}:
                unavailable_masked += len(ids)
                if seg.field_path:
                    masked_field_paths.add(seg.field_path.split("[", 1)[0].split(".", 1)[0])

    for seg in envelope.segments:
        _append(seg)

    input_ids = prompt_ids + sep_ids + target_ids
    labels = [IGNORE_INDEX] * (len(prompt_ids) + len(sep_ids)) + target_labels
    attention = [1] * len(input_ids)
    prompt_masked = len(prompt_ids) + len(sep_ids)

    if len(input_ids) > max_seq_len:
        overflow = len(input_ids) - max_seq_len
        if overflow >= len(prompt_ids):
            raise FullSchemaTokenMaskError("sequence_too_long_even_after_prompt_trim")
        input_ids = input_ids[overflow:]
        labels = labels[overflow:]
        attention = attention[overflow:]
        prompt_masked = max(0, prompt_masked - overflow)

    pad_count = 0
    if len(input_ids) < max_seq_len:
        pad_count = max_seq_len - len(input_ids)
        input_ids = input_ids + [pad_token_id] * pad_count
        labels = labels + [IGNORE_INDEX] * pad_count
        attention = attention + [0] * pad_count

    if semantic_supervised <= 0:
        raise FullSchemaTokenMaskError("zero_semantic_supervised_tokens")

    if labels == input_ids:
        raise FullSchemaTokenMaskError("labels_must_not_equal_input_ids")

    total = len(input_ids)
    supervised_total = sum(1 for label in labels if label != IGNORE_INDEX)
    diagnostics = {
        "total_tokens": total,
        "prompt_masked": prompt_masked,
        "structural_supervised": structural_supervised,
        "semantic_supervised": semantic_supervised,
        "weak_supervised": weak_supervised,
        "unavailable_masked": unavailable_masked,
        "padding_masked": pad_count,
        "supervised_percentage": round(100.0 * supervised_total / max(1, total), 4),
        "supervised_field_paths": sorted(supervised_field_paths),
        "masked_field_paths": sorted(masked_field_paths),
        "command_reconstruction": False,
        "envelope_id": envelope.envelope_id,
        "target_supervised_tokens": supervised_total,
        "supervised_token_percentage": round(100.0 * supervised_total / max(1, total), 4),
    }
    return MaskedEnvelopeSequence(
        input_ids=tuple(input_ids),
        labels=tuple(labels),
        attention_mask=tuple(attention),
        diagnostics=diagnostics,
    )
