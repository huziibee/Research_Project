"""Experiment runner with synthetic/development/official gates.

Integrity model
---------------
* ``RunContext`` (Section E) is the single owner of the ``synthetic_only`` /
  ``official_result`` flags on every persisted result; adapters may set
  whatever values they like internally but the runner always overwrites them
  before a row is written, and recomputes the result hash accordingly.
* The input manifest (Section C) hashes the *complete* ``SystemInput``
  records (including dialogue/scene/capability context, eligibility
  metadata, protected-data flags), plus any supplied cached analysis content
  and provenance, the input schema version, and an explicit record-ordering
  policy. It intentionally excludes timestamps so identical inputs always
  hash identically.
* Resuming a run (Section D) re-derives the same identity bundle used at
  original-run time (systems/versions, provider identities, model
  identities, evaluator version, source commit) and refuses to continue if
  anything about the run's identity - or any already-written result's hash -
  has drifted. Growing the record set on resume is allowed; silently losing
  track of already-completed work is not.
* Official-mode gating (Section B) is derived from the system capability
  registry (``ambiguity_manager.systems.capabilities``), never from
  hard-coded system-id checks.
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
from typing import Any

from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema.v2.version import SCHEMA_VERSION
from ambiguity_manager.systems.capabilities import (
  SystemCapabilities,
  is_provenance_approved,
  load_capability_registry,
)
from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput, SystemResult
from ambiguity_manager.systems.errors import (
  DuplicateResultError,
  OfficialRunBlockedError,
  ProtectedDataBlockedError,
  ResumeContractError,
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


@dataclass(frozen=True)
class RunContext:
  """Runner-owned execution-mode flags.

  Adapters/systems must never be trusted to set ``synthetic_only`` /
  ``official_result`` themselves for the persisted record; the runner always
  derives them from ``run_mode`` alone and overwrites whatever the adapter
  returned.
  """

  run_mode: str
  synthetic_only: bool
  official_result: bool

  @classmethod
  def for_run_mode(cls, run_mode: str) -> "RunContext":
    if run_mode == "synthetic_smoke":
      return cls(run_mode=run_mode, synthetic_only=True, official_result=False)
    if run_mode == "development":
      return cls(run_mode=run_mode, synthetic_only=False, official_result=False)
    if run_mode == "official":
      # Passing the official gates in this codebase never certifies a result
      # as official_result=True; that requires evidence this task does not
      # produce. official_result stays False here by construction.
      return cls(run_mode=run_mode, synthetic_only=False, official_result=False)
    raise ValueError(f"unknown run_mode: {run_mode}")

  def apply(self, result: SystemResult) -> SystemResult:
    """Overwrite the runner-owned flags on ``result`` and recompute its hash."""
    result.synthetic_only = self.synthetic_only
    result.official_result = self.official_result
    return result.with_computed_hash()

  def to_dict(self) -> dict[str, Any]:
    return {
      "run_mode": self.run_mode,
      "synthetic_only": self.synthetic_only,
      "official_result": self.official_result,
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
    cached_analyses: dict[str, StructuredAnalysis] | None = None,
  ) -> None:
    capabilities = capabilities if capabilities is not None else load_capability_registry()
    identities = identities if identities is not None else load_selected_identities()
    cached_analyses = cached_analyses or {}
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
        approved = any(
          is_provenance_approved(analysis.analysis_provenance)
          for analysis in cached_analyses.values()
        )
        if not approved:
          missing.append(f"{sid}:approved_analysis_provenance")

    if missing:
      raise OfficialRunBlockedError(missing)

  # -- Section C: full input-manifest hashing -------------------------------

  def _record_identity_hash(
    self, record: SystemInput, cached: StructuredAnalysis | None
  ) -> str:
    return sha256_json(
      {
        "input": record.to_dict(),
        "cached_analysis": cached.to_dict() if cached is not None else None,
      }
    )

  def _build_input_manifest(
    self,
    *,
    records: list[SystemInput],
    cached_analyses: dict[str, StructuredAnalysis],
    systems: list[str],
    run_mode: str,
  ) -> tuple[dict[str, Any], dict[str, str]]:
    record_entries: list[dict[str, Any]] = []
    fingerprints: dict[str, str] = {}
    for record in records:
      cached = cached_analyses.get(record.record_id)
      identity_hash = self._record_identity_hash(record, cached)
      fingerprints[record.record_id] = identity_hash
      record_entries.append(
        {
          "record_id": record.record_id,
          "input": record.to_dict(),
          "input_fingerprint": record.fingerprint(),
          "cached_analysis": cached.to_dict() if cached is not None else None,
          "cached_analysis_fingerprint": cached.fingerprint() if cached is not None else None,
          "record_identity_hash": identity_hash,
        }
      )
    manifest = {
      "input_schema_version": SCHEMA_VERSION,
      "run_mode": run_mode,
      "systems": list(systems),
      "record_ordering_policy": RECORD_ORDERING_POLICY,
      "record_count": len(records),
      "records": record_entries,
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
    cached_analyses: dict[str, StructuredAnalysis],
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

    stored_fingerprints: dict[str, str] = existing_manifest.get("record_identity_fingerprints") or {}
    current_by_id = {r.record_id: r for r in records}
    completed_record_ids = {key.split("::", 1)[0] for key in completed_keys}
    for record_id in completed_record_ids:
      record = current_by_id.get(record_id)
      if record is None:
        mismatches.append(f"input_manifest:missing_completed_record:{record_id}")
        continue
      fresh_fp = self._record_identity_hash(record, cached_analyses.get(record_id))
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
    cached_analyses: dict[str, StructuredAnalysis] | None = None,
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
    cached_analyses = cached_analyses or {}
    run_context = RunContext.for_run_mode(run_mode)

    # Section F: protected-data gate. Refuse outright outside official mode;
    # synthetic and development runs must never process protected records.
    if run_mode != "official":
      for record in records:
        if record.protected_data:
          raise ProtectedDataBlockedError(record.record_id, run_mode)

    if run_mode == "official":
      self.check_official_gates(
        prerequisites=prerequisites or OfficialPrerequisites(),
        systems=systems,
        protected_labels_in_prompts=protected_labels_in_prompts,
        cached_analyses=cached_analyses,
      )

    config_hash = sha256_json(config)
    input_manifest, record_fingerprints = self._build_input_manifest(
      records=records,
      cached_analyses=cached_analyses,
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
        cached_analyses=cached_analyses,
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
            cached = cached_analyses.get(record.record_id)
            result: SystemResult = system.run(record, cached_analysis=cached)
            if result.execution_status in {"provider_unavailable", "not_executable"}:
              not_executable_count += 1
            result = run_context.apply(result)
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
              )
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
    resume_contract = manifest.get("resume_contract") or {}
    stored_versions = resume_contract.get("system_versions") or {}
    run_context = RunContext.for_run_mode(manifest.get("run_mode"))

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
