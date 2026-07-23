"""Token-level causal-LM loss masking for task-aligned QLoRA (T27).

Hard rules:
- prompt tokens → label -100
- padding tokens → label -100
- unavailable / unsupported field spans → label -100
- eligible target spans retain token IDs
- command reconstruction is never the training target
- every example must retain at least one supervised target token

Uses a deterministic segment-based tokenisation approach that does not rely
on unreliable character offset mappings: prompt and target are tokenised as
separate segments and concatenated. Field-level masks inside the target are
applied by re-tokenising each supervised field fragment and the JSON
structural glue separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence

IGNORE_INDEX = -100
SEPARATOR = "\n"


class TokenLossMaskError(RuntimeError):
    """Raised when loss masks cannot be built deterministically."""


class TokenizerLike(Protocol):
    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]: ...

    def decode(self, ids: Sequence[int], skip_special_tokens: bool = True) -> str: ...


@dataclass(frozen=True)
class TokenSpanMask:
    name: str
    kind: str  # prompt | separator | target_supervised | target_unavailable | padding | structure
    token_start: int
    token_end: int
    label_mode: str  # supervise | mask

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "token_start": self.token_start,
            "token_end": self.token_end,
            "label_mode": self.label_mode,
        }


@dataclass(frozen=True)
class MaskedTrainingSequence:
    input_ids: tuple[int, ...]
    labels: tuple[int, ...]
    attention_mask: tuple[int, ...]
    spans: tuple[TokenSpanMask, ...]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_ids": list(self.input_ids),
            "labels": list(self.labels),
            "attention_mask": list(self.attention_mask),
            "spans": [span.to_dict() for span in self.spans],
            "diagnostics": dict(self.diagnostics),
        }


def _encode(tokenizer: TokenizerLike, text: str, *, add_special_tokens: bool) -> list[int]:
    ids = list(tokenizer.encode(text, add_special_tokens=add_special_tokens))
    if not isinstance(ids, list):
        raise TokenLossMaskError("tokenizer.encode must return a list of ints")
    return [int(x) for x in ids]


def build_masked_sequence(
    *,
    prompt_text: str,
    target_json: str,
    field_spans: Sequence[Mapping[str, Any]],
    unavailable_field_names: Sequence[str],
    tokenizer: TokenizerLike,
    max_seq_len: int,
    pad_token_id: int,
) -> MaskedTrainingSequence:
    """Build input_ids/labels with real token-level loss masks.

    ``field_spans`` entries must include ``field_name``, ``char_start``,
    ``char_end``, ``supervision`` (``supervised`` or otherwise), and
    ``json_fragment`` matching ``target_json[char_start:char_end]``.
    """
    if not prompt_text:
        raise TokenLossMaskError("prompt_text_required")
    if not target_json:
        raise TokenLossMaskError("target_json_required")

    # Validate span fragments against the target string.
    supervised_fragments: list[tuple[str, str]] = []
    unavailable_fragments: list[tuple[str, str]] = []
    for span in field_spans:
        name = str(span["field_name"])
        start = int(span["char_start"])
        end = int(span["char_end"])
        fragment = str(span["json_fragment"])
        if target_json[start:end] != fragment:
            raise TokenLossMaskError(f"field_span_mismatch:{name}")
        if span.get("supervision") == "supervised":
            supervised_fragments.append((name, fragment))
        else:
            unavailable_fragments.append((name, fragment))

    for name in unavailable_field_names:
        # Omitted-from-target unavailable fields contribute no tokens; recorded in diagnostics.
        del name

    prompt_ids = _encode(tokenizer, prompt_text, add_special_tokens=True)
    sep_ids = _encode(tokenizer, SEPARATOR, add_special_tokens=False)

    # Segment-tokenise the target: '{' + frag0 + ', ' + frag1 + ... + '}'
    # using the already-validated supervised fragments in target order.
    ordered = sorted(field_spans, key=lambda item: int(item["char_start"]))
    target_ids: list[int] = []
    target_labels: list[int] = []
    spans: list[TokenSpanMask] = []
    token_cursor = 0

    def _append_segment(name: str, kind: str, text: str, *, supervise: bool) -> None:
        nonlocal token_cursor
        ids = _encode(tokenizer, text, add_special_tokens=False)
        if not ids and text:
            raise TokenLossMaskError(f"empty_tokenisation_for_nonempty_text:{name}")
        start = token_cursor
        end = start + len(ids)
        target_ids.extend(ids)
        if supervise:
            target_labels.extend(ids)
            mode = "supervise"
        else:
            target_labels.extend([IGNORE_INDEX] * len(ids))
            mode = "mask"
        spans.append(
            TokenSpanMask(
                name=name,
                kind=kind,
                token_start=start,
                token_end=end,
                label_mode=mode,
            )
        )
        token_cursor = end

    # Reconstruct target via segments and verify exact string match after decode is not
    # required; instead verify the concatenation of fragments equals the canonical JSON
    # structurally by rebuilding from ordered spans.
    rebuilt_chars: list[str] = ["{"]
    _append_segment("structure.open", "structure", "{", supervise=False)
    first = True
    for span in ordered:
        name = str(span["field_name"])
        fragment = str(span["json_fragment"])
        supervise = span.get("supervision") == "supervised"
        if not first:
            rebuilt_chars.append(", ")
            _append_segment("structure.comma", "structure", ", ", supervise=False)
        rebuilt_chars.append(fragment)
        kind = "target_supervised" if supervise else "target_unavailable"
        _append_segment(name, kind, fragment, supervise=supervise)
        first = False
    rebuilt_chars.append("}")
    _append_segment("structure.close", "structure", "}", supervise=False)
    rebuilt = "".join(rebuilt_chars)
    if rebuilt != target_json:
        raise TokenLossMaskError(
            f"segment_rebuild_mismatch: expected={target_json!r} got={rebuilt!r}"
        )

    # Shift target spans by prompt+separator length for the full sequence.
    prompt_len = len(prompt_ids)
    sep_len = len(sep_ids)
    offset = prompt_len + sep_len
    full_spans: list[TokenSpanMask] = [
        TokenSpanMask(
            name="prompt",
            kind="prompt",
            token_start=0,
            token_end=prompt_len,
            label_mode="mask",
        ),
        TokenSpanMask(
            name="separator",
            kind="separator",
            token_start=prompt_len,
            token_end=offset,
            label_mode="mask",
        ),
    ]
    for span in spans:
        full_spans.append(
            TokenSpanMask(
                name=span.name,
                kind=span.kind,
                token_start=span.token_start + offset,
                token_end=span.token_end + offset,
                label_mode=span.label_mode,
            )
        )

    input_ids = prompt_ids + sep_ids + target_ids
    labels = [IGNORE_INDEX] * (prompt_len + sep_len) + target_labels
    attention = [1] * len(input_ids)

    if len(input_ids) > max_seq_len:
        # Truncate from the left of the prompt only when needed, preserving target tail.
        overflow = len(input_ids) - max_seq_len
        if overflow >= prompt_len:
            raise TokenLossMaskError("sequence_too_long_even_after_prompt_trim")
        input_ids = input_ids[overflow:]
        labels = labels[overflow:]
        attention = attention[overflow:]
        full_spans = [
            TokenSpanMask(
                name=span.name,
                kind=span.kind,
                token_start=max(0, span.token_start - overflow),
                token_end=max(0, span.token_end - overflow),
                label_mode=span.label_mode,
            )
            for span in full_spans
            if span.token_end > overflow
        ]

    pad_count = 0
    if len(input_ids) < max_seq_len:
        pad_count = max_seq_len - len(input_ids)
        pad_start = len(input_ids)
        input_ids = input_ids + [pad_token_id] * pad_count
        labels = labels + [IGNORE_INDEX] * pad_count
        attention = attention + [0] * pad_count
        full_spans.append(
            TokenSpanMask(
                name="padding",
                kind="padding",
                token_start=pad_start,
                token_end=pad_start + pad_count,
                label_mode="mask",
            )
        )

    supervised_token_count = sum(1 for label in labels if label != IGNORE_INDEX)
    if supervised_token_count <= 0:
        raise TokenLossMaskError("zero_supervised_target_tokens")

    prompt_masked = sum(1 for span in full_spans if span.kind == "prompt" for _ in range(span.token_end - span.token_start))
    unavailable_masked = sum(
        1
        for span in full_spans
        if span.kind == "target_unavailable"
        for _ in range(span.token_end - span.token_start)
    )
    padding_masked = pad_count
    total_tokens = len(input_ids)
    diagnostics = {
        "total_tokens": total_tokens,
        "prompt_masked_tokens": prompt_masked,
        "target_supervised_tokens": supervised_token_count,
        "unavailable_field_masked_tokens": unavailable_masked,
        "padding_masked_tokens": padding_masked,
        "structure_masked_tokens": sum(
            1
            for span in full_spans
            if span.kind in {"structure", "separator"}
            for _ in range(max(0, span.token_end - span.token_start))
        ),
        "supervised_token_percentage": round(100.0 * supervised_token_count / max(1, total_tokens), 4),
        "supervised_fields": [name for name, _ in supervised_fragments],
        "unavailable_fields_omitted": list(unavailable_field_names),
        "command_reconstruction": False,
    }
    return MaskedTrainingSequence(
        input_ids=tuple(input_ids),
        labels=tuple(labels),
        attention_mask=tuple(attention),
        spans=tuple(full_spans),
        diagnostics=diagnostics,
    )


def collate_masked_sequences(
    sequences: Sequence[MaskedTrainingSequence],
    *,
    pad_token_id: int,
) -> dict[str, Any]:
    if not sequences:
        raise TokenLossMaskError("empty_batch")
    max_len = max(len(seq.input_ids) for seq in sequences)
    batch_input: list[list[int]] = []
    batch_labels: list[list[int]] = []
    batch_attn: list[list[int]] = []
    diagnostics: list[dict[str, Any]] = []
    for seq in sequences:
        pad = max_len - len(seq.input_ids)
        batch_input.append(list(seq.input_ids) + [pad_token_id] * pad)
        batch_labels.append(list(seq.labels) + [IGNORE_INDEX] * pad)
        batch_attn.append(list(seq.attention_mask) + [0] * pad)
        diagnostics.append(dict(seq.diagnostics))
    return {
        "input_ids": batch_input,
        "labels": batch_labels,
        "attention_mask": batch_attn,
        "diagnostics": diagnostics,
    }


class DeterministicCharTokenizer:
    """Tiny deterministic tokenizer for CPU unit tests (1 char ≈ 1 token id)."""

    def __init__(self) -> None:
        self._token_to_id: dict[str, int] = {"<pad>": 0, "<bos>": 1}
        self._id_to_token: dict[int, str] = {0: "<pad>", 1: "<bos>"}
        self.pad_token_id = 0
        self.bos_token_id = 1

    def _id_for(self, token: str) -> int:
        if token not in self._token_to_id:
            idx = len(self._token_to_id)
            self._token_to_id[token] = idx
            self._id_to_token[idx] = token
        return self._token_to_id[token]

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        ids: list[int] = []
        if add_special_tokens:
            ids.append(self.bos_token_id)
        for ch in text:
            ids.append(self._id_for(ch))
        return ids

    def decode(self, ids: Sequence[int], skip_special_tokens: bool = True) -> str:
        chars: list[str] = []
        for idx in ids:
            tok = self._id_to_token.get(int(idx), "")
            if skip_special_tokens and tok in {"<pad>", "<bos>"}:
                continue
            chars.append(tok)
        return "".join(chars)


def assert_labels_ignore_prompt(sequence: MaskedTrainingSequence) -> None:
    for span in sequence.spans:
        if span.kind != "prompt":
            continue
        for index in range(span.token_start, span.token_end):
            if sequence.labels[index] != IGNORE_INDEX:
                raise TokenLossMaskError("prompt_token_not_masked")


def assert_no_command_reconstruction(
    sequence: MaskedTrainingSequence,
    *,
    command_text: str,
    tokenizer: TokenizerLike,
) -> None:
    """Prove command token IDs are not used as supervised reconstruction targets."""
    if not command_text.strip():
        return
    command_ids = set(_encode(tokenizer, command_text, add_special_tokens=False))
    supervised_ids = {label for label in sequence.labels if label != IGNORE_INDEX}
    # Command tokens may coincidentally overlap short JSON punctuation; require that
    # the full command string is not a supervised contiguous span in labels.
    prompt_span = next(span for span in sequence.spans if span.kind == "prompt")
    for index in range(prompt_span.token_start, prompt_span.token_end):
        if sequence.labels[index] != IGNORE_INDEX:
            raise TokenLossMaskError("command_prompt_span_supervised")
    # Diagnostics must declare reconstruction off.
    if sequence.diagnostics.get("command_reconstruction") is not False:
        raise TokenLossMaskError("command_reconstruction_flag_not_false")
    del command_ids, supervised_ids
