#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ambiguity_manager.model.t28_trainer import package_manifest, sha256_file  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--base-revision", required=True)
    p.add_argument("--seed", type=int, required=True)
    a = p.parse_args()
    required = {"adapter_config.json", "adapter_model.safetensors"}
    present = {x.name for x in a.checkpoint.iterdir()} if a.checkpoint.is_dir() else set()
    if not a.checkpoint.is_dir() or not required.issubset(present):
        raise SystemExit("incomplete_checkpoint")
    manifest = package_manifest(a.checkpoint, {"run_id": a.run_id, "checkpoint_id": a.checkpoint.name, "base_revision": a.base_revision, "seed": a.seed})
    manifest["checkpoint_sha256"] = sha256_file(a.checkpoint / "adapter_model.safetensors")
    a.output.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
