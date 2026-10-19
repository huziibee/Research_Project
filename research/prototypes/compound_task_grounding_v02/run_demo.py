"""CLI for model-authored semantic fixtures.

Usage: python run_demo.py CA-0608
       python run_demo.py CA-0608 --answer quantity_ml=20
       python run_demo.py --all
"""
import argparse
import json
from pathlib import Path
from compound_manager import resolve, apply_answer

EXAMPLES=Path(__file__).parent / "examples"


def run(case_id, answer):
    path=EXAMPLES/(case_id + ".json")
    spec=json.loads(path.read_text(encoding="utf-8"))
    initial=resolve(spec)
    state=spec
    for item in answer:
        k,sep,v=item.partition("=")
        if not sep: raise ValueError("expected variable=value")
        opts=[o["value"] for o in state["variables"][k]["options"]]
        match=[o for o in opts if str(o)==v]
        if not match: raise ValueError(f"unknown option {k}={v}, choose {opts}")
        state=apply_answer(state,k,match[0])
    final=resolve(state)
    return {"case":case_id,"initial":initial,"after_answer":final if answer else None}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("case",nargs="?",default="CA-0608")
    parser.add_argument("--all",action="store_true")
    parser.add_argument("--answer",action="append",default=[])
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if args.all and args.answer: raise ValueError("--all cannot be combined with --answer")
    ids=[p.stem for p in sorted(EXAMPLES.glob("CA-*.json"))]+["SYN-DEPENDENT-001"] if args.all else [args.case]
    results=[run(case,args.answer) for case in ids]
    data=json.dumps(results,indent=2,ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(exist_ok=True,parents=True)
        args.output.write_text(data+"\n",encoding="utf-8")
    print(data)

if __name__=="__main__": main()