"""Targeted frozen capability-repaired Goal-First readiness experiment.

No generation, raw-source classification, threshold tuning, or paper editing.
prepare verifies 56/57/83/87 before run. Labels and gate are protocol-locked.
"""
from __future__ import annotations

import argparse
import collections
import copy
import csv
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/pilot120/gliner25_action_readiness_repair_v1"
LEGACY = ROOT / "scripts/experiments/gliner25_goalfirst_semantic_router_v1.py"
LEGACY_SHA = "41fcd0e02ecd782f28acf2a183ca404f7a3c7177d8fcd601246787e5a9d1cd07"
if hashlib.sha256(LEGACY.read_bytes()).hexdigest() != LEGACY_SHA:
    raise ValueError("pinned renderer/metric module changed")
spec = importlib.util.spec_from_file_location("frozen_semantic_v1", LEGACY)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from lib_capability_debate_20260918 import analysis_from_dict, patch_capability_in_analysis
from ambiguity_manager.systems.routing import DeterministicRouter

JUDGMENTS = ROOT / "research/pilot120/capability_intervention/capability_judgments_cluster.jsonl"
JUDGMENTS_SHA = "e4706a5e061b6f0da90801365fc58787db102027681e83de0209622a04f649b1"
RESIDUAL = ROOT / "research/pilot120/capability_intervention/residual_error_ledger.csv"
RESIDUAL_SHA_LF = "e54368560eb4cd3aba178b667c2b9f27ff50037ea86daaaab72b73ac34b00224"
READY = {
    "ACTION_READY": "The requested job is understood and the available semantic/contextual representation determines one sufficiently specific concrete action. Any remaining unknown information would not materially change which action the robot performs.",
    "ACTION_BLOCKING_AMBIGUITY": "The requested job is understood, but one or more unresolved plausible values would lead to materially different concrete robot actions. The robot should ask for the missing decision-relevant information before acting.",
    "HARD_BLOCKED": "The requested job is sufficiently understood and grounded, but execution is genuinely prevented by capability, authorization, prohibition, or unacceptable safety constraints.",
}
CONDITIONS = ["A_intent_only", "B_intent_unresolved", "C_task_slots_unresolved", "D_full_without_risk", "E_full_with_risk", "F_direct_full_with_risk"]
HYBRIDS = CONDITIONS[:5]
MAIN = "D_full_without_risk"
GOLD_C_DIAGNOSTICS = {
    "CA-0215": "filing_medium", "CA-0225": "filing_medium", "CA-0762": "filing_medium",
    "CA-0552": "destination_unit", "CA-0727": "destination_unit",
    "CA-0608": "quantity", "CA-0889": "quantity",
}


def lf_hash(path):
    return old.sha(path.read_bytes().replace(b"\r\n", b"\n"))


def route(a):
    decision = DeterministicRouter(policy="goal_first_v2").route(analysis_from_dict(a))
    return old.norm(decision.recommended_strategy.value), decision.matched_rule_id


