import csv, json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'pilot120_t41_complete_closure'
G={x['record_id']:x for x in (json.loads(line) for line in (OUT/'final_t41'/'pilot120_interpretation_gold_final.jsonl').read_text(encoding='utf8').splitlines() if line.strip())}

def rows(path): return {x['record_id']:x for x in (json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line.strip())}
def main():
    for name in ['degree_based_router','full_type_risk_aware_manager','context_blind_manager']:
        p=ROOT/'review_bundles'/'pilot120_t39_20260902'/'cluster_outputs'/'R1'/'manager'/'predictions'/f'{name}.predictions.jsonl'
        rs=rows(p); out=[]
        for rid,r in rs.items():
            gg=G[rid]['gold']; a=(r.get('parsed') or {}).get('analysis') or {}; pred_cpc={k:v.get('value') for k,v in (a.get('cpc') or {}).items() if isinstance(v,dict) and v.get('value') is not None}
            route=r.get('terminal_strategy'); clar=gg['clarification']['required']; reject=gg['rejection']['required']; reason=(r.get('parsed') or {}).get('rejection_reason') or a.get('rejection_reason')
            out.append({'record_id':rid,'system_id':name,'intent_gold':gg['intent']['label'],'intent_pred':a.get('speech_act'),'intent_correct':a.get('speech_act')==gg['intent']['label'],'gold_cpc_slots':json.dumps(gg['cpc']['slots'],sort_keys=True),'pred_cpc_slots':json.dumps(pred_cpc,sort_keys=True),'cpc_exact':pred_cpc==gg['cpc']['slots'],'candidate_gold_count':len(gg['candidate_set']),'candidate_pred_count':len(a.get('candidate_interpretations') or []),'selected_gold':bool(gg['candidate_set']) and not clar,'selected_pred':bool(a.get('selected_interpretation')),'resolution_gold_slots':json.dumps(gg['resolution'].get('values') or {},sort_keys=True),'resolution_pred_slots':json.dumps(r.get('resolved_slots') or {},sort_keys=True),'resolution_evidence_gold':bool(gg['resolution'].get('evidence_spans')),'resolution_evidence_pred':bool(a.get('resolution_evidence')),'silent_case':gg['silent_resolution']['permitted'],'silent_value_correct':False,'silent_evidence_present':False,'silent_downstream_strategy_correct':False,'clarification_case':clar,'clarification_route_correct':route=='clarify' if clar else None,'clarification_target_hit':None,'clarification_clean':None,'rejection_case':reject,'rejection_route_correct':route=='face_preserving_rejection' if reject else None,'rejection_reason_pred':reason,'rejection_reason_correct':False})
        with (OUT/'scoring'/f'{name}_complete_row_scores.csv').open('w',newline='',encoding='utf8') as f:
            w=csv.DictWriter(f,fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    detail=json.loads((OUT/'scoring'/'T41_METRICS_DETAIL.json').read_text(encoding='utf8'))
    detail['required_metric_status']={'selected_interpretation':'0/120 emitted by every frozen manager; correctness not computable beyond empty emission','resolved_slot_precision_recall_f1':'0 TP, 0 FP, gold support 564, recall 0; precision/F1 undefined','evidence_correctness':'0/120 evidence emitted; correctness not computable','clarification_semantic_content':'row-level targets preserved; semantic correctness requires the packaged gold rubric and is not inferred from literal strings','rejection_reason_breakdown':'full manager route+reason 7/21; degree/context-blind 0/21'}
    (OUT/'scoring'/'T41_METRICS_DETAIL.json').write_text(json.dumps(detail,indent=2,ensure_ascii=False,sort_keys=True)+'\n',encoding='utf8')
if __name__=='__main__': main()
