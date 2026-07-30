"""A01-only vLLM OpenAI-compatible runner with append-only raw attempts."""
from __future__ import annotations
import argparse, json, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

FROZEN_RESPONSE_SCHEMA={"type":"object","required":["record_id","speech_act","cpc","candidate_interpretations","ambiguity_present","ambiguity_types","compound_ambiguity_count","risk_level","capability_status","recommended_strategy","annotator_role","confidence","timestamp","handbook_version","annotation_schema_version","package_version"],"properties":{"record_id":{"type":"string"},"speech_act":{"type":"string"},"cpc":{"type":"object"},"candidate_interpretations":{"type":"array"},"ambiguity_present":{"type":"boolean"},"ambiguity_types":{"type":"array","items":{"type":"string"}},"compound_ambiguity_count":{"type":"integer"},"risk_level":{"type":"string","enum":["none","low","medium","high","unknown"]},"capability_status":{"type":"string","enum":["capable","conditional","incapable","unknown"]},"recommended_strategy":{"type":"string","enum":["execute","clarify","silently_resolve","face_preserving_rejection","multi_step"]},"annotator_role":{"type":"string","enum":["ANN-A","ANN-B"]},"confidence":{"type":"string","enum":["low","medium","high"]},"timestamp":{"type":"string"},"handbook_version":{"type":"string"},"annotation_schema_version":{"type":"string"},"package_version":{"type":"string"}}}

def post(url, body):
    req=urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=180) as response: return json.loads(response.read())

def parsed_schema_errors(obj, record_id):
    if not isinstance(obj, dict): return ["parsed_annotation_not_object"]
    errors=[]
    if obj.get("record_id", record_id) != record_id: errors.append("record_id_mismatch")
    required={"record_id","speech_act","cpc","candidate_interpretations","ambiguity_present","ambiguity_types","compound_ambiguity_count","risk_level","capability_status","recommended_strategy","annotator_role","confidence","timestamp","handbook_version","annotation_schema_version","package_version"}
    errors.extend(f"missing_required_field:{field}" for field in sorted(required-set(obj)))
    if obj.get("confidence") not in {"high", "medium", "low"}: errors.append("confidence_must_be_frozen_enum")
    return errors

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--model",required=True); ap.add_argument("--revision",required=True); ap.add_argument("--annotator",required=True); ap.add_argument("--port",type=int,required=True); ap.add_argument("--pilot",required=True); ap.add_argument("--output",required=True); ap.add_argument("--cache",required=True); ap.add_argument("--server-log",required=True); ap.add_argument("--limit",type=int); a=ap.parse_args()
    out=Path(a.output); out.mkdir(parents=True,exist_ok=True); raw=out/"raw.jsonl"; parsed=out/"parsed.jsonl"; expected=[]
    lines=Path(a.pilot).read_text(encoding="utf-8").splitlines()
    if a.limit: lines=lines[:a.limit]
    for line in lines:
        if not line.strip(): continue
        rec=json.loads(line); expected.append(rec["record_id"]); prompt=f"Command: {rec['command']}\nContext: {rec.get('context') or '(none)'}\nReturn one JSON annotation matching the frozen A01 schema."
        body={"model":a.model,"messages":[{"role":"system","content":"You are an independent A01 annotation assistant. Use only supplied evidence. Return JSON only."},{"role":"user","content":prompt}],"temperature":0.0,"top_p":1.0,"max_tokens":768,"n":1,"response_format":{"type":"json_schema","json_schema":{"name":"a01_annotation","schema":FROZEN_RESPONSE_SCHEMA}}}
        attempts=[]; obj=None; error="none"
        for attempt in range(3):
            try:
                started=time.time(); response=post(f"http://127.0.0.1:{a.port}/v1/chat/completions",body); content=response["choices"][0]["message"]["content"]; obj=json.loads(content); schema_errors=parsed_schema_errors(obj, rec["record_id"])
                entry={"attempt":attempt+1,"response":response,"elapsed_seconds":time.time()-started}
                if schema_errors:
                    entry.update({"status":"schema_invalid","retry_reason":"schema_invalid_output","schema_errors":schema_errors}); attempts.append(entry); error="schema_error"; continue
                attempts.append(entry); error="none"; break
            except Exception as exc: attempts.append({"attempt":attempt+1,"error":repr(exc),"retry_reason":"transport_or_parse_failure"}); error="retry_exhausted"
        valid=not parsed_schema_errors(obj, rec["record_id"])
        provider = "Google" if "gemma" in a.model.lower() else ("Z.ai" if "glm" in a.model.lower() else "unknown")
        wrapper={"record_id":rec["record_id"],"annotator_id":a.annotator,"model_name":a.model,"model_provider":provider,"model_revision":a.revision,"inference_engine":"vLLM 0.20.1","quantisation":"BF16","prompt_version":"a01-prompt-1.0.0","handbook_version":"a01-handbook-1.0.0","schema_version":"a01-annotation-1.0.0","decoding_parameters":{"temperature":0.0,"top_p":1.0,"max_tokens":768,"max_model_len":8192,"max_num_seqs":1,"seed":20260728},"timestamp":datetime.now(timezone.utc).isoformat(),"raw_response":attempts,"parsed_annotation":obj,"schema_validity":valid,"confidence":(obj or {}).get("confidence","unknown") if isinstance(obj,dict) else "unknown","rationale":(obj or {}).get("rationale") if isinstance(obj,dict) else None,"error_status":error if valid else "schema_error"}
        with raw.open("a",encoding="utf-8") as f: f.write(json.dumps(wrapper,ensure_ascii=False)+"\n")
        if valid:
            with parsed.open("a",encoding="utf-8") as f: f.write(json.dumps(dict(obj,record_id=rec["record_id"]),ensure_ascii=False)+"\n")
    (out/"expected_manifest.json").write_text(json.dumps({"record_ids":expected,"completed":len([x for x in parsed.read_text(encoding="utf-8").splitlines() if x.strip()]) if parsed.exists() else 0},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
