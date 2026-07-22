"""Experiment runner with synthetic/development/official gates."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.schema.v2.version import SCHEMA_VERSION
from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput, SystemResult
from ambiguity_manager.systems.errors import DuplicateResultError, OfficialRunBlockedError
from ambiguity_manager.systems.hashing import sha256_hex, sha256_json
from ambiguity_manager.systems.provenance import build_run_provenance, utc_now_iso
from ambiguity_manager.systems.variants import SYSTEM_IDS, get_registry


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


@dataclass
class OfficialPrerequisites:
  adjudicated_gold_dataset: Path | None = None
  t15_split_manifest: Path | None = None
  protocol_freeze_identifier: str | None = None
  selected_model_strategy: str | None = None
  handbook_version: str | None = None
  schema_version: str = SCHEMA_VERSION

  def missing(self, *, model_backed: bool) -> list[str]:
    missing: list[str] = []
    if self.adjudicated_gold_dataset is None or not Path(self.adjudicated_gold_dataset).is_file():
      missing.append("adjudicated_gold_dataset")
    if self.t15_split_manifest is None or not Path(self.t15_split_manifest).is_file():
      missing.append("t15_split_manifest")
    if not self.protocol_freeze_identifier:
      missing.append("protocol_freeze_identifier")
    if model_backed and not self.selected_model_strategy:
      missing.append("selected_model_strategy")
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

  def check_official_gates(
    self,
    *,
    prerequisites: OfficialPrerequisites,
    systems: list[str],
    protected_labels_in_prompts: bool = False,
  ) -> None:
    model_backed = any(s == "direct_base_llm" for s in systems)
    missing = prerequisites.missing(model_backed=model_backed)
    if protected_labels_in_prompts:
      missing.append("protected_label_leakage")
    # Model-backed systems also need a live provider for official execution.
    if model_backed:
      direct = self.registry.get("direct_base_llm")
      if direct is None or getattr(direct, "provider", None) is None:
        missing.append("model_provider")
    if missing:
      raise OfficialRunBlockedError(missing)

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

    if run_mode == "official":
      self.check_official_gates(
        prerequisites=prerequisites or OfficialPrerequisites(),
        systems=systems,
        protected_labels_in_prompts=protected_labels_in_prompts,
      )

    config_hash = sha256_json(config)
    input_manifest = {
      "record_ids": [r.record_id for r in records],
      "count": len(records),
    }
    input_manifest_hash = sha256_json(input_manifest)
    if run_id is None:
      run_id = sha256_hex(f"{config_hash}:{input_manifest_hash}".encode("utf-8"))[:16]
      run_id = f"{run_mode}-{run_id}"

    out_dir = output_dir or self._run_dir(run_id, run_mode)
    results_path = out_dir / "results.jsonl"
    failures_path = out_dir / "failures.jsonl"
    summary_path = out_dir / "summary.json"
    manifest_path = out_dir / "run_manifest.json"

    completed: set[str] = set()
    if resume and results_path.is_file():
      for line in results_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
          continue
        row = json.loads(line)
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
      synthetic_only=run_mode != "official",
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
        if record.protected_data and run_mode != "official":
          # Still allow synthetic, but mark; official gate handles protected leakage.
          pass
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
            failed_result = SystemResult(
              record_id=record.record_id,
              system_id=system_id,
              system_version=getattr(system, "system_version", "1.0.0"),
              analysis=StructuredAnalysis(),
              recommended_strategy=None,
              execution_status="failed",
              runtime_metadata={"error_type": type(exc).__name__, "error_message": str(exc)},
              synthetic_only=run_mode != "official",
              official_result=False,
            ).with_computed_hash()
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
      "synthetic_only": run_mode != "official",
      "official_result": False,
      "created_at": utc_now_iso(),
      "provenance": provenance,
    }
    summary_path.write_text(
      json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
      encoding="utf-8",
    )
    manifest = {
      "run_id": run_id,
      "run_mode": run_mode,
      "paths": {
        "results": str(results_path.as_posix()),
        "failures": str(failures_path.as_posix()),
        "summary": str(summary_path.as_posix()),
      },
      "config_hash": config_hash,
      "input_manifest_hash": input_manifest_hash,
      "provenance": provenance,
      "manifest_hash": "",
    }
    manifest["manifest_hash"] = sha256_json({k: v for k, v in manifest.items() if k != "manifest_hash"})
    manifest_path.write_text(
      json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
      encoding="utf-8",
    )
    return summary

  def verify_run(self, run_path: Path) -> dict[str, Any]:
    run_path = Path(run_path)
    manifest = load_json(run_path / "run_manifest.json")
    summary = load_json(run_path / "summary.json")
    results_path = run_path / "results.jsonl"
    keys: list[str] = []
    duplicates = 0
    seen: set[str] = set()
    for line in results_path.read_text(encoding="utf-8").splitlines():
      if not line.strip():
        continue
      row = json.loads(line)
      key = self._result_key(row["record_id"], row["system_id"])
      if key in seen:
        duplicates += 1
      seen.add(key)
      keys.append(key)
    ok = duplicates == 0 and summary.get("run_id") == manifest.get("run_id")
    return {
      "ok": ok,
      "run_id": manifest.get("run_id"),
      "result_rows": len(keys),
      "duplicates": duplicates,
      "synthetic_only": summary.get("synthetic_only", True),
      "official_result": summary.get("official_result", False),
    }
