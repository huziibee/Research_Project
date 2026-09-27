#!/usr/bin/env python3
"""Run one AmbiK ambiguity-type system on a target-free packet."""
from __future__ import annotations
import argparse, hashlib, json, os, sys, tempfile, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path
ALLOWED={"commonsense","preference","safety_precondition"}
# Canonical labels plus AmbiK source strings (docs/mapping/ambik_mapping.md) and
# common surface variants. Unknown types stay rejected — do not invent gold.
ALIASES={
    "commonsense":"commonsense","common_sense":"commonsense","common-sense":"commonsense","common sense":"commonsense",
    "common_sense_knowledge":"commonsense","common-sense-knowledge":"commonsense","common sense knowledge":"commonsense",
    "commonsense_knowledge":"commonsense","cs_knowledge":"commonsense","world_knowledge":"commonsense",
    "preference":"preference","preferences":"preference","prefer":"preference","user_preference":"preference",
    "user_preferences":"preference",
    "safety_precondition":"safety_precondition","safety-precondition":"safety_precondition","safety precondition":"safety_precondition",
    "safety":"safety_precondition","precondition":"safety_precondition","safety_check":"safety_precondition",
    "safety_preconditions":"safety_precondition",
}
TYPE_KEYS=("ambiguity_types","ambiguity_type","types","labels","predicted_types")
def sha(path:Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest()
def extract_json(text:str):
    text=text.strip()
    if text.startswith("```"):
        lines=text.splitlines()
        text="\n".join(lines[1:-1] if lines[-1].strip()=="```" else lines[1:]).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start,end=text.find("{"),text.rfind("}")
        if start>=0 and end>start:
            return json.loads(text[start:end+1])
        start,end=text.find("["),text.rfind("]")
        if start>=0 and end>start:
            return json.loads(text[start:end+1])
        raise
def _item_text(item:object)->str|None:
    if isinstance(item,str):
        return item
    if isinstance(item,dict):
        for key in ("ambiguity_type","type","label","name","value"):
            value=item.get(key)
            if isinstance(value,str) and value.strip():
                return value
    return None

def parse(text:str)->list[str]:
    value=extract_json(text)
    raw=None
    if isinstance(value,dict):
        for key in TYPE_KEYS:
            if key in value:
                raw=value.get(key)
                break
    elif isinstance(value,list):
        raw=value
    elif isinstance(value,str):
        raw=value
    if isinstance(raw,str):
        raw=[raw]
    if not isinstance(raw,list):
        raise ValueError("ambiguity_types_invalid")
    normalized=[]
    seen=set()
    for item in raw:
        text_item=_item_text(item)
        if not text_item or not text_item.strip():
            continue
        folded=text_item.strip().casefold()
        key=" ".join(folded.replace("-","_").split())
        mapped=ALIASES.get(folded) or ALIASES.get(key) or ALIASES.get(key.replace(" ","_")) or (text_item.strip() if text_item.strip() in ALLOWED else None)
        if mapped in ALLOWED and mapped not in seen:
            seen.add(mapped)
            normalized.append(mapped)
    # Empty / unknown-only lists are model abstentions, not gold fills.
    # Record [] so the packet can finish; the scorer treats [] as incorrect.
    return sorted(normalized)
def main()->None:
    p=argparse.ArgumentParser(); p.add_argument("--packet",type=Path,required=True); p.add_argument("--prompt",type=Path,required=True); p.add_argument("--model",required=True); p.add_argument("--revision",required=True); p.add_argument("--port",type=int,required=True); p.add_argument("--out",type=Path,required=True); p.add_argument("--manifest-out",type=Path,required=True); p.add_argument("--seed",type=int,required=True); p.add_argument("--temperature",type=float,default=0.0); p.add_argument("--limit",type=int); a=p.parse_args()
    if float(a.temperature)<0: raise SystemExit("temperature_must_be_nonnegative")
    if a.out.exists() or a.manifest_out.exists(): raise ValueError("output_or_manifest_exists")
    rows=[json.loads(line) for line in a.packet.read_text(encoding="utf-8").splitlines() if line.strip()]; rows=rows[:a.limit] if a.limit else rows
    if not rows or len({row.get("record_id") for row in rows})!=len(rows): raise ValueError("packet_coverage_or_duplicate_mismatch")
    prompt=a.prompt.read_text(encoding="utf-8"); started=time.time(); out=[]
    for i,row in enumerate(rows):
        body={"model":a.model,"messages":[{"role":"system","content":prompt},{"role":"user","content":"USER COMMAND:\n"+row["command"]+"\n\nSCENE CONTEXT:\n"+row["scene_context"]}],"temperature":float(a.temperature),"top_p":1.0,"seed":a.seed+i,"max_tokens":96,"response_format":{"type":"json_object"}}
        error=None
        for _ in range(3):
            try:
                req=urllib.request.Request(f"http://127.0.0.1:{a.port}/v1/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"},method="POST")
                with urllib.request.urlopen(req,timeout=180) as r: result=parse(json.loads(r.read().decode())["choices"][0]["message"]["content"])
                error=None; break
            except Exception as exc:
                error=exc
                body["messages"].append({"role":"user","content":"Technical retry: return exactly one valid JSON object with only ambiguity_types, a non-empty unique list chosen only from commonsense, preference, safety_precondition."})
        if error:
            print(f"rejected_payload:{row['record_id']}:{error!r}", file=sys.stderr, flush=True)
            raise SystemExit(f"prediction_failed:{row['record_id']}:{error!r}")
        out.append({"record_id":row["record_id"],"source_fingerprint_sha256":row["source_fingerprint_sha256"],"ambiguity_types":result})
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile("w",encoding="utf-8",newline="\n",dir=a.out.parent,delete=False) as h:
        for row in out:h.write(json.dumps(row,sort_keys=True)+"\n")
        temp=Path(h.name)
    os.replace(temp,a.out); manifest={"status":"AMBIK_AMBIGUITY_TYPE_INFERENCE_COMPLETE","model":a.model,"model_revision":a.revision,"packet_sha256":sha(a.packet),"prompt_sha256":sha(a.prompt),"output_sha256":sha(a.out),"record_count":len(out),"decoder_parameters":{"temperature":float(a.temperature),"top_p":1.0,"seed":a.seed,"max_tokens":96,"technical_retries":2},"started_at_utc":datetime.fromtimestamp(started,timezone.utc).isoformat(),"elapsed_seconds":round(time.time()-started,3)}
    a.manifest_out.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
if __name__ == "__main__":main()
