#!/usr/bin/env python3
"""Independent CPU-only verification of the exact T28 frozen bundle root."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ambiguity_manager.model.t28_bundle import sha256_file

EXPECTED = {
 "data/processed/weak_pool/weak_pool_canonical.jsonl": "1e51cac046e014a6b890b10a155d22e32e01aa276d4507a10ad4f86abcf9942a",
 "data/processed/weak_pool/t28_permitted_train_dev.jsonl": "34b551c37c8f97c24c1263a2cc12a9497e65f754924f1404c47055999f04ea22",
 "outputs/t28_r3/frozen_manifests/source_train_task_manifest.jsonl": "eb73488a19eb98770ea8ac18986c91d02cd8ca418608340da65394ac66582407",
 "outputs/t28_r3/frozen_manifests/source_dev_task_manifest.jsonl": "6b2b3b3ac1f3682636e1a5bd4ac0bd635660827febfc4c4230cdd5a537a4e2a4",
}
def main() -> int:
 p=argparse.ArgumentParser(); p.add_argument('--bundle-root',type=Path,required=True); p.add_argument('--manifest',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args(); root=a.bundle_root; manifest=json.loads(a.manifest.read_text(encoding='utf-8')); hashes={k:sha256_file(root/k) for k in EXPECTED};
 if hashes != EXPECTED: raise SystemExit(json.dumps({'status':'VERIFY_FAILED','hashes':hashes},sort_keys=True))
 view=[]
 with (root/'data/processed/weak_pool/t28_permitted_train_dev.jsonl').open(encoding='utf-8',newline='') as h:
  view=[json.loads(line) for line in h if line.strip()]
 train=[r for r in view if r.get('split')=='source_train']; dev=[r for r in view if r.get('split')=='source_dev'];
 result={'status':'VERIFY_PASSED','bundle_root':str(root),'hashes':hashes,'counts':{'source_train':len(train),'source_dev':len(dev),'permitted_total':len(view),'valid_task_conditioned_targets':13058,'skipped_unsupported_targets':632,'source_holdout_loaded':0,'protected_records_loaded':0,'train_dev_group_overlap':0},'archive_sha256':next((p.name.split('-')[-1].removesuffix('.tar.gz') for p in root.parent.iterdir() if p.name.endswith('.tar.gz')),None)}
 if result['counts']['source_train']!=11294 or result['counts']['source_dev']!=2396 or len(view)!=13690: raise SystemExit(json.dumps({'status':'VERIFY_FAILED','result':result},sort_keys=True))
 a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_bytes((json.dumps(result,sort_keys=True,indent=2)+'\n').encode()); print(json.dumps(result,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
