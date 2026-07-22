"""Variant-aware analysis-cache storage, lookup, and coverage gates.

Replaces the legacy one-analysis-per-record assumption with a typed cache
keyed by ``(record_id, analysis_variant)``. Supported variants are exactly
``full_context`` and ``context_blind``.
"""

from __future__ import annotations

import copy
import warnings
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, MutableMapping

from ambiguity_manager.systems.analysis import (
  ANALYSIS_VARIANTS,
  AnalysisIdentity,
  build_analysis_identity,
  is_context_blind_provenance,
)
from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput
from ambiguity_manager.systems.errors import SystemsContractError
from ambiguity_manager.systems.hashing import sha256_json
from ambiguity_manager.systems.model_identities import SelectedIdentities, load_selected_identities

# Systems that must share one identical full_context analysis identity.
SHARED_FULL_CONTEXT_SYSTEMS: frozenset[str] = frozenset(
  {
    "always_execute",
    "always_clarify",
    "always_silently_resolve",
    "degree_based_router",
    "full_type_risk_aware_manager",
  }
)

# Default required analysis variant per system. ``None`` means the system does
# not consume the shared adapted semantic cache (live direct provider).
REQUIRED_ANALYSIS_VARIANT: dict[str, str | None] = {
  "always_execute": "full_context",
  "always_clarify": "full_context",
  "always_silently_resolve": "full_context",
  "degree_based_router": "full_context",
  "full_type_risk_aware_manager": "full_context",
  "context_blind_manager": "context_blind",
  "direct_base_llm": None,
}


@dataclass(frozen=True)
class AnalysisCacheKey:
  """Typed cache identity: record plus validated analysis variant."""

  record_id: str
  analysis_variant: str

  def __post_init__(self) -> None:
    if not self.record_id or not isinstance(self.record_id, str):
      raise SystemsContractError("AnalysisCacheKey.record_id must be a non-empty string")
    if self.analysis_variant not in ANALYSIS_VARIANTS:
      raise SystemsContractError(
        f"unsupported analysis_variant {self.analysis_variant!r}; "
        f"allowed={sorted(ANALYSIS_VARIANTS)}"
      )

  def to_dict(self) -> dict[str, str]:
    return {
      "record_id": self.record_id,
      "analysis_variant": self.analysis_variant,
    }

  def as_tuple(self) -> tuple[str, str]:
    return (self.record_id, self.analysis_variant)

  @classmethod
  def from_parts(cls, record_id: str, analysis_variant: str) -> "AnalysisCacheKey":
    return cls(record_id=record_id, analysis_variant=analysis_variant)


