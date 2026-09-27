"""Read-only check of the curated repository tree and preserved Pilot-120 files.

This checks identity and structure, not scientific validity or redistribution rights.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data/annotations/pilot_120_v1"
RESEARCH = ROOT / "research/pilot120"
HASHES = {
    "data/annotations/pilot_120_v1/source_canonical.jsonl": "f33b1e29f1e8aa256a475f07213aa07247def47d8e2148d54a472a40b71b05c9",
    "data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl": "5e23ad1a92ff1873c8f039a8ce560a111dd6fb6b8ae8c11d6cf34dbfa1c360db",
    "data/annotations/pilot_120_v1/GOLD_POLICY.json": "3c1f0a4d43c29996062a4a2ecd321e4023a38f5fad950801f96e07e23aac4a34",
    "data/annotations/pilot_120_v1/frozen/FROZEN_MANIFEST.json": "c61489101bfbc6cf0222538107abd272b50ce59c2f2a4292e95773f686d60230",
    "research/pilot120/artifacts/t07_matched_baseline_completion_20260927_FINAL.zip": "34ca50e034ca37b617068bb50c734d12fa26282fb5eec563c11ead700163e491",
    "research/pilot120/artifacts/p120_full_analysis_20260923.zip": "0305b1e9ab062876ee6ee89778cc6028d2eaf01718b7dd0295944e7d9cb81a01",
    "research/pilot120/artifacts/pilot120_t41_complete_closure.zip": "aea638cf05eab66610429e69f0d88f112eb09b4bd5582bb0d1b23d0a6dd3c21a",
    "research/pilot120/artifacts/pilot120_historical_annotation_handoff.zip": "0c51676e92cd8dd4068cc12a84c2533d3b7c70be6df32777e4d66682296ee560",
    "research/pilot120/artifacts/pilot120_intent_evaluation_20260902.zip": "541f2990305a54ccabee9f2e24c77da5b1597b54453956374c97f74b47ab3116",
    "research/pilot120/artifacts/pilot120_semantic_intent_final.zip": "cd5cdcdc042cb01bc60dfbb0b32ae73bf85844b641f11051c7fa53f9e21a9d8a",
    "research/pilot120/artifacts/gold_v2_officialization_20260914.zip": "4809e928b67c73fa93c3ea926675d1a779a4b83783e2f79d82d55387de2da5d8",
}


def main() -> int:
    raw = subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=ROOT)
    tracked = {item.decode("utf-8") for item in raw.split(b"\0") if item}
    problems = []
    for path in sorted(tracked):
        parts = Path(path).parts
        if path.startswith(("data/raw/", "data/development/", "data/processed/", "outputs/")):
            if Path(path).name != ".gitkeep":
                problems.append(f"unexpected generated path: {path}")
        if parts[0] in {"unneeded", "local_archive"} or path in {"rubric.txt", "spec_text.txt"}:
            problems.append(f"unrelated root path: {path}")
        if Path(path).name.lower() in {".env", "id_rsa", "id_ed25519"}:
            problems.append(f"credential filename: {path}")
        if path.lower().endswith((".pem", ".key")):
            problems.append(f"credential filename: {path}")
        if path.lower().endswith((".zip", ".tar", ".tar.gz", ".7z")):
            if path not in HASHES:
                problems.append(f"unregistered archive: {path}")

    for path, expected in HASHES.items():
        target = ROOT / path
        if path not in tracked or not target.is_file():
            problems.append(f"missing tracked artifact: {path}")
            continue
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            problems.append(f"SHA-256 mismatch: {path}")
        if target.suffix == ".zip":
            with zipfile.ZipFile(target) as archive:
                if archive.testzip() is not None:
                    problems.append(f"ZIP CRC failure: {path}")

    source = PILOT / "source_canonical.jsonl"
    if source.is_file():
        ids = [json.loads(line)["record_id"] for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(ids) != 120 or len(set(ids)) != 120:
            problems.append("source must contain 120 unique IDs")
        for case_id in ids:
            path = f"research/pilot120/cases/{case_id}.json"
            if path not in tracked:
                problems.append(f"missing tracked case: {case_id}")
            elif json.loads((ROOT / path).read_text(encoding="utf-8"))["record_id"] != case_id:
                problems.append(f"case ID mismatch: {case_id}")
        actual = {p.name for p in (RESEARCH / "cases").glob("CA-*.json")}
        if actual != {f"{case_id}.json" for case_id in ids}:
            problems.append("case directory does not match frozen ID set")

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/release/build_pilot120_cases.py"), "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if result.returncode:
        problems.append("case source/output content check failed: " + (result.stderr or result.stdout).strip()[-500:])

    print(f"tracked_paths={len(tracked)} cases={120 if source.is_file() else 0} verified_files={len(HASHES)}")
    for issue in problems[:20]:
        print(issue)
    print("RIGHTS_STATUS=UNRESOLVED_FOR_PUBLIC_REDISTRIBUTION")
    print("REPOSITORY_TREE=" + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
