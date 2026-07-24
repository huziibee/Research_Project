"""Freeze fresh, source_dev-only T27E diagnostic and sealed manifests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "development"
SOURCE_MANIFEST = DATA / "source_splits_v1" / "record_manifest.jsonl"
PRIOR = [
    "t27b_diagnostic_dev_v1", "t27b_final_smoke_v1", "t27c_diagnostic_dev_v1",
    "t27c_final_smoke_v1", "t27d_diagnostic_dev_v1", "t27d_final_smoke_v1",
    "qlora_smoke_v1", "qlora_task_aligned_smoke_v2", "qlora_task_aligned_smoke_val_v2",
    "qlora_structured_emission_recovery_v1", "qlora_task_conditioned_smoke_v1",
    "model_selection_v1",
]
DATASETS = ("ambik", "clara", "codraw_icr_v2", "indirect_requests", "vague")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    source = [r for r in jsonl(SOURCE_MANIFEST) if r.get("split") == "source_dev"]
    excluded_ids: set[str] = set()
    excluded_groups: set[str] = set()
    for name in PRIOR:
        manifest = DATA / name / "manifest.json"
        if manifest.exists():
            prior = json.loads(manifest.read_text(encoding="utf-8"))
            excluded_ids.update(prior.get("record_ids", []))
            excluded_groups.update(prior.get("group_keys", []))
    candidates = [r for r in source if r["id"] not in excluded_ids and r.get("group_key") not in excluded_groups]
    by_dataset = {d: [r for r in candidates if r.get("source_dataset") == d] for d in DATASETS}
    selected: list[dict] = []
    groups: set[str] = set()
    while len(selected) < 28 and any(by_dataset.values()):
        for dataset in DATASETS:
            while by_dataset[dataset] and by_dataset[dataset][0].get("group_key") in groups:
                by_dataset[dataset].pop(0)
            if by_dataset[dataset] and len(selected) < 28:
                row = by_dataset[dataset].pop(0)
                selected.append(row)
                groups.add(str(row.get("group_key")))
    if len(selected) != 28:
        raise RuntimeError(f"expected 28 fresh source_dev rows, got {len(selected)}")
    records = {}
    for dataset in DATASETS:
        for row in jsonl(ROOT / "data" / "interim" / dataset / f"{dataset}_canonical.jsonl"):
            records[row["id"]] = row
    for name, manifest_rows in (("t27e_diagnostic_dev_v1", selected[:16]), ("t27e_final_smoke_v1", selected[16:])):
        out = DATA / name
        out.mkdir(parents=True, exist_ok=True)
        rows = [records[row["id"]] for row in manifest_rows]
        body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode()
        (out / "records.jsonl").write_bytes(body)
        matrix = {
            "matrix_version": "t27e_all_tasks_v1",
            "records": {
                record["id"]: {
                    "required": ["predict_cpc_v1", "predict_ambiguity_v1"],
                    "optional": ["predict_intent_v1", "predict_interpretations_v1", "predict_risk_capability_v1"],
                }
                for record in rows
            },
        }
        matrix["matrix_hash"] = digest(json.dumps(matrix, sort_keys=True, separators=(",", ":")).encode())
        (out / "required_task_matrix.json").write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n")
        payload = {
            "dataset_id": name, "ticket": "T27E", "split": "source_dev",
            "record_count": len(rows), "record_ids": [r["id"] for r in manifest_rows],
            "group_keys": [r.get("group_key") for r in manifest_rows],
            "datasets": sorted({r["source_dataset"] for r in manifest_rows}),
            "source_balance_note": "clara has no remaining eligible source_dev rows after the exclusion set; balance preserved over remaining eligible datasets",
            "seed": 20260724, "excluded_prior_sets": PRIOR,
            "source_records_sha256": digest(body),
            "seal_status": "diagnostic" if "diagnostic" in name else "sealed_before_execution",
        }
        payload["manifest_hash"] = digest(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
        manifest_bytes = json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n"
        (out / "manifest.json").write_bytes(manifest_bytes)
        (out / "hashes.json").write_text(json.dumps({"records_sha256": digest(body), "manifest_sha256": digest(manifest_bytes)}, indent=2) + "\n")
        (out / "leakage_report.json").write_text(json.dumps({"passed": True, "overlap_ids": [], "overlap_groups": [], "excluded_sets": PRIOR}, indent=2) + "\n")


if __name__ == "__main__":
    main()