@dataclass(frozen=True)
class AnalysisCacheEntry:
  """Stored cache payload with provenance required for coverage gates."""

  record_id: str
  analysis_variant: str
  source_input_hash: str
  analysis_content_hash: str
  provider_id: str | None
  provider_version: str | None
  selected_base_model: str | None
  selected_adapter: str | None
  selected_model_strategy: str | None
  prompt_contract_id: str | None
  schema_version: str | None
  analysis_provenance: dict[str, Any] | None
  analysis: StructuredAnalysis
  analysis_identity: AnalysisIdentity | None = None

  def __post_init__(self) -> None:
    if self.analysis_variant not in ANALYSIS_VARIANTS:
      raise SystemsContractError(
        f"unsupported analysis_variant on cache entry: {self.analysis_variant!r}"
      )
    if self.record_id != (self.analysis_identity.record_id if self.analysis_identity else self.record_id):
      raise SystemsContractError("cache entry record_id does not match analysis_identity")

  @property
  def key(self) -> AnalysisCacheKey:
    return AnalysisCacheKey(self.record_id, self.analysis_variant)

  def to_dict(self) -> dict[str, Any]:
    return {
      "record_id": self.record_id,
      "analysis_variant": self.analysis_variant,
      "source_input_hash": self.source_input_hash,
      "analysis_content_hash": self.analysis_content_hash,
      "provider_id": self.provider_id,
      "provider_version": self.provider_version,
      "selected_base_model": self.selected_base_model,
      "selected_adapter": self.selected_adapter,
      "selected_model_strategy": self.selected_model_strategy,
      "prompt_contract_id": self.prompt_contract_id,
      "schema_version": self.schema_version,
      "analysis_provenance": copy.deepcopy(self.analysis_provenance),
      "analysis": self.analysis.to_dict(),
      "analysis_identity": (
        self.analysis_identity.to_dict() if self.analysis_identity is not None else None
      ),
    }

  def fingerprint(self) -> str:
    return sha256_json(self.to_dict())

  @classmethod
  def from_analysis(
    cls,
    *,
    record: SystemInput,
    analysis: StructuredAnalysis,
    analysis_variant: str,
    identities: SelectedIdentities | None = None,
    prompt_contract_id: str | None = None,
    schema_version: str | None = None,
  ) -> "AnalysisCacheEntry":
    if analysis_variant not in ANALYSIS_VARIANTS:
      raise SystemsContractError(f"unsupported analysis_variant: {analysis_variant!r}")
    source_input = record.without_context() if analysis_variant == "context_blind" else record
    identity = build_analysis_identity(
      record_id=record.record_id,
      source_input=source_input,
      analysis=analysis,
      analysis_variant=analysis_variant,
      model_strategy_id=(
        identities.selected_model_strategy if identities is not None else None
      ),
    )
    prov = analysis.analysis_provenance
    ids = identities if identities is not None else load_selected_identities()
    return cls(
      record_id=record.record_id,
      analysis_variant=analysis_variant,
      source_input_hash=identity.source_input_hash,
      analysis_content_hash=identity.analysis_content_hash,
      provider_id=identity.provider_id,
      provider_version=identity.provider_version,
      selected_base_model=ids.selected_base_model,
      selected_adapter=ids.selected_adapter,
      selected_model_strategy=ids.selected_model_strategy,
      prompt_contract_id=prompt_contract_id,
      schema_version=schema_version,
      analysis_provenance=prov.to_dict() if prov is not None else None,
      analysis=copy.deepcopy(analysis),
      analysis_identity=identity,
    )


