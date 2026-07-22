"""Experiment runner with synthetic/development/official gates.

Integrity model
---------------
* ``RunContext`` (Section E) is the single owner of the ``synthetic_only`` /
  ``official_result`` flags on every persisted result; adapters may set
  whatever values they like internally but the runner always overwrites them
  before a row is written, and recomputes the result hash accordingly.
  Official mode uses ``pending_official`` -> gate checks ->
  ``approved_official`` (``official_result=True`` only after all gates pass).
* The input manifest (Section C) hashes the *complete* ``SystemInput``
  records (including dialogue/scene/capability context, eligibility
  metadata, protected-data flags), plus any supplied cached analysis content
  and provenance (including analysis variant and source-input hash), the
  input schema version, and an explicit record-ordering policy. It
  intentionally excludes timestamps so identical inputs always hash
  identically.
* Resuming a run (Section D) re-derives the same identity bundle used at
  original-run time (systems/versions, provider identities, model
  identities, evaluator version, source commit) and refuses to continue if
  anything about the run's identity - or any already-written result's hash -
  has drifted. Growing the record set on resume is allowed; silently losing
  track of already-completed work is not.
* Official-mode gating (Section B) is derived from the system capability
  registry (``ambiguity_manager.systems.capabilities``), never from
  hard-coded system-id checks. Failed gates raise before any result rows
  are written.
* Protected-data records (Section F) are refused outright outside
  ``run_mode="official"``.
* ``verify_run`` (Section G) independently re-derives everything it can from
  the artefacts on disk and writes a ``verification_report.json``.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema.v2.version import SCHEMA_VERSION
from ambiguity_manager.systems.capabilities import (
  SystemCapabilities,
  is_provenance_approved,
  load_capability_registry,
)
from ambiguity_manager.systems.analysis import (
  AnalysisIdentity,
  build_analysis_identity,
  is_context_blind_provenance,
)
from ambiguity_manager.systems.analysis_cache import (
  AnalysisCacheEntry,
  AnalysisCacheKey,
  AnalysisCacheStore,
  build_coverage_matrix,
  coerce_analysis_cache,
  required_variant_for_system,
  resolve_cached_analysis_for_system,
)
from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput, SystemResult
from ambiguity_manager.systems.errors import (
  DuplicateResultError,
  OfficialRunBlockedError,
  ProtectedDataBlockedError,
  ResumeContractError,
  SystemsContractError,
)
from ambiguity_manager.systems.hashing import sha256_hex, sha256_json
from ambiguity_manager.systems.model_identities import SelectedIdentities, load_selected_identities
from ambiguity_manager.systems.provenance import build_run_provenance, utc_now_iso
from ambiguity_manager.systems.variants import SYSTEM_IDS, get_registry


RECORD_ORDERING_POLICY = "as_provided_stable_list_order"


def _git_commit(root: Path) -> str | None:
  try:
    out = subprocess.check_output(
      ["git", "rev-parse", "HEAD"],
      cwd=str(root),
      stderr=subprocess.DEVNULL,
      text=True,
    )
    return out.strip()
  except (subprocess.CalledProcessError, FileNotFoundError, OSError):
    return None


def load_json(path: Path) -> Any:
  return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
  if not path.is_file():
    return []
  rows: list[dict[str, Any]] = []
  for line in path.read_text(encoding="utf-8").splitlines():
    if line.strip():
      rows.append(json.loads(line))
  return rows


def _default_evaluator_version() -> str:
  # Lazily imported: evaluation.evaluator is lightweight (no heavy ML deps)
  # but this keeps execution.py's own import surface minimal.
  from ambiguity_manager.evaluation.evaluator import DeterministicEvaluator

  return DeterministicEvaluator().evaluator_version


def _record_is_explicitly_synthetic(record: SystemInput) -> bool:
  source = (record.input_provenance.source or "").strip().lower()
  return source == "synthetic"


@dataclass(frozen=True)
class RunContext:
  """Runner-owned execution-mode flags.

  Adapters/systems must never be trusted to set ``synthetic_only`` /
  ``official_result`` themselves for the persisted record; the runner always
  derives them from the validated ``RunContext`` and overwrites whatever the
  adapter returned.

  Official mode uses an explicit approval transition:
  ``pending_official()`` -> gate checks -> ``approved_official()``.
  Only the approved context may label results ``official_result=True``.
  """

  run_mode: str
  synthetic_only: bool
  official_result: bool
  approved: bool = True

  @classmethod
  def for_run_mode(
    cls,
    run_mode: str,
    *,
    synthetic_inputs: bool = False,
  ) -> "RunContext":
    if run_mode == "synthetic_smoke":
      return cls(
        run_mode=run_mode,
        synthetic_only=True,
        official_result=False,
        approved=True,
      )
    if run_mode == "development":
      return cls(
        run_mode=run_mode,
        synthetic_only=bool(synthetic_inputs),
        official_result=False,
        approved=True,
      )
    if run_mode == "official":
      # Official mode starts unapproved. Callers must transition through
      # approved_official() after every prerequisite gate passes.
      return cls.pending_official()
    raise ValueError(f"unknown run_mode: {run_mode}")

  @classmethod
  def pending_official(cls) -> "RunContext":
    """Unapproved official context — must not be used to label result rows."""
    return cls(
      run_mode="official",
      synthetic_only=False,
      official_result=False,
      approved=False,
    )

  @classmethod
  def approved_official(cls) -> "RunContext":
    """Validated official context after every prerequisite gate has passed."""
    return cls(
      run_mode="official",
      synthetic_only=False,
      official_result=True,
      approved=True,
    )

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "RunContext":
    if not isinstance(data, dict):
      raise ValueError("run_context must be an object")
    run_mode = str(data.get("run_mode") or "")
    return cls(
      run_mode=run_mode,
      synthetic_only=bool(data.get("synthetic_only", False)),
      official_result=bool(data.get("official_result", False)),
      approved=bool(data.get("approved", True)),
    )

  def ensure_executable(self) -> None:
    if self.run_mode == "official" and not self.approved:
      raise OfficialRunBlockedError(["official_run_context_not_approved"])
    if self.official_result and not self.approved:
      raise OfficialRunBlockedError(["official_result_requires_approved_context"])

  def apply(
    self,
    result: SystemResult,
    *,
    run_id: str | None = None,
  ) -> SystemResult:
    """Overwrite the runner-owned flags on ``result`` and recompute its hash."""
    self.ensure_executable()
    result.synthetic_only = self.synthetic_only
    result.official_result = self.official_result
    result.run_mode = self.run_mode
    if run_id is not None:
      result.run_id = run_id
    return result.with_computed_hash()

  def to_dict(self) -> dict[str, Any]:
    return {
      "run_mode": self.run_mode,
      "synthetic_only": self.synthetic_only,
      "official_result": self.official_result,
      "approved": self.approved,
    }


@dataclass
class OfficialPrerequisites:
  adjudicated_gold_dataset: Path | None = None
  t15_split_manifest: Path | None = None
  protocol_freeze_identifier: str | None = None
  selected_model_strategy: str | None = None
  selected_base_model: str | None = None
  selected_adapter: str | None = None
  handbook_version: str | None = None
  schema_version: str = SCHEMA_VERSION

  @classmethod
  def from_selected_identities(
    cls,
    identities: SelectedIdentities | None = None,
    **overrides: Any,
  ) -> "OfficialPrerequisites":
    """Build prerequisites whose model-identity fields come from the identity
    contract (``configs/model/selected_identities_v1.json``). All three
    remain ``None`` for as long as that contract's fields are null.
    """
    resolved = identities if identities is not None else load_selected_identities()
    kwargs: dict[str, Any] = {
      "selected_base_model": resolved.selected_base_model,
      "selected_adapter": resolved.selected_adapter,
      "selected_model_strategy": resolved.selected_model_strategy,
    }
    kwargs.update(overrides)
    return cls(**kwargs)

  def missing(self, *, capabilities: list[SystemCapabilities] | None = None) -> list[str]:
    caps = capabilities or []
    missing: list[str] = []
    if self.adjudicated_gold_dataset is None or not Path(self.adjudicated_gold_dataset).is_file():
      missing.append("adjudicated_gold_dataset")
    if self.t15_split_manifest is None or not Path(self.t15_split_manifest).is_file():
      missing.append("t15_split_manifest")
    if not self.protocol_freeze_identifier:
      missing.append("protocol_freeze_identifier")
    if any(c.requires_selected_model_strategy for c in caps) and not self.selected_model_strategy:
      missing.append("selected_model_strategy")
    if any(c.requires_selected_base_model for c in caps) and not self.selected_base_model:
      missing.append("selected_base_model")
    if any(c.requires_selected_adapter for c in caps) and not self.selected_adapter:
      missing.append("selected_adapter")
    if not self.handbook_version:
      missing.append("handbook_version")
    return missing


@dataclass
class ExperimentRunner:
  paths: ProjectPaths = field(default_factory=ProjectPaths.from_repo_root)
  registry: dict[str, Any] = field(default_factory=get_registry)

  def validate_config(self, config: dict[str, Any] | Path) -> dict[str, Any]:
    if isinstance(config, Path):
      config = load_json(config)
    required = ["config_id", "run_mode", "systems"]
    missing = [k for k in required if k not in config]
    if missing:
      raise ValueError(f"invalid config missing fields: {missing}")
    if config["run_mode"] not in {"synthetic_smoke", "development", "official"}:
      raise ValueError(f"invalid run_mode: {config['run_mode']}")
    for sid in config["systems"]:
      if sid not in SYSTEM_IDS:
        raise ValueError(f"unknown system: {sid}")
    return config

  # -- Section B: capability-registry-derived official gates ---------------

  def check_official_gates(
    self,
    *,
    prerequisites: OfficialPrerequisites,
    systems: list[str],
    protected_labels_in_prompts: bool = False,
    capabilities: dict[str, SystemCapabilities] | None = None,
    identities: SelectedIdentities | None = None,
    cached_analyses: AnalysisCacheStore | dict[Any, Any] | None = None,
    records: list[SystemInput] | None = None,
  ) -> None:
    capabilities = capabilities if capabilities is not None else load_capability_registry()
    identities = identities if identities is not None else load_selected_identities()
    # Official mode rejects legacy flat caches; require typed variant keys.
    try:
      cache_store = coerce_analysis_cache(cached_analyses, compatibility_mode="reject_legacy")
    except SystemsContractError as exc:
      raise OfficialRunBlockedError([f"analysis_cache:{exc}"]) from exc
    caps = [capabilities[sid] for sid in systems if sid in capabilities]

    missing = prerequisites.missing(capabilities=caps)
    if protected_labels_in_prompts:
      missing.append("protected_label_leakage")

    provider_missing_reported = False
    for sid in systems:
      cap = capabilities.get(sid)
      if cap is None:
        missing.append(f"{sid}:unknown_system_capabilities")
        continue
      if "official" not in cap.allowed_run_modes:
        missing.append(f"{sid}:official_run_mode_not_allowed")
      if cap.requires_live_model_provider:
        system = self.registry.get(sid)
        if system is None or getattr(system, "provider", None) is None:
          # Kept as a bare "model_provider" entry (not system-prefixed) for
          # backward compatibility with existing probes/tests.
          if not provider_missing_reported:
            missing.append("model_provider")
            provider_missing_reported = True
      if cap.forbids_selected_adapter and identities.selected_adapter is not None:
        missing.append(f"{sid}:base_model_must_remain_unadapted")
      if cap.requires_approved_analysis_provenance_in_official_mode:
        required_variant = (
          cap.required_analysis_variant
          if cap.required_analysis_variant is not None
          else required_variant_for_system(sid)
        )
        if required_variant is None:
          continue
        # Per (record, system, required variant) provenance coverage.
        record_list = list(records or [])
        if not record_list:
          # Without records, require at least one approved matching-variant entry.
          approved = any(
            entry.analysis_variant == required_variant
            and is_provenance_approved(entry.analysis.analysis_provenance)
            for entry in cache_store.values()
          )
          if not approved:
            missing.append(f"{sid}:approved_analysis_provenance")
          continue
        for record in record_list:
          entry = cache_store.get(AnalysisCacheKey(record.record_id, required_variant))
          if entry is None or not is_provenance_approved(entry.analysis.analysis_provenance):
            missing.append(
              f"{sid}:approved_analysis_provenance:{record.record_id}:{required_variant}"
            )

    if records is not None:
      coverage = build_coverage_matrix(
        records=records,
        systems=systems,
        cache=cache_store,
        run_mode="official",
        identities=identities,
      )
      for row in coverage.missing_rows():
        missing.append(
          f"coverage:{row.system_id}:{row.record_id}:{row.required_analysis_variant}:{row.validation_result}"
        )

    if missing:
      raise OfficialRunBlockedError(missing)

  # -- Section C: full input-manifest hashing -------------------------------

  def _record_identity_hash(
    self,
    record: SystemInput,
    cached_entries: list[AnalysisCacheEntry] | StructuredAnalysis | None,
  ) -> str:
    if isinstance(cached_entries, StructuredAnalysis):
      entries_payload = [
        {
          "cached_analysis": cached_entries.to_dict(),
          "analysis_identity": self._cached_analysis_identity(record, cached_entries).to_dict(),
        }
      ]
    elif cached_entries:
      entries_payload = []
      for entry in sorted(cached_entries, key=lambda e: e.analysis_variant):
        entries_payload.append(
          {
            "analysis_variant": entry.analysis_variant,
            "cached_analysis": entry.analysis.to_dict(),
            "source_input_hash": entry.source_input_hash,
            "analysis_content_hash": entry.analysis_content_hash,
            "analysis_identity": (
              entry.analysis_identity.to_dict()
              if entry.analysis_identity is not None
              else self._cached_analysis_identity(record, entry.analysis).to_dict()
            ),
          }
        )
    else:
      entries_payload = []
    return sha256_json(
      {
        "input": record.to_dict(),
        "cached_analyses": entries_payload,
      }
    )

  def _cached_analysis_identity(
    self,
    record: SystemInput,
    cached: StructuredAnalysis,
    *,
    analysis_variant: str | None = None,
  ) -> AnalysisIdentity:
    if analysis_variant is None:
      is_blind = is_context_blind_provenance(cached.analysis_provenance)
      variant = "context_blind" if is_blind else "full_context"
    else:
      variant = analysis_variant
    source_input = record.without_context() if variant == "context_blind" else record
    return build_analysis_identity(
      record_id=record.record_id,
      source_input=source_input,
      analysis=cached,
      analysis_variant=variant,
    )

  def _entries_for_record(
    self,
    store: AnalysisCacheStore,
    record: SystemInput,
  ) -> list[AnalysisCacheEntry]:
    entries: list[AnalysisCacheEntry] = []
    for variant in sorted(("full_context", "context_blind")):
      entry = store.get(AnalysisCacheKey(record.record_id, variant))
      if entry is not None:
        entries.append(entry)
    return entries

  def _build_input_manifest(
    self,
    *,
    records: list[SystemInput],
    cached_analyses: AnalysisCacheStore | dict[Any, Any],
    systems: list[str],
    run_mode: str,
  ) -> tuple[dict[str, Any], dict[str, str]]:
    compatibility = (
      "reject_legacy" if run_mode == "official" else "legacy_as_full_context"
    )
    store = coerce_analysis_cache(cached_analyses, compatibility_mode=compatibility)
    record_entries: list[dict[str, Any]] = []
    fingerprints: dict[str, str] = {}
    for record in records:
      entries = self._entries_for_record(store, record)
      identity_hash = self._record_identity_hash(record, entries)
      fingerprints[record.record_id] = identity_hash
      cached_variant_payloads: list[dict[str, Any]] = []
      for entry in entries:
        try:
          store.validate_entry_integrity(entry, record=record)
        except SystemsContractError:
          # Integrity failures are surfaced via coverage matrix; still record.
          pass
        identity = entry.analysis_identity or self._cached_analysis_identity(
          record,
          entry.analysis,
          analysis_variant=entry.analysis_variant,
        )
        cached_variant_payloads.append(
          {
            "record_id": entry.record_id,
            "analysis_variant": entry.analysis_variant,
            "source_input_hash": entry.source_input_hash,
            "analysis_content_hash": entry.analysis_content_hash,
            "provider_id": entry.provider_id,
            "provider_version": entry.provider_version,
            "selected_base_model": entry.selected_base_model,
            "selected_adapter": entry.selected_adapter,
            "selected_model_strategy": entry.selected_model_strategy,
            "prompt_contract_id": entry.prompt_contract_id,
            "schema_version": entry.schema_version,
            "analysis_provenance": entry.analysis_provenance,
            "analysis_identity": identity.to_dict(),
            "cached_analysis": entry.analysis.to_dict(),
            "cached_analysis_fingerprint": entry.analysis.fingerprint(),
          }
        )
      # Backward-compatible single-entry projection prefers full_context.
      primary = next(
        (e for e in entries if e.analysis_variant == "full_context"),
        entries[0] if entries else None,
      )
      entry: dict[str, Any] = {
        "record_id": record.record_id,
        "input": record.to_dict(),
        "input_fingerprint": record.fingerprint(),
        "ablated_input_fingerprint": record.without_context().fingerprint(),
        "cached_analyses": cached_variant_payloads,
        "cached_analysis": primary.analysis.to_dict() if primary is not None else None,
        "cached_analysis_fingerprint": (
          primary.analysis.fingerprint() if primary is not None else None
        ),
        "record_identity_hash": identity_hash,
      }
      if primary is not None:
        analysis_identity = primary.analysis_identity or self._cached_analysis_identity(
          record,
          primary.analysis,
          analysis_variant=primary.analysis_variant,
        )
        entry["analysis_identity"] = analysis_identity.to_dict()
        entry["analysis_variant"] = analysis_identity.analysis_variant
        entry["source_input_hash"] = analysis_identity.source_input_hash
        entry["analysis_content_hash"] = analysis_identity.analysis_content_hash
      else:
        entry["analysis_identity"] = None
        entry["analysis_variant"] = None
        entry["source_input_hash"] = None
        entry["analysis_content_hash"] = None
      record_entries.append(entry)

    coverage = build_coverage_matrix(
      records=records,
      systems=systems,
      cache=store,
      run_mode=run_mode,
    )
    manifest = {
      "input_schema_version": SCHEMA_VERSION,
      "run_mode": run_mode,
      "systems": list(systems),
      "record_ordering_policy": RECORD_ORDERING_POLICY,
      "record_count": len(records),
      "records": record_entries,
      "cached_analysis_entries": store.to_manifest_entries(),
      "cache_store_fingerprint": store.fingerprint(),
      "coverage_matrix": coverage.to_dict(),
    }
    return manifest, fingerprints


  def _expected_matrix(self, records: list[SystemInput], systems: list[str]) -> list[str]:
    return sorted(self._result_key(r.record_id, sid) for r in records for sid in systems)

  # -- Section D: resume contract identity bundle ---------------------------

  def _build_identity_bundle(self, *, systems: list[str]) -> dict[str, Any]:
    system_versions: dict[str, str | None] = {}
    provider_identities: dict[str, dict[str, Any]] = {}
    for sid in systems:
      system = self.registry.get(sid)
      if system is None:
        system_versions[sid] = None
        continue
      system_versions[sid] = getattr(system, "system_version", None)
      provider = getattr(system, "provider", None) or getattr(system, "analysis_provider", None)
      if provider is not None:
        provider_identities[sid] = {
          "provider_id": getattr(provider, "provider_id", None),
          "provider_version": getattr(provider, "provider_version", None),
        }
    identities = load_selected_identities()
    return {
      "system_versions": system_versions,
      "provider_identities": provider_identities,
      "model_identities": {
        "selected_base_model": identities.selected_base_model,
        "selected_adapter": identities.selected_adapter,
        "selected_model_strategy": identities.selected_model_strategy,
      },
      "evaluator_version": _default_evaluator_version(),
    }

  def _verify_resume_contract(
    self,
    *,
    existing_manifest: dict[str, Any],
    config_hash: str,
    run_mode: str,
    systems: list[str],
    records: list[SystemInput],
    cached_analyses: AnalysisCacheStore | Mapping[Any, Any],
    results_path: Path,
  ) -> None:
    mismatches: list[str] = []

    if existing_manifest.get("run_mode") != run_mode:
      mismatches.append("run_mode")
    if existing_manifest.get("config_hash") != config_hash:
      mismatches.append("config_hash")
    if existing_manifest.get("systems") != list(systems):
      mismatches.append("systems")

    stored_contract = existing_manifest.get("resume_contract") or {}
    fresh_bundle = self._build_identity_bundle(systems=systems)
    fresh_source_commit = _git_commit(self.paths.root)
    for key in ("system_versions", "provider_identities", "model_identities", "evaluator_version"):
      if stored_contract.get(key) != fresh_bundle.get(key):
        mismatches.append(key)
    if stored_contract.get("source_commit") != fresh_source_commit:
      mismatches.append("source_commit")

    existing_rows = _read_jsonl(results_path)
    completed_keys: set[str] = set()
    result_hash_mismatches: list[str] = []
    for row in existing_rows:
      key = self._result_key(row["record_id"], row["system_id"])
      completed_keys.add(key)
      recomputed = SystemResult.from_dict(row).compute_hash()
      if recomputed != row.get("result_hash"):
        result_hash_mismatches.append(key)
    if result_hash_mismatches:
      mismatches.append(f"existing_result_hash:{sorted(result_hash_mismatches)}")

    compatibility = (
      "reject_legacy" if run_mode == "official" else "legacy_as_full_context"
    )
    store = coerce_analysis_cache(cached_analyses, compatibility_mode=compatibility)
    stored_fingerprints: dict[str, str] = existing_manifest.get("record_identity_fingerprints") or {}
    current_by_id = {r.record_id: r for r in records}
    completed_record_ids = {key.split("::", 1)[0] for key in completed_keys}
    for record_id in completed_record_ids:
      record = current_by_id.get(record_id)
      if record is None:
        mismatches.append(f"input_manifest:missing_completed_record:{record_id}")
        continue
      fresh_fp = self._record_identity_hash(record, self._entries_for_record(store, record))
      stored_fp = stored_fingerprints.get(record_id)
      if stored_fp is not None and stored_fp != fresh_fp:
        mismatches.append(f"input_manifest:record_changed:{record_id}")

    expected_matrix = set(self._expected_matrix(records, systems))
    orphaned = sorted(completed_keys - expected_matrix)
    if orphaned:
      mismatches.append(f"expected_matrix:orphaned_results:{orphaned}")

    if mismatches:
      raise ResumeContractError(mismatches)

  def _run_dir(self, run_id: str, run_mode: str) -> Path:
    base = self.paths.outputs / "manager_experiments"
    if run_mode == "synthetic_smoke":
      base = base / "synthetic"
    elif run_mode == "development":
      base = base / "development"
    else:
      base = base / "official"
    return base / run_id

  def _result_key(self, record_id: str, system_id: str) -> str:
    return f"{record_id}::{system_id}"

  def run(
    self,
    *,
    config: dict[str, Any],
    records: list[SystemInput],
    cached_analyses: AnalysisCacheStore | Mapping[Any, Any] | None = None,
    run_id: str | None = None,
    resume: bool = False,
    output_dir: Path | None = None,
    dry_run: bool = False,
    prerequisites: OfficialPrerequisites | None = None,
    protected_labels_in_prompts: bool = False,
  ) -> dict[str, Any]:
    config = self.validate_config(config)
    run_mode = config["run_mode"]
    systems = list(config.get("systems") or list(SYSTEM_IDS))
    compatibility = (
      "reject_legacy" if run_mode == "official" else "legacy_as_full_context"
    )
    cache_store = coerce_analysis_cache(
      cached_analyses or {},
      compatibility_mode=compatibility,
    )

    # Section F: protected-data gate. Refuse outright outside official mode;
    # synthetic and development runs must never process protected records.
    if run_mode != "official":
      for record in records:
        if record.protected_data:
          raise ProtectedDataBlockedError(record.record_id, run_mode)

    # Build RunContext only after mode validation. Official mode remains
    # unapproved until every prerequisite gate passes; failed gates raise
    # before any result rows are written.
    if run_mode == "official":
      pending = RunContext.pending_official()
      assert pending.approved is False and pending.official_result is False
      missing: list[str] = []
      synthetic_ids = [
        r.record_id for r in records if _record_is_explicitly_synthetic(r)
      ]
      if synthetic_ids:
        missing.append(f"official_cannot_use_synthetic_inputs:{sorted(synthetic_ids)}")
      try:
        self.check_official_gates(
          prerequisites=prerequisites or OfficialPrerequisites(),
          systems=systems,
          protected_labels_in_prompts=protected_labels_in_prompts,
          cached_analyses=cache_store,
          records=records,
        )
      except OfficialRunBlockedError as exc:
        missing.extend(exc.missing)
      if missing:
        raise OfficialRunBlockedError(missing)
      run_context = RunContext.approved_official()
    elif run_mode == "development":
      synthetic_inputs = bool(records) and all(
        _record_is_explicitly_synthetic(r) for r in records
      )
      run_context = RunContext.for_run_mode(
        "development",
        synthetic_inputs=synthetic_inputs,
      )
    else:
      run_context = RunContext.for_run_mode(run_mode)
    run_context.ensure_executable()

    config_hash = sha256_json(config)
    input_manifest, record_fingerprints = self._build_input_manifest(
      records=records,
      cached_analyses=cache_store,
      systems=systems,
      run_mode=run_mode,
    )
    input_manifest_hash = sha256_json(input_manifest)
    if run_id is None:
      run_id = sha256_hex(f"{config_hash}:{input_manifest_hash}".encode("utf-8"))[:16]
      run_id = f"{run_mode}-{run_id}"

    out_dir = output_dir or self._run_dir(run_id, run_mode)
    results_path = out_dir / "results.jsonl"
    failures_path = out_dir / "failures.jsonl"
    summary_path = out_dir / "summary.json"
    manifest_path = out_dir / "run_manifest.json"

    if resume and manifest_path.is_file():
      existing_manifest = load_json(manifest_path)
      self._verify_resume_contract(
        existing_manifest=existing_manifest,
        config_hash=config_hash,
        run_mode=run_mode,
        systems=systems,
        records=records,
        cached_analyses=cache_store,
        results_path=results_path,
      )

    completed: set[str] = set()
    if resume and results_path.is_file():
      for row in _read_jsonl(results_path):
        completed.add(self._result_key(row["record_id"], row["system_id"]))

    if out_dir.exists() and not resume and results_path.exists() and not dry_run:
      # Never overwrite a completed run silently.
      raise DuplicateResultError(f"run directory already exists: {out_dir}")

    if dry_run:
      return {
        "run_id": run_id,
        "dry_run": True,
        "systems": systems,
        "record_count": len(records),
        "output_dir": str(out_dir),
      }

    out_dir.mkdir(parents=True, exist_ok=True)
    provenance = build_run_provenance(
      source_commit=_git_commit(self.paths.root),
      run_mode=run_mode,
      system_ids=systems,
      config_hashes={"experiment_config": config_hash},
      input_manifest_hash=input_manifest_hash,
      schema_version=SCHEMA_VERSION,
      evaluator_version=_default_evaluator_version(),
      synthetic_only=run_context.synthetic_only,
      official_result=run_context.official_result,
    )

    results_count = 0
    failures_count = 0
    skipped_count = 0
    not_executable_count = 0

    # Append mode for resume; otherwise create fresh.
    results_mode = "a" if resume else "w"
    failures_mode = "a" if resume else "w"

    with results_path.open(results_mode, encoding="utf-8") as results_fh, failures_path.open(
      failures_mode, encoding="utf-8"
    ) as failures_fh:
      for record in records:
        for system_id in systems:
          key = self._result_key(record.record_id, system_id)
          if key in completed:
            continue
          system = self.registry[system_id]
          try:
            cached = resolve_cached_analysis_for_system(
              cache_store,
              record_id=record.record_id,
              system_id=system_id,
            )
            result: SystemResult = system.run(record, cached_analysis=cached)
            if result.execution_status in {"provider_unavailable", "not_executable"}:
              not_executable_count += 1
            result = run_context.apply(result, run_id=run_id)
            row = result.to_dict()
            row["run_id"] = run_id
            row["run_mode"] = run_mode
            # Guard duplicates within the same write pass.
            if key in completed:
              raise DuplicateResultError(key)
            results_fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
            completed.add(key)
            results_count += 1
          except Exception as exc:  # noqa: BLE001 - retain failures honestly
            failures_count += 1
            failure = {
              "run_id": run_id,
              "record_id": record.record_id,
              "system_id": system_id,
              "error_type": type(exc).__name__,
              "error_message": str(exc),
              "created_at": utc_now_iso(),
            }
            failures_fh.write(json.dumps(failure, sort_keys=True, ensure_ascii=False) + "\n")
            # Also retain a not-lost marker in results for visibility? Spec says failures JSONL
            # and no silent record loss — emit a skipped/failed result row too.
            failed_result = run_context.apply(
              SystemResult(
                record_id=record.record_id,
                system_id=system_id,
                system_version=getattr(system, "system_version", "1.0.0"),
                analysis=StructuredAnalysis(),
                recommended_strategy=None,
                execution_status="failed",
                runtime_metadata={"error_type": type(exc).__name__, "error_message": str(exc)},
              ),
              run_id=run_id,
            )
            row = failed_result.to_dict()
            row["run_id"] = run_id
            row["run_mode"] = run_mode
            results_fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
            completed.add(key)
            skipped_count += 1

    summary = {
      "run_id": run_id,
      "run_mode": run_mode,
      "config_id": config.get("config_id"),
      "config_hash": config_hash,
      "input_manifest_hash": input_manifest_hash,
      "systems": systems,
      "record_count": len(records),
      "results_written": results_count,
      "failures_written": failures_count,
      "skipped_or_failed_retained": skipped_count,
      "not_executable_count": not_executable_count,
      "completed_keys": len(completed),
      "synthetic_only": run_context.synthetic_only,
      "official_result": run_context.official_result,
      "created_at": utc_now_iso(),
      "provenance": provenance,
    }
    summary_path.write_text(
      json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
      encoding="utf-8",
    )

    results_bytes = results_path.read_bytes()
    failures_bytes = failures_path.read_bytes()
    summary_bytes = summary_path.read_bytes()

    resume_contract = self._build_identity_bundle(systems=systems)
    resume_contract["source_commit"] = provenance.get("source_commit")

    manifest = {
      "run_id": run_id,
      "run_mode": run_mode,
      "systems": systems,
      "paths": {
        "results": str(results_path.as_posix()),
        "failures": str(failures_path.as_posix()),
        "summary": str(summary_path.as_posix()),
      },
      "config": config,
      "config_hash": config_hash,
      "input_manifest": input_manifest,
      "input_manifest_hash": input_manifest_hash,
      "record_identity_fingerprints": record_fingerprints,
      "expected_matrix": self._expected_matrix(records, systems),
      "resume_contract": resume_contract,
      "run_context": run_context.to_dict(),
      "provenance": provenance,
      "results_file": {"sha256": sha256_hex(results_bytes), "size_bytes": len(results_bytes)},
      "failures_file": {"sha256": sha256_hex(failures_bytes), "size_bytes": len(failures_bytes)},
      "summary_file": {"sha256": sha256_hex(summary_bytes), "size_bytes": len(summary_bytes)},
      "manifest_hash": "",
    }
    manifest["manifest_hash"] = sha256_json({k: v for k, v in manifest.items() if k != "manifest_hash"})
    manifest_path.write_text(
      json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
      encoding="utf-8",
    )

    # In addition to being embedded in run_manifest.json, the full input
    # manifest and the exact config snapshot that produced this run are each
    # also stored as standalone files, so either artefact can be inspected,
    # diffed, or reused (e.g. for resume) without parsing the whole manifest.
    (out_dir / "input_manifest.json").write_text(
      json.dumps(input_manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
      encoding="utf-8",
    )
    (out_dir / "config_snapshot.json").write_text(
      json.dumps(config, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
      encoding="utf-8",
    )
    return summary

  # -- Section G: strengthened verify_run -----------------------------------

  def verify_run(self, run_path: Path) -> dict[str, Any]:
    run_path = Path(run_path)
    manifest = load_json(run_path / "run_manifest.json")
    summary = load_json(run_path / "summary.json")
    results_path = run_path / "results.jsonl"
    failures_path = run_path / "failures.jsonl"
    summary_path = run_path / "summary.json"

    checks: dict[str, bool] = {}

    recomputed_manifest_hash = sha256_json({k: v for k, v in manifest.items() if k != "manifest_hash"})
    checks["manifest_hash_valid"] = recomputed_manifest_hash == manifest.get("manifest_hash")

    checks["config_hash_consistent"] = manifest.get("config_hash") == summary.get("config_hash")
    if manifest.get("config") is not None:
      checks["config_hash_recomputable"] = sha256_json(manifest["config"]) == manifest.get("config_hash")
    else:
      checks["config_hash_recomputable"] = True

    stored_input_manifest = manifest.get("input_manifest")
    if stored_input_manifest is not None:
      checks["input_manifest_hash_valid"] = (
        sha256_json(stored_input_manifest) == manifest.get("input_manifest_hash")
      )
    else:
      checks["input_manifest_hash_valid"] = True
    checks["input_manifest_hash_consistent"] = (
      manifest.get("input_manifest_hash") == summary.get("input_manifest_hash")
    )

    # The standalone input_manifest.json / config_snapshot.json files must
    # never drift from what is embedded in run_manifest.json.
    input_manifest_file = run_path / "input_manifest.json"
    if input_manifest_file.is_file():
      checks["input_manifest_file_consistent"] = (
        load_json(input_manifest_file) == stored_input_manifest
      )
    else:
      checks["input_manifest_file_consistent"] = True
    config_snapshot_file = run_path / "config_snapshot.json"
    if config_snapshot_file.is_file():
      checks["config_snapshot_file_consistent"] = (
        load_json(config_snapshot_file) == manifest.get("config")
      )
    else:
      checks["config_snapshot_file_consistent"] = True

    results_bytes = results_path.read_bytes() if results_path.is_file() else b""
    failures_bytes = failures_path.read_bytes() if failures_path.is_file() else b""
    summary_bytes = summary_path.read_bytes() if summary_path.is_file() else b""
    results_file_info = {"sha256": sha256_hex(results_bytes), "size_bytes": len(results_bytes)}
    failures_file_info = {"sha256": sha256_hex(failures_bytes), "size_bytes": len(failures_bytes)}
    summary_file_info = {"sha256": sha256_hex(summary_bytes), "size_bytes": len(summary_bytes)}
    checks["results_file_hash_valid"] = results_file_info == (manifest.get("results_file") or {})
    checks["failures_file_hash_valid"] = failures_file_info == (manifest.get("failures_file") or {})
    checks["summary_file_hash_valid"] = summary_file_info == (manifest.get("summary_file") or {})

    rows = _read_jsonl(results_path)
    seen: set[str] = set()
    duplicate_keys: list[str] = []
    result_hash_mismatches: list[str] = []
    version_mismatches: list[str] = []
    flag_mismatches: list[str] = []
    mode_mismatches: list[str] = []
    context_blind_cache_mismatches: list[str] = []
    resume_contract = manifest.get("resume_contract") or {}
    stored_versions = resume_contract.get("system_versions") or {}

    stored_run_context = manifest.get("run_context")
    if stored_run_context is not None:
      run_context = RunContext.from_dict(stored_run_context)
    else:
      # Legacy manifests without an embedded run_context: reconstruct non-official
      # modes only. Official mode without an embedded approved context cannot be
      # treated as official_result=true.
      run_context = RunContext.for_run_mode(manifest.get("run_mode"))

    checks["run_mode_manifest_summary_consistent"] = (
      manifest.get("run_mode") == summary.get("run_mode") == run_context.run_mode
    )
    checks["run_context_approved_when_official_result"] = (
      (not run_context.official_result) or run_context.approved
    )
    checks["official_result_implies_official_mode"] = (
      (not run_context.official_result) or run_context.run_mode == "official"
    )
    checks["synthetic_smoke_implies_synthetic_only"] = (
      run_context.run_mode != "synthetic_smoke" or run_context.synthetic_only
    )

    input_records_by_id: dict[str, dict[str, Any]] = {}
    for entry in (stored_input_manifest or {}).get("records") or []:
      if isinstance(entry, dict) and entry.get("record_id"):
        input_records_by_id[str(entry["record_id"])] = entry

    for row in rows:
      key = self._result_key(row["record_id"], row["system_id"])
      if key in seen:
        duplicate_keys.append(key)
      seen.add(key)
      recomputed_hash = SystemResult.from_dict(row).compute_hash()
      if recomputed_hash != row.get("result_hash"):
        result_hash_mismatches.append(key)
      expected_version = stored_versions.get(row["system_id"])
      if expected_version is not None and row.get("system_version") != expected_version:
        version_mismatches.append(key)
      if (
        row.get("synthetic_only") != run_context.synthetic_only
        or row.get("official_result") != run_context.official_result
      ):
        flag_mismatches.append(key)
      if row.get("run_mode") not in (None, run_context.run_mode):
        mode_mismatches.append(key)

      # Context-blind results that executed successfully must not reference a
      # full-context analysis identity or a mismatched ablated input hash.
      if row.get("system_id") == "context_blind_manager" and row.get("execution_status") == "ok":
        identity = (row.get("runtime_metadata") or {}).get("analysis_identity") or {}
        ablation = (row.get("runtime_metadata") or {}).get("context_ablation") or {}
        entry = input_records_by_id.get(str(row["record_id"]), {})
        expected_ablated = entry.get("ablated_input_fingerprint")
        if identity.get("analysis_variant") == "full_context":
          context_blind_cache_mismatches.append(key)
        if (
          identity.get("analysis_variant")
          and identity.get("analysis_variant") != "context_blind"
        ):
          context_blind_cache_mismatches.append(key)
        if expected_ablated and identity.get("source_input_hash") not in (
          None,
          expected_ablated,
        ):
          context_blind_cache_mismatches.append(key)
        if expected_ablated and ablation.get("ablated_input_hash") not in (
          None,
          expected_ablated,
        ):
          context_blind_cache_mismatches.append(key)
        # Supplied cache in the input manifest must not have been substituted
        # as a full-context identity for an ok context-blind execution.
        if entry.get("analysis_variant") == "full_context" and identity.get(
          "analysis_content_hash"
        ) == entry.get("analysis_content_hash"):
          context_blind_cache_mismatches.append(key)

    expected_matrix = set(manifest.get("expected_matrix") or [])
    missing_keys = sorted(expected_matrix - seen)
    extra_keys = sorted(seen - expected_matrix)

    checks["no_duplicate_results"] = not duplicate_keys
    checks["no_missing_results"] = not missing_keys
    checks["no_extra_results"] = not extra_keys
    checks["completed_matches_expected"] = seen == expected_matrix
    checks["all_result_hashes_valid"] = not result_hash_mismatches
    checks["system_versions_consistent"] = not version_mismatches
    checks["flag_consistency"] = not flag_mismatches
    checks["run_mode_consistency"] = not mode_mismatches
    checks["context_blind_analysis_identity_consistent"] = not context_blind_cache_mismatches

    failure_rows = _read_jsonl(failures_path)
    failed_result_rows = [r for r in rows if r.get("execution_status") == "failed"]
    successful_rows = [r for r in rows if r.get("execution_status") != "failed"]
    checks["failures_count_consistent"] = summary.get("failures_written") == len(failure_rows)
    checks["skipped_accounting_consistent"] = (
      summary.get("skipped_or_failed_retained") == len(failed_result_rows)
    )
    checks["results_written_consistent"] = summary.get("results_written") == len(successful_rows)
    checks["completed_keys_consistent"] = summary.get("completed_keys") == len(seen)

    checks["summary_flags_consistent"] = (
      summary.get("synthetic_only") == run_context.synthetic_only
      and summary.get("official_result") == run_context.official_result
    )

    # Evaluation bundles, when present, must inherit the same validated status.
    eval_flag_mismatches: list[str] = []
    for eval_name in ("evaluation_bundle.json", "evaluation_bundles.json"):
      eval_path = run_path / eval_name
      if not eval_path.is_file():
        continue
      payload = load_json(eval_path)
      bundles = payload if isinstance(payload, list) else (
        list(payload.values()) if isinstance(payload, dict) and "metrics" not in payload else [payload]
      )
      if isinstance(payload, dict) and "metrics" in payload:
        bundles = [payload]
      elif isinstance(payload, dict):
        bundles = list(payload.values())
      for idx, bundle in enumerate(bundles):
        if not isinstance(bundle, dict):
          continue
        if (
          bundle.get("synthetic_only") != run_context.synthetic_only
          or bundle.get("official_result") != run_context.official_result
          or bundle.get("run_mode") not in (None, run_context.run_mode)
        ):
          eval_flag_mismatches.append(f"{eval_name}:{idx}")
    checks["evaluation_bundle_flags_consistent"] = not eval_flag_mismatches

    provenance = manifest.get("provenance") or {}
    checks["source_commit_consistent"] = provenance.get("source_commit") == resume_contract.get(
      "source_commit"
    )
    checks["provider_identities_present"] = "provider_identities" in resume_contract
    checks["model_identities_present"] = "model_identities" in resume_contract
    checks["evaluator_version_present"] = bool(resume_contract.get("evaluator_version"))

    ok = all(checks.values()) and summary.get("run_id") == manifest.get("run_id")

    report = {
      "ok": ok,
      "run_id": manifest.get("run_id"),
      "run_mode": manifest.get("run_mode"),
      "checks": checks,
      "duplicates": len(duplicate_keys),
      "duplicate_keys": duplicate_keys,
      "missing_result_keys": missing_keys,
      "extra_result_keys": extra_keys,
      "result_hash_mismatches": result_hash_mismatches,
      "version_mismatches": version_mismatches,
      "flag_mismatches": flag_mismatches,
      "mode_mismatches": mode_mismatches,
      "context_blind_cache_mismatches": sorted(set(context_blind_cache_mismatches)),
      "evaluation_flag_mismatches": eval_flag_mismatches,
      "result_rows": len(rows),
      "synthetic_only": summary.get("synthetic_only", True),
      "official_result": summary.get("official_result", False),
      "generated_at": utc_now_iso(),
    }
    (run_path / "verification_report.json").write_text(
      json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
      encoding="utf-8",
    )
    return report
