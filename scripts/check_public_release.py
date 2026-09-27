#!/usr/bin/env python3
"""Read-only path audit of the Git index before building a public research tree.

This is deliberately conservative. Passing it does not establish dataset rights,
absence of secrets in file contents, or a clean Git history.
"""
from __future__ import annotations

import argparse
import subprocess
from collections import defaultdict
from pathlib import Path


def category(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    if normalized.startswith("data/raw/") and normalized != "data/raw/.gitkeep":
        return "upstream_raw_or_gitlink"
    if normalized.startswith("data/annotations/"):
        return "annotation_or_derived_text"
    if normalized.startswith("data/development/") or normalized.startswith("data/processed/"):
        return "derived_dataset"
    if normalized.startswith("outputs/") and normalized != "outputs/.gitkeep":
        return "generated_output"
    if normalized.startswith(".t41_closure_work/") or normalized.startswith("research_evidence_package_"):
        return "local_evidence_archive"
    if normalized.lower().endswith((".zip", ".tar", ".tar.gz", ".7z")):
        return "archive"
    basename = Path(normalized).name.lower()
    if basename in {".env", "id_rsa", "id_ed25519"} or basename.endswith((".pem", ".key")):
        return "credential_filename"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    proc = subprocess.run(
        ["git", "ls-files", "--cached", "-z"],
        cwd=args.root,
        capture_output=True,
        check=True,
    )
    paths = [p.decode("utf-8", errors="replace") for p in proc.stdout.split(b"\0") if p]
    findings: dict[str, list[str]] = defaultdict(list)
    for path in paths:
        kind = category(path)
        if kind:
            findings[kind].append(path)
    print(f"tracked_paths={len(paths)}")
    for kind, members in sorted(findings.items()):
        print(f"{kind}={len(members)}")
        for path in members[:3]:
            print(f"  {path}")
    if findings:
        print("PUBLIC_RELEASE_PATH_AUDIT=FAIL")
        return 1
    print("PUBLIC_RELEASE_PATH_AUDIT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