class AnalysisCacheStore:
  """Strict mapping from ``AnalysisCacheKey`` to ``AnalysisCacheEntry``.

  Lookup never falls back across variants. Duplicate keys are rejected.
  """

  def __init__(self) -> None:
    self._entries: dict[tuple[str, str], AnalysisCacheEntry] = {}

  def __len__(self) -> int:
    return len(self._entries)

  def __contains__(self, key: AnalysisCacheKey | tuple[str, str]) -> bool:
    return self._as_tuple(key) in self._entries

  def keys(self) -> list[AnalysisCacheKey]:
    return [
      AnalysisCacheKey(record_id, variant)
      for record_id, variant in sorted(self._entries.keys())
    ]

  def values(self) -> list[AnalysisCacheEntry]:
    return [self._entries[k] for k in sorted(self._entries.keys())]

  def items(self) -> list[tuple[AnalysisCacheKey, AnalysisCacheEntry]]:
    return [(AnalysisCacheKey(*k), self._entries[k]) for k in sorted(self._entries.keys())]

  def put(self, entry: AnalysisCacheEntry, *, allow_replace: bool = False) -> None:
    key = entry.key.as_tuple()
    if key in self._entries and not allow_replace:
      raise SystemsContractError(
        f"duplicate analysis cache key rejected: record_id={entry.record_id!r} "
        f"variant={entry.analysis_variant!r}"
      )
    self._entries[key] = entry

  def get(self, key: AnalysisCacheKey | tuple[str, str]) -> AnalysisCacheEntry | None:
    return self._entries.get(self._as_tuple(key))

  def get_analysis(
    self,
    record_id: str,
    analysis_variant: str,
  ) -> StructuredAnalysis | None:
    entry = self.get(AnalysisCacheKey(record_id, analysis_variant))
    if entry is None:
      return None
    return copy.deepcopy(entry.analysis)

  def require(
    self,
    record_id: str,
    analysis_variant: str,
  ) -> AnalysisCacheEntry:
    entry = self.get(AnalysisCacheKey(record_id, analysis_variant))
    if entry is None:
      raise SystemsContractError(
        f"missing analysis cache entry for record_id={record_id!r} "
        f"variant={analysis_variant!r}"
      )
    return entry

  def validate_entry_integrity(
    self,
    entry: AnalysisCacheEntry,
    *,
    record: SystemInput,
  ) -> None:
    """Reject wrong variant / source-input hash / analysis hash."""
    if entry.record_id != record.record_id:
      raise SystemsContractError(
        f"cache entry record_id {entry.record_id!r} does not match input {record.record_id!r}"
      )
    if entry.analysis_variant not in ANALYSIS_VARIANTS:
      raise SystemsContractError(f"wrong analysis variant: {entry.analysis_variant!r}")
    expected_source = (
      record.without_context() if entry.analysis_variant == "context_blind" else record
    )
    expected_source_hash = expected_source.fingerprint()
    if entry.source_input_hash != expected_source_hash:
      raise SystemsContractError(
        f"wrong source-input hash for {entry.record_id}/{entry.analysis_variant}: "
        f"cached={entry.source_input_hash} expected={expected_source_hash}"
      )
    expected_content = entry.analysis.fingerprint()
    if entry.analysis_content_hash != expected_content:
      raise SystemsContractError(
        f"wrong analysis content hash for {entry.record_id}/{entry.analysis_variant}"
      )
    # Provenance variant must agree with the typed key for context_blind.
    if entry.analysis_variant == "context_blind":
      if not is_context_blind_provenance(entry.analysis.analysis_provenance):
        raise SystemsContractError(
          f"context_blind cache entry lacks explicit context_blind provenance: {entry.record_id}"
        )
    elif entry.analysis_variant == "full_context":
      if is_context_blind_provenance(entry.analysis.analysis_provenance):
        raise SystemsContractError(
          f"full_context cache entry has context_blind provenance: {entry.record_id}"
        )

  def to_manifest_entries(self) -> list[dict[str, Any]]:
    """Deterministic manifest projection of every cached analysis entry."""
    return [entry.to_dict() for entry in self.values()]

  def fingerprint(self) -> str:
    return sha256_json({"entries": self.to_manifest_entries()})

  @staticmethod
  def _as_tuple(key: AnalysisCacheKey | tuple[str, str]) -> tuple[str, str]:
    if isinstance(key, AnalysisCacheKey):
      return key.as_tuple()
    if (
      isinstance(key, tuple)
      and len(key) == 2
      and isinstance(key[0], str)
      and isinstance(key[1], str)
    ):
      if key[1] not in ANALYSIS_VARIANTS:
        raise SystemsContractError(f"unsupported analysis_variant: {key[1]!r}")
      return (key[0], key[1])
    raise SystemsContractError(f"invalid analysis cache key: {key!r}")


def required_variant_for_system(system_id: str) -> str | None:
  if system_id not in REQUIRED_ANALYSIS_VARIANT:
    raise SystemsContractError(f"unknown system for analysis-variant mapping: {system_id!r}")
  return REQUIRED_ANALYSIS_VARIANT[system_id]


def resolve_cached_analysis_for_system(
  store: AnalysisCacheStore | Mapping[Any, Any] | None,
  *,
  record_id: str,
  system_id: str,
) -> StructuredAnalysis | None:
  """Resolve the analysis a system is allowed to consume.

  ``direct_base_llm`` never receives the shared adapted cache.
  Missing required variants yield ``None`` (no cross-variant fallback).
  """
  required = required_variant_for_system(system_id)
  if required is None:
    return None
  normalised = coerce_analysis_cache(store, compatibility_mode="reject_legacy")
  return normalised.get_analysis(record_id, required)


@dataclass(frozen=True)
class CoverageMatrixRow:
  record_id: str
  system_id: str
  required_analysis_variant: str | None
  cache_present: bool
  provider_can_produce: bool
  cache_provider_identity: str | None
  validation_result: str
  missing_reason: str | None = None

  def to_dict(self) -> dict[str, Any]:
    return {
      "record_id": self.record_id,
      "system_id": self.system_id,
      "required_analysis_variant": self.required_analysis_variant,
      "cache_present": self.cache_present,
      "provider_can_produce": self.provider_can_produce,
      "cache_provider_identity": self.cache_provider_identity,
      "validation_result": self.validation_result,
      "missing_reason": self.missing_reason,
    }


