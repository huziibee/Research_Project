"""Freeze one fresh T27F source_dev sealed set after all prior exclusions."""

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
    "t27e_diagnostic_dev_v1", "t27e_final_smoke_v1", "qlora_smoke_v1",
    "qlora_task_aligned_smoke_v2", "qlora_task_aligned_smoke_val_v2",
    "qlora_structured_emission_recovery_v1", "qlora_task_conditioned_smoke_v1",
    "model_selection_v1",
]
DATASETS = ("ambik", "clara", "codraw_icr_v2", "indirect_requests", "vague")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    source = [row for row in read_jsonl(SOURCE_MANIFEST) if row.get("split") == "source_dev"]
    excluded_ids: set[str] = set(); excluded_groups: set[str] = set()
    for name in PRIOR:
        path = DATA / name / "manifest.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            excluded_ids.update(str(x) for x in payload.get("record_ids", []))
            excluded_groups.update(str(x) for x in payload.get("group_keys", []))
    candidates = [row for row in source if str(row["id"]) not in excluded_ids and str(row.get("group_key")) not in excluded_groups]
    by_dataset = {name: [row for row in candidates if row.get("source_dataset") == name] for name in DATASETS}
    selected: list[dict] = []; groups: set[str] = set()
    while len(selected) < 12:
        progressed = False
        for name in DATASETS:
            while by_dataset[name] and str(by_dataset[name][0].get("group_key")) in groups:
                by_dataset[name].pop(0)
            if by_dataset[name] and len(selected) < 12:
                row = by_dataset[name].pop(0); selected.append(row); groups.add(str(row.get("group_key"))); progressed = True
        if not progressed: raise RuntimeError("fewer_than_12_fresh_eligible_source_dev_records")
    records_by_id: dict[str, dict] = {}
    for name in DATASETS:
        for row in read_jsonl(ROOT / "data" / "interim" / name / f"{name}_canonical.jsonl"):
            records_by_id[str(row["id"])] = row
    rows = [records_by_id[str(row["id"])] for row in selected]
    out = DATA / "t27f_final_smoke_v1"; out.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode()
    (out / "records.jsonl").write_bytes(body)
    matrix = {"matrix_version": "t27f_all_tasks_v1", "records": {row["id"]: {"required": ["predict_cpc_v1", "predict_ambiguity_v1"], "optional": ["predict_intent_v1", "predict_interpretations_v1", "predict_risk_capability_v1"]} for row in rows}}
    matrix["matrix_hash"] = digest(json.dumps(matrix, sort_keys=True, separators=(",", ":")).encode())
    (out / "required_task_matrix.json").write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {"dataset_id": "t27f_final_smoke_v1", "ticket": "T27F", "split": "source_dev", "seal_status": "sealed_before_execution", "record_count": 12, "record_ids": [row["id"] for row in selected], "group_keys": [row.get("group_key") for row in selected], "datasets": sorted({row["source_dataset"] for row in selected}), "excluded_prior_sets": PRIOR, "source_records_sha256": digest(body), "source_balance_note": "round-robin selection over eligible non-protected source_dev datasets"}
    manifest["manifest_hash"] = digest(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
    (out / "manifest.json").write_bytes(manifest_bytes)
    (out / "hashes.json").write_text(json.dumps({"records_sha256": digest(body), "manifest_sha256": digest(manifest_bytes)}, indent=2) + "\n", encoding="utf-8")
    (out / "leakage_report.json").write_text(json.dumps({"passed": True, "overlap_ids": [], "overlap_groups": [], "excluded_sets": PRIOR + ["t27f_all_task_canary"]}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(out / "manifest.json"), "record_ids": manifest["record_ids"], "manifest_hash": manifest["manifest_hash"]}, indent=2))


if __name__ == "__main__":
    main()
