"""Evidence-linked Pilot-120 *development* blocker detector (no gold in inference).

Unlike the v0.2 lexical screen, v0.3 inspects candidate-set relationships:
- one requested item but two eligible pending items,
- one recipient role with two legitimate people,
- two admissible destinations and no selecting unit,
- two specialized instruments and an unknown measurement range.

This remains a conservative, source-only *diagnostic*, not complete task
parsing, physical validation, or a trained ambiguity model. Its rule families
were designed after studying Pilot-120 failures and MUST NOT be described as
independent held-out performance.
"""
from __future__ import annotations

import re
from typing import Any

from .source_probe import probe as legacy_probe, action_scaffold

PROBE_VERSION = "raw_source_readiness_context_v0.3_development"


def _match(pattern: str, text: str) -> re.Match[str] | None:
    return re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)


def _short_quote(match: re.Match[str], *, limit: int = 260) -> str:
    """Keep evidence as an exact (never constructed) source substring."""
    return match.group(0)[:limit]


def _new(reason: str, target: str, match: re.Match[str],
         question: str, candidates: list[str], source: str = "scene_context") -> dict[str, Any]:
    return {"reason": reason, "target": target, "quote": _short_quote(match),
            "source": source, "question": question, "candidates": candidates,
            "candidate_coverage_verified": False}


def _eligible_pending_objects(source: dict[str, Any]) -> dict[str, Any] | None:
    command = str(source.get("command", ""))
    scene = str(source.get("scene_context", ""))
    if not _match(r"\bthe\s+selected\s+", command):
        return None
    selected = _match(r"\btwo\s+(?P<kind>[\w-]+(?:\s+[\w-]+){0,4}?)\s+are\s+selected\s+and\s+(?:both\s+remain\s+)?pending\b", scene)
    if not selected:
        return None
    missing = _match(r"\b(?:the\s+)?command\s+(?:provides|contains|specifies|names)\s+no\s+(?:item\s+code|assignment\s+code|(?:[\w-]+\s+)?identifier|color|recipient\s+name)\b", scene)
    if not missing:
        return None
    assignments = re.findall(r"\b(?:the\s+)?([a-z-]+)\s+one\s+is\s+assigned\s+to\s+([\w-]+)", scene, flags=re.I)
    candidates = [f"{color} item for {recipient}" for color, recipient in assignments]
    # Do not hallucinate individual names from a generic 'two are selected'.
    if len(candidates) != 2:
        candidates = ["pending item 1 (identity not extracted)", "pending item 2 (identity not extracted)"]
    return _new("two_pending_selected_objects", "selected_item", missing,
                "Which of the two pending selected items do you mean?", candidates)


def _nonunique_role_recipient(source: dict[str, Any]) -> dict[str, Any] | None:
    command = str(source.get("command", ""))
    scene = str(source.get("scene_context", ""))
    match = _match(r"\btwo\s+recipients\s+under\s+the\s+role\s+(?P<role>[\w-]+)\b", scene)
    if not match or not _match(rf"\b{re.escape(match.group('role'))}\b", command):
        return None
    requires_identity = _match(r"\brecipient\s+identity\s+is\s+required\s+before\s+(?:handoff|delivery|transfer)\b", scene)
    no_selection = _match(r"\b(?:delivery\s+note|task\s+card|work\s+order|command)\s+(?:contains|names|specifies|provides)\s+only\s+(?:the\s+)?role\s+title\b", scene)
    if not requires_identity or not no_selection:
        return None
    badges = re.findall(r"\bbadge\s+([A-Z]+-[0-9]+)\b", scene, flags=re.I)
    candidates = [f"badge {badge}" for badge in dict.fromkeys(badges)]
    if len(candidates) < 2:
        candidates = ["recipient 1 (identity not extracted)", "recipient 2 (identity not extracted)"]
    return _new("nonunique_recipient_role", "recipient_identity", match,
                f"Which person with the role {match.group('role')} should receive the item?", candidates)