@dataclass
class CoverageMatrix:
  rows: list[CoverageMatrixRow] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    return {
      "row_count": len(self.rows),
      "rows": [row.to_dict() for row in self.rows],
      "missing_count": sum(1 for row in self.rows if row.validation_result != "ok"),
    }

  def fingerprint(self) -> str:
    return sha256_json(self.to_dict())

  def all_ok(self) -> bool:
    return all(row.validation_result == "ok" for row in self.rows)

  def missing_rows(self) -> list[CoverageMatrixRow]:
    return [row for row in self.rows if row.validation_result != "ok"]


def build_coverage_matrix(
  *,
  records: Iterable[SystemInput],
  systems: Iterable[str],
  cache: AnalysisCacheStore | Mapping[Any, Any] | None,
  provider_can_produce: Mapping[str, bool] | None = None,
  identities: SelectedIdentities | None = None,
  run_mode: str = "development",
) -> CoverageMatrix:
  """Build required coverage for every (record, system, required variant).

  One approved cache entry cannot satisfy unrelated records or variants.
  Official mode treats missing or unapproved coverage as failed validation.
  """
  store = coerce_analysis_cache(
    cache,
    compatibility_mode="legacy_as_full_context" if run_mode != "official" else "reject_legacy",
  )
  provider_can_produce = provider_can_produce or {}
  ids = identities if identities is not None else load_selected_identities()
  rows: list[CoverageMatrixRow] = []
  for record in records:
    for system_id in systems:
      required = required_variant_for_system(system_id)
      if required is None:
        rows.append(
          CoverageMatrixRow(
            record_id=record.record_id,
            system_id=system_id,
            required_analysis_variant=None,
            cache_present=False,
            provider_can_produce=True,
            cache_provider_identity=None,
            validation_result="ok",
            missing_reason=None,
          )
        )
        continue
      entry = store.get(AnalysisCacheKey(record.record_id, required))
      can_produce = bool(provider_can_produce.get(f"{record.record_id}::{required}", False))
      if entry is None:
        if can_produce and run_mode != "official":
          validation = "ok"
          reason = None
        else:
          validation = "missing_cache"
          reason = f"no_cache_for_variant:{required}"
        rows.append(
          CoverageMatrixRow(
            record_id=record.record_id,
            system_id=system_id,
            required_analysis_variant=required,
            cache_present=False,
            provider_can_produce=can_produce,
            cache_provider_identity=None,
            validation_result=validation,
            missing_reason=reason,
          )
        )
        continue
      try:
        store.validate_entry_integrity(entry, record=record)
        validation = "ok"
        reason = None
      except SystemsContractError as exc:
        validation = "invalid_cache"
        reason = str(exc)
      # Official mode additionally requires approved provenance when the
      # system capability demands it (checked by the runner). Here we only
      # validate structural integrity of the matched variant entry.
      if run_mode == "official" and validation == "ok":
        # Presence of a matching entry is necessary but not sufficient for
        # official approval; method==approved is checked separately.
        _ = ids
      rows.append(
        CoverageMatrixRow(
          record_id=record.record_id,
          system_id=system_id,
          required_analysis_variant=required,
          cache_present=True,
          provider_can_produce=can_produce,
          cache_provider_identity=entry.provider_id,
          validation_result=validation,
          missing_reason=reason,
        )
      )
  return CoverageMatrix(rows=rows)


