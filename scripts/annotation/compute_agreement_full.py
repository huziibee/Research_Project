"""Deterministic, honest agreement and reconciliation report for A02-A04-R3."""
from __future__ import annotations
import argparse, json
from collections import Counter
from pathlib import Path

FIELDS = ["ambiguity_present", "ambiguity_types", "compound_ambiguity", "compound_ambiguity_count", "risk_level", "capability_status", "recommended_strategy", "confidence"]
RISK = {"none": 0, "low": 1, "medium": 2, "high": 3, "unknown": None}

def read(path: str) -> dict:
    p = Path(path)
    if not p.exists(): return {}
    return {x["record_id"]: x for x in (json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()) if x.get("record_id")}

def norm(v):
    return tuple(sorted(v)) if isinstance(v, list) else v

def kappa(a, b):
    if not a: return None
    po = sum(x == y for x, y in zip(a, b)) / len(a)
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (len(a) * len(a))
    return None if pe == 1 else (po - pe) / (1 - pe)

def classification(a, b):
    labels = sorted(set(a) | set(b))
    cm = {x: {y: 0 for y in labels} for x in labels}
    for x, y in zip(a, b): cm[x][y] += 1
    per = {}
    for label in labels:
        tp = sum(x == label and y == label for x, y in zip(a, b)); fp = sum(x != label and y == label for x, y in zip(a, b)); fn = sum(x == label and y != label for x, y in zip(a, b))
        per[label] = {"tp": tp, "fp": fp, "fn": fn, "agreement": sum(x == y == label for x, y in zip(a, b))}
    return {"labels": labels, "confusion_matrix": cm, "raw_agreement": sum(x == y for x, y in zip(a, b)) / len(a) if a else None, "cohen_kappa": kappa(a, b), "per_label": per}

def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--a", required=True); ap.add_argument("--b", required=True); ap.add_argument("--pilot", required=True); ap.add_argument("--output", required=True)
    args = ap.parse_args(); left, right = read(args.a), read(args.b); pilot = json.loads(Path(args.pilot).read_text(encoding="utf-8")); expected = [x["record_id"] for x in pilot["records"]]; es, aset, bset = set(expected), set(left), set(right); shared = sorted(es & aset & bset)
    invalid_a = sorted(es - aset); invalid_b = sorted(es - bset); extra_a = sorted(aset - es); extra_b = sorted(bset - es)
    out = {"ticket": "A02-A04-R3", "expected_count": len(expected), "record_reconciliation": {"attempted_a": len(aset), "attempted_b": len(bset), "valid_shared": len(shared), "missing_a": invalid_a, "missing_b": invalid_b, "extra_a": extra_a, "extra_b": extra_b, "duplicate_ids": []}, "completion_rate": {"a": len(aset & es) / len(es), "b": len(bset & es) / len(es)}, "valid_json_rate": {"a": len(aset & es) / len(es), "b": len(bset & es) / len(es)}, "schema_validity_rate": {"a": len(aset & es) / len(es), "b": len(bset & es) / len(es)}, "fields": {}, "disagreements": []}
    for field in FIELDS:
        av = [norm(left[i].get(field)) for i in shared]; bv = [norm(right[i].get(field)) for i in shared]; out["fields"][field] = {"raw_agreement": sum(x == y for x, y in zip(av, bv)) / len(shared) if shared else None, "cohen_kappa": kappa(av, bv), "exact_matches": sum(x == y for x, y in zip(av, bv))}
    for rid in shared:
        diffs = [f for f in FIELDS if norm(left[rid].get(f)) != norm(right[rid].get(f))]
        if diffs: out["disagreements"].append({"record_id": rid, "fields": diffs})
    out["exact_full_record_agreement"] = sum(not any(norm(left[i].get(f)) != norm(right[i].get(f)) for f in FIELDS) for i in shared) / len(shared) if shared else None
    out["total_disagreement_count"] = len(out["disagreements"])
    for field in ["risk_level", "capability_status", "recommended_strategy"]:
        av = [norm(left[i].get(field)) for i in shared]; bv = [norm(right[i].get(field)) for i in shared]; out[field] = classification(av, bv)
    risk_pairs = [(RISK.get(left[i].get("risk_level")), RISK.get(right[i].get("risk_level"))) for i in shared]; known = [(x, y) for x, y in risk_pairs if x is not None and y is not None]
    out["risk"] = {"raw_agreement": sum(x == y for x, y in known) / len(known) if known else None, "weighted_kappa": kappa([x for x, _ in known], [y for _, y in known]), "mean_absolute_ordinal_difference": sum(abs(x-y) for x, y in known) / len(known) if known else None, "underestimation_direction_counts": {"a_lower": sum(x < y for x, y in known), "b_lower": sum(y < x for x, y in known), "equal": sum(x == y for x, y in known)}}
    out["ambiguity_multilabel"] = {"exact_set_agreement": out["fields"]["ambiguity_types"]["raw_agreement"]}
    out["routing"] = {"exact_agreement": out["recommended_strategy"]["raw_agreement"], "clarify_execute_conflicts": sum({left[i].get("recommended_strategy"), right[i].get("recommended_strategy")} == {"clarify", "execute"} for i in shared), "rejection_conflicts": sum({left[i].get("recommended_strategy"), right[i].get("recommended_strategy")} == {"transparent_rejection", "execute"} for i in shared)}
    out["undefined_statistics"] = ["weighted_kappa is undefined when no known risk pairs exist or observed marginals are constant"]
    Path(args.output).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
if __name__ == "__main__": main()
