#!/usr/bin/env python3
import json
from pathlib import Path

native = Path("/home-mscluster/mbangie/t12-hpc/code/followon-native-20260911")
root = Path("/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b")
runner = (native / "scripts" / "run_ambik_ambiguity_type.py").read_text(encoding="utf-8")
print("=== RUNNER ALIASES ===")
for i, line in enumerate(runner.splitlines(), 1):
    if any(k in line for k in ("ALIASES", "ALLOWED", "common_sense", "def parse", "ambiguity_types_invalid", "rejected_payload")):
        print(f"{i}:{line}")
print("\n=== PACKET 211 ===")
for i, line in enumerate((native / "inputs" / "ambik_packet.jsonl").read_text(encoding="utf-8").splitlines(), 1):
    row = json.loads(line)
    if row.get("record_id") == "ambik:211":
        print("line", i, json.dumps({k: row.get(k) for k in ("record_id", "command", "scene_context")}, ensure_ascii=False)[:500])
        break
print("\n=== GEMMA 211 ===")
g = root / "native" / "gemma4" / "ambik" / "predictions.jsonl"
for line in g.read_text(encoding="utf-8").splitlines():
    if '"ambik:211"' in line:
        print(line)
        break
print("\n=== 53420 AMBIK LOGS ===")
print((root / "native_retry" / "task_logs" / "glm47_ambik.stderr.log").read_text(encoding="utf-8", errors="replace"))
print("\n=== INDIRECT COUNTS ===")
for rel in ("native/gemma4/indirect/predictions.jsonl", "native/glm47/indirect/predictions.jsonl"):
    p = root / rel
    n = sum(1 for line in p.open(encoding="utf-8") if line.strip()) if p.exists() else 0
    print(rel, "rows", n, "exists", p.exists())
