#!/usr/bin/env bash
# Diagnose failed native schema errors. Read-only.
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
root = Path("/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b")
native_code = Path("/home-mscluster/mbangie/t12-hpc/code/followon-native-20260911")

print("=== CLUSTER RUNNER SNIPPETS ===")
for rel in ("scripts/run_ambik_ambiguity_type.py", "scripts/run_native_context_structured.py"):
    text = (native_code / rel).read_text(encoding="utf-8")
    print(f"----- {rel} -----")
    for i, line in enumerate(text.splitlines(), 1):
        if any(k in line for k in ("ambiguity_types", "condition", "indirect_schema", "ALLOWED", "valid(", "def parse", "source_native")):
            print(f"{i}:{line}")

print("\n=== PACKET ROWS ===")
import json
ambik_packet = native_code / "inputs" / "ambik_packet.jsonl"
indirect_packet = native_code / "inputs" / "indirect.jsonl"
for path, rid in ((ambik_packet, "ambik:211"), (indirect_packet, "indirect_requests:train:234")):
    print(f"----- {path.name} {rid} -----")
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("record_id") == rid:
            print("line", i, "keys", sorted(row.keys()))
            print(json.dumps({k: row.get(k) for k in ("record_id", "condition", "command", "scene_context") if k in row or k == "condition"}, ensure_ascii=False)[:800])
            break

print("\n=== GEMMA AMBIK 211 ===")
g = root / "native" / "gemma4" / "ambik" / "predictions.jsonl"
if g.exists():
    for line in g.read_text(encoding="utf-8").splitlines():
        if '"ambik:211"' in line:
            print(line)
            break

print("\n=== SERVER LOG TAILS ===")
for rel in (
    "native/glm47/ambik/server.log",
    "native/glm47/indirect/server.log",
    "native/gemma4/indirect/server.log",
    "native/glm47/clara/server.log",
):
    p = root / rel
    if not p.exists():
        print(rel, "MISSING")
        continue
    text = p.read_text(encoding="utf-8", errors="replace")
    print(f"----- {rel} size={p.stat().st_size} -----")
    print(text[-1500:])
    print()
PY
