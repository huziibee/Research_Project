#!/usr/bin/env python3
"""Prepare target-free queued-study packets; gold stays in separate keys."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
def h(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def write(p,rows):
 if p.exists():raise ValueError(f"output_exists:{p}")
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text("".join(json.dumps(x,sort_keys=True,ensure_ascii=False)+"\n" for x in rows),encoding="utf-8",newline="\n")
def main():
 a=argparse.ArgumentParser();a.add_argument("--dataset",choices=("clara","indirect_requests"),required=True);a.add_argument("--source",type=Path,required=True);a.add_argument("--packet",type=Path,required=True);a.add_argument("--key",type=Path,required=True);x=a.parse_args(); rows=[json.loads(s) for s in x.source.read_text(encoding="utf-8").splitlines() if s.strip()];p=[];k=[]
 for r in rows:
  f=h(r); key={"record_id":r["id"],"source_fingerprint_sha256":f,"label_status":"EXPLORATORY_WEAK_SOURCE_LABEL"}
  if x.dataset=="clara":
   key|={q:r.get(q) for q in ("ambiguity_present","capability_status","recommended_strategy")}
   for condition,scene,capability in (("full_context",r["scene_context"],r["capability_context"]),("context_blind",None,None)):p.append({"study_id":"clara_context_routing_v1","record_id":r["id"],"condition":condition,"command":r["command"],"scene_context":scene,"capability_context":capability,"source_fingerprint_sha256":f})
  else:
   key|={q:r.get(q) for q in ("ambiguity_present","ambiguity_types","missing_slots")};p.append({"study_id":"indirect_pragmatic_recovery_v1","record_id":r["id"],"condition":"source_native_context","command":r["command"],"scene_context":r["scene_context"],"capability_context":None,"source_fingerprint_sha256":f})
  k.append(key)
 if len({z["record_id"] for z in k})!=len(rows):raise ValueError("duplicate_ids")
 write(x.packet,p);write(x.key,k);print(json.dumps({"dataset":x.dataset,"packet_rows":len(p),"key_rows":len(k),"packet_sha256":hashlib.sha256(x.packet.read_bytes()).hexdigest()},sort_keys=True))
if __name__=="__main__":main()
