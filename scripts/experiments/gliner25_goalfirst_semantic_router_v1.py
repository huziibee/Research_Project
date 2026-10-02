"""Frozen Goal-First semantics -> GLiNER routing; exploratory, no source packets.

prepare locks the protocol before inference; run resumes only the identical protocol;
score loads annotations only after every inference condition has 120 unique rows.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import importlib.metadata
import io
import json
import math
import platform
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/pilot120/gliner25_goalfirst_semantic_router_v1"
GF_ZIP = ROOT / "research/pilot120/artifacts/p120_full_analysis_20260923.zip"
GF_MEMBER = "temperature_ablation_existing/T0.7/predictions/goal_first_manager_v2.predictions.jsonl"
GF_SHA = "e6cb2070aa56c566f955ce064775ffaac489a82962135ee69445b6e53182f258"
BASE_ZIP = ROOT / "research/pilot120/artifacts/t07_matched_baseline_completion_20260927_FINAL.zip"
BASE_MEMBER = "t07_matched_baseline_completion_20260922/17_t07_case_level_comparison.csv"
BASE_SHA = "f1e013cc6a6f70b9b58da390d704c48ee41f05c57b12b6dec23affbc8c9c3ddc"
GOLD = ROOT / "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl"
CAP = ROOT / "research/pilot120/capability_intervention/sprint_rescue_summary.json"
MODEL_MANIFEST = ROOT / "research/pilot120/gliner25_decide_capability_probe_v1/model_snapshot_sha256.json"
MODEL_REVISION = "5a7adf72a23b4d311abae6ce050d7f0012bb3416"
MODEL_ID = "fastino/GLiNER2.5-Decide"
EXPECTED = {
    GF_ZIP: "0305b1e9ab062876ee6ee89778cc6028d2eaf01718b7dd0295944e7d9cb81a01",
    BASE_ZIP: "34ca50e034ca37b617068bb50c734d12fa26282fb5eec563c11ead700163e491",
    GOLD: "5e23ad1a92ff1873c8f039a8ce560a111dd6fb6b8ae8c11d6cf34dbfa1c360db",
    CAP: "af2acdb8fb87f2005159504d074ba94fb79b681f88d9f9c0aa7534112a7a8588",
    MODEL_MANIFEST: "77e7c87764194fca2336196658f6a3a2f45999c14db2160bef610a9584cb7ec5",
}
ROUTES = ["EXECUTE", "CLARIFY", "REFUSE"]
DIRECT = {
    "EXECUTE": "The semantic representation describes one sufficiently grounded concrete robot action, and there is no hard capability, authorization, prohibition, or unacceptable safety blocker.",
    "CLARIFY": "The requested job is understood, but the semantic representation still contains unresolved decision-relevant information such that different plausible values would lead to different concrete actions.",
    "REFUSE": "The requested job is understood and sufficiently specified, but execution is blocked by a genuine capability, authorization, prohibition, or unacceptable safety constraint.",
}
READINESS = {
    "ACTION_READY": "One concrete action is sufficiently grounded.",
    "ACTION_BLOCKING_AMBIGUITY": "An unresolved variable has multiple plausible values that would lead to materially different concrete robot actions.",
    "HARD_BLOCKED": "The task is sufficiently grounded, but capability, authorization, prohibition, or unacceptable safety blocks execution.",
}
READY_MAP = dict(zip(READINESS, ROUTES))
SLOTS = ["action", "actor", "object", "object_attributes", "destination", "spatial_relation", "quantity", "time", "recipient", "tool", "conditions", "constraints", "negation"]
GROUND = ["unresolved_slots", "ambiguity_types"]
EXTRA = ["ambiguity_present", "primary_ambiguity_type", "compound_ambiguity", "compound_ambiguity_count", "resolved_slots", "context_sampling_uncertainty", "candidate_interpretations", "selected_interpretation", "supporting_evidence", "resolution_evidence", "resolution_method", "unsupported_specificity"]
FIELDS = {
    "A_intent_only": ["intent_summary"],
    "B_intent_grounding": ["intent_summary"] + GROUND,
    "C_intent_task_slots": ["intent_summary", "speech_act", "cpc"],
    "D_grounding_capability": ["intent_summary", "speech_act", "cpc"] + GROUND + ["capability_status"],
    "E_full_without_risk": ["intent_summary", "speech_act", "cpc"] + GROUND + ["capability_status"] + EXTRA,
    "F_full": ["intent_summary", "speech_act", "cpc"] + GROUND + ["capability_status"] + EXTRA + ["risk_level", "risk_relevant"],
}
CONDITIONS = list(FIELDS) + ["G_action_readiness_full"]
EXCLUDED = ["recommended_strategy", "rejection_reason", "strategy_sequence", "clarification_question", "clarification_targets", "analysis_provenance"]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def verify(path, expected):
    actual = sha(path.read_bytes())
    if actual != expected:
        raise ValueError(f"hash mismatch: {path}")


def unique(rows):
    result = {r["record_id"]: r for r in rows}
    if len(rows) != 120 or len(result) != 120:
        raise ValueError("requires exactly 120 unique records")
    return result


def frozen():
    verify(GF_ZIP, EXPECTED[GF_ZIP])
    with zipfile.ZipFile(GF_ZIP) as z:
        raw = z.read(GF_MEMBER)
    if sha(raw) != GF_SHA:
        raise ValueError("GF member mismatch")
    rows = unique([json.loads(line) for line in raw.splitlines()])
    for r in rows.values():
        a = r["parsed"]["analysis"]
        if a["intent_summary"] != r["intent_summary"] or set(a["cpc"]) != set(SLOTS):
            raise ValueError("unexpected frozen semantic structure")
    return rows


def render(a, condition):
    """Only allowlisted analysis values; never outer predictions or raw_output.

    Empty and null saved values are retained, not fabricated. CPC keeps both
    status and value. Semantic findings are individually allowlisted; all
    router_validation findings are excluded, regardless of their content.
    """
    if condition == "G_action_readiness_full":
        condition = "F_full"
    if condition == "A_intent_only":
        return a["intent_summary"]
    chunks = []
    for field in FIELDS[condition]:
        if field not in a:
            continue
        if field == "cpc":
            for slot in SLOTS:
                if slot in a[field]:
                    chunks.append(slot.replace("_", " ").title() + ":\n" + dump(a[field][slot]))
        else:
            value = a[field]
            chunks.append(field.replace("_", " ").title() + ":\n" + (value if isinstance(value, str) else dump(value)))
    if condition in ("D_grounding_capability", "E_full_without_risk", "F_full"):
        allowed = ["pilot_capability_status:"]
        if condition in ("E_full_without_risk", "F_full"):
            allowed.append("pilot_ambiguity_types:")
        findings = [s for s in a.get("findings", []) if any(s.startswith(p) for p in allowed)]
        if findings:
            chunks.append("Semantic findings:\n" + dump(findings))
    return "\n\n".join(chunks)


def protocol(rows):
    return {
        "experiment": "gliner25_goalfirst_semantic_router_v1", "status": "exploratory development-set diagnostic",
        "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
        "input_archive": GF_ZIP.relative_to(ROOT).as_posix(), "input_member": GF_MEMBER, "input_sha256": GF_SHA,
        "frozen_file_hashes": {p.relative_to(ROOT).as_posix(): h for p,h in EXPECTED.items()},
        "baseline_member": BASE_MEMBER, "baseline_member_sha256": BASE_SHA,
        "renderer_code_sha256": sha(Path(__file__).read_bytes()), "renderer_fields": FIELDS,
        "slot_order": SLOTS, "excluded_analysis_fields": EXCLUDED,
        "findings_policy": "Only pilot_capability_status: in D/E/F and pilot_ambiguity_types: in E/F. Exclude router_validation and all other findings.",
        "route_labels": DIRECT, "readiness_labels": READINESS, "readiness_mapping": READY_MAP,
        "classification": "single-label argmax; no threshold tuning; failed rows remain wrong in denominator",
        "condition_order": CONDITIONS, "primary_condition": "F_full",
        "best_rule": "Maximum direct-route accuracy across A-F; tie broken by listed order. Exploratory selection, not a held-out estimate.",
        "input_hashes": {c: {rid: sha(render(r["parsed"]["analysis"], c).encode()) for rid,r in sorted(rows.items())} for c in CONDITIONS},
    }


def prepare(rows):
    OUT.mkdir(parents=True, exist_ok=True)
    p = protocol(rows)
    target = OUT / "protocol.json"
    if target.exists() and json.loads(target.read_text(encoding="utf-8")) != p:
        raise ValueError("protocol already locked; use a new version for changes")
    if not target.exists():
        write_json(target, p)
    analyses = [r["parsed"]["analysis"] for r in rows.values()]
    audit = {
        "record_count": len(rows), "unique_ids": len(rows), "system_versions": dict(collections.Counter(r["system_version"] for r in rows.values())),
        "model_ids": dict(collections.Counter(r["model_id"] for r in rows.values())),
        "semantic_field_coverage": {k: {"present": sum(k in a for a in analyses), "nonempty": sum(bool(a.get(k)) for a in analyses)} for k in sorted(analyses[0])},
        "original_failed_rows": [rid for rid,r in rows.items() if r.get("failed")],
        "uncertainty_field": "context_sampling_uncertainty (score, agreement, variant_count); no invented uncertainty_score",
        "source_packet_read": False, "outer_prediction_rendered": False,
    }
    write_json(OUT / "input_audit.json", audit)
    print("PROTOCOL_LOCKED", sha(target.read_bytes()), flush=True)


def run(rows, model_dir):
    prepare(rows)
    verify(MODEL_MANIFEST, EXPECTED[MODEL_MANIFEST])
    manifest = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    if manifest["revision"] != MODEL_REVISION or manifest["model_id"] != MODEL_ID:
        raise ValueError("wrong model identity")
    for name, h in manifest["files"].items():
        verify(model_dir / name, h)
    import torch
    from gliner2 import AutoExtractor
    torch.set_num_threads(4)
    model = AutoExtractor.from_pretrained(str(model_dir))
    protocol_hash = sha((OUT / "protocol.json").read_bytes())
    versions = {p: importlib.metadata.version(p) for p in ["gliner2", "torch", "transformers", "huggingface-hub", "tokenizers", "numpy"]}
    write_json(OUT / "runtime.json", {"python": platform.python_version(), "packages": versions, "device": "cpu", "threads": 4, "platform": platform.platform(), "model_files": manifest})
    for condition in CONDITIONS:
        path = OUT / (condition + ".predictions.jsonl")
        previous = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
        seen = set()
        for p in previous:
            rid = p["record_id"]
            if rid not in rows or rid in seen or p["input_sha256"] != sha(render(rows[rid]["parsed"]["analysis"],condition).encode()):
                raise ValueError("invalid resume predictions")
            seen.add(rid)
            validate_prediction(p, condition, protocol_hash)
        labels = READINESS if condition.startswith("G_") else DIRECT
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            for rid,r in sorted(rows.items()):
                if rid in seen:
                    continue
                text = render(r["parsed"]["analysis"], condition)
                pred = {"record_id": rid, "condition": condition, "protocol_sha256": protocol_hash, "input_sha256": sha(text.encode()), "failed": False}
                start = time.monotonic()
                try:
                    result = model.classify_text(text, {"decision": {"labels": labels}}, include_confidence=True)["decision"]
                    label = result["label"]
                    if label not in labels:
                        raise ValueError("out-of-schema decision")
                    pred.update(label=label, route=READY_MAP[label] if condition.startswith("G_") else label, confidence=result["confidence"])
                except Exception as e:
                    # Do not serialize exception messages: they may contain input text.
                    pred.update(failed=True, label=None, route="FAILED", error_class=type(e).__name__)
                pred["elapsed_seconds"] = round(time.monotonic()-start, 4)
                stream.write(dump(pred) + "\n")
                stream.flush()
                seen.add(rid)
                if len(seen) % 10 == 0:
                    print(condition, len(seen), "/120", flush=True)


def norm(route):
    return "REFUSE" if route.lower() in ("refuse", "face_preserving_rejection", "reject") else route.upper()


def validate_prediction(p, condition, protocol_hash):
    if p["condition"] != condition or p["protocol_sha256"] != protocol_hash:
        raise ValueError("prediction protocol identity mismatch")
    if p["failed"]:
        if p["route"] != "FAILED" or p["label"] is not None:
            raise ValueError("inconsistent failed row")
    else:
        labels = READINESS if condition.startswith("G_") else DIRECT
        if p["label"] not in labels or p["route"] != (READY_MAP[p["label"]] if condition.startswith("G_") else p["label"]):
            raise ValueError("inconsistent successful row")


def metric(pred, gold):
    confusion = {g: {p: 0 for p in ROUTES + ["FAILED"]} for g in ROUTES}
    for rid in gold:
        confusion[gold[rid]][pred[rid]] += 1
    classes = {}
    for c in ROUTES:
        tp = confusion[c][c]
        fp = sum(confusion[g][c] for g in ROUTES if g != c)
        fn = sum(confusion[c].values()) - tp
        precision = tp / (tp+fp) if tp+fp else 0
        recall = tp / (tp+fn)
        classes[c] = {"precision": precision, "recall": recall, "f1": 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0, "support": tp+fn}
    correct = sum(confusion[c][c] for c in ROUTES)
    return {"n": 120, "correct": correct, "accuracy": correct/120, "macro_f1": sum(x["f1"] for x in classes.values())/3, "per_class": classes, "confusion": confusion, "required_refusal_false_execute": confusion["REFUSE"]["EXECUTE"], "failed": sum(confusion[c]["FAILED"] for c in ROUTES)}


def paired(a, b, gold):
    counts = collections.Counter((a[rid] == gold[rid], b[rid] == gold[rid]) for rid in gold)
    x, y = counts[True,False], counts[False,True]
    n = x+y
    p = min(1, 2*sum(math.comb(n,k) for k in range(min(x,y)+1))/2**n) if n else 1.0
    return {"both_correct": counts[True,True], "first_only_correct": x, "second_only_correct": y, "both_wrong": counts[False,False], "exact_mcnemar_two_sided_p": p, "discordant": n}


def cohort(ids, pred, gold):
    fixed = sum(pred[rid] == gold[rid] for rid in ids)
    return {"n": len(ids), "correct": fixed, "wrong": len(ids)-fixed, "predicted_route_distribution": dict(collections.Counter(pred[rid] for rid in ids)), "ids": sorted(ids)}


def score(rows):
    prepare(rows)
    predictions = {}
    protocol_hash = sha((OUT / "protocol.json").read_bytes())
    for c in CONDITIONS:
        records = unique([json.loads(x) for x in (OUT / (c+".predictions.jsonl")).read_text(encoding="utf-8").splitlines()])
        if set(records) != set(rows):
            raise ValueError("prediction ID mismatch")
        for rid,p in records.items():
            validate_prediction(p,c,protocol_hash)
            if p["input_sha256"] != sha(render(rows[rid]["parsed"]["analysis"],c).encode()):
                raise ValueError("scoring input hash mismatch")
        predictions[c] = {rid:p["route"] for rid,p in records.items()}
    for path in (GOLD, CAP, BASE_ZIP):
        verify(path, EXPECTED[path])
    gold_records = unique([json.loads(x) for x in GOLD.read_bytes().splitlines()])
    gold = {rid:norm(r["terminal_strategy"]) for rid,r in gold_records.items()}
    with zipfile.ZipFile(BASE_ZIP) as z:
        raw = z.read(BASE_MEMBER)
    if sha(raw) != BASE_SHA:
        raise ValueError("baseline member mismatch")
    baseline_rows = unique(list(csv.DictReader(io.StringIO(raw.decode()))))
    if set(gold) != set(rows) or set(baseline_rows) != set(gold):
        raise ValueError("gold/baseline/GF IDs differ")
    baseline = {name: {rid:norm(r[field]) for rid,r in baseline_rows.items()} for name,field in [("Goal_First_original","gf_route"),("Raw_Qwen","raw_route"),("Fine_Tune","ft_route")]}
    if any(baseline["Goal_First_original"][rid] != norm(rows[rid]["terminal_strategy"]) for rid in rows):
        raise ValueError("GF baseline does not match semantic artifact")
    for rid,r in baseline_rows.items():
        if norm(r["gold_route"]) != gold[rid]:
            raise ValueError("baseline gold mismatch")
    # Saved per-case correctness is sufficient for paired accuracy. No model or
    # updated routing code is rerun to manufacture a historical baseline.
    cap = json.loads(CAP.read_text(encoding="utf-8"))
    cap_ok = {}
    for name,key in [("Post_capability","llm_patch_capability_current_router"),("Capability_oracle","oracle_gold_capability_current_router")]:
        ok = cap[key]["_route_ok"]
        if set(ok) != set(gold) or not all(isinstance(v,bool) for v in ok.values()):
            raise ValueError("invalid saved capability correctness")
        cap_ok[name] = ok
    counts = {k:sum(v[rid]==gold[rid] for rid in gold) for k,v in baseline.items()}
    counts.update({k:sum(v.values()) for k,v in cap_ok.items()})
    if counts != {"Goal_First_original":56,"Raw_Qwen":96,"Fine_Tune":92,"Post_capability":83,"Capability_oracle":87}:
        raise ValueError(f"baseline counts mismatch: {counts}")
    intent_ok = {rid:r["gf_official_intent"] == "True" for rid,r in baseline_rows.items()}
    ids63 = [rid for rid in gold if intent_ok[rid] and baseline["Goal_First_original"][rid] != gold[rid]]
    if sum(intent_ok.values()) != 117 or len(ids63) != 63:
        raise ValueError("intent cohort mismatch")
    metrics = {c:metric(p,gold) for c,p in predictions.items()}
    best = max(FIELDS, key=lambda c:metrics[c]["correct"])
    bp = predictions[best]
    pair83 = paired({rid:"YES" if cap_ok["Post_capability"][rid] else "NO" for rid in gold}, {rid:"YES" if bp[rid]==gold[rid] else "NO" for rid in gold}, {rid:"YES" for rid in gold})
    false_refusal_ids = [rid for rid in gold if gold[rid] != "REFUSE" and baseline["Goal_First_original"][rid] == "REFUSE"]
    result = {
        "scientific_status": "exploratory; Pilot-120 informed development; best condition selected on this set; no confirmatory multiplicity-adjusted significance",
        "best_direct_condition": best, "primary_condition": "F_full", "metrics": metrics, "baselines_correct": counts,
        "best_vs_original": paired(baseline["Goal_First_original"],bp,gold), "best_vs_post_capability": pair83,
        "intent_correct_route_wrong": cohort(ids63,bp,gold),
        "gold_clarify": cohort([rid for rid in gold if gold[rid]=="CLARIFY"],bp,gold),
        "gold_refuse": cohort([rid for rid in gold if gold[rid]=="REFUSE"],bp,gold),
        "original_false_refusals": cohort(false_refusal_ids,bp,gold),
        "risk_E_first_F_second": paired(predictions["E_full_without_risk"],predictions["F_full"],gold),
        "direct_F_first_readiness_G_second": paired(predictions["F_full"],predictions["G_action_readiness_full"],gold),
        "cohort_provenance": "FINAL 17_t07_case_level_comparison.csv two-judge intent-positive cohort; 117 is not independently human-validated official correctness",
        "older_sprint_cohort_discrepancy": "older sprint cohort substitutes CA-0878 for CA-0845; final matched cohort used",
    }
    write_json(OUT / "metrics.json", result)
    ledger = []
    for rid in sorted(gold):
        ledger.append({"record_id":rid,"gold_route":gold[rid],"goal_first_route":baseline["Goal_First_original"][rid],"goal_first_intent_positive":intent_ok[rid],"post_capability_correct":cap_ok["Post_capability"][rid],"capability_oracle_correct":cap_ok["Capability_oracle"][rid],**{c:predictions[c][rid] for c in CONDITIONS}})
    (OUT / "paired_case_ledger.jsonl").write_text("".join(dump(r)+"\n" for r in ledger), encoding="utf-8")
    write_json(OUT / "failed_rows.json", [{"condition":c,"record_id":rid} for c,p in predictions.items() for rid,v in p.items() if v=="FAILED"])
    print(json.dumps({"best":best,"correct":metrics[best]["correct"],"macro_f1":metrics[best]["macro_f1"],"all":{c:m["correct"] for c,m in metrics.items()}},indent=2),flush=True)


def main():
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["prepare","run","score","hash"])
    p.add_argument("--model-dir", type=Path, default=ROOT/"outputs/model_runs/gliner25_decide/model")
    args = p.parse_args()
    if args.mode == "hash":
        write_json(OUT / "SHA256_FINAL.json", {x.relative_to(ROOT).as_posix():sha(x.read_bytes()) for x in sorted(OUT.glob("*")) if x.is_file() and x.name != "SHA256_FINAL.json"})
        return
    rows = frozen()
    if args.mode == "prepare": prepare(rows)
    elif args.mode == "run": run(rows,args.model_dir)
    else: score(rows)


if __name__ == "__main__":
    main()
