"""Deterministic JSON extraction and bounded repair."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

MAX_REPAIR_ROUNDS = 2
MAX_REPAIR_OPERATIONS = 6

_FENCE_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


@dataclass
class ParseResult:
    raw_output: str
    extracted_json_text: str | None
    parsed_object: dict[str, Any] | None
    repair_attempts: int
    repair_log: list[str]


def extract_and_repair_json(raw_output: str) -> ParseResult:
    repair_log: list[str] = []
    attempts = 0
    candidate = raw_output.strip()

    for _round in range(MAX_REPAIR_ROUNDS + 1):
        if attempts >= MAX_REPAIR_OPERATIONS:
            break

        fence_match = _FENCE_PATTERN.search(candidate)
        if fence_match and attempts < MAX_REPAIR_OPERATIONS:
            candidate = fence_match.group(1).strip()
            repair_log.append("remove_markdown_json_fence")
            attempts += 1

        isolated = _isolate_outer_object(candidate)
        if isolated != candidate and attempts < MAX_REPAIR_OPERATIONS:
            candidate = isolated
            repair_log.append("isolate_outermost_balanced_object")
            attempts += 1

        repaired, ops = _apply_deterministic_repairs(candidate, MAX_REPAIR_OPERATIONS - attempts)
        for op in ops:
            repair_log.append(op)
        attempts += len(ops)
        candidate = repaired

        parsed = _try_parse(candidate)
        if parsed is not None:
            return ParseResult(
                raw_output=raw_output,
                extracted_json_text=candidate,
                parsed_object=parsed,
                repair_attempts=attempts,
                repair_log=repair_log,
            )

    return ParseResult(
        raw_output=raw_output,
        extracted_json_text=candidate if candidate else None,
        parsed_object=None,
        repair_attempts=attempts,
        repair_log=repair_log,
    )


def _try_parse(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _isolate_outer_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return text
    depth = 0
    end = -1
    for index, char in enumerate(text[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    if end < 0:
        return text
    return text[start : end + 1]


def _apply_deterministic_repairs(text: str, remaining_ops: int) -> tuple[str, list[str]]:
    operations: list[str] = []
    current = text

    if remaining_ops > 0:
        stripped = _remove_suffix_after_balanced_close(current)
        if stripped != current:
            current = stripped
            operations.append("remove_suffix_after_final_balanced_brace")
            remaining_ops -= 1

    if remaining_ops > 0:
        no_trailing = _remove_trailing_commas(current)
        if no_trailing != current:
            current = no_trailing
            operations.append("remove_trailing_commas")
            remaining_ops -= 1

    if remaining_ops > 0:
        normalised = _normalise_python_literals(current)
        if normalised != current:
            current = normalised
            operations.append("normalise_python_literals")
            remaining_ops -= 1

    if remaining_ops > 0:
        deduped = _remove_duplicated_outer_braces(current)
        if deduped != current:
            current = deduped
            operations.append("remove_duplicated_outer_braces")
            remaining_ops -= 1

    return current, operations


def _remove_suffix_after_balanced_close(text: str) -> str:
    isolated = _isolate_outer_object(text)
    if isolated and isolated in text:
        prefix_index = text.find(isolated)
        if prefix_index >= 0:
            return text[prefix_index : prefix_index + len(isolated)]
    return text


def _remove_trailing_commas(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text)


def _normalise_python_literals(text: str) -> str:
    text = re.sub(r"\bTrue\b", "true", text)
    text = re.sub(r"\bFalse\b", "false", text)
    text = re.sub(r"\bNone\b", "null", text)
    return text


def _remove_duplicated_outer_braces(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{{") and stripped.endswith("}}"):
        inner = stripped[1:-1]
        if _try_parse(inner) is not None:
            return inner
    return text