def reconstruct():
    """Uses gold only to VERIFY the historical condition, never for model input."""
    frozen = old.frozen()
    old.verify(JUDGMENTS, JUDGMENTS_SHA)
    old.verify(old.GOLD, old.EXPECTED[old.GOLD])
    old.verify(old.CAP, old.EXPECTED[old.CAP])
    # The historical CSV is text; normalize line endings for portability.
    if lf_hash(RESIDUAL) != RESIDUAL_SHA_LF:
        raise ValueError("frozen residual ledger changed")
    judgments = old.unique([json.loads(x) for x in JUDGMENTS.read_bytes().splitlines()])
    gold_rows = old.unique([json.loads(x) for x in old.GOLD.read_bytes().splitlines()])
    gold = {rid:old.norm(r["terminal_strategy"]) for rid,r in gold_rows.items()}
    if set(frozen) != set(gold) or set(judgments) != set(gold):
        raise ValueError("120-ID mismatch")
    saved = json.loads(old.CAP.read_text(encoding="utf-8"))
    keys = ["emit_baseline_pre_codefix", "codefix_only_frozen_capability", "llm_patch_capability_current_router", "oracle_gold_capability_current_router"]
    counts = [0]*4
    states, baseline, rules, repaired_caps = {}, {}, {}, {}
    for rid,r in sorted(frozen.items()):
        a = copy.deepcopy(r["parsed"]["analysis"])
        judgment = judgments[rid]
        if judgment["failed"]:
            raise ValueError("failed frozen capability judgment")
        # Explicit projection: no gold_capability_status, match flag, reason,
        # raw_output, confidence, or source packet enters semantic inference.
        cap = judgment["capability_status"]
        repaired = patch_capability_in_analysis(a,cap)
        changed = {k for k in set(a)|set(repaired) if a.get(k)!=repaired.get(k)}
        if not changed <= {"capability_status","findings"}:
            raise ValueError("unexpected semantic mutation")
        v83,rule = route(repaired)
        values = [old.norm(r["terminal_strategy"]),route(a)[0],v83,route(patch_capability_in_analysis(a,gold_rows[rid]["capability_status"]))[0]]
        for i,v in enumerate(values):
            ok = v == gold[rid]
            if saved[keys[i]]["_route_ok"][rid] != ok:
                raise ValueError("saved per-case historical condition mismatch")
            counts[i] += ok
        states[rid],baseline[rid],rules[rid],repaired_caps[rid] = repaired,v83,rule,cap
    if counts != [56,57,83,87]:
        raise ValueError(f"historical accuracy mismatch: {counts}")
    residual = {rid for rid in gold if baseline[rid]!=gold[rid]}
    ledger = list(csv.DictReader(io.StringIO(RESIDUAL.read_text(encoding="utf-8"))))
    if len(ledger)!=37 or {r["record_id"] for r in ledger}!=residual:
        raise ValueError("residual IDs mismatch")
    for r in ledger:
        rid=r["record_id"]
        if old.norm(r["predicted_route"])!=baseline[rid] or old.norm(r["gold_route"])!=gold[rid]:
            raise ValueError("residual per-case route mismatch")
    composition = collections.Counter(gold[rid]+"->"+baseline[rid] for rid in residual)
    if dict(composition)!={"EXECUTE->CLARIFY":26,"EXECUTE->REFUSE":4,"CLARIFY->EXECUTE":5,"CLARIFY->REFUSE":2}:
        raise ValueError("residual composition mismatch")
    if sum(baseline[rid]=="REFUSE" for rid in gold)!=27 or any(baseline[rid]!="REFUSE" for rid in gold if gold[rid]=="REFUSE"):
        raise ValueError("refusal preservation premise mismatch")
    return states,baseline,rules,repaired_caps,gold,counts


def render(a,condition):
    if condition=="A_intent_only": return a["intent_summary"]
    if condition=="B_intent_unresolved": return old.render(a,"B_intent_grounding")
    if condition=="C_task_slots_unresolved":
        return old.render(a,"C_intent_task_slots")+"\n\nUnresolved slots:\n"+old.dump(a["unresolved_slots"])
    text=old.render(a,"E_full_without_risk" if condition=="D_full_without_risk" else "F_full")
    # Explicit existing semantic prohibition markers, not router trace/comments.
    markers=[x for x in a.get("findings",[]) if x in ("prohibited","unsafe_action")]
    if markers: text+="\n\nHard constraint findings:\n"+old.dump(markers)
    return text


def hybrid(label,baseline_route,failed=False):
    # Freeze the EXISTING refusal gate. No gold-derived gate or whitelist.
    if baseline_route=="REFUSE": return "REFUSE","baseline_refusal_preserved"
    if failed: return "FAILED","inference_failed"
    if label=="ACTION_READY": return "EXECUTE","readiness_ready"
    if label=="ACTION_BLOCKING_AMBIGUITY": return "CLARIFY","readiness_ambiguity"
    if label=="HARD_BLOCKED": return baseline_route,"unsupported_hard_block_fallback"
    raise ValueError("unknown readiness label")


