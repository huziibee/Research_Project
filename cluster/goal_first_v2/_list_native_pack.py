#!/usr/bin/env python3
from pathlib import Path
root = Path("/home-mscluster/mbangie/t12-hpc/code/followon-native-20260911")
for rel in ("inputs", "protocol", "scripts"):
    d = root / rel
    print("====", d)
    if d.exists():
        for p in sorted(d.iterdir()):
            if p.is_file():
                print(f"{p.name}\t{p.stat().st_size}")
print("==== runner condition/parse check")
text = (root / "scripts" / "run_native_context_structured.py").read_text(encoding="utf-8")
for i, line in enumerate(text.splitlines(), 1):
    if "source_native_context" in line or "empty_aliases" in line or "extract_json" in line:
        print(f"{i}:{line}")
text = (root / "scripts" / "run_ambik_ambiguity_type.py").read_text(encoding="utf-8")
for i, line in enumerate(text.splitlines(), 1):
    if "ALIASES" in line or "extra" in line or "extract_json" in line:
        print(f"ambik {i}:{line}")