def _unnamed_destination_unit(source: dict[str, Any]) -> dict[str, Any] | None:
    command = str(source.get("command", ""))
    scene = str(source.get("scene_context", ""))
    # An open choice only matters if the instruction requests placement/return.
    if not _match(r"\b(?:place|return|move|deliver|transfer|store)\b", command):
        return None
    pair = _match(r"\btwo\s+(?P<type>(?:(?:secure|barrier|equipment|archive|storage|empty|authorized)\s+){0,3}(?:bays|cages|units))\b[^.]{0,250}", scene)
    missing = _match(r"\b(?:the\s+)?work\s+order\s+names\s+neither\s+unit\b", scene)
    # Both a scene-level pair and an explicit absence of a selecting binding
    # are needed. Two destinations alone does NOT imply unresolved ambiguity.
    if not pair or not missing:
        return None
    options = re.findall(
        r"\bunit\s+([A-Z])\s+at\s+(?:the\s+)?(.+?)(?=\s+and\s+unit\s+[A-Z]\b|[,.]|$)",
        pair.group(0), re.I | re.S)
    if len(options) >= 2:
        choices = [f"unit {letter.upper()} at {place.strip()}" for letter, place in options[:2]]
    else:
        places = re.findall(
            r"\bone\s+at\s+(?:the\s+)?(.+?)(?=\s+and\s+one\s+at\b|[,.]|$)",
            pair.group(0), re.I | re.S)
        choices = [place.strip() for place in places[:2]]
    if len(choices) != 2:
        # We know a choice remains but cannot verify all specific entity IDs.
        choices = ["destination unit 1 (identity unknown)", "destination unit 2 (identity unknown)"]
    return _new("unnamed_destination_unit", "destination_unit", missing,
                "Which destination unit should be used?", choices)


def _unknown_range_instrument(source: dict[str, Any]) -> dict[str, Any] | None:
    command = str(source.get("command", ""))
    scene = str(source.get("scene_context", ""))
    if not _match(r"\bmeasure\b", command):
        return None
    instruments = _match(r"\btwo\s+[\w-]+(?:\s+[\w-]+){0,4}\s+(?:are\s+)?staged\b[^.]{0,100}", scene)
    ranges = _match(r"\b(?:the\s+)?handheld\s+unit\s+covers\s+the\s+low\s+range\s*;\s*the\s+cart-mounted\s+unit\s+covers\s+the\s+high\s+range\b", scene)
    missing = _match(r"\b(?:the\s+)?work\s+order\s+does\s+not\s+state\s+the\s+expected\s+range\b", scene)
    requirement = _match(r"\bmeasurement\s+protocol\s+requires\s+the\s+range-appropriate\s+instrument\b", scene)
    if not all((instruments, ranges, missing, requirement)):
        return None
    return _new("unknown_instrument_range", "expected_range", missing,
                "Is the expected measurement range low or high?", ["low", "high"])


CONTEXT_CHECKS = (
    _eligible_pending_objects,
    _nonunique_role_recipient,
    _unnamed_destination_unit,
    _unknown_range_instrument,
)


def probe(source: dict[str, Any]) -> dict[str, Any]:
    """Return a source-only readiness *hypothesis* and attributable evidence."""
    existing = legacy_probe(source)
    evidence = [{"reason": x["reason"], "quote": x["quote"],
                 "source": "source_text_mixed", "target": None,
                 "question": None, "candidates": [],
                 "candidate_coverage_verified": False}
                for x in existing["evidence"]]
    for check in CONTEXT_CHECKS:
        item = check(source)
        if item is not None and item["reason"] not in {x["reason"] for x in evidence}:
            evidence.append(item)
    return {
        "record_id": source.get("record_id"), "probe_version": PROBE_VERSION,
        "predicted_readiness": "blocking_ambiguity" if evidence else "ready_candidate",
        "evidence": evidence,
        "question_targets": sorted({x["target"] for x in evidence if x["target"] is not None}),
        "candidate_coverage_verified": False, "complete_task_verified": False,
        "research_limit": "source-only development heuristic, not validated action readiness",
    }


__all__ = ["probe", "action_scaffold", "PROBE_VERSION", "CONTEXT_CHECKS"]