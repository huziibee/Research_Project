#!/usr/bin/env python3
"""Target-free strict JSON runner for CLARA and Indirect Requests."""
from __future__ import annotations
import argparse,json,hashlib,urllib.request,time,os,sys,tempfile
from pathlib import Path
from datetime import datetime,timezone
SPECS={"clara":{"keys":{"ambiguity_present","capability_status","recommended_strategy"},"enums":{"capability_status":{"capable","conditional","incapable","unknown",None},"recommended_strategy":{"execute","clarify","reject",None}}},"indirect":{"keys":{"ambiguity_present","ambiguity_types","missing_slots"},"enums":{}}
}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def extract_json(text):
 text=text.strip()
 if text.startswith("```"):
  lines=text.splitlines(); text="\n".join(lines[1:-1] if lines[-1].strip()=="```" else lines[1:]).strip()
 try: return json.loads(text)
 except json.JSONDecodeError:
  start,end=text.find("{"),text.rfind("}")
  if start>=0 and end>start: return json.loads(text[start:end+1])
  raise
def _as_bool(value):
 if isinstance(value,bool): return value
 if isinstance(value,str) and value.strip().casefold() in {"true","false"}: return value.strip().casefold()=="true"
 raise ValueError("schema_invalid")
def valid(value,task):
 s=SPECS[task]
 if isinstance(value,str): value=extract_json(value)
 if not isinstance(value,dict): raise ValueError("schema_invalid")
 if task=="clara":
  if set(value)!=s["keys"] or not isinstance(value["ambiguity_present"],bool): raise ValueError("schema_invalid")
  if any(value[k] not in s["enums"][k] for k in s["enums"]): raise ValueError("enum_invalid")
  return value
 if any(k not in value for k in s["keys"]): raise ValueError("schema_invalid")
 present=_as_bool(value["ambiguity_present"])
 raw_types=value["ambiguity_types"]
 if isinstance(raw_types,str): raw_types=[raw_types] if raw_types.strip() else []
 if not isinstance(raw_types,list): raise ValueError("indirect_schema_invalid")
 types=[]
 empty_aliases={"","none","null","n/a","na","unambiguous","no_ambiguity","none_of_the_above"}
 for item in raw_types:
  if not isinstance(item,str): raise ValueError("indirect_schema_invalid")
  token=item.strip().casefold().replace("-","_").replace(" ","_")
  if token in empty_aliases: continue
  if token=="pragmatic":
   if "pragmatic" not in types: types.append("pragmatic")
   continue
  raise ValueError("indirect_schema_invalid")
 if types not in ([], ["pragmatic"]): raise ValueError("indirect_schema_invalid")
 slots=value["missing_slots"]
 if isinstance(slots,str): slots=[slots] if slots.strip() else []
 if not isinstance(slots,list): raise ValueError("indirect_schema_invalid")
 clean=[]
 for item in slots:
  if not isinstance(item,str): raise ValueError("indirect_schema_invalid")
  if item.strip(): clean.append(item.strip())
 return {"ambiguity_present":present,"ambiguity_types":types,"missing_slots":clean}
def main():
 p=argparse.ArgumentParser();p.add_argument("--task",choices=SPECS,required=True);p.add_argument("--packet",type=Path,required=True);p.add_argument("--prompt",type=Path,required=True);p.add_argument("--model",required=True);p.add_argument("--revision",required=True);p.add_argument("--port",type=int,required=True);p.add_argument("--out",type=Path,required=True);p.add_argument("--manifest-out",type=Path,required=True);p.add_argument("--seed",type=int,required=True);p.add_argument("--temperature",type=float,default=0.0);p.add_argument("--limit",type=int);a=p.parse_args()
 if float(a.temperature)<0:raise SystemExit("temperature_must_be_nonnegative")
 if a.out.exists() or a.manifest_out.exists():raise ValueError("output_exists")
 rows=[json.loads(x) for x in a.packet.read_text(encoding="utf-8").splitlines() if x.strip()];rows=rows[:a.limit] if a.limit else rows; prompt=a.prompt.read_text(encoding="utf-8");out=[];started=time.time()
 for i,r in enumerate(rows):
  user="USER COMMAND:\n"+r["command"]+("\n\nSCENE CONTEXT:\n"+r["scene_context"] if r.get("scene_context") else "")+("\n\nCAPABILITY CONTEXT:\n"+r["capability_context"] if r.get("capability_context") else "");body={"model":a.model,"messages":[{"role":"system","content":prompt},{"role":"user","content":user}],"temperature":float(a.temperature),"top_p":1.0,"seed":a.seed+i,"max_tokens":160,"response_format":{"type":"json_object"}}
  err=None
  for _ in range(3):
   try:
    q=urllib.request.Request(f"http://127.0.0.1:{a.port}/v1/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"},method="POST");
    with urllib.request.urlopen(q,timeout=180) as z:v=valid(json.loads(z.read().decode())["choices"][0]["message"]["content"],a.task)
    err=None;break
   except Exception as e:
    err=e
    body["messages"].append({"role":"user","content":"Technical retry: return exactly one valid JSON object matching the required fields and permitted values for this same item; no prose or extra fields."})
  if err:
   print(f"rejected_payload:{r['record_id']}:{err!r}",file=sys.stderr,flush=True)
   raise SystemExit(f"prediction_failed:{r['record_id']}:{err!r}")
  cond=r.get("condition") or ("source_native_context" if a.task=="indirect" else None)
  if not cond:raise KeyError("condition")
  out.append({"record_id":r["record_id"],"condition":cond,"source_fingerprint_sha256":r["source_fingerprint_sha256"],**v})
 a.out.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile("w",encoding="utf-8",newline="\n",dir=a.out.parent,delete=False) as h:
  for x in out:h.write(json.dumps(x,sort_keys=True)+"\n")
  t=h.name
 os.replace(t,a.out);a.manifest_out.write_text(json.dumps({"task":a.task,"model":a.model,"model_revision":a.revision,"packet_sha256":sha(a.packet),"prompt_sha256":sha(a.prompt),"output_sha256":sha(a.out),"record_count":len(out),"decoder":{"temperature":float(a.temperature),"top_p":1.0,"seed":a.seed,"max_tokens":160},"started_at_utc":datetime.fromtimestamp(started,timezone.utc).isoformat()},indent=2,sort_keys=True)+"\n",encoding="utf-8")
if __name__=="__main__":main()
