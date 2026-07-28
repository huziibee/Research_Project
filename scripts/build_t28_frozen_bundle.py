#!/usr/bin/env python3
"""Build the deterministic binary-safe, content-addressed T28 input bundle."""
from __future__ import annotations
import argparse, json, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ambiguity_manager.model.t28_bundle import build_manifest, canonical_json, sha256_file, write_deterministic_tar_gz

FILES = [
 ("data/processed/weak_pool/weak_pool_canonical.jsonl", "canonical_corpus", "15839"),
 ("data/processed/weak_pool/t28_permitted_train_dev.jsonl", "permitted_train_dev_view", "13690"),
 ("outputs/t28_r3/frozen_manifests/source_train_task_manifest.jsonl", "train_manifest", "11294"),
 ("outputs/t28_r3/frozen_manifests/source_dev_task_manifest.jsonl", "dev_manifest", "2396"),
 ("configs/model/evidence/t27f_schema_preflight_live.json", "effective_schema_registry", None),
 ("configs/model/t28_training_plan_v1.json", "frozen_training_plan", None),
 ("configs/model/t28_frozen_run_matrix_v1.json", "frozen_run_matrix", None),
 ("configs/model/t28_frozen_selection_policy_v1.json", "frozen_selection_policy", None),
]

def main() -> int:
 p=argparse.ArgumentParser(); p.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1]); p.add_argument("--artifact-dir",type=Path,required=True); args=p.parse_args(); args.artifact_dir.mkdir(parents=True,exist_ok=True)
 manifest=build_manifest(args.root, FILES); mb=canonical_json(manifest); mh=__import__('hashlib').sha256(mb).hexdigest(); manifest_path=args.artifact_dir/f"t28-frozen-inputs-{mh}.manifest.json"; manifest_path.write_bytes(mb)
 temp=args.artifact_dir/f".t28-build-{mh}.tar.gz"; write_deterministic_tar_gz(temp,args.root,mb,"bundle_manifest.json",manifest["members"]); archive_sha=sha256_file(temp); archive=args.artifact_dir/f"t28-frozen-inputs-{archive_sha}.tar.gz"; temp.replace(archive)
 (args.artifact_dir/f"{archive.name}.sha256").write_bytes(f"{archive_sha}  {archive.name}\n".encode()); (args.artifact_dir/f"{archive.name}.build.json").write_bytes(canonical_json({"archive":archive.name,"archive_sha256":archive_sha,"manifest":manifest_path.name,"manifest_sha256":mh,"members":manifest["members"]}))
 print(json.dumps({"status":"BUILT","archive":str(archive),"archive_sha256":archive_sha,"manifest":str(manifest_path),"manifest_sha256":mh},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
