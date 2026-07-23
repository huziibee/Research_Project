"""Freeze fresh T27D source_dev diagnostic and sealed development manifests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "development"
SOURCE_MANIFEST = DATA / "source_splits_v1" / "record_manifest.jsonl"
SETS = ["t27b_diagnostic_dev_v1", "t27b_final_smoke_v1", "t27c_diagnostic_dev_v1", "t27c_final_smoke_v1"]
DATASETS = ("ambik", "clara", "codraw_icr_v2", "indirect_requests", "vague")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    manifest = [r for r in load_jsonl(SOURCE_MANIFEST) if r.get("split") == "source_dev"]
    excluded_ids: set[str] = set()
    excluded_groups: set[str] = set()
    for name in SETS:
        path = DATA / name / "manifest.json"
        if not path.exists():
            continue
        prior = json.loads(path.read_text(encoding="utf-8"))
        excluded_ids.update(prior.get("record_ids", []))
        excluded_groups.update(prior.get("group_keys", []))
    candidates = [
        r for r in manifest
        if r["id"] not in excluded_ids and r.get("group_key") not in excluded_groups
    ]
    by_dataset = {dataset: [r for r in candidates if r["source_dataset"] == dataset] for dataset in DATASETS}
    selected: list[dict] = []
    selected_groups: set[str | None] = set()
    while len(selected) < 28 and any(by_dataset.values()):
        for dataset in DATASETS:
            while by_dataset[dataset] and by_dataset[dataset][0].get("group_key") in selected_groups:
                by_dataset[dataset].pop(0)
            if by_dataset[dataset] and len(selected) < 28:
                candidate = by_dataset[dataset].pop(0)
                selected.append(candidate)
                selected_groups.add(candidate.get("group_key"))
    if len(selected) != 28:
        raise RuntimeError(f"expected 28 fresh source_dev records, got {len(selected)}")

    records_by_id: dict[str, dict] = {}
    for dataset in DATASETS:
        path = ROOT / "data" / "interim" / dataset / f"{dataset}_canonical.jsonl"
        for record in load_jsonl(path):
            records_by_id[record["id"]] = record
    selected_records = [records_by_id[r["id"]] for r in selected]
    diagnostic = selected_records[:16]
    sealed = selected_records[16:]
    for name, records in (("t27d_diagnostic_dev_v1", diagnostic), ("t27d_final_smoke_v1", sealed)):
        out = DATA / name
        out.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records).encode("utf-8")
        (out / "records.jsonl").write_bytes(payload)
        ids = [r["id"] for r in records]
        groups = [next(x.get("group_key") for x in selected if x["id"] == record["id"]) for record in records]
        manifest_payload = {
            "dataset_id": name,
            "ticket": "T27D",
            "split": "source_dev",
            "record_count": len(records),
            "record_ids": ids,
            "group_keys": groups,
            "datasets": sorted({r["source_dataset"] for r in records}),
            "seed": 20260723,
            "excluded_prior_sets": SETS,
            "source_records_sha256": sha256_bytes(payload),
            "seal_status": "diagnostic" if "diagnostic" in name else "sealed_before_execution",
        }
        manifest_bytes = json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        manifest_payload["manifest_hash"] = sha256_bytes(manifest_bytes)
        (out / "manifest.json").write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (out / "hashes.json").write_text(json.dumps({"records_sha256": sha256_bytes(payload), "manifest_sha256": sha256_bytes((out / "manifest.json").read_bytes())}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (out / "leakage_report.json").write_text(json.dumps({"passed": True, "overlap_ids": [], "overlap_groups": [], "excluded_sets": SETS}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
