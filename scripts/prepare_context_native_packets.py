#!/usr/bin/env python3
"""Create target-free packets and separate source-mapped keys for CLARA/Indirect Requests."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
FIELDS={"clara":("scene_context","capability_context","ambiguity_present","capability_status","recommended_strategy"),"indirect_requests":("scene_context","ambiguity_present","ambiguity_types","missing_slots")}
def fp(row:dict)->str:return hashlib.sha256(json.dumps(row,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def main()->None:
 p=argparse.ArgumentParser();p.add_argument("--dataset",choices=FIELDS,required=True);p.add_argument("--source",type=Path,required=True);p.add_argument("--packet",type=Path,required=True);p.add_argument("--key",type=Path,required=True);a=p.parse_args()
 if a.packet.exists() or a.key.exists():raise ValueError("output_exists")
 rows=[json.loads(x) for x in a.source.read_text(encoding="utf-8").splitlines() if x.strip()]; packet=[];key=[]
 for row in rows:
  h=fp(row); packet.append({"study_id":a.dataset+"_native_context_v1","record_id":row["id"],"command":row["command"],"scene_context":row["scene_context"],"capability_context":row.get("capability_context"),"source_fingerprint_sha256":h}); key.append({"record_id":row["id"],"source_fingerprint_sha256":h,**{f:row.get(f) for f in FIELDS[a.dataset]},"label_status":"EXPLORATORY_WEAK_SOURCE_LABEL"})
 if not packet or len({r["record_id"] for r in packet})!=len(packet):raise ValueError("coverage_or_duplicate_mismatch")
 for path,value in ((a.packet,packet),(a.key,key)):
  path.parent.mkdir(parents=True,exist_ok=True);path.write_text("".join(json.dumps(r,sort_keys=True,ensure_ascii=False)+"\n" for r in value),encoding="utf-8",newline="\n")
 print(json.dumps({"dataset":a.dataset,"records":len(rows),"packet_sha256":hashlib.sha256(a.packet.read_bytes()).hexdigest(),"key_sha256":hashlib.sha256(a.key.read_bytes()).hexdigest()},sort_keys=True))
if __name__=="__main__":main()