def lock(data):
    states,base,rules,caps,gold,counts=data
    OUT.mkdir(parents=True,exist_ok=True)
    source_paths=[ROOT/"scripts/lib_capability_debate_20260918.py",*sorted((ROOT/"src/ambiguity_manager").rglob("*.py")),ROOT/"configs/systems/route_precedence.json"]
    source_hashes={p.relative_to(ROOT).as_posix():lf_hash(p) for p in source_paths if p.exists()}
    p={"experiment":"gliner25_action_readiness_repair_v1","status":"exploratory frozen development-set diagnostic","model_id":old.MODEL_ID,"model_revision":old.MODEL_REVISION,
       "script_sha256":old.sha(Path(__file__).read_bytes()),"pinned_previous_renderer_sha256":LEGACY_SHA,"routing_source_sha256_LF":source_hashes,
       "frozen_inputs":{**{p.relative_to(ROOT).as_posix():h for p,h in old.EXPECTED.items()},JUDGMENTS.relative_to(ROOT).as_posix():JUDGMENTS_SHA},
       "semantic_member":old.GF_MEMBER,"semantic_member_sha256":old.GF_SHA,"residual_ledger_sha256_LF":RESIDUAL_SHA_LF,
       "condition_order":CONDITIONS,"primary_condition":MAIN,"readiness_labels":READY,"direct_labels":old.DIRECT,"readiness_route_mapping":old.READY_MAP,
       "best_rule":"max hybrid exact accuracy across A-E; tie broken by condition order; exploratory set-selected result",
       "classification":"single-label argmax, no confidence threshold tuning; no extra inference retries",
       "derived_controls":"Report always-ACTION_READY with the identical preserved-refusal gate; also map secondary direct predictions through that same gate (E->READY,C->AMBIGUITY,R->HARD_BLOCKED). No extra inference or label tuning.",
       "gate":"Preserve all baseline REFUSE outcomes from exact repaired goal_first_v2. Nongated READY->EXECUTE; AMBIGUITY->CLARIFY; unsupported HARD_BLOCKED->baseline route with disagreement recorded; failed nongated->FAILED. Gate still uses original risk in every ablation.",
       "input_fields":{"A":"intent_summary only","B":"intent_summary,unresolved_slots,ambiguity_types","C":"intent_summary,speech_act,13 CPC cells,unresolved_slots; no risk/capability","D":"previous E semantic allowlist with repaired capability; no risk fields","E":"D plus risk_level,risk_relevant","F":"same text as E; direct three-way routing without hybrid gate"},
       "exclusions":old.EXCLUDED+["all outer outputs","router_validation findings","capability judgment gold fields/reason/raw_output","source packet","case ID","baseline route"],
       "input_hashes":{c:{rid:old.sha(render(a,c).encode()) for rid,a in states.items()} for c in CONDITIONS}}
    target=OUT/"protocol.json"
    if target.exists() and json.loads(target.read_text())!=p: raise ValueError("locked protocol changed; create new version")
    if not target.exists(): old.write_json(target,p)
    rows=[{"record_id":rid,"route":base[rid],"matched_rule_id":rules[rid],"capability_after_repair":caps[rid],"canonical_capability":states[rid]["capability_status"],"risk":states[rid]["risk_level"],"gate_refuse":base[rid]=="REFUSE","semantic_state_sha256":old.sha(old.dump(states[rid]).encode()),"case_record":"../cases/"+rid+".json"} for rid in states]
    content="".join(old.dump(r)+"\n" for r in rows)
    baseline_path=OUT/"baseline83.predictions.jsonl"
    if baseline_path.exists() and baseline_path.read_text()!=content: raise ValueError("reconstructed baseline changed")
    if not baseline_path.exists(): baseline_path.write_text(content,encoding="utf-8",newline="\n")
    old.write_json(OUT/"baseline_audit.json",{"n":120,"ids":sorted(states),"progression":counts,"baseline_metrics":old.metric(base,gold),"residual_composition":dict(collections.Counter(gold[rid]+"->"+base[rid] for rid in gold if base[rid]!=gold[rid])),"gate_count":27,"gate_rules":dict(collections.Counter(rules[rid] for rid in base if base[rid]=="REFUSE")),"patch_fields":["capability_status","findings pilot_capability_status only"],"all_other_semantic_fields_unchanged":True,"capability_model_id":"Qwen/Qwen3-8B","capability_temperature":0.0,"capability_revision":"NOT_RECORDED in frozen judgment rows","provenance_commit":"4929fd0f525fae3989fc74223de0ab7c4b967b55","router_commit":"0f59fd1ef5186dbee6d69a258f348e9fb2baa33c"})
    print("BASELINE_VERIFIED",counts,"PROTOCOL_LOCKED",old.sha(target.read_bytes()),flush=True)


