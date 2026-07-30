"""A01-only vLLM OpenAI-compatible runner with append-only raw attempts."""
from __future__ import annotations
import argparse, json, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

def post(url, body):
    req=urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=180) as response: return json.loads(response.read())

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--model",required=True); ap.add_argument("--revision",required=True); ap.add_argument("--annotator",required=True); ap.add_argument("--port",type=int,required=True); ap.add_argument("--pilot",required=True); ap.add_argument("--output",required=True); ap.add_argument("--cache",required=True); ap.add_argument("--server-log",required=True); ap.add_argument("--limit",type=int); a=ap.parse_args()
    out=Path(a.output); out.mkdir(parents=True,exist_ok=True); raw=out/"raw.jsonl"; parsed=out/"parsed.jsonl"; expected=[]
    lines=Path(a.pilot).read_text(encoding="utf-8").splitlines()
    if a.limit: lines=lines[:a.limit]
    for line in lines:
        if not line.strip(): continue
        rec=json.loads(line); expected.append(rec["record_id"]); prompt=f"Command: {rec['command']}\nContext: {rec.get('context') or '(none)'}\nReturn one JSON annotation matching the frozen A01 schema."
        body={"model":a.model,"messages":[{"role":"system","content":"You are an independent A01 annotation assistant. Use only supplied evidence. Return JSON only."},{"role":"user","content":prompt}],"temperature":0.0,"top_p":1.0,"max_tokens":768,"n":1,"response_format":{"type":"json_object"}}
        attempts=[]; obj=None; error="none"
        for attempt in range(3):
            try:
                started=time.time(); response=post(f"http://127.0.0.1:{a.port}/v1/chat/completions",body); content=response["choices"][0]["message"]["content"]; obj=json.loads(content); attempts.append({"attempt":attempt+1,"response":response,"elapsed_seconds":time.time()-started}); break
            except Exception as exc: attempts.append({"attempt":attempt+1,"error":repr(exc)}); error="retry_exhausted"
        valid=isinstance(obj,dict) and obj.get("record_id",rec["record_id"])==rec["record_id"]
        provider = "Google" if "gemma" in a.model.lower() else ("Z.ai" if "glm" in a.model.lower() else "unknown")
        wrapper={"record_id":rec["record_id"],"annotator_id":a.annotator,"model_name":a.model,"model_provider":provider,"model_revision":a.revision,"inference_engine":"vLLM 0.20.1","quantisation":"BF16","prompt_version":"a01-prompt-1.0.0","handbook_version":"a01-handbook-1.0.0","schema_version":"a01-annotation-1.0.0","decoding_parameters":{"temperature":0.0,"top_p":1.0,"max_tokens":768,"max_model_len":8192,"max_num_seqs":1,"seed":20260728},"timestamp":datetime.now(timezone.utc).isoformat(),"raw_response":attempts,"parsed_annotation":obj,"schema_validity":valid,"confidence":(obj or {}).get("confidence","unknown") if isinstance(obj,dict) else "unknown","rationale":(obj or {}).get("rationale") if isinstance(obj,dict) else None,"error_status":error if valid else "schema_error"}
        with raw.open("a",encoding="utf-8") as f: f.write(json.dumps(wrapper,ensure_ascii=False)+"\n")
        if valid:
            with parsed.open("a",encoding="utf-8") as f: f.write(json.dumps(dict(obj,record_id=rec["record_id"]),ensure_ascii=False)+"\n")
    (out/"expected_manifest.json").write_text(json.dumps({"record_ids":expected,"completed":len([x for x in parsed.read_text(encoding="utf-8").splitlines() if x.strip()]) if parsed.exists() else 0},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
