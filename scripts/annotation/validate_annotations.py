"""Validate A01 schemas and semantic invariants without repairing records."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from jsonschema import Draft202012Validator
def load(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def validate_annotation(a):
    errors=[]
    p=a.get("parsed_annotation") or a if isinstance(a, dict) else a
    if not isinstance(p, dict):
        return ["parsed_annotation_must_be_object_or_null"]
    types=p.get("ambiguity_types",[])
    if p.get("ambiguity_present") is False and types: errors.append("ambiguity_present_false_requires_empty_types")
    if p.get("compound_ambiguity") is True and len(set(types))<2: errors.append("compound_requires_two_types")
    if p.get("compound_ambiguity") is True and p.get("compound_ambiguity_count")!=len(set(types)): errors.append("compound_count_mismatch")
    if p.get("recommended_strategy")=="execute" and any(p.get(k) in {"unknown","unresolved"} for k in ("capability_status","risk_level")): errors.append("execute_with_critical_unknown")
    if p.get("capability_status")=="incapable" and p.get("recommended_strategy")=="execute": errors.append("incapable_execute")
    if p.get("recommended_strategy")=="transparent_rejection" and not p.get("rejection_explanation"): errors.append("rejection_requires_reason")
    if p.get("recommended_strategy")=="clarify" and not (p.get("clarification_question") or p.get("clarification_target")): errors.append("clarification_requires_target")
    return errors
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--schema",required=True); ap.add_argument("--input",required=True); a=ap.parse_args(); validator=Draft202012Validator(load(a.schema)); errors=[]
    for n,line in enumerate(Path(a.input).read_text(encoding="utf-8").splitlines(),1):
        if not line.strip(): continue
        item=json.loads(line); errors += [f"line {n}: schema: {e.message}" for e in validator.iter_errors(item)]; errors += [f"line {n}: semantic: {e}" for e in validate_annotation(item.get('parsed_annotation') or item)]
    for error in errors: print(error)
    return 1 if errors else 0
if __name__=="__main__": raise SystemExit(main())