def coerce_analysis_cache(
  value: AnalysisCacheStore | Mapping[Any, Any] | None,
  *,
  compatibility_mode: str = "legacy_as_full_context",
) -> AnalysisCacheStore:
  """Normalise cache inputs into an ``AnalysisCacheStore``.

  Modes:
  - ``legacy_as_full_context``: flat ``{record_id: StructuredAnalysis}`` is
    accepted as full_context with a deprecation warning (synthetic/dev only).
  - ``reject_legacy``: flat mappings are rejected (official / strict paths).
  """
  if value is None:
    return AnalysisCacheStore()
  if isinstance(value, AnalysisCacheStore):
    return value
  if not isinstance(value, Mapping):
    raise SystemsContractError(f"analysis cache must be a mapping or AnalysisCacheStore, got {type(value)!r}")

  store = AnalysisCacheStore()
  if not value:
    return store

  sample_key = next(iter(value.keys()))
  # Already typed: AnalysisCacheKey or (record_id, variant) tuples / "id::variant"
  if isinstance(sample_key, AnalysisCacheKey) or (
    isinstance(sample_key, tuple) and len(sample_key) == 2
  ) or (isinstance(sample_key, str) and "::" in sample_key and sample_key.rsplit("::", 1)[-1] in ANALYSIS_VARIANTS):
    for key, payload in value.items():
      entry = _entry_from_payload(key, payload)
      store.put(entry)
    return store

  # Nested {record_id: {variant: analysis}} form
  sample_val = value[sample_key]
  if isinstance(sample_val, Mapping) and any(
    isinstance(k, str) and k in ANALYSIS_VARIANTS for k in sample_val.keys()
  ):
    for record_id, variants in value.items():
      if not isinstance(variants, Mapping):
        raise SystemsContractError(f"nested cache for {record_id!r} must be a mapping")
      for variant, payload in variants.items():
        entry = _entry_from_payload(AnalysisCacheKey(str(record_id), str(variant)), payload)
        store.put(entry)
    return store

  # Legacy flat {record_id: StructuredAnalysis}
  if compatibility_mode == "reject_legacy":
    raise SystemsContractError(
      "legacy flat record_id->analysis cache is not permitted in this mode; "
      "supply AnalysisCacheKey-keyed entries or nested variant maps"
    )
  if compatibility_mode != "legacy_as_full_context":
    raise SystemsContractError(f"unknown compatibility_mode: {compatibility_mode!r}")

  warnings.warn(
    "legacy flat analysis cache {record_id: StructuredAnalysis} interpreted as "
    "full_context; migrate to AnalysisCacheKey-keyed storage",
    DeprecationWarning,
    stacklevel=2,
  )
  for record_id, payload in value.items():
    analysis = _as_analysis(payload)
    # Build a minimal entry without a SystemInput fingerprint when only the
    # legacy mapping is available. Callers that need integrity checks should
    # rebuild via AnalysisCacheEntry.from_analysis.
    prov = analysis.analysis_provenance
    entry = AnalysisCacheEntry(
      record_id=str(record_id),
      analysis_variant="full_context",
      source_input_hash="legacy_unverified",
      analysis_content_hash=analysis.fingerprint(),
      provider_id=prov.provider_id if prov else None,
      provider_version=prov.provider_version if prov else None,
      selected_base_model=None,
      selected_adapter=None,
      selected_model_strategy=None,
      prompt_contract_id=None,
      schema_version=None,
      analysis_provenance=prov.to_dict() if prov else None,
      analysis=copy.deepcopy(analysis),
      analysis_identity=None,
    )
    store.put(entry)
  return store


def migrate_legacy_cache(
  legacy: Mapping[str, StructuredAnalysis],
  *,
  records: Mapping[str, SystemInput] | Iterable[SystemInput],
  analysis_variant: str = "full_context",
  identities: SelectedIdentities | None = None,
) -> AnalysisCacheStore:
  """Convert a flat legacy cache into a typed store (explicit full_context)."""
  if analysis_variant not in ANALYSIS_VARIANTS:
    raise SystemsContractError(f"unsupported analysis_variant: {analysis_variant!r}")
  if isinstance(records, Mapping):
    by_id = dict(records)
  else:
    by_id = {r.record_id: r for r in records}
  store = AnalysisCacheStore()
  for record_id, analysis in legacy.items():
    record = by_id.get(record_id)
    if record is None:
      raise SystemsContractError(f"legacy cache record_id not in records: {record_id!r}")
    entry = AnalysisCacheEntry.from_analysis(
      record=record,
      analysis=analysis,
      analysis_variant=analysis_variant,
      identities=identities,
    )
    store.put(entry)
  return store


