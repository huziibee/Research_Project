#!/usr/bin/env python3
"""Capture and verify the immutable execution contract for T39 GPU components."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any


BASE_MODEL = "Qwen/Qwen3-8B"
BASE_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
CRITICAL_CODE_PATHS = (
    "configs/evaluation/pilot_120_v1.json",
    "configs/evaluation/pilot120_early_analysis_policy_v1.json",
    "configs/evaluation/pilot120_t39_evidence_policy_v1.json",
    "scripts/evaluate_pilot_120_direct_base.py",
    "scripts/evaluate_pilot_120_manager_systems.py",
    "scripts/pilot120_t39_evidence.py",
    "scripts/pilot120_t39_runtime_provenance.py",
    "src/ambiguity_manager/evaluation/pilot_120.py",
    "cluster/pilot120/t39_provenance_preflight.sbatch",
    "cluster/pilot120/t39_direct_base.sbatch",
    "cluster/pilot120/t39_selected_adapter.sbatch",
    "cluster/pilot120/t39_manager_bundle.sbatch",
    "cluster/pilot120/t39_replica_evidence.sbatch",
    "cluster/pilot120/t39_reproducibility_audit.sbatch",
    "cluster/pilot120/submit_t39_batch.sh",
    "cluster/pilot120/submit_t39_replicate_continuation.sh",
    "cluster/pilot120/submit_t39_component_recovery.sh",
)


def _sha256(path: Path) -> str:
    """Hash files in bounded memory, including multi-gigabyte model shards."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(path: Path) -> str:
    if not path.is_dir():
        raise ValueError(f"t39_contract_tree_not_directory:{path}")
    digest = hashlib.sha256()
    files = sorted((child for child in path.rglob("*") if child.is_file()), key=lambda child: child.relative_to(path).as_posix())
    if not files:
        raise ValueError(f"t39_contract_tree_empty:{path}")
    for child in files:
        digest.update(child.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256(child).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise SystemExit(f"t39_runtime_output_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"t39_contract_not_json_object:{path}")
    return payload


def _torch_payload() -> dict[str, Any]:
    try:
        import torch

        cuda_available = bool(torch.cuda.is_available())
        return {
            "version": getattr(torch, "__version__", None),
            "cuda_version": getattr(torch.version, "cuda", None),
            "cuda_available": cuda_available,
            "gpu_name": torch.cuda.get_device_name(0) if cuda_available else None,
        }
    except Exception as exc:
        return {"status": "NOT_COMPUTED", "reason": f"torch_probe_failed:{type(exc).__name__}:{exc}"}


def _capture_contract(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    container = args.container.resolve()
    adapter = args.adapter.resolve()
    adapter_identity = args.adapter_identity.resolve()
    model_snapshot = args.model_snapshot.resolve()
    if not root.is_dir() or not container.is_file() or not adapter_identity.is_file():
        raise ValueError("t39_contract_required_path_missing")
    actual_container_sha256 = _sha256(container)
    if actual_container_sha256 != args.expected_container_sha256:
        raise ValueError("t39_contract_container_sha256_mismatch")
    critical_code_sha256 = {relative: _sha256(root / relative) for relative in CRITICAL_CODE_PATHS}
    model_config = model_snapshot / "config.json"
    if not model_config.is_file():
        raise ValueError("t39_contract_model_config_missing")
    payload = {
        "status": "T39_EXECUTION_CONTRACT_CAPTURED",
        "scope": "non_protected_pilot120_v1_evidence_only",
        "valid_for_official_use": False,
        "immutable_code_commit": args.code_commit,
        "code_root": str(root),
        "critical_code_sha256": critical_code_sha256,
        "container": {"path": str(container), "sha256": actual_container_sha256},
        "adapter": {
            "path": str(adapter),
            "tree_sha256": _tree_sha256(adapter),
            "identity_path": str(adapter_identity),
            "identity_sha256": _sha256(adapter_identity),
        },
        "model": {
            "id": BASE_MODEL,
            "revision": BASE_REVISION,
            "snapshot_path": str(model_snapshot),
            "snapshot_tree_sha256": _tree_sha256(model_snapshot),
            "config_sha256": _sha256(model_config),
        },
    }
    _write_once(args.output.resolve(), payload)
    return payload


def _verify_contract(args: argparse.Namespace) -> dict[str, Any]:
    contract_path = args.contract.resolve()
    contract = _load_json(contract_path)
    root = args.root.resolve()
    container = args.container.resolve()
    adapter = args.adapter.resolve()
    adapter_identity = args.adapter_identity.resolve()
    model_snapshot = args.model_snapshot.resolve()
    if contract.get("status") != "T39_EXECUTION_CONTRACT_CAPTURED":
        raise ValueError("t39_contract_status_invalid")
    if contract.get("immutable_code_commit") != args.code_commit or contract.get("code_root") != str(root):
        raise ValueError("t39_contract_code_identity_mismatch")
    if contract.get("container") != {"path": str(container), "sha256": _sha256(container)}:
        raise ValueError("t39_contract_container_identity_mismatch")
    adapter_contract = contract.get("adapter") or {}
    if adapter_contract.get("path") != str(adapter) or adapter_contract.get("identity_path") != str(adapter_identity):
        raise ValueError("t39_contract_adapter_path_mismatch")
    if adapter_contract.get("tree_sha256") != _tree_sha256(adapter) or adapter_contract.get("identity_sha256") != _sha256(adapter_identity):
        raise ValueError("t39_contract_adapter_bytes_mismatch")
    model_contract = contract.get("model") or {}
    if model_contract.get("id") != BASE_MODEL or model_contract.get("revision") != BASE_REVISION or model_contract.get("snapshot_path") != str(model_snapshot):
        raise ValueError("t39_contract_model_identity_mismatch")
    if model_contract.get("config_sha256") != _sha256(model_snapshot / "config.json"):
        raise ValueError("t39_contract_model_config_mismatch")
    observed_code = {relative: _sha256(root / relative) for relative in CRITICAL_CODE_PATHS}
    if observed_code != contract.get("critical_code_sha256"):
        raise ValueError("t39_contract_critical_code_bytes_mismatch")
    return {
        "contract_path": str(contract_path),
        "contract_sha256": _sha256(contract_path),
        "status": "T39_EXECUTION_CONTRACT_VERIFIED",
        "model_snapshot_tree_sha256_captured_at_preflight": model_contract["snapshot_tree_sha256"],
        "model_config_sha256_verified_at_component": model_contract["config_sha256"],
    }


def _common_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--container", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--adapter-identity", type=Path, required=True)
    parser.add_argument("--model-snapshot", type=Path, required=True)
    parser.add_argument("--code-commit", required=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture-contract")
    _common_parser(capture)
    capture.add_argument("--expected-container-sha256", required=True)
    capture.add_argument("--output", type=Path, required=True)
    capture.set_defaults(run=_capture_contract)
    verify = sub.add_parser("verify-component")
    _common_parser(verify)
    verify.add_argument("--contract", type=Path, required=True)
    verify.add_argument("--component", choices=("direct_base", "selected_adapter", "manager_bundle"), required=True)
    verify.add_argument("--replicate-id", required=True)
    verify.add_argument("--output", type=Path, required=True)
    verify.set_defaults(run=_verify_contract)
    args = parser.parse_args()
    result = args.run(args)
    if args.command == "verify-component":
        payload = {
            "status": "T39_RUNTIME_PROVENANCE_CAPTURED",
            "component": args.component,
            "replicate_id": args.replicate_id,
            "execution_contract": result,
            "slurm": {
                "job_id": os.environ.get("T39_SLURM_JOB_ID", "unknown"),
                "node": os.environ.get("T39_SLURMD_NODENAME", "unknown"),
                "cluster": os.environ.get("SLURM_CLUSTER_NAME", "unknown"),
            },
            "runtime": {
                "python": sys.version,
                "implementation": platform.python_implementation(),
                "platform": platform.platform(),
                "packages": {name: _version(name) for name in ("torch", "transformers", "peft", "accelerate", "bitsandbytes")},
                "torch": _torch_payload(),
                "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", "unknown"),
            },
        }
        _write_once(args.output.resolve(), payload)
        result = payload
    print(json.dumps({"status": result["status"], "component": getattr(args, "component", None)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
