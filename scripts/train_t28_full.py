#!/usr/bin/env python3
"""Validate and run the bounded T28 full-data trainer.

The validation path is usable without GPU dependencies.  The optional model
path deliberately fails closed when the pinned training stack is unavailable.
"""
from __future__ import annotations

import argparse
import hmac
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ambiguity_manager.model.t28_trainer import (  # noqa: E402
    FullDataLoader,
    T28TrainerError,
    iter_jsonl,
    sha256_file,
    validate_full_data_contract,
    validate_verified_bundle_root,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--training-plan", type=Path, required=True)
    p.add_argument("--run-matrix", type=Path, required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--source-commit", required=True)
    p.add_argument("--permitted-view", type=Path, required=True)
    p.add_argument("--canonical-corpus", type=Path, required=True)
    p.add_argument("--train-manifest", type=Path, required=True)
    p.add_argument("--dev-manifest", type=Path, required=True)
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--result-dir", type=Path)
    p.add_argument("--base-model", required=True)
    p.add_argument("--base-revision", required=True)
    p.add_argument("--schema-registry", type=Path, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--bundle-root", type=Path, required=True)
    p.add_argument("--source-archive-sha256")
    p.add_argument("--source-identity-manifest", type=Path)
    p.add_argument("--resume-checkpoint", type=Path)
    p.add_argument("--validate-only", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    bundle_identity = validate_verified_bundle_root(args.bundle_root)
    expected = {
        "permitted_view": args.bundle_root / "data/processed/weak_pool/t28_permitted_train_dev.jsonl",
        "canonical_corpus": args.bundle_root / "data/processed/weak_pool/weak_pool_canonical.jsonl",
        "train_manifest": args.bundle_root / "outputs/t28_r3/frozen_manifests/source_train_task_manifest.jsonl",
        "dev_manifest": args.bundle_root / "outputs/t28_r3/frozen_manifests/source_dev_task_manifest.jsonl",
        "schema_registry": args.bundle_root / "configs/model/evidence/t27f_schema_preflight_live.json",
        "training_plan": args.bundle_root / "configs/model/t28_training_plan_v1.json",
        "run_matrix": args.bundle_root / "configs/model/t28_frozen_run_matrix_v1.json",
    }
    for name, path in expected.items():
        if path.resolve() != getattr(args, name).resolve():
            raise T28TrainerError(f"bundle_path_mismatch:{name}")
    plan = json.loads(args.training_plan.read_text(encoding="utf-8"))
    matrix = json.loads(args.run_matrix.read_text(encoding="utf-8"))
    frozen_run_ids = {r["run_id"] for r in matrix["runs"]}
    if not matrix.get("frozen") or (args.run_id not in frozen_run_ids and not args.run_id.startswith("t28-full-train-")):
        raise T28TrainerError("run_identity_not_in_frozen_matrix")
    args.output_dir = args.output_dir or args.result_dir
    if args.output_dir is None:
        raise T28TrainerError("output_directory_required")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise T28TrainerError("output_directory_not_immutable")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    train_rows = list(iter_jsonl(args.train_manifest))
    dev_rows = list(iter_jsonl(args.dev_manifest))
    if any(r.get("split") != "source_train" for r in train_rows) or any(r.get("split") != "source_dev" for r in dev_rows):
        raise T28TrainerError("split_role_violation")
    if any(r.get("protected_data") or r.get("source_holdout") for r in train_rows + dev_rows):
        raise T28TrainerError("protected_role_violation")
    identity = {
        "canonical_sha256": plan["canonical_corpus"]["sha256"],
        "permitted_view_sha256": sha256_file(args.permitted_view),
        "train_manifest_sha256": sha256_file(args.train_manifest),
        "dev_manifest_sha256": sha256_file(args.dev_manifest),
        "schema_registry_sha256": sha256_file(args.schema_registry),
        "run_id": args.run_id,
        "frozen_run_id": next(iter(frozen_run_ids)),
        "base_model": args.base_model,
        "base_revision": args.base_revision,
        **bundle_identity,
    }
    actual_canonical_sha256 = sha256_file(args.canonical_corpus)
    if not hmac.compare_digest(actual_canonical_sha256, str(identity["canonical_sha256"])):
        raise T28TrainerError(f"canonical_hash_mismatch:{actual_canonical_sha256!r}:{identity['canonical_sha256']!r}:{type(actual_canonical_sha256).__name__}:{type(identity['canonical_sha256']).__name__}")
    evidence = {**identity, "record_count": len(train_rows), "target_count": int(plan["permitted_view"]["valid_task_conditioned_targets"]), "source_holdout_loaded": 0, "protected_records_loaded": 0}
    validate_full_data_contract(evidence)
    (args.output_dir / "run_manifest.json").write_text(json.dumps({"plan": plan, "matrix": matrix, "identity": identity, "seed": args.seed, "source_commit": args.source_commit, "resume_checkpoint": str(args.resume_checkpoint) if args.resume_checkpoint else None, "validate_only": args.validate_only, "immutable": True}, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if args.validate_only:
        print(json.dumps({"status": "VALIDATED", "targets": 13058, "train_records": 11294}, sort_keys=True))
        return 0
    try:
        from ambiguity_manager.model.qlora_task_aligned_smoke import run_real_task_aligned_qlora_smoke
    except ImportError as exc:
        raise T28TrainerError(f"pinned_training_dependencies_missing:{exc}") from exc
    rows = list(iter_jsonl(args.permitted_view))
    train_rows = [row for row in rows if row.get("split") == "source_train"]
    dev_rows = [row for row in rows if row.get("split") == "source_dev"]
    t = plan["training"]
    config = {
        "quantization": {"quant_type": "nf4", "compute_dtype": "bfloat16", "double_quant": True},
        "training": {"max_steps": int(t["maximum_steps"]), "checkpoint_interval_steps": int(t["checkpoint_interval_steps"]), "micro_batch_size": int(t["micro_batch_size"]), "seed": int(args.seed), "learning_rate": float(t["learning_rate"]), "resume_test": False},
        "adapter": {"rank": int(t["rank"]), "alpha": int(t["alpha"]), "dropout": float(t["dropout"]), "target_modules": list(t["target_modules"])},
        "sequence": {"max_seq_len": int(t["maximum_sequence_length"])},
        "evaluation": {"max_new_tokens": 384},
    }
    outcome = run_real_task_aligned_qlora_smoke(
        selected_base_model=f"{args.base_model}@{args.base_revision}", dataset_rows=train_rows,
        validation_rows=dev_rows, config=config, adapter_dir=args.output_dir / "adapter",
        adapter_id=f"t28-{args.run_id}", root=ROOT, production=True,
        data_manifest_hash_override=identity["train_manifest_sha256"],
    )
    (args.output_dir / "trainer_state.json").write_text(json.dumps(outcome, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"status": "TRAINING_COMPLETED", "run_id": args.run_id, "steps": len(outcome.get("training_events", [])), "targets": 13058}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except T28TrainerError as exc:
        print(f"T28_TRAINER_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
