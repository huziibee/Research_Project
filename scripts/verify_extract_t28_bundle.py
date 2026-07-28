#!/usr/bin/env python3
"""Verify and safely extract a T28 content-addressed bundle."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ambiguity_manager.model.t28_bundle import safe_extract, sha256_file
def main() -> int:
 p=argparse.ArgumentParser(); p.add_argument('--archive',type=Path,required=True); p.add_argument('--manifest',type=Path,required=True); p.add_argument('--manifest-sha256'); p.add_argument('--destination',type=Path,required=True); a=p.parse_args();
 if a.manifest_sha256 and hashlib.sha256(a.manifest.read_bytes()).hexdigest() != a.manifest_sha256: raise SystemExit('manifest_hash_mismatch')
 m=json.loads(a.manifest.read_text(encoding='utf-8')); ah=sha256_file(a.archive); result=safe_extract(a.archive,a.destination,m,ah); print(json.dumps(result,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
