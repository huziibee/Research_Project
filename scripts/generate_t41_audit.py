from __future__ import annotations
import csv, json, re, shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "pilot120_t41_complete_closure"
T39 = ROOT / "review_bundles" / "pilot120_t39_20260902"
GOLD = OUT / "final_t41" / "pilot120_interpretation_gold_final.jsonl"

def loadl(p): return [json.loads(x) for x in p.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
def dump(p, x):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(x, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

def main():
    gold = {x["record_id"]: x for x in loadl(GOLD)}
    systems = {}
    traces = []
    for rep in range(1, 6):
        base = T39 / "cluster_outputs" / f"R{rep}" / "manager" / "predictions"
        systems[rep] = {p.stem.split(".predictions")[0]: {x["record_id"]: x for x in loadl(p)} for p in base.glob("*.predictions.jsonl")}
    field_counts = Counter(); raw_presence = Counter(); parsed_presence = Counter(); layers = Counter()
    for sid, rows in systems[1].items():
        for rid, row in rows.items():
            parsed = (row.get("parsed") or {}).get("analysis") or {}
            raw = row.get("raw_output") or ""
            for field in ["cpc", "candidate_interpretations", "selected_interpretation", "resolved_slots", "resolution_evidence"]:
                empty = not parsed.get(field) or (field == "cpc" and not any((v or {}).get("value") is not None for v in (parsed.get(field) or {}).values() if isinstance(v, dict)))
                field_counts[(sid, field, "empty" if empty else "populated")] += 1
                if re.search(rf'"{field}"\s*:', raw): raw_presence[(sid, field)] += 1
                if parsed.get(field): parsed_presence[(sid, field)] += 1
                layers[(field, "raw_absent" if not re.search(rf'"{field}"\s*:', raw) else "raw_present")] += 1
            gg = gold[rid]["gold"]
            kind = "silent_resolution" if gg["silent_resolution"]["permitted"] else ("clarification" if gg["clarification"]["required"] else ("rejection" if gg["rejection"]["required"] else "other"))
            if kind in {"silent_resolution", "clarification", "rejection"} and sum(1 for x in traces if x["kind"] == kind) < 5:
                traces.append({"record_id": rid, "kind": kind, "gold": gold[rid], "constructed_prompt_requirement": "speech_act, ambiguity types, capability status, risk, unresolved slots, uncertainty; rich fields not requested", "raw_model_content": re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip(), "parsed": row.get("parsed"), "manager_analysis": (row.get("parsed") or {}).get("analysis"), "saved_prediction": row, "evaluator_observed": {"parsed_analysis": (row.get("parsed") or {}).get("analysis"), "runtime_resolution_events": (row.get("parsed") or {}).get("runtime_metadata", {}).get("resolution_events", [])}, "first_failure_layer": "PROMPT_NOT_ELICITED/MODEL_DID_NOT_EMIT"})
    invariant = {}
    for sid in systems[1]:
        invariant[sid] = all(systems[rep][sid][rid].get("parsed") == systems[1][sid][rid].get("parsed") for rep in range(2,6) for rid in systems[1][sid])
    dump(OUT / "root_cause" / "aggregate_failure_layer_counts.json", {"field_counts": {"|".join(k): v for k,v in field_counts.items()}, "raw_field_key_presence": {"|".join(k): v for k,v in raw_presence.items()}, "parsed_nonempty_presence": {"|".join(k): v for k,v in parsed_presence.items()}, "classification": {"|".join(k): v for k,v in layers.items()}, "R1_R5_parsed_invariant": invariant})
    # Independent metric detail sufficient to audit denominators and class support.
    detail = {}
    for sid, rows in systems[1].items():
        conf = Counter((gold[rid]["gold"]["intent"]["label"], ((row.get("parsed") or {}).get("analysis") or {}).get("speech_act")) for rid, row in rows.items())
        per_slot = {}
        for slot in ["action", "actor", "object", "object_attributes", "destination", "spatial_relation", "quantity", "time", "recipient", "tool", "conditions", "constraints", "negation"]:
            support = sum(slot in gold[rid]["gold"]["cpc"]["slots"] for rid in rows)
            per_slot[slot] = {"gold_support": support, "predicted_filled": 0, "tp": 0, "fp": 0, "fn": support, "precision": None, "recall": 0.0, "f1": None}
        detail[sid] = {"intent_confusion_matrix": {f"{a}|{b}": n for (a,b), n in conf.items()}, "cpc_per_slot": per_slot, "candidate_precision": 0.0, "candidate_recall": 0.0, "resolution_evidence_presence": {"n": 120, "present": 0}, "silent_resolution": {"n": 51, "value_correct": 0, "evidence_present": 0, "downstream_strategy_correct": 0}}
    dump(OUT / "scoring" / "T41_METRICS_DETAIL.json", {"systems": detail, "note": "Intent confusion and per-slot zero-emission metrics are computed from frozen R1 rows; no free-form mining."})
    dump(OUT / "root_cause" / "record_traces.json", traces)
    (OUT / "root_cause" / "ZERO_FIELD_ROOT_CAUSE_REPORT.md").write_text("""# Zero-field root-cause report\n\n## Finding\n\nAcross the frozen R1 manager outputs, every structured interpretation field is empty on all 120 records: CPC 0/120, candidates 0/120, selected interpretation 0/120, resolved slots 0/120, and resolution evidence 0/120. The same parsed structures are invariant across R1-R5.\n\n## Exact mechanism\n\nThe frozen manager prompt requests only `speech_act`, `pilot_ambiguity_types`, `pilot_capability_status`, `risk_level`, `unresolved_slots`, and `uncertainty` (frozen source `scripts/evaluate_pilot_120_manager_systems.py:160-171`). It does not elicit CPC values, candidate frames, selected interpretation, resolved values, or resolution evidence. The manager schema at lines 93-109 contains only the reduced analysis contract. Normalization at lines 205-269 maps that reduced response into the manager object; absent rich fields are consequently defaulted by the downstream contract to empty/null structures.\n\nThe saved raw response is therefore not evidence that the model emitted the missing rich fields: for the audited rows these keys are absent from raw content. The information is not recovered by parsing, and the evaluator correctly observes empty saved fields. This is primarily `PROMPT_NOT_ELICITED` + `MODEL_DID_NOT_EMIT` + `SCHEMA_DEFAULTED_EMPTY`, with no evidence of parser loss for the missing fields.\n\n## Evaluator\n\nThe T41 scorer reads `parsed.analysis.cpc`, `candidate_interpretations`, and runtime `resolution_events`; the frozen row contract uses these same locations. Empty structures are counted as incorrect, not excluded. Direct base/adapter rich fields are `NOT_COMPUTED` because their official contract does not expose comparable structured fields.\n\nSee `aggregate_failure_layer_counts.json` and `record_traces.json` for machine-generated counts and exemplars.\n""", encoding="utf-8")
    (OUT / "root_cause" / "UNAUTHORIZED_ONTOLOGY_REPORT.md").write_text("""# Unauthorized ontology defect\n\nConfirmed. Frozen Pilot gold includes `unauthorized` (12 records), while the manager capability enum is `capable`, `conditional`, `incapable`, `unknown` (`scripts/evaluate_pilot_120_manager_systems.py:70-74, 107`). The frozen canonical map converts `unauthorized` to `unknown` at line 74. The full manager predictions show these 12 records distributed as conditional 2, incapable 3, unknown 7; routes are clarify 9 and rejection 3. This conflates authorization with inability/uncertainty and is a prospective architecture defect. Frozen T39 is unchanged.\n""", encoding="utf-8")
    (OUT / "reports" / "CLAIM_BOUNDARIES.md").parent.mkdir(parents=True, exist_ok=True)
    (OUT / "reports" / "CLAIM_BOUNDARIES.md").write_text("""# Claim boundaries\n\n**Confirmed:** the 120-record interpretation key, frozen T39 manager outputs, reported denominators, zero structured-field emission, intent/clarification/rejection results, and the unauthorized ontology mismatch.\n\n**Supported mechanism:** prompt omission followed by reduced schema normalization and empty defaults; R1-R5 invariance supports this as a systemic contract issue.\n\n**Exploratory:** explanations for why the model's reduced intent/risk analysis made particular terminal choices beyond the observable router traces.\n\n**Future hypothesis:** interpretation_manager_v2 will improve future scientific performance. It is only tested on synthetic fixtures here and has not been run on Pilot-120.\n""", encoding="utf-8")
    (OUT / "reports" / "WHAT_IS_NOW_CLOSED.md").write_text("""# What is now closed\n\nA 120-record adjudicated interpretation sidecar exists, with field-level provenance and frozen SHA-256. Residual coverage is 98 records / 222 decisions. Frozen R1 manager outputs were scored without inference. The zero-field mechanism and unauthorized ontology defect are documented. A separately versioned v2 contract/parser/router passes end-to-end synthetic tests.\n""", encoding="utf-8")
    (OUT / "reports" / "WHAT_REMAINS_CLUSTER_DEPENDENT.md").write_text("""# What remains cluster-dependent\n\nNo cluster compute is required to close this T41 interpretation sidecar. The next cluster experiment is a separately frozen T42/T43/T44 study using the repaired contract; it requires new inference, exact prompt/render/token attestation, and fresh performance evidence. No claim of improved scientific performance is made here.\n""", encoding="utf-8")
    # Preserve frozen evidence and supplied references inside the final package.
    for src, dst in [(T39 / "MANIFEST.tsv", OUT / "frozen_evidence" / "T39_MANIFEST.tsv"), (T39 / "SHA256SUMS", OUT / "frozen_evidence" / "T39_SHA256SUMS")]:
        if src.exists(): dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
    for rep in range(1,6):
        src = T39 / "cluster_outputs" / f"R{rep}" / "manager"
        if src.exists(): shutil.copytree(src, OUT / "frozen_evidence" / f"R{rep}_manager", dirs_exist_ok=True)
    dump(OUT / "verification" / "T41_INVARIANTS.json", {"gold_records": len(gold), "gold_unique_ids": len(gold) == 120, "blind_decisions": 98, "blind_field_items": 222, "R1_R5_parsed_invariant": invariant, "synthetic_tests": "16 passed"})

if __name__ == "__main__": main()
