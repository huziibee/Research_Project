"""Context-sampling uncertainty diagnostics over supplied analyses."""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema.v2.taxonomies import CPC_SLOT_NAMES
from ambiguity_manager.systems.candidate_generation import candidate_set_fingerprint
from ambiguity_manager.systems.contracts import StructuredAnalysis
from ambiguity_manager.systems.hashing import sha256_json


def _load_uncertainty_policy(path: Path | None = None) -> dict[str, Any]:
  if path is None:
    path = ProjectPaths.from_repo_root().configs / "manager" / "uncertainty_policy_v1.json"
  return json.loads(path.read_text(encoding="utf-8"))


def _enumish(value: Any) -> str | None:
  if value is None:
    return None
  return value.value if hasattr(value, "value") else str(value)


def categorical_entropy(values: list[str | None]) -> float:
  filtered = [v if v is not None else "<null>" for v in values]
  if not filtered:
    return 0.0
  counts = Counter(filtered)
  total = len(filtered)
  entropy = 0.0
  for count in counts.values():
    p = count / total
    entropy -= p * math.log2(p)
  return entropy


def variation_ratio(values: list[str | None]) -> float:
  filtered = [v if v is not None else "<null>" for v in values]
  if not filtered:
    return 0.0
  counts = Counter(filtered)
  majority = counts.most_common(1)[0][1]
  return 1.0 - (majority / len(filtered))


def disagreement_rate(values: list[str | None]) -> float:
  filtered = [v if v is not None else "<null>" for v in values]
  if not filtered:
    return 0.0
  return 0.0 if len(set(filtered)) <= 1 else 1.0


@dataclass(frozen=True)
class UncertaintyDiagnostics:
  total_sample_count: int
  insufficient_samples: bool
  candidate_set_disagreement: float
  selected_interpretation_disagreement: float
  intent_disagreement: float
  cpc_slot_disagreement: dict[str, float]
  ambiguity_type_disagreement: float
  route_disagreement: float | None
  intent_entropy: float
  intent_variation_ratio: float
  per_slot_support_counts: dict[str, dict[str, int]]
  policy_status: str
  policy_valid_for_official_use: bool
  diagnostics_hash: str
  notes: list[str] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    return {
      "total_sample_count": self.total_sample_count,
      "insufficient_samples": self.insufficient_samples,
      "candidate_set_disagreement": self.candidate_set_disagreement,
      "selected_interpretation_disagreement": self.selected_interpretation_disagreement,
      "intent_disagreement": self.intent_disagreement,
      "cpc_slot_disagreement": dict(self.cpc_slot_disagreement),
      "ambiguity_type_disagreement": self.ambiguity_type_disagreement,
      "route_disagreement": self.route_disagreement,
      "intent_entropy": self.intent_entropy,
      "intent_variation_ratio": self.intent_variation_ratio,
      "per_slot_support_counts": {
        slot: dict(counts) for slot, counts in self.per_slot_support_counts.items()
      },
      "policy_status": self.policy_status,
      "policy_valid_for_official_use": self.policy_valid_for_official_use,
      "diagnostics_hash": self.diagnostics_hash,
      "notes": list(self.notes),
    }


def compute_uncertainty_diagnostics(
  samples: list[StructuredAnalysis],
  *,
  policy: dict[str, Any] | None = None,
  include_route: bool = True,
) -> UncertaintyDiagnostics:
  policy = policy or _load_uncertainty_policy()
  min_samples = int(policy.get("minimum_sample_count", 2))
  total = len(samples)
  insufficient = total < min_samples
  candidate_fps = [candidate_set_fingerprint(s.candidate_interpretations) for s in samples]
  selected = [
    s.selected_interpretation.frame_id if s.selected_interpretation else None for s in samples
  ]
  intents = [s.speech_act for s in samples]
  ambiguity_sets = [
    ",".join(sorted(_enumish(t) or "" for t in s.ambiguity_types)) for s in samples
  ]
  routes = [_enumish(s.recommended_strategy) for s in samples] if include_route else []
  cpc_disagreement: dict[str, float] = {}
  per_slot_support: dict[str, dict[str, int]] = {}
  for slot_name in CPC_SLOT_NAMES:
    values: list[str | None] = []
    support: Counter[str] = Counter()
    for sample in samples:
      slot = getattr(sample.cpc, slot_name)
      value = slot.value if slot.value is not None else None
      values.append(value)
      key = value if value is not None else "<null>"
      support[key] += 1
    cpc_disagreement[slot_name] = disagreement_rate(values)
    per_slot_support[slot_name] = dict(support)
  diagnostics = UncertaintyDiagnostics(
    total_sample_count=total,
    insufficient_samples=insufficient,
    candidate_set_disagreement=disagreement_rate(candidate_fps),
    selected_interpretation_disagreement=disagreement_rate(selected),
    intent_disagreement=disagreement_rate(intents),
    cpc_slot_disagreement=cpc_disagreement,
    ambiguity_type_disagreement=disagreement_rate(ambiguity_sets),
    route_disagreement=disagreement_rate(routes) if include_route else None,
    intent_entropy=categorical_entropy(intents),
    intent_variation_ratio=variation_ratio(intents),
    per_slot_support_counts=per_slot_support,
    policy_status=str(policy.get("status", "development_only")),
    policy_valid_for_official_use=bool(policy.get("valid_for_official_use", False)),
    diagnostics_hash="",
    notes=[
      "thresholds_unfrozen" if not policy.get("frozen", False) else "thresholds_frozen",
      "development_only" if policy.get("status") == "development_only" else "status_other",
    ],
  )
  payload = diagnostics.to_dict()
  payload.pop("diagnostics_hash", None)
  object.__setattr__(
    diagnostics,
    "diagnostics_hash",
    sha256_json(payload),
  ) if False else None
  # frozen dataclass: rebuild with hash
  return UncertaintyDiagnostics(
    total_sample_count=diagnostics.total_sample_count,
    insufficient_samples=diagnostics.insufficient_samples,
    candidate_set_disagreement=diagnostics.candidate_set_disagreement,
    selected_interpretation_disagreement=diagnostics.selected_interpretation_disagreement,
    intent_disagreement=diagnostics.intent_disagreement,
    cpc_slot_disagreement=diagnostics.cpc_slot_disagreement,
    ambiguity_type_disagreement=diagnostics.ambiguity_type_disagreement,
    route_disagreement=diagnostics.route_disagreement,
    intent_entropy=diagnostics.intent_entropy,
    intent_variation_ratio=diagnostics.intent_variation_ratio,
    per_slot_support_counts=diagnostics.per_slot_support_counts,
    policy_status=diagnostics.policy_status,
    policy_valid_for_official_use=diagnostics.policy_valid_for_official_use,
    diagnostics_hash=sha256_json(payload),
    notes=list(diagnostics.notes),
  )


def scalar_uncertainty_score(diagnostics: UncertaintyDiagnostics) -> float:
  """Development-only scalar for degree-based router; not official."""
  components = [
    diagnostics.candidate_set_disagreement,
    diagnostics.selected_interpretation_disagreement,
    diagnostics.intent_disagreement,
    diagnostics.ambiguity_type_disagreement,
    diagnostics.intent_variation_ratio,
  ]
  slot_vals = list(diagnostics.cpc_slot_disagreement.values())
  if slot_vals:
    components.append(sum(slot_vals) / len(slot_vals))
  if diagnostics.route_disagreement is not None:
    components.append(diagnostics.route_disagreement)
  if not components:
    return 0.0
  return sum(components) / len(components)
