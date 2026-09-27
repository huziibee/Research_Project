#!/usr/bin/env python3
"""Refresh manifests and rezip Pack A + Pack B after review patches."""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "outputs" / "paper_writer_handoff_20260922"
PACK_A = STAGING / "A_EVIDENCE_FOR_PAPER"
PACK_B = STAGING / "B_FRAMING_AND_IDEAS"
OUT_A = ROOT / "outputs" / "PaperWriter_A_EVIDENCE_COMPLETE_20260922.zip"
OUT_B = ROOT / "outputs" / "PaperWriter_B_FRAMING_IDEAS_20260922.zip"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def refresh_manifest(pack: Path, name: str) -> dict:
    files = [p for p in pack.rglob("*") if p.is_file() and p.name != "MANIFEST.json"]
    rows = [
        {
            "path": str(p.relative_to(pack)).replace("\\", "/"),
            "bytes": p.stat().st_size,
            "sha256": sha256_file(p),
        }
        for p in sorted(files)
    ]
    summary = {
        "pack": name,
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "total_bytes": sum(r["bytes"] for r in rows),
        "reviews_included_in_parent_folder": True,
    }
    (pack / "MANIFEST.json").write_text(
        json.dumps({"summary": summary, "files": rows}, indent=2), encoding="utf-8"
    )
    return summary


def zip_dir(src: Path, out_zip: Path) -> None:
    if out_zip.exists():
        out_zip.unlink()
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                zf.write(p, arcname=str(Path(src.name) / p.relative_to(src)).replace("\\", "/"))
        # also include review reports at pack root inside zip
        for rev in [STAGING / "REVIEW_A_EVIDENCE.md", STAGING / "REVIEW_B_FRAMING.md"]:
            if rev.exists() and src.name.startswith("A_") and rev.name.startswith("REVIEW_A"):
                zf.write(rev, arcname=f"{src.name}/_REVIEW/{rev.name}")
            if rev.exists() and src.name.startswith("B_") and rev.name.startswith("REVIEW_B"):
                zf.write(rev, arcname=f"{src.name}/_REVIEW/{rev.name}")


def main() -> int:
    sa = refresh_manifest(PACK_A, "A_EVIDENCE_FOR_PAPER")
    sb = refresh_manifest(PACK_B, "B_FRAMING_AND_IDEAS")
    zip_dir(PACK_A, OUT_A)
    zip_dir(PACK_B, OUT_B)
    handoff = {
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "pack_a_zip": str(OUT_A),
        "pack_b_zip": str(OUT_B),
        "pack_a_zip_bytes": OUT_A.stat().st_size,
        "pack_b_zip_bytes": OUT_B.stat().st_size,
        "pack_a": sa,
        "pack_b": sb,
        "review_a": "PASS_WITH_GAPS (High gap fixed; rezipped)",
        "review_b": "PASS after patches",
        "full_archive_pointer": "research_evidence_package_20260922/",
    }
    (STAGING / "BUILD_SUMMARY.json").write_text(json.dumps(handoff, indent=2), encoding="utf-8")
    (STAGING / "HANDOFF_README.md").write_text(
        f"""# Paper-writer handoff (2026-09-22)

Two zips for a separate model that will write the honours research paper.

## Deliverables

| Zip | Role | Path |
|---|---|---|
| **Pack A — Evidence** | Full factual context (neutral). Prefer for all numbers. | `{OUT_A.name}` ({OUT_A.stat().st_size} bytes) |
| **Pack B — Framing** | Ideas, narrative guardrails, anti-drift lessons. Opinionated. | `{OUT_B.name}` ({OUT_B.stat().st_size} bytes) |

## How the writing model should use them

1. Open **Pack A** first: `A_EVIDENCE_FOR_PAPER/00_START_HERE.md`
2. Before citing **113/120** two-judge: read `A_EVIDENCE_FOR_PAPER/13_intent_judging_and_comparators/README.md`
3. Open **Pack B** if the draft drifts (routing-win narrative, embodiment claims, grade language): start at `B_FRAMING_AND_IDEAS/00_START_HERE.md` and `08_project_history_lessons.md`
4. If Pack B prose conflicts with Pack A JSON → **Pack A wins**
5. Exhaustive raw archive (optional deep dive): `research_evidence_package_20260922/` (~10.6 GiB, not inside these zips)

## Review status

- Pack A review: `REVIEW_A_EVIDENCE.md` → PASS_WITH_GAPS (High gap fixed in staging; this zip refreshed)
- Pack B review: `REVIEW_B_FRAMING.md` → PASS after patches

## What Pack A deliberately excludes

- `grade-estimate.md`, `rubric.md` (mark forecasting) — framing-only in Pack B with do-not-cite banners

Built UTC: {handoff['built_utc']}
""",
        encoding="utf-8",
    )
    print(json.dumps(handoff, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