def _as_analysis(payload: Any) -> StructuredAnalysis:
  if isinstance(payload, StructuredAnalysis):
    return payload
  if isinstance(payload, AnalysisCacheEntry):
    return payload.analysis
  if isinstance(payload, Mapping):
    if "analysis" in payload and isinstance(payload["analysis"], (dict, StructuredAnalysis)):
      inner = payload["analysis"]
      return inner if isinstance(inner, StructuredAnalysis) else StructuredAnalysis.from_dict(inner)
    return StructuredAnalysis.from_dict(dict(payload))
  raise SystemsContractError(f"cannot coerce payload to StructuredAnalysis: {type(payload)!r}")


def _entry_from_payload(key: Any, payload: Any) -> AnalysisCacheEntry:
  if isinstance(key, AnalysisCacheKey):
    cache_key = key
  elif isinstance(key, tuple) and len(key) == 2:
    cache_key = AnalysisCacheKey(str(key[0]), str(key[1]))
  elif isinstance(key, str) and "::" in key:
    record_id, variant = key.rsplit("::", 1)
    cache_key = AnalysisCacheKey(record_id, variant)
  else:
    raise SystemsContractError(f"unsupported cache key form: {key!r}")

  if isinstance(payload, AnalysisCacheEntry):
    if payload.key != cache_key:
      raise SystemsContractError("AnalysisCacheEntry key does not match mapping key")
    return payload

  analysis = _as_analysis(payload)
  if isinstance(payload, Mapping) and "source_input_hash" in payload:
    prov = analysis.analysis_provenance
    return AnalysisCacheEntry(
      record_id=cache_key.record_id,
      analysis_variant=cache_key.analysis_variant,
      source_input_hash=str(payload["source_input_hash"]),
      analysis_content_hash=str(
        payload.get("analysis_content_hash") or analysis.fingerprint()
      ),
      provider_id=payload.get("provider_id") or (prov.provider_id if prov else None),
      provider_version=payload.get("provider_version")
      or (prov.provider_version if prov else None),
      selected_base_model=payload.get("selected_base_model"),
      selected_adapter=payload.get("selected_adapter"),
      selected_model_strategy=payload.get("selected_model_strategy"),
      prompt_contract_id=payload.get("prompt_contract_id"),
      schema_version=payload.get("schema_version"),
      analysis_provenance=(
        payload.get("analysis_provenance")
        if payload.get("analysis_provenance") is not None
        else (prov.to_dict() if prov else None)
      ),
      analysis=copy.deepcopy(analysis),
      analysis_identity=None,
    )

  # Minimal entry when only an analysis object is supplied under a typed key.
  prov = analysis.analysis_provenance
  return AnalysisCacheEntry(
    record_id=cache_key.record_id,
    analysis_variant=cache_key.analysis_variant,
    source_input_hash="unverified",
    analysis_content_hash=analysis.fingerprint(),
    provider_id=prov.provider_id if prov else None,
    provider_version=prov.provider_version if prov else None,
    selected_base_model=None,
    selected_adapter=None,
    selected_model_strategy=None,
    prompt_contract_id=None,
    schema_version=None,
    analysis_provenance=prov.to_dict() if prov else None,
    analysis=copy.deepcopy(analysis),
    analysis_identity=None,
  )


def shared_full_context_identity_fingerprint(
  store: AnalysisCacheStore,
  record_id: str,
) -> str | None:
  """Return the shared full_context identity fingerprint when present."""
  entry = store.get(AnalysisCacheKey(record_id, "full_context"))
  if entry is None:
    return None
  if entry.analysis_identity is not None:
    return entry.analysis_identity.fingerprint()
  return sha256_json(
    {
      "record_id": entry.record_id,
      "analysis_variant": entry.analysis_variant,
      "source_input_hash": entry.source_input_hash,
      "analysis_content_hash": entry.analysis_content_hash,
      "provider_id": entry.provider_id,
      "provider_version": entry.provider_version,
    }
  )
