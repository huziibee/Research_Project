#!/usr/bin/env bash
# Inspect existing temp emits, submit T0.3 GF ablation after 58442, pack analysis zip.
set -euo pipefail

PRIO=/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915
FC=/home-mscluster/mbangie/t12-hpc/code/final_close-20260913
T07=/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922
T07_OUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922
REC_OUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_one_turn_recovery-20260922
T03_CODE=/home-mscluster/mbangie/t12-hpc/code/pilot120_t03_gf_ablation-20260923
T03_OUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_t03_gf_ablation-20260923
EXP_T07="${T07_OUT}/t07_matched_baseline_completion_20260922"
REC="${REC_OUT}/one_turn_recovery_20260922"

echo "=== SQUEUE ==="
squeue -u mbangie
echo "=== 58442 ==="
sacct -j 58442 --format=JobID,JobName,State,Elapsed,ExitCode,End,NodeList -P

python3 - <<'PY'
import json
from pathlib import Path

def load_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows

def norm(v):
    t = str(v or "").strip().lower()
    if t in {"face_preserving_rejection", "reject", "refuse", "rejection"}:
        return "refuse"
    if t in {"clarify", "clarification", "ask"}:
        return "clarify"
    if t in {"execute", "act", "silently_resolve"}:
        return "execute"
    return t or "missing"

def content_tokens(text):
    import re
    stop = {
        "a","an","the","to","of","and","or","for","in","on","at","with","from","by",
        "is","are","be","this","that","it","as","into","then"
    }
    return {t for t in re.findall(r"[a-z0-9]+", str(text or "").lower()) if t not in stop and len(t) > 1}

def jaccard(a, b):
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def auto_pass(summary, refs, thr=0.18):
    pt = content_tokens(summary)
    best = 0.0
    for ref in refs:
        if not str(ref).strip():
            continue
        best = max(best, jaccard(pt, content_tokens(ref)))
    return best >= thr

gold = {}
for cand in [
    Path("/home-mscluster/mbangie/t12-hpc/code/final_close-20260913/data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl"),
    Path("/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922/data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl"),
]:
    if cand.exists():
        for row in load_jsonl(cand):
            gold[row["record_id"]] = row
        break

refs = {}
for cand in [
    Path("/home-mscluster/mbangie/t12-hpc/code/final_close-20260913/pilot120_intent_evaluation_20260902/pilot120_intent_evaluation_20260902/intent_gold_references_120.jsonl"),
    Path("/home-mscluster/mbangie/t12-hpc/code/final_close-20260913/data/annotations/pilot_120_v1/intent_gold_references_120.jsonl"),
    Path("/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922/data/annotations/pilot_120_v1/intent_gold_references_120.jsonl"),
]:
    if cand.exists():
        for row in load_jsonl(cand):
            rid = row.get("record_id")
            refs.setdefault(rid, [])
            for key in ("reference_a", "reference_b", "intent_text", "gold_intent", "references"):
                val = row.get(key)
                if isinstance(val, list):
                    refs[rid].extend(str(x) for x in val)
                elif val:
                    refs[rid].append(str(val))
        print("INTENT_REFS", cand, "n", len(refs))
        break

def score_pred(path):
    rows = load_jsonl(path)
    if not rows:
        return {"exists": Path(path).exists(), "n": 0}
    ok = 0
    failed = 0
    intent = 0
    for p in rows:
        if p.get("failed"):
            failed += 1
            continue
        g = gold.get(p["record_id"], {})
        if norm(p.get("terminal_strategy")) == norm(g.get("terminal_strategy")):
            ok += 1
        if auto_pass(p.get("intent_summary") or "", refs.get(p["record_id"], [])):
            intent += 1
    man = {}
    mp = Path(path).resolve().parents[1] / "run_manifest.json"
    if mp.exists():
        man = json.loads(mp.read_text(encoding="utf-8"))
    return {
        "path": str(path),
        "n": len(rows),
        "unique": len({r.get("record_id") for r in rows}),
        "route": ok,
        "intent_screen": intent,
        "failed": failed,
        "temperature": man.get("temperature"),
        "seed": man.get("seed"),
        "status": man.get("status"),
        "code_root": man.get("root") or man.get("code_root"),
    }

prio = Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915")
table = {}
for T in ["T0.0", "T0.3", "T0.5", "T0.7", "T1.0"]:
    pred = prio / T / "predictions" / "goal_first_manager_v2.predictions.jsonl"
    table[T] = score_pred(pred)
    print("SCORE", T, json.dumps(table[T]))

# other likely T0.3/T0.0
others = []
results = Path("/home-mscluster/mbangie/t12-hpc/results")
for p in sorted(results.glob("**/T0.3/**/goal_first_manager_v2.predictions.jsonl")):
    others.append(str(p))
print("T03_CANDIDATES")
for p in others:
    print(" ", p)

ft = Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_t07_matched_baseline-20260922/t07_matched_baseline_completion_20260922/emit/t28_selected_adapter_llm/t28_selected_adapter_llm.predictions.jsonl")
print("FT_N", ft.exists(), sum(1 for line in ft.open() if line.strip()) if ft.exists() else 0)
Path("/tmp/able_ix_existing_scores.json").write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
print("WROTE /tmp/able_ix_existing_scores.json")
PY

echo "=== CODE DIRS ==="
ls -d /home-mscluster/mbangie/t12-hpc/code/* 2>/dev/null | head -40
echo "=== T0.5 MANIFEST ==="
python3 -c 'import json; p="/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915/T0.5/run_manifest.json";
import pathlib
print(pathlib.Path(p).exists())
print(open(p).read()[:2500] if pathlib.Path(p).exists() else "missing")'
echo "=== T0.3 MANIFEST ==="
python3 -c 'import pathlib; p=pathlib.Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915/T0.3/run_manifest.json"); print(p.exists()); print(p.read_text()[:2500] if p.exists() else "missing")'
echo "=== T0.0 MANIFEST ==="
python3 -c 'import pathlib; p=pathlib.Path("/home-mscluster/mbangie/t12-hpc/results/pilot120_temp_priority-20260915/T0.0/run_manifest.json"); print(p.exists()); print(p.read_text()[:2500] if p.exists() else "missing")'

echo INSPECT_DONE