def validate(p,c,protocol_hash,states,base):
    rid=p["record_id"]
    if p["condition"]!=c or p["protocol_sha256"]!=protocol_hash or p["input_sha256"]!=old.sha(render(states[rid],c).encode()): raise ValueError("prediction identity mismatch")
    labels=old.DIRECT if c==CONDITIONS[-1] else READY
    if p["failed"]:
        if p["label"] is not None or p["gliner_route"]!="FAILED": raise ValueError("invalid failed prediction")
    elif p["label"] not in labels or p["gliner_route"]!=(p["label"] if c==CONDITIONS[-1] else old.READY_MAP[p["label"]]): raise ValueError("invalid label mapping")
    if c in HYBRIDS:
        expected,reason=hybrid(p["label"],base[rid],p["failed"])
        if p["hybrid_route"]!=expected or p["hybrid_rule"]!=reason: raise ValueError("invalid hybrid route/rule")
        if p["gate_disagreement"]!=(base[rid]=="REFUSE" and p["label"]!="HARD_BLOCKED") or p["unsupported_hard_block"]!=(base[rid]!="REFUSE" and p["label"]=="HARD_BLOCKED"): raise ValueError("invalid disagreement flags")


def run(data,model_dir):
    lock(data)
    states,base,*_=data
    old.verify(old.MODEL_MANIFEST,old.EXPECTED[old.MODEL_MANIFEST])
    manifest=json.loads(old.MODEL_MANIFEST.read_text())
    for name,h in manifest["files"].items(): old.verify(model_dir/name,h)
    import torch
    from gliner2 import AutoExtractor
    torch.set_num_threads(4)
    model=AutoExtractor.from_pretrained(str(model_dir))
    ph=old.sha((OUT/"protocol.json").read_bytes())
    old.write_json(OUT/"runtime.json",{"python":platform.python_version(),"platform":platform.platform(),"threads":4,"device":"cpu","model_snapshot":manifest,"packages":{p:importlib.metadata.version(p) for p in ["gliner2","torch","transformers","huggingface-hub","numpy","tokenizers"]}})
    for c in CONDITIONS:
        path=OUT/(c+".predictions.jsonl")
        prev=[json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
        seen=set()
        for p in prev:
            if p["record_id"] not in states or p["record_id"] in seen: raise ValueError("bad resume IDs")
            validate(p,c,ph,states,base);seen.add(p["record_id"])
        labels=old.DIRECT if c==CONDITIONS[-1] else READY
        with path.open("a",encoding="utf-8",newline="\n") as stream:
            for rid,a in states.items():
                if rid in seen: continue
                text=render(a,c);p={"record_id":rid,"condition":c,"protocol_sha256":ph,"input_sha256":old.sha(text.encode()),"failed":False};start=time.monotonic()
                try:
                    result=model.classify_text(text,{"decision":{"labels":labels}},include_confidence=True)["decision"]
                    label=result["label"]
                    if label not in labels: raise ValueError("out-of-schema label")
                    p.update(label=label,confidence=result["confidence"],gliner_route=label if c==CONDITIONS[-1] else old.READY_MAP[label])
                except Exception as e: p.update(failed=True,label=None,gliner_route="FAILED",error_class=type(e).__name__)
                if c in HYBRIDS:
                    final,reason=hybrid(p["label"],base[rid],p["failed"])
                    p.update(hybrid_route=final,hybrid_rule=reason,gate_disagreement=base[rid]=="REFUSE" and p["label"]!="HARD_BLOCKED",unsupported_hard_block=base[rid]!="REFUSE" and p["label"]=="HARD_BLOCKED")
                p["elapsed_seconds"]=round(time.monotonic()-start,4);stream.write(old.dump(p)+"\n");stream.flush();seen.add(rid)
                if len(seen)%10==0: print(c,len(seen),"/120",flush=True)


def load_predictions(data):
    states,base,*_=data;ph=old.sha((OUT/"protocol.json").read_bytes());tables={}
    for c in CONDITIONS:
        rows=old.unique([json.loads(x) for x in (OUT/(c+".predictions.jsonl")).read_text().splitlines()])
        if set(rows)!=set(states): raise ValueError("prediction coverage mismatch")
        for p in rows.values(): validate(p,c,ph,states,base)
        tables[c]=rows
    return tables


def score(data,details_path):
    lock(data);states,base,rules,caps,gold,counts=data;tables=load_predictions(data)
    raw={c:{rid:p["gliner_route"] for rid,p in rows.items()} for c,rows in tables.items()}
    routed={c:{rid:p["hybrid_route"] for rid,p in tables[c].items()} for c in HYBRIDS}
    metrics={c:old.metric(p,gold) for c,p in routed.items()};raw_metrics={c:old.metric(p,gold) for c,p in raw.items()}
    best=max(HYBRIDS,key=lambda c:metrics[c]["correct"]);bp=routed[best]
    residual=[rid for rid in gold if base[rid]!=gold[rid]];over=[rid for rid in gold if gold[rid]=="EXECUTE" and base[rid]=="CLARIFY"]
    missed=[rid for rid in gold if gold[rid]=="CLARIFY" and base[rid]!=gold[rid]]
    def subset(ids,c):
        return {"n":len(ids),"label_counts":dict(collections.Counter(tables[c][rid]["label"] for rid in ids)),"hybrid_correct":sum(routed[c][rid]==gold[rid] for rid in ids),"hybrid_route_counts":dict(collections.Counter(routed[c][rid] for rid in ids))}
    changed=[rid for rid in gold if bp[rid]!=base[rid]]
    paired=old.paired(base,bp,gold)
    result={"status":"exploratory frozen development-set diagnostic; best selected on this set; unadjusted exact McNemar","primary_condition":MAIN,"best_hybrid_condition":best,"hybrid_metrics":metrics,"raw_readiness_and_direct_metrics":raw_metrics,"baseline_metrics":old.metric(base,gold),"baseline_counts":{"Original_Goal_First":56,"Gate_fix":57,"Capability_repair":83,"Capability_oracle":87,"Raw_Qwen":96,"Fine_Tune":92},"paired_best_vs83":paired,"changed_count":len(changed),"fixed":paired["second_only_correct"],"regressions":paired["first_only_correct"],"net":metrics[best]["correct"]-83,"changed_only":{"both_correct":0,"baseline_only":sum(base[rid]==gold[rid] and bp[rid]!=gold[rid] for rid in changed),"hybrid_only":sum(base[rid]!=gold[rid] and bp[rid]==gold[rid] for rid in changed),"both_wrong":sum(base[rid]!=gold[rid] and bp[rid]!=gold[rid] for rid in changed)},"residual37":{c:subset(residual,c) for c in HYBRIDS},"overclarified26":{c:subset(over,c) for c in HYBRIDS},"missed_clarify7":{c:subset(missed,c) for c in HYBRIDS},"risk_D_first_E_second":old.paired(routed["D_full_without_risk"],routed["E_full_with_risk"],gold),"overclarified26_risk_transitions":[{"record_id":rid,"without_risk":tables["D_full_without_risk"][rid]["label"],"with_risk":tables["E_full_with_risk"][rid]["label"]} for rid in over],"gate_disagreements":{c:sum(p["gate_disagreement"] for p in tables[c].values()) for c in HYBRIDS},"unsupported_hard_blocks":{c:sum(p["unsupported_hard_block"] for p in tables[c].values()) for c in HYBRIDS},"failures":{c:sum(p["failed"] for p in rows.values()) for c,rows in tables.items()}}
    direct_control={rid:hybrid({"EXECUTE":"ACTION_READY","CLARIFY":"ACTION_BLOCKING_AMBIGUITY","REFUSE":"HARD_BLOCKED"}.get(p["label"]),base[rid],p["failed"])[0] for rid,p in tables[CONDITIONS[-1]].items()}
    always_ready={rid:hybrid("ACTION_READY",base[rid])[0] for rid in gold}
    result["derived_controls"]={"direct_with_identical_gate":old.metric(direct_control,gold),"always_ready_with_identical_gate":old.metric(always_ready,gold),"best_vs_direct_with_gate":old.paired(direct_control,bp,gold),"best_vs_always_ready_with_gate":old.paired(always_ready,bp,gold)}
    # Reverify matched Raw/FT context rather than assigning remembered numbers.
    import zipfile
    old.verify(old.BASE_ZIP,old.EXPECTED[old.BASE_ZIP])
    with zipfile.ZipFile(old.BASE_ZIP) as z: raw_base=z.read(old.BASE_MEMBER)
    if old.sha(raw_base)!=old.BASE_SHA: raise ValueError("matched baseline member mismatch")
    baseline_rows=old.unique(list(csv.DictReader(io.StringIO(raw_base.decode()))))
    for field,expected in [("raw_route",96),("ft_route",92)]:
        if sum(old.norm(r[field])==gold[rid] for rid,r in baseline_rows.items())!=expected: raise ValueError("matched baseline mismatch")
    old.write_json(OUT/"metrics.json",result)
    ledger=[];details=[]
    for rid in sorted(gold):
        r={"record_id":rid,"gold_route":gold[rid],"baseline83_route":base[rid],"best_hybrid_route":bp[rid],"changed":rid in changed,"baseline_correct":base[rid]==gold[rid],"hybrid_correct":bp[rid]==gold[rid],"fixed":base[rid]!=gold[rid] and bp[rid]==gold[rid],"regressed":base[rid]==gold[rid] and bp[rid]!=gold[rid],"capability_after_repair":caps[rid],"risk":states[rid]["risk_level"],"case_record":"../cases/"+rid+".json","semantic_artifact_member":old.GF_MEMBER,"semantic_artifact_sha256":old.GF_SHA,"unresolved_slot_names":[s["slot_name"] for s in states[rid]["unresolved_slots"]],"ambiguity_types":states[rid]["ambiguity_types"],"operational_missing_variable_posthoc":GOLD_C_DIAGNOSTICS.get(rid),"conditions":{c:{"label":tables[c][rid]["label"],"raw_route":raw[c][rid],"hybrid_route":routed[c][rid] if c in HYBRIDS else None} for c in CONDITIONS}}
        ledger.append(r)
        if rid in residual:
            details.append({**r,"goal_first_intent_summary":states[rid]["intent_summary"],"unresolved_slots":states[rid]["unresolved_slots"],"semantic_representation":states[rid],"diagnostic_note":"Posthoc source-context diagnostic categories did not enter model inputs."})
    def jsonl(name,rows): (OUT/name).write_text("".join(old.dump(r)+"\n" for r in rows),encoding="utf-8",newline="\n")
    jsonl("case_ledger.jsonl",ledger);jsonl("changed_case_ledger.jsonl",[r for r in ledger if r["changed"]]);jsonl("residual37.jsonl",[r for r in ledger if r["record_id"] in residual]);jsonl("missed_clarify7.jsonl",[r for r in ledger if r["record_id"] in missed])
    old.write_json(OUT/"failed_rows.json",[{"condition":c,"record_id":rid,"error_class":p.get("error_class")} for c,rows in tables.items() for rid,p in rows.items() if p["failed"]])
    details_path.parent.mkdir(parents=True,exist_ok=True);old.write_json(details_path,details)
    print(json.dumps({"best":best,"hybrid_scores":{c:m["correct"] for c,m in metrics.items()},"direct":raw_metrics[CONDITIONS[-1]]["correct"],"fixed":result["fixed"],"regressions":result["regressions"],"net":result["net"],"details":str(details_path)},indent=2),flush=True)


def main():
    if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    p=argparse.ArgumentParser();p.add_argument("mode",choices=["prepare","run","score","hash"]);p.add_argument("--model-dir",type=Path,default=ROOT/"outputs/model_runs/gliner25_decide/model");p.add_argument("--details-path",type=Path,default=ROOT/"outputs/model_runs/gliner25_decide/action_readiness_repair_v1/residual37_full_details.json");args=p.parse_args()
    if args.mode=="hash":
        old.write_json(OUT/"SHA256_FINAL.json",{x.relative_to(ROOT).as_posix():old.sha(x.read_bytes()) for x in sorted(OUT.glob("*")) if x.is_file() and x.name!="SHA256_FINAL.json"});return
    data=reconstruct()
    if args.mode=="prepare": lock(data)
    elif args.mode=="run": run(data,args.model_dir)
    else: score(data,args.details_path)


if __name__=="__main__": main()
