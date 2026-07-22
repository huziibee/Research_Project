"""Duplicate detection for annotation candidates."""

from __future__ import annotations

import re
from typing import Any

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def normalise_text(text: str) -> str:
  lowered = text.casefold().strip()
  lowered = _PUNCT_RE.sub(" ", lowered)
  return _WS_RE.sub(" ", lowered).strip()


def command_key(record: dict[str, Any]) -> str:
  return normalise_text(str(record.get("command", "")))


def context_command_key(record: dict[str, Any]) -> str:
  dialogue = record.get("dialogue_history") or []
  dialogue_norm = " || ".join(normalise_text(str(x)) for x in dialogue)
  scene = normalise_text(str(record.get("scene_context") or ""))
  capability = normalise_text(str(record.get("capability_context") or ""))
  return f"{command_key(record)}::{scene}::{capability}::{dialogue_norm}"


def cpc_fingerprint(cpc: dict[str, Any] | None) -> str | None:
  if not isinstance(cpc, dict):
    return None
  parts: list[str] = []
  for name in sorted(cpc):
    slot = cpc[name]
    if not isinstance(slot, dict):
      continue
    if slot.get("status") == "filled" and slot.get("value"):
      parts.append(f"{name}={normalise_text(str(slot['value']))}")
  if not parts:
    return None
  return "|".join(parts)


def find_duplicates(records: list[dict[str, Any]]) -> dict[str, list[list[str]]]:
  exact: dict[str, list[str]] = {}
  normalised: dict[str, list[str]] = {}
  context_cmd: dict[str, list[str]] = {}
  groups: dict[str, list[str]] = {}
  templates: dict[str, list[str]] = {}
  frames: dict[str, list[str]] = {}

  for record in records:
    rid = str(record.get("record_id"))
    exact.setdefault(str(record.get("command")), []).append(rid)
    normalised.setdefault(command_key(record), []).append(rid)
    context_cmd.setdefault(context_command_key(record), []).append(rid)
    hidden = record.get("hidden") or {}
    group_id = hidden.get("group_id")
    template_id = hidden.get("template_id")
    if group_id:
      groups.setdefault(str(group_id), []).append(rid)
    if template_id:
      templates.setdefault(str(template_id), []).append(rid)
    intended = hidden.get("intended_answer") or {}
    fp = cpc_fingerprint(intended.get("cpc"))
    if fp:
      frames.setdefault(fp, []).append(rid)

  def clusters(mapping: dict[str, list[str]]) -> list[list[str]]:
    return sorted([sorted(v) for v in mapping.values() if len(v) > 1], key=lambda x: x[0])

  return {
    "exact_command": clusters(exact),
    "normalised_command": clusters(normalised),
    "context_command": clusters(context_cmd),
    "group_id": clusters(groups),
    "template_id": clusters(templates),
    "cpc_frame": clusters(frames),
  }
