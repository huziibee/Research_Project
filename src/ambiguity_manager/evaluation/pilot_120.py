"""Pilot-120 v1: evaluation-only dataset preflight, freeze gates, and evaluator.

This module never invents human ANN-A / ANN-B labels. Freeze hard-fails until
final-protocol dual annotation + adjudication gates are genuinely closed.
"""

from __future__ import annotations

import hashlib
import json
import math
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ambiguity_manager.governance.hashing import sha256_hex

PILOT_120_VERSION = "pilot_120_v1"
EXPECTED_N = 120
EXPECTED_CAPABILITY = {"A": 99, "B": 21, "C": 0, "D": 0}
PUBLIC_FIELDS = (
    "record_id",
    "command",
    "dialogue_history",
    "scene_context",
    "capability_context",
)
FORBIDDEN_VIEW_KEYS = {
    "qa_capability_class",
    "one_path_determinacy",
    "canonical_route",
    "terminal_strategy",
    "ambiguity_types",
    "capability_status",
    "gold_lifecycle",
    "owner_route",
    "human_gate_required",
    "annotator_a",
    "annotator_b",
    "pilot_gold",
}
CORE_AGREE_FIELDS = (
    "terminal_strategy",
    "capability_status",
    "record_validity",
)
TERMINALS = {"execute", "clarify", "face_preserving_rejection"}


class Pilot120Error(ValueError):
    """Hard-fail gate violation for Pilot-120."""


@dataclass
class GateResult:
    name: str
    ok: bool
    detail: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "data": self.data,
        }


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_paths(root: Path | None = None) -> dict[str, Path]:
    root = root or project_root()
    return {
        "root": root,
        "canonical_jsonl": root / "data" / "annotations" / "pilot_120_v1" / "source_canonical.jsonl",
        "canonical_provenance": root
        / "data"
        / "annotations"
        / "pilot_120_v1"
        / "SOURCE_PROVENANCE.json",
        "final_protocol": root / "annotations" / "manual_kappa_v7_final_protocol",
        "subset_manifest": root
        / "annotations"
        / "manual_kappa_v7_final_protocol"
        / "subset_manifest.json",
        "inputs": root / "annotations" / "manual_kappa_v7_final_protocol" / "inputs",
        "annotator_a": root / "annotations" / "manual_kappa_v7_final_protocol" / "annotator_a",
        "annotator_b": root / "annotations" / "manual_kappa_v7_final_protocol" / "annotator_b",
        "adjudication": root / "annotations" / "manual_kappa_v7_final_protocol" / "adjudication",
        "gold": root / "annotations" / "manual_kappa_v7_final_protocol" / "gold",
        "agreement": root
        / "annotations"
        / "manual_kappa_v7_final_protocol"
        / "final_protocol_annotation_agreement.json",
        "capability_audit": root
        / "annotations"
        / "private_owner_qa_v7"
        / "FULL_1000_CAPABILITY_AUDIT.json",
        "one_path_qa": root
        / "annotations"
        / "private_owner_qa_v7"
        / "FULL_1000_ONE_PATH_QA.json",
        "repair_log": root
        / "annotations"
        / "private_owner_qa_v7"
        / "FINAL_SEMANTIC_REPAIR_CHANGELOG.json",
        "pilot_kappa_strata": root / "annotations" / "manual_kappa_v7" / "KAPPA_STRATA.md",
        "pilot_gold": root / "annotations" / "manual_kappa_v7" / "gold",
        "t28_train": root
        / "outputs"
        / "t28_r3"
        / "frozen_manifests"
        / "source_train_task_manifest.jsonl",
        "t28_dev": root
        / "outputs"
        / "t28_r3"
        / "frozen_manifests"
        / "source_dev_task_manifest.jsonl",
        "roles": root / "configs" / "annotation" / "annotation_roles_v1.json",
        "adj01_decision": root
        / "annotations"
        / "manual_kappa_v7_final_protocol"
        / "adjudication"
        / "ADJ01_DECISION_REQUEST.md",
        "freeze_dir": root / "data" / "annotations" / "pilot_120_v1" / "frozen",
        "packages_dir": root
        / "annotations"
        / "manual_kappa_v7_final_protocol"
        / "packages",
        "status": root / "data" / "annotations" / "pilot_120_v1" / "STATUS.json",
        "config": root / "configs" / "evaluation" / "pilot_120_v1.json",
        "gold_policy": root / "data" / "annotations" / "pilot_120_v1" / "GOLD_POLICY.json",
        "pilot_eval_gold": root
        / "annotations"
        / "manual_kappa_v7"
        / "eval"
        / "subset_final_gold_eval.jsonl",
        "pilot_gold_manifest": root / "annotations" / "manual_kappa_v7" / "gold_manifest.json",
        "frozen_gold_jsonl": root
        / "data"
        / "annotations"
        / "pilot_120_v1"
        / "pilot_120_final_gold.jsonl",
    }


def sha256_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def sha256_text(text: str) -> str:
    return sha256_hex(text.encode("utf-8"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(dict(r), ensure_ascii=False, sort_keys=True) for r in rows]
    text = "\n".join(lines) + ("\n" if lines else "")
    # Binary write with LF only — Path.write_text on Windows would translate to CRLF
    # and break cross-platform / rematerialization hashes.
    path.write_bytes(text.encode("utf-8"))
    return sha256_text(text)


def expected_record_ids(paths: dict[str, Path] | None = None) -> list[str]:
    paths = paths or default_paths()
    man = load_json(paths["subset_manifest"])
    ids = list(man["record_ids"])
    if len(ids) != EXPECTED_N or len(set(ids)) != EXPECTED_N:
        raise Pilot120Error(
            f"subset_manifest must contain {EXPECTED_N} unique IDs; got {len(ids)}"
        )
    return ids


def materialize_canonical_source(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    """Build deterministic canonical JSONL from final-protocol repaired inputs."""
    paths = paths or default_paths()
    ids = expected_record_ids(paths)
    records: list[dict[str, Any]] = []
    for rid in ids:
        src = load_json(paths["inputs"] / f"{rid}.json")
        rec = {k: src.get(k) if k != "dialogue_history" else (src.get(k) or []) for k in PUBLIC_FIELDS}
        if rec["record_id"] != rid:
            raise Pilot120Error(f"input file mismatch for {rid}")
        leaked = sorted(set(src) & FORBIDDEN_VIEW_KEYS)
        if leaked:
            raise Pilot120Error(f"forbidden private keys in input {rid}: {leaked}")
        records.append(rec)
    sha = write_jsonl(paths["canonical_jsonl"], records)
    provenance = {
        "artifact": "pilot_120_v1_source_canonical",
        "n_records": len(records),
        "record_ids": ids,
        "source_of_truth_inputs": str(
            paths["inputs"].relative_to(paths["root"]).as_posix()
        ),
        "subset_manifest": str(
            paths["subset_manifest"].relative_to(paths["root"]).as_posix()
        ),
        "repair_changelog": str(
            paths["repair_log"].relative_to(paths["root"]).as_posix()
        ),
        "repair_scope": "kappa_subset_only_minimal_repair (capability_context only)",
        "source_canonical_jsonl_sha256": sha,
        "ordering": "subset_manifest.record_ids (deterministic)",
        "NOT": [
            "historical pilot ANN-A / ANN-B outputs",
            "historical pilot gold",
            "private owner QA labels",
            "final-protocol gold (until gates close)",
        ],
    }
    dump_json(paths["canonical_provenance"], provenance)
    return provenance


def _audit_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if "records" in payload:
            recs = payload["records"]
            if isinstance(recs, dict):
                return list(recs.values())
            return list(recs)
        if all(isinstance(v, dict) for v in payload.values()):
            return list(payload.values())
    raise Pilot120Error("unrecognised capability/one-path audit shape")


def _jsonl_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    for row in load_jsonl(path):
        rid = str(row.get("record_id") or row.get("id") or "")
        if rid:
            out.add(rid)
    return out


def cohen_kappa(y1: Sequence[Any], y2: Sequence[Any]) -> float | None:
    if len(y1) != len(y2) or not y1:
        return None
    n = len(y1)
    labels = sorted(set(y1) | set(y2), key=lambda x: str(x))
    if len(labels) == 1:
        return 1.0 if list(y1) == list(y2) else 0.0
    agree = sum(a == b for a, b in zip(y1, y2)) / n
    c1 = Counter(y1)
    c2 = Counter(y2)
    chance = sum((c1[lab] / n) * (c2[lab] / n) for lab in labels)
    if math.isclose(1.0 - chance, 0.0):
        return 1.0 if math.isclose(agree, 1.0) else 0.0
    return (agree - chance) / (1.0 - chance)


def run_preflight(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    paths = paths or default_paths()
    gates: list[GateResult] = []

    if not paths["canonical_jsonl"].exists():
        materialize_canonical_source(paths)

    ids = expected_record_ids(paths)
    id_set = set(ids)
    rows = load_jsonl(paths["canonical_jsonl"])
    row_ids = [r["record_id"] for r in rows]

    gates.append(
        GateResult(
            "record_count",
            len(rows) == EXPECTED_N,
            f"canonical rows={len(rows)} expected={EXPECTED_N}",
            {"n": len(rows)},
        )
    )
    gates.append(
        GateResult(
            "unique_ids",
            len(row_ids) == len(set(row_ids)) == EXPECTED_N,
            f"unique={len(set(row_ids))}",
        )
    )
    gates.append(
        GateResult(
            "expected_ids_present",
            row_ids == ids,
            "canonical order must equal subset_manifest.record_ids",
            {"mismatch": [a for a, b in zip(row_ids, ids) if a != b][:10]},
        )
    )

    for rec in rows:
        bad = sorted(set(rec) - set(PUBLIC_FIELDS))
        leaked = sorted(set(rec) & FORBIDDEN_VIEW_KEYS)
        if bad or leaked:
            gates.append(
                GateResult(
                    "source_structure",
                    False,
                    f"{rec.get('record_id')} has unexpected/forbidden keys",
                    {"extra": bad, "leaked": leaked},
                )
            )
            break
    else:
        gates.append(
            GateResult(
                "source_structure",
                True,
                "public fields only; no private/historical labels",
            )
        )

    # Deterministic ordering + stable hash
    source_sha = sha256_file(paths["canonical_jsonl"])
    rematerialized = materialize_canonical_source(paths)
    source_sha2 = rematerialized["source_canonical_jsonl_sha256"]
    gates.append(
        GateResult(
            "stable_hash",
            source_sha == source_sha2,
            f"sha256={source_sha2}",
            {"sha256": source_sha2},
        )
    )
    gates.append(
        GateResult(
            "deterministic_ordering",
            True,
            "ordered by subset_manifest.record_ids",
        )
    )

    # Capability distribution (private audit; engineering validation only)
    audit_rows = _audit_records(load_json(paths["capability_audit"]))
    subset_audit = [r for r in audit_rows if r.get("record_id") in id_set]
    cap_counts = Counter(r.get("qa_capability_class") for r in subset_audit)
    expected_ok = (
        len(subset_audit) == EXPECTED_N
        and cap_counts.get("A", 0) == EXPECTED_CAPABILITY["A"]
        and cap_counts.get("B", 0) == EXPECTED_CAPABILITY["B"]
        and cap_counts.get("C", 0) == EXPECTED_CAPABILITY["C"]
        and cap_counts.get("D", 0) == EXPECTED_CAPABILITY["D"]
    )
    gates.append(
        GateResult(
            "capability_distribution",
            expected_ok,
            f"A/B/C/D = {cap_counts.get('A',0)}/{cap_counts.get('B',0)}/"
            f"{cap_counts.get('C',0)}/{cap_counts.get('D',0)}",
            {"counts": dict(cap_counts)},
        )
    )
    gates.append(
        GateResult(
            "capability_d_zero",
            cap_counts.get("D", 0) == 0,
            f"D={cap_counts.get('D', 0)}",
        )
    )

    one_rows = _audit_records(load_json(paths["one_path_qa"]))
    osub = [r for r in one_rows if r.get("record_id") in id_set]
    n_true = sum(1 for r in osub if r.get("one_path_determinacy") is True)
    gates.append(
        GateResult(
            "one_path_determinacy",
            len(osub) == EXPECTED_N and n_true == EXPECTED_N,
            f"{n_true}/{EXPECTED_N} one_path_determinacy=true",
            {"n_true": n_true},
        )
    )

    # Leakage vs T28 train/dev
    train_ids = _jsonl_ids(paths["t28_train"])
    dev_ids = _jsonl_ids(paths["t28_dev"])
    leak_train = sorted(id_set & train_ids)
    leak_dev = sorted(id_set & dev_ids)
    gates.append(
        GateResult(
            "no_t28_train_dev_leakage",
            not leak_train and not leak_dev,
            f"overlap train={len(leak_train)} dev={len(leak_dev)}",
            {"train": leak_train[:20], "dev": leak_dev[:20]},
        )
    )

    # Blind input views: per-file under final-protocol inputs
    blind_ok = True
    blind_detail = "all 120 input files are public-only"
    for rid in ids:
        p = paths["inputs"] / f"{rid}.json"
        if not p.exists():
            blind_ok = False
            blind_detail = f"missing input {rid}"
            break
        obj = load_json(p)
        if sorted(set(obj) & FORBIDDEN_VIEW_KEYS):
            blind_ok = False
            blind_detail = f"input leaks private keys: {rid}"
            break
    gates.append(GateResult("blind_annotator_views", blind_ok, blind_detail))

    # Repair integrity: capability_context-only, IDs/commands/scenes preserved
    repair = load_json(paths["repair_log"])
    repair_ok = True
    repair_detail = f"n_changes={repair.get('n_changes')}"
    for change in repair.get("changes") or []:
        if change.get("field") != "capability_context":
            repair_ok = False
            repair_detail = f"non-capability repair on {change.get('record_id')}"
            break
        if change.get("scope") != "kappa_subset_only_minimal_repair":
            repair_ok = False
            repair_detail = f"unexpected repair scope on {change.get('record_id')}"
            break
        rid = change["record_id"]
        if rid not in id_set:
            repair_ok = False
            repair_detail = f"repair outside Pilot-120: {rid}"
            break
        rec = next(r for r in rows if r["record_id"] == rid)
        if rec["capability_context"] != change.get("new_value"):
            repair_ok = False
            repair_detail = f"canonical capability_context != repair new_value for {rid}"
            break
    gates.append(GateResult("repair_capability_context_only", repair_ok, repair_detail))

    failed = [g for g in gates if not g.ok]
    report = {
        "artifact": PILOT_120_VERSION,
        "status": "preflight_pass" if not failed else "preflight_fail",
        "source_sha256": source_sha2,
        "gates": [g.to_dict() for g in gates],
        "failed_gates": [g.name for g in failed],
        "capability_counts": {
            "A": cap_counts.get("A", 0),
            "B": cap_counts.get("B", 0),
            "C": cap_counts.get("C", 0),
            "D": cap_counts.get("D", 0),
        },
        "one_path_true": n_true,
        "n_records": len(rows),
    }
    dump_json(paths["root"] / "data" / "annotations" / "pilot_120_v1" / "PREFLIGHT.json", report)
    if failed:
        raise Pilot120Error(
            "Pilot-120 preflight failed: " + ", ".join(g.name for g in failed)
        )
    return report


def load_gold_policy(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    paths = paths or default_paths()
    if not paths["gold_policy"].exists():
        return {
            "decision": "require_final_protocol_reannotation",
            "final_protocol_reannotation_required": True,
            "steve_ben_reannotation_required": True,
            "adj01_required_for_this_freeze": True,
        }
    return load_json(paths["gold_policy"])


def uses_pilot_adjudicated_gold(paths: dict[str, Path] | None = None) -> bool:
    policy = load_gold_policy(paths)
    return policy.get("decision") == "use_existing_pilot_adjudicated_gold"


def honest_freeze_claim(paths: dict[str, Path] | None = None) -> str:
    policy = load_gold_policy(paths)
    if uses_pilot_adjudicated_gold(paths):
        return str(
            policy.get("honest_claim")
            or "Pilot-120 v1: PILOT-ADJUDICATED GOLD (Grok×Claude/GLM), "
            "CAPABILITY-REPAIRED SOURCE, FROZEN, HASHED, EVALUATION-ONLY"
        )
    return (
        "Pilot-120 v1: FINAL-PROTOCOL ANNOTATED, ADJUDICATED, FROZEN, HASHED, EVALUATION-ONLY"
    )


def verify_pilot_adjudicated_gold(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    """Validate existing pilot gold is complete enough to freeze under owner policy."""
    paths = paths or default_paths()
    ids = expected_record_ids(paths)
    missing = []
    bad_lifecycle = []
    gated = []
    invalid = []
    terminals: Counter[str] = Counter()
    for rid in ids:
        path = paths["pilot_gold"] / f"{rid}.json"
        if not path.exists():
            missing.append(rid)
            continue
        gold = load_json(path)
        if gold.get("gold_lifecycle") != "final_gold":
            bad_lifecycle.append(rid)
        if gold.get("human_gate_required") is True:
            gated.append(rid)
        if gold.get("record_validity") != "valid":
            invalid.append(rid)
        term = gold.get("terminal_strategy")
        if term not in TERMINALS:
            invalid.append(rid)
        terminals[str(term)] += 1
    ok = (
        not missing
        and not bad_lifecycle
        and not gated
        and not invalid
        and len(ids) == EXPECTED_N
    )
    return {
        "ok": ok,
        "n": EXPECTED_N - len(missing),
        "missing": missing,
        "bad_lifecycle": bad_lifecycle,
        "human_gate_required": gated,
        "invalid": invalid,
        "terminal_distribution": dict(terminals),
        "pilot_gold_manifest_exists": paths["pilot_gold_manifest"].exists(),
        "agreement_label": "pilot_annotation_agreement",
    }


def adj01_status(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    paths = paths or default_paths()
    roles = load_json(paths["roles"])
    adj = roles.get("roles", {}).get("ADJ-01", {})
    resolution_path = paths["adjudication"] / "ADJ01_RESOLUTION.json"
    resolution = load_json(resolution_path) if resolution_path.exists() else None
    unresolved = adj.get("status") == "unresolved" and not (
        resolution and resolution.get("status") == "resolved"
    )
    return {
        "role_config_status": adj.get("status"),
        "person_name": (resolution or {}).get("person_name") or adj.get("person_name"),
        "unresolved": unresolved,
        "note": (
            "ADJ-01 is the official adjudicator identity slot in "
            "configs/annotation/annotation_roles_v1.json. "
            "It is NOT automatically the pilot Claude Sonnet packet adjudicator. "
            "Pilot kappa used Claude Sonnet for disagreement packets under "
            "annotations/manual_kappa_v7/GOLD_ADJUDICATION_RULES.md; that does not "
            "resolve official ADJ-01 for final-protocol gold without an explicit "
            "policy decision recorded in ADJ01_RESOLUTION.json."
        ),
        "blocks_freeze": unresolved,
        "resolution_path": str(resolution_path.relative_to(paths["root"]).as_posix())
        if resolution_path.exists()
        else None,
        "decision_request": str(
            paths["adj01_decision"].relative_to(paths["root"]).as_posix()
        )
        if paths["adj01_decision"].exists()
        else None,
    }


def annotation_progress(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    paths = paths or default_paths()
    ids = expected_record_ids(paths)
    a_ids = {p.stem for p in paths["annotator_a"].glob("CA-*.json")}
    b_ids = {p.stem for p in paths["annotator_b"].glob("CA-*.json")}
    return {
        "n_expected": EXPECTED_N,
        "ann_a_complete": len(a_ids & set(ids)),
        "ann_b_complete": len(b_ids & set(ids)),
        "ann_a_missing": sorted(set(ids) - a_ids),
        "ann_b_missing": sorted(set(ids) - b_ids),
        "both_complete": sorted(set(ids) & a_ids & b_ids),
        "complete_pairs": len(set(ids) & a_ids & b_ids),
    }


def _load_annotation_dir(directory: Path, ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for rid in ids:
        path = directory / f"{rid}.json"
        if not path.exists():
            continue
        obj = load_json(path)
        if obj.get("record_id") != rid:
            raise Pilot120Error(f"annotation id mismatch in {path}")
        out[rid] = obj
    return out


def compute_final_protocol_agreement(
    paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    paths = paths or default_paths()
    ids = expected_record_ids(paths)
    progress = annotation_progress(paths)
    if progress["complete_pairs"] != EXPECTED_N:
        report = {
            "label": "final_protocol_annotation_agreement",
            "status": "not_started"
            if progress["complete_pairs"] == 0
            else "incomplete",
            "n_expected": EXPECTED_N,
            "n_complete_pairs": progress["complete_pairs"],
            "ann_a_complete": progress["ann_a_complete"],
            "ann_b_complete": progress["ann_b_complete"],
            "note": (
                "Populate after fresh A/B annotations. Do not copy pilot kappa numbers here. "
                "Historical pilot agreement remains labelled pilot_annotation_agreement."
            ),
            "pilot_annotation_agreement_ref": str(
                paths["pilot_kappa_strata"].relative_to(paths["root"]).as_posix()
            ),
        }
        dump_json(paths["agreement"], report)
        return report

    a = _load_annotation_dir(paths["annotator_a"], ids)
    b = _load_annotation_dir(paths["annotator_b"], ids)
    pairs = [(rid, a[rid], b[rid]) for rid in ids]

    metrics: dict[str, Any] = {}
    for field_name in CORE_AGREE_FIELDS + ("recommended_strategy", "primary_ambiguity_type", "risk_level"):
        y1 = [str(x[1].get(field_name)) for x in pairs]
        y2 = [str(x[2].get(field_name)) for x in pairs]
        raw = sum(u == v for u, v in zip(y1, y2)) / len(pairs)
        metrics[field_name] = {
            "cohen_kappa": cohen_kappa(y1, y2),
            "raw_agreement": raw,
            "n_disagree": sum(u != v for u, v in zip(y1, y2)),
        }

    # Ambiguity multilabel
    exact = 0
    jaccards: list[float] = []
    type_disagree = 0
    for _, aa, bb in pairs:
        sa = set(aa.get("ambiguity_types") or [])
        sb = set(bb.get("ambiguity_types") or [])
        if sa == sb:
            exact += 1
        else:
            type_disagree += 1
        if not sa and not sb:
            jaccards.append(1.0)
        else:
            jaccards.append(len(sa & sb) / len(sa | sb))
    metrics["ambiguity_types"] = {
        "exact_set_agreement": exact / len(pairs),
        "mean_jaccard": sum(jaccards) / len(jaccards),
        "n_set_disagreement": type_disagree,
    }

    # Capability class distribution on A (reporting only)
    metrics["capability_status_distribution_ann_a"] = dict(
        Counter(str(x[1].get("capability_status")) for x in pairs)
    )
    metrics["capability_status_distribution_ann_b"] = dict(
        Counter(str(x[2].get("capability_status")) for x in pairs)
    )
    metrics["terminal_strategy_distribution_ann_a"] = dict(
        Counter(str(x[1].get("terminal_strategy")) for x in pairs)
    )
    metrics["terminal_strategy_distribution_ann_b"] = dict(
        Counter(str(x[2].get("terminal_strategy")) for x in pairs)
    )

    disagreements = []
    for rid, aa, bb in pairs:
        fields = []
        if aa.get("terminal_strategy") != bb.get("terminal_strategy"):
            fields.append("terminal_strategy")
        if set(aa.get("ambiguity_types") or []) != set(bb.get("ambiguity_types") or []):
            fields.append("ambiguity_types")
        if aa.get("capability_status") != bb.get("capability_status"):
            fields.append("capability_status")
        if aa.get("record_validity") != bb.get("record_validity"):
            fields.append("record_validity")
        if fields:
            disagreements.append({"record_id": rid, "fields": fields})

    report = {
        "label": "final_protocol_annotation_agreement",
        "status": "complete",
        "n_expected": EXPECTED_N,
        "n_complete_pairs": EXPECTED_N,
        "metrics": metrics,
        "n_core_disagreement_records": len(disagreements),
        "disagreement_records": disagreements,
        "pilot_annotation_agreement": {
            "label": "pilot_annotation_agreement",
            "ref": str(paths["pilot_kappa_strata"].relative_to(paths["root"]).as_posix()),
            "note": "Historical (~0.95 terminal κ). Do not overwrite or mix with final-protocol metrics.",
        },
    }
    dump_json(paths["agreement"], report)
    return report


def build_disagreement_adjudication_queue(
    paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    paths = paths or default_paths()
    agreement = compute_final_protocol_agreement(paths)
    if agreement.get("status") != "complete":
        raise Pilot120Error(
            "cannot build adjudication queue before ANN-A and ANN-B are both 120/120"
        )
    ids = expected_record_ids(paths)
    a = _load_annotation_dir(paths["annotator_a"], ids)
    b = _load_annotation_dir(paths["annotator_b"], ids)
    packets_dir = paths["adjudication"] / "packets"
    packets_dir.mkdir(parents=True, exist_ok=True)
    queue = []
    for item in agreement["disagreement_records"]:
        rid = item["record_id"]
        packet = {
            "record_id": rid,
            "fields": item["fields"],
            "ann_a": {
                k: a[rid].get(k)
                for k in (
                    "terminal_strategy",
                    "ambiguity_types",
                    "capability_status",
                    "record_validity",
                    "strategy_sequence",
                    "confidence",
                )
            },
            "ann_b": {
                k: b[rid].get(k)
                for k in (
                    "terminal_strategy",
                    "ambiguity_types",
                    "capability_status",
                    "record_validity",
                    "strategy_sequence",
                    "confidence",
                )
            },
            "input": load_json(paths["inputs"] / f"{rid}.json"),
            "status": "pending",
            "decision_required_from": "ADJ-01 (once resolved) or recorded adjudicator",
        }
        dump_json(packets_dir / f"{rid}.json", packet)
        queue.append({"record_id": rid, "fields": item["fields"], "status": "pending"})
    payload = {
        "n_packets": len(queue),
        "packets": queue,
        "note": "Only genuine ANN-A/ANN-B disagreements. Raw A/B files remain immutable.",
    }
    dump_json(paths["adjudication"] / "pending_queue.json", payload)
    return payload


def _decision_complete(paths: dict[str, Path], rid: str) -> bool:
    path = paths["adjudication"] / "decisions" / f"{rid}.json"
    if not path.exists():
        return False
    obj = load_json(path)
    return obj.get("status") == "resolved" or obj.get("decisions") is not None


def assemble_final_gold(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    paths = paths or default_paths()
    if uses_pilot_adjudicated_gold(paths):
        return assemble_pilot_adjudicated_gold(paths)
    return assemble_final_protocol_gold(paths)


def assemble_pilot_adjudicated_gold(
    paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Promote existing Grok/GLM+adjudicated pilot gold onto repaired Pilot-120 source."""
    paths = paths or default_paths()
    if not uses_pilot_adjudicated_gold(paths):
        raise Pilot120Error("gold policy is not use_existing_pilot_adjudicated_gold")
    check = verify_pilot_adjudicated_gold(paths)
    if not check["ok"]:
        raise Pilot120Error(f"pilot gold not ready for freeze: {check}")

    ids = expected_record_ids(paths)
    gold_rows: list[dict[str, Any]] = []
    out_gold_dir = paths["root"] / "data" / "annotations" / "pilot_120_v1" / "gold"
    out_gold_dir.mkdir(parents=True, exist_ok=True)
    # Do NOT write into final_protocol/gold/ — that tree remains reserved for optional
    # future Steve/Ben final-protocol reannotation and must stay empty under this policy.

    for rid in ids:
        pilot = load_json(paths["pilot_gold"] / f"{rid}.json")
        gold = {
            "record_id": rid,
            "record_validity": pilot.get("record_validity"),
            "ambiguity_types": list(pilot.get("ambiguity_types") or []),
            "terminal_strategy": pilot.get("terminal_strategy"),
            "capability_status": pilot.get("capability_status"),
            "strategy_sequence": pilot.get("strategy_sequence"),
            "gold_lifecycle": "final_gold",
            "gold_status": pilot.get("gold_status"),
            "field_status": pilot.get("field_status"),
            "human_gate_required": False,
            "annotator_b_era": pilot.get("annotator_b_era"),
            "annotator_b_model": pilot.get("annotator_b_model"),
            "provenance": {
                **(pilot.get("provenance") or {}),
                "gold_policy": "use_existing_pilot_adjudicated_gold",
                "pilot_gold_sha256": sha256_file(paths["pilot_gold"] / f"{rid}.json"),
                "repaired_input_sha256": sha256_file(paths["inputs"] / f"{rid}.json"),
                "agreement_label": "pilot_annotation_agreement",
                "protocol": "pilot_adjudicated_gold_on_capability_repaired_source",
            },
        }
        if gold["terminal_strategy"] not in TERMINALS:
            raise Pilot120Error(f"{rid}: bad terminal {gold['terminal_strategy']!r}")
        dump_json(out_gold_dir / f"{rid}.json", gold)
        gold_rows.append(gold)

    out_jsonl = paths["frozen_gold_jsonl"]
    sha = write_jsonl(out_jsonl, gold_rows)
    # Mirror into final-protocol eval path used by config for continuity
    mirror = paths["final_protocol"] / "eval" / "pilot_120_final_gold.jsonl"
    write_jsonl(mirror, gold_rows)
    summary = {
        "n_gold": len(gold_rows),
        "gold_jsonl": str(out_jsonl.relative_to(paths["root"]).as_posix()),
        "mirror_jsonl": str(mirror.relative_to(paths["root"]).as_posix()),
        "sha256": sha,
        "gold_policy": "use_existing_pilot_adjudicated_gold",
        "agreement_label": "pilot_annotation_agreement",
        "terminal_distribution": check["terminal_distribution"],
        "note": (
            "Labels copied from annotations/manual_kappa_v7/gold; "
            "paired with capability-repaired Pilot-120 source. "
            "Not a Steven James / Benjamin Rosman final-protocol reannotation."
        ),
    }
    dump_json(paths["root"] / "data" / "annotations" / "pilot_120_v1" / "gold_manifest.json", summary)
    dump_json(paths["final_protocol"] / "gold_manifest.json", summary)
    return summary


def assemble_final_protocol_gold(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    paths = paths or default_paths()
    adj = adj01_status(paths)
    if adj["unresolved"]:
        raise Pilot120Error(
            "ADJ-01 unresolved: cannot assemble final gold. "
            "Record an explicit ADJ01_RESOLUTION.json first."
        )
    agreement = compute_final_protocol_agreement(paths)
    if agreement.get("status") != "complete":
        raise Pilot120Error("ANN-A/ANN-B incomplete; cannot assemble final gold")

    ids = expected_record_ids(paths)
    a = _load_annotation_dir(paths["annotator_a"], ids)
    b = _load_annotation_dir(paths["annotator_b"], ids)
    disagree_ids = {d["record_id"] for d in agreement["disagreement_records"]}
    missing_decisions = [rid for rid in sorted(disagree_ids) if not _decision_complete(paths, rid)]
    if missing_decisions:
        raise Pilot120Error(
            "adjudication incomplete for: " + ", ".join(missing_decisions[:20])
        )

    gold_rows: list[dict[str, Any]] = []
    paths["gold"].mkdir(parents=True, exist_ok=True)
    for rid in ids:
        aa, bb = a[rid], b[rid]
        if rid in disagree_ids:
            decision = load_json(paths["adjudication"] / "decisions" / f"{rid}.json")
            decisions = decision.get("decisions") or {}
            terminal = (decisions.get("terminal_strategy") or {}).get("value")
            if terminal is None and aa.get("terminal_strategy") == bb.get("terminal_strategy"):
                terminal = aa.get("terminal_strategy")
            amb_a = set(aa.get("ambiguity_types") or [])
            amb_b = set(bb.get("ambiguity_types") or [])
            amb = set(amb_a & amb_b)
            for lab in decisions.get("ambiguity_types_add") or []:
                amb.add(lab)
            for lab in decisions.get("ambiguity_types_remove") or []:
                amb.discard(lab)
            if "ambiguity_types" not in decisions and amb_a == amb_b:
                amb = amb_a
            cap = (decisions.get("capability_status") or {}).get("value")
            if cap is None and aa.get("capability_status") == bb.get("capability_status"):
                cap = aa.get("capability_status")
            validity = (decisions.get("record_validity") or {}).get("value")
            if validity is None and aa.get("record_validity") == bb.get("record_validity"):
                validity = aa.get("record_validity")
            lifecycle = "adjudicated_provisional"
            if decision.get("human_gate_required"):
                lifecycle = "human_review_required"
            elif decision.get("promote_final_gold"):
                lifecycle = "final_gold"
            field_status = "adjudicated"
        else:
            terminal = aa.get("terminal_strategy")
            amb = set(aa.get("ambiguity_types") or [])
            cap = aa.get("capability_status")
            validity = aa.get("record_validity")
            lifecycle = "auto_agreed"
            field_status = "auto_agree"
            decision = None

        if terminal not in TERMINALS:
            raise Pilot120Error(f"{rid}: invalid/missing terminal_strategy={terminal!r}")
        if lifecycle == "human_review_required":
            raise Pilot120Error(
                f"{rid}: human_review_required must not enter final gold export"
            )

        gold = {
            "record_id": rid,
            "record_validity": validity,
            "ambiguity_types": sorted(amb),
            "terminal_strategy": terminal,
            "capability_status": cap,
            "gold_lifecycle": "final_gold" if lifecycle in {"auto_agreed", "final_gold", "adjudicated_provisional"} else lifecycle,
            "field_status": {
                "terminal_strategy": field_status,
                "ambiguity_types": field_status,
                "capability_status": field_status,
                "record_validity": field_status,
            },
            "provenance": {
                "annotator_a_sha256": sha256_file(paths["annotator_a"] / f"{rid}.json"),
                "annotator_b_sha256": sha256_file(paths["annotator_b"] / f"{rid}.json"),
                "input_sha256": sha256_file(paths["inputs"] / f"{rid}.json"),
                "adjudication_decision_sha256": (
                    sha256_file(paths["adjudication"] / "decisions" / f"{rid}.json")
                    if decision is not None
                    else None
                ),
                "protocol": "final_protocol_reannotation",
            },
            "human_gate_required": False,
        }
        dump_json(paths["gold"] / f"{rid}.json", gold)
        gold_rows.append(gold)

    out_jsonl = paths["frozen_gold_jsonl"]
    sha = write_jsonl(out_jsonl, gold_rows)
    mirror = paths["final_protocol"] / "eval" / "pilot_120_final_gold.jsonl"
    write_jsonl(mirror, gold_rows)
    summary = {
        "n_gold": len(gold_rows),
        "gold_jsonl": str(out_jsonl.relative_to(paths["root"]).as_posix()),
        "mirror_jsonl": str(mirror.relative_to(paths["root"]).as_posix()),
        "sha256": sha,
        "n_adjudicated": len(disagree_ids),
        "n_auto_agreed": EXPECTED_N - len(disagree_ids),
    }
    dump_json(paths["final_protocol"] / "gold_manifest.json", summary)
    return summary


def compare_to_historical_pilot(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    paths = paths or default_paths()
    ids = expected_record_ids(paths)
    gold_dir = paths["root"] / "data" / "annotations" / "pilot_120_v1" / "gold"
    if not gold_dir.exists() or len(list(gold_dir.glob("CA-*.json"))) != EXPECTED_N:
        # fall back to final-protocol gold dir
        gold_dir = paths["gold"]
    if len(list(gold_dir.glob("CA-*.json"))) != EXPECTED_N:
        raise Pilot120Error("final gold incomplete; refuse historical comparison")
    changed = []
    unchanged = 0
    for rid in ids:
        final = load_json(gold_dir / f"{rid}.json")
        pilot_path = paths["pilot_gold"] / f"{rid}.json"
        if not pilot_path.exists():
            changed.append({"record_id": rid, "reason": "missing_pilot_gold"})
            continue
        pilot = load_json(pilot_path)
        dims = []
        if final.get("terminal_strategy") != pilot.get("terminal_strategy"):
            dims.append("terminal_strategy")
        if set(final.get("ambiguity_types") or []) != set(pilot.get("ambiguity_types") or []):
            dims.append("ambiguity_types")
        if final.get("capability_status") != pilot.get("capability_status"):
            dims.append("capability_status")
        if dims:
            changed.append(
                {
                    "record_id": rid,
                    "dimensions_changed": dims,
                    "pilot": {
                        "terminal_strategy": pilot.get("terminal_strategy"),
                        "capability_status": pilot.get("capability_status"),
                        "ambiguity_types": pilot.get("ambiguity_types"),
                    },
                    "final": {
                        "terminal_strategy": final.get("terminal_strategy"),
                        "capability_status": final.get("capability_status"),
                        "ambiguity_types": final.get("ambiguity_types"),
                    },
                }
            )
        else:
            unchanged += 1

    repair = load_json(paths["repair_log"])
    repaired_ids = {c["record_id"] for c in repair.get("changes") or []}
    repair_terminal_changes = [
        c for c in changed if c.get("record_id") in repaired_ids and "terminal_strategy" in c.get("dimensions_changed", [])
    ]
    report = {
        "n_unchanged": unchanged,
        "n_changed": len(changed),
        "changed": changed,
        "repaired_capability_context_ids": sorted(repaired_ids),
        "repaired_ids_with_terminal_strategy_change_vs_pilot": [
            c["record_id"] for c in repair_terminal_changes
        ],
        "note": (
            "Under use_existing_pilot_adjudicated_gold, label comparison should be identity. "
            "Source capability_context repairs are separate from label changes."
        ),
    }
    dump_json(
        paths["root"] / "data" / "annotations" / "pilot_120_v1" / "COMPARE_TO_PILOT_GOLD.json",
        report,
    )
    return report


def freeze_guard_blocks(paths: dict[str, Path] | None = None) -> list[str]:
    """Return human-readable blockers; empty list means freeze may proceed."""
    paths = paths or default_paths()
    blocks: list[str] = []
    try:
        run_preflight(paths)
    except Pilot120Error as exc:
        blocks.append(f"preflight: {exc}")

    if uses_pilot_adjudicated_gold(paths):
        check = verify_pilot_adjudicated_gold(paths)
        if not check["ok"]:
            blocks.append(f"pilot adjudicated gold incomplete: {check}")
        return blocks

    progress = annotation_progress(paths)
    if progress["ann_a_complete"] != EXPECTED_N:
        blocks.append(
            f"ANN-A incomplete: {progress['ann_a_complete']}/{EXPECTED_N} "
            "(official annotator: Steven James / ANN-A)"
        )
    if progress["ann_b_complete"] != EXPECTED_N:
        blocks.append(
            f"ANN-B incomplete: {progress['ann_b_complete']}/{EXPECTED_N} "
            "(official annotator: Benjamin Rosman / ANN-B)"
        )

    adj = adj01_status(paths)
    if adj["unresolved"]:
        blocks.append(
            "ADJ-01 unresolved: name official adjudicator in "
            "annotations/manual_kappa_v7_final_protocol/adjudication/ADJ01_RESOLUTION.json"
        )

    if progress["complete_pairs"] == EXPECTED_N:
        agreement = compute_final_protocol_agreement(paths)
        disagree = {d["record_id"] for d in agreement.get("disagreement_records") or []}
        missing = [rid for rid in sorted(disagree) if not _decision_complete(paths, rid)]
        if missing:
            blocks.append(
                f"adjudication incomplete for {len(missing)} disagreement(s); "
                f"examples: {', '.join(missing[:10])}"
            )
        gold_n = len(list(paths["gold"].glob("CA-*.json")))
        if gold_n != EXPECTED_N:
            blocks.append(f"final gold incomplete: {gold_n}/{EXPECTED_N}")

    return blocks


def write_status(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    paths = paths or default_paths()
    if not paths["canonical_jsonl"].exists():
        materialize_canonical_source(paths)
    try:
        preflight = run_preflight(paths)
        preflight_ok = True
    except Pilot120Error as exc:
        preflight = {"status": "preflight_fail", "error": str(exc)}
        preflight_ok = False
        pre_path = paths["root"] / "data" / "annotations" / "pilot_120_v1" / "PREFLIGHT.json"
        if pre_path.exists():
            preflight = load_json(pre_path)

    progress = annotation_progress(paths)
    blocks = freeze_guard_blocks(paths)
    if not preflight_ok and not any(b.startswith("preflight:") for b in blocks):
        blocks = [f"preflight: {preflight.get('error', 'failed')}", *blocks]
    claim_allowed = not blocks
    policy = load_gold_policy(paths)
    claim = honest_freeze_claim(paths) if claim_allowed else (
        "Pilot-120 v1: PREFLIGHT READY; GOLD POLICY SET TO PILOT-ADJUDICATED; FREEZE PENDING"
        if uses_pilot_adjudicated_gold(paths)
        else "Pilot-120 v1: PREFLIGHT READY; FINAL-PROTOCOL ANNOTATION / ADJUDICATION / FREEZE GATES OPEN"
    )
    status = {
        "claim": claim,
        "claim_allowed": claim_allowed,
        "gold_policy": policy,
        "evaluation_only": True,
        "must_not_train_or_select_on_pilot_120": True,
        "source_sha256": sha256_file(paths["canonical_jsonl"])
        if paths["canonical_jsonl"].exists()
        else None,
        "preflight": preflight,
        "annotation_progress": progress,
        "adj01": adj01_status(paths),
        "adj01_required_for_this_freeze": bool(policy.get("adj01_required_for_this_freeze", True)),
        "steve_ben_reannotation_required": bool(
            policy.get("steve_ben_reannotation_required", True)
        ),
        "freeze_blockers": blocks,
        "human_gate": {
            "required": bool(blocks) and not uses_pilot_adjudicated_gold(paths),
            "ann_a": "Steven James",
            "ann_b": "Benjamin Rosman",
            "instructions": str(
                (
                    paths["final_protocol"] / "HUMAN_ANNOTATION_GATE.md"
                ).relative_to(paths["root"]).as_posix()
            ),
            "note": (
                "Under use_existing_pilot_adjudicated_gold, Steve/Ben reannotation is not required."
                if uses_pilot_adjudicated_gold(paths)
                else "Final-protocol reannotation still required."
            ),
        },
        "pilot_annotation_agreement_label_only": "pilot_annotation_agreement",
        "final_protocol_agreement_label": "final_protocol_annotation_agreement",
        "agreement_used_for_freeze": (
            "pilot_annotation_agreement"
            if uses_pilot_adjudicated_gold(paths)
            else "final_protocol_annotation_agreement"
        ),
    }
    dump_json(paths["status"], status)
    return status


def freeze(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    paths = paths or default_paths()
    blocks = freeze_guard_blocks(paths)
    if blocks:
        write_status(paths)
        raise Pilot120Error(
            "Refuse freeze — open gates:\n- " + "\n- ".join(blocks)
        )
    gold_summary = assemble_final_gold(paths)
    compare = compare_to_historical_pilot(paths)
    preflight = run_preflight(paths)

    freeze_dir = paths["freeze_dir"]
    freeze_dir.mkdir(parents=True, exist_ok=True)

    hashes = {
        "source_canonical_jsonl": sha256_file(paths["canonical_jsonl"]),
        "final_gold_jsonl": gold_summary["sha256"],
        "gold_policy": sha256_file(paths["gold_policy"]),
        "subset_manifest": sha256_file(paths["subset_manifest"]),
        "handbook_v7": sha256_file(
            paths["final_protocol"] / "briefs" / "handbook_v7.md"
        ),
        "output_schema_v7": sha256_file(
            paths["final_protocol"] / "briefs" / "output_schema_v7.json"
        ),
        "config_pilot_120_v1": sha256_file(paths["config"])
        if paths["config"].exists()
        else None,
        "pilot_kappa_strata": sha256_file(paths["pilot_kappa_strata"])
        if paths["pilot_kappa_strata"].exists()
        else None,
        "pilot_gold_manifest": sha256_file(paths["pilot_gold_manifest"])
        if paths["pilot_gold_manifest"].exists()
        else None,
    }

    if uses_pilot_adjudicated_gold(paths):
        ids = expected_record_ids(paths)
        pilot_blob = "".join(
            (paths["pilot_gold"] / f"{rid}.json").read_text(encoding="utf-8") for rid in ids
        )
        hashes["pilot_gold_corpus"] = sha256_text(pilot_blob)
        if paths["agreement"].exists():
            hashes["final_protocol_agreement_placeholder"] = sha256_file(paths["agreement"])
    else:
        ids = expected_record_ids(paths)
        a_blob = "".join(
            (paths["annotator_a"] / f"{rid}.json").read_text(encoding="utf-8") for rid in ids
        )
        b_blob = "".join(
            (paths["annotator_b"] / f"{rid}.json").read_text(encoding="utf-8") for rid in ids
        )
        hashes["annotator_a_corpus"] = sha256_text(a_blob)
        hashes["annotator_b_corpus"] = sha256_text(b_blob)
        hashes["final_protocol_agreement"] = sha256_file(paths["agreement"])
        adj_dir = paths["adjudication"] / "decisions"
        adj_files = sorted(adj_dir.glob("CA-*.json")) if adj_dir.exists() else []
        if adj_files:
            hashes["adjudication_decisions_corpus"] = sha256_text(
                "".join(p.read_text(encoding="utf-8") for p in adj_files)
            )

    claim = honest_freeze_claim(paths)
    manifest = {
        "freeze_id": PILOT_120_VERSION,
        "claim": claim,
        "gold_policy": load_gold_policy(paths),
        "evaluation_only": True,
        "immutable": True,
        "n_records": EXPECTED_N,
        "record_ids": ids,
        "hashes": hashes,
        "gold": gold_summary,
        "compare_to_pilot": {
            "n_changed": compare["n_changed"],
            "n_unchanged": compare["n_unchanged"],
            "repaired_ids_with_terminal_strategy_change_vs_pilot": compare[
                "repaired_ids_with_terminal_strategy_change_vs_pilot"
            ],
        },
        "preflight_status": preflight["status"],
        "loader_guard": "ambiguity_manager.evaluation.pilot_120.assert_evaluation_only",
        "agreement_label": (
            "pilot_annotation_agreement"
            if uses_pilot_adjudicated_gold(paths)
            else "final_protocol_annotation_agreement"
        ),
    }
    manifest_path = freeze_dir / "FROZEN_MANIFEST.json"
    if manifest_path.exists():
        existing = load_json(manifest_path)
        dump_json(freeze_dir / "FROZEN_MANIFEST.json.tmp", manifest)
        tmp_sha = sha256_file(freeze_dir / "FROZEN_MANIFEST.json.tmp")
        existing_sha = sha256_file(manifest_path)
        (freeze_dir / "FROZEN_MANIFEST.json.tmp").unlink(missing_ok=True)
        if tmp_sha != existing_sha and json.dumps(existing, sort_keys=True) != json.dumps(
            manifest, sort_keys=True
        ):
            # Allow overwrite when gold policy changes from blocked→pilot-adjudicated freeze.
            # Still refuse silent mutation of an already-frozen identical-id claim with different bytes
            # unless the previous freeze was absent or claim_allowed was false historically.
            if existing.get("immutable") and existing.get("claim") == claim:
                raise Pilot120Error(
                    "frozen manifest already exists and differs; refusing overwrite"
                )
    dump_json(manifest_path, manifest)
    hashes["frozen_manifest"] = sha256_file(manifest_path)
    manifest["hashes"] = hashes
    dump_json(manifest_path, manifest)
    write_status(paths)
    return manifest


def assert_evaluation_only(purpose: str) -> None:
    """Hard guard: Pilot-120 must never be used for training or model selection."""
    purpose_l = purpose.strip().lower()
    forbidden = ("train", "training", "finetune", "fine-tune", "checkpoint_select", "model_selection", "select_adapter")
    if any(tok in purpose_l for tok in forbidden):
        raise Pilot120Error(
            f"Pilot-120 is evaluation-only; refused purpose={purpose!r}"
        )


def build_blind_packages(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    """Create ANN-A / ANN-B delivery packages without historical labels."""
    paths = paths or default_paths()
    run_preflight(paths)
    ids = expected_record_ids(paths)
    packages = paths["packages_dir"]
    # Deterministic but different orderings per annotator
    order_a = list(ids)
    order_b = list(reversed(ids))
    built = {}
    for role, person, order in (
        ("ANN-A", "Steven James", order_a),
        ("ANN-B", "Benjamin Rosman", order_b),
    ):
        pkg_dir = packages / role.lower().replace("-", "_")
        if pkg_dir.exists():
            for p in pkg_dir.rglob("*"):
                if p.is_file():
                    p.unlink()
        records_dir = pkg_dir / "records"
        submissions_dir = pkg_dir / "submissions_templates"
        records_dir.mkdir(parents=True, exist_ok=True)
        submissions_dir.mkdir(parents=True, exist_ok=True)
        # copy briefs
        briefs_src = paths["final_protocol"] / "briefs"
        briefs_dst = pkg_dir / "briefs"
        briefs_dst.mkdir(parents=True, exist_ok=True)
        for name in ("annotator_brief.md", "handbook_v7.md", "output_schema_v7.json", "input_schema_v7.json"):
            src = briefs_src / name
            (briefs_dst / name).write_bytes(src.read_bytes())

        index = []
        for i, rid in enumerate(order):
            rec = load_json(paths["inputs"] / f"{rid}.json")
            leaked = sorted(set(rec) & FORBIDDEN_VIEW_KEYS)
            if leaked:
                raise Pilot120Error(f"package leak in {rid}: {leaked}")
            view = {
                "record_order_index": i,
                "record_id": rid,
                "command": rec["command"],
                "dialogue_history": rec.get("dialogue_history") or [],
                "scene_context": rec["scene_context"],
                "capability_context": rec["capability_context"],
            }
            dump_json(records_dir / f"{i:03d}_{rid}.json", view)
            template = {
                "record_id": rid,
                "record_validity": "<valid|invalid_or_inconsistent>",
                "validity_issue": None,
                "intent": "<short intent paraphrase>",
                "resolved_slots": {},
                "ambiguity_present": True,
                "ambiguity_types": [],
                "primary_ambiguity_type": None,
                "compound_ambiguity": True,
                "compound_ambiguity_count": 0,
                "risk_level": "<none|low|medium|high>",
                "risk_factors": [],
                "capability_status": "<capable|conditionally_capable|incapable|unauthorized|unsafe>",
                "recommended_strategy": "<execute|clarify|silently_resolve|face_preserving_rejection|multi_step>",
                "terminal_strategy": "<execute|clarify|face_preserving_rejection>",
                "strategy_sequence": [],
                "canonical_outcome": {},
                "evidence": [],
                "confidence": 0.0,
                "annotator_role": role,
            }
            dump_json(submissions_dir / f"{rid}.template.json", template)
            index.append({"record_order_index": i, "record_id": rid})

        start = f"""# START HERE — {person} ({role})

You are the official **{role}** annotator for **Pilot-120 final-protocol** reannotation.

## What to annotate

Exactly **120** records under `records/` in the listed order (`record_order_index`).

## Blindness rules

- Use only: this START_HERE, `briefs/`, and **one** `records/` file at a time.
- Do **NOT** open:
  - `annotations/manual_kappa_v7/` (pilot ANN-A/ANN-B, gold, adjudication, kappa)
  - `annotations/private_owner_qa_v7/`
  - the other annotator package
  - any historical kappa / gold / agreement numbers
- Do **NOT** discuss labels with the other annotator before both submissions are complete.

## How to submit

1. For each record, write a complete v7 annotation JSON (see `briefs/output_schema_v7.json`).
2. Save as `CA-XXXX.json` (use the real record_id).
3. Deliver the folder of 120 JSON files for import:

```text
python -m ambiguity_manager.evaluation.pilot_120_cli import-annotations \\
  --role {role} \\
  --from-dir <YOUR_SUBMISSION_DIR>
```

Validate one file:

```text
python -m ambiguity_manager.evaluation.pilot_120_cli validate-annotation \\
  --annotation <CA-XXXX.json> \\
  --input annotations/manual_kappa_v7_final_protocol/inputs/CA-XXXX.json
```

## Role identity

- Official ANN-A: Steven James
- Official ANN-B: Benjamin Rosman
- AUTHOR-01 must not act as ANN-A or ANN-B on this set
"""
        (pkg_dir / "START_HERE.md").write_text(start, encoding="utf-8")
        dump_json(pkg_dir / "record_order.json", {"role": role, "person": person, "order": index})

        zip_path = packages / f"Pilot120_FinalProtocol_{role}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in pkg_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, arcname=str(file_path.relative_to(pkg_dir).as_posix()))
        built[role] = {
            "dir": str(pkg_dir.relative_to(paths["root"]).as_posix()),
            "zip": str(zip_path.relative_to(paths["root"]).as_posix()),
            "sha256": sha256_file(zip_path),
            "n_records": len(order),
        }
    dump_json(packages / "PACKAGE_MANIFEST.json", built)
    return built


def import_annotations(
    *,
    role: str,
    from_dir: Path,
    paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    paths = paths or default_paths()
    role = role.upper().replace("_", "-")
    if role not in {"ANN-A", "ANN-B"}:
        raise Pilot120Error("role must be ANN-A or ANN-B")
    dest = paths["annotator_a"] if role == "ANN-A" else paths["annotator_b"]
    dest.mkdir(parents=True, exist_ok=True)
    ids = expected_record_ids(paths)
    schema_path = paths["final_protocol"] / "briefs" / "output_schema_v7.json"
    schema = load_json(schema_path)
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover
        raise Pilot120Error("jsonschema is required to import annotations") from exc

    imported = []
    for rid in ids:
        # accept CA-XXXX.json or any *CA-XXXX*.json
        candidates = list(from_dir.glob(f"{rid}.json"))
        if not candidates:
            candidates = list(from_dir.rglob(f"{rid}.json"))
        if not candidates:
            continue
        obj = load_json(candidates[0])
        jsonschema.validate(obj, schema)
        if obj.get("record_id") != rid:
            raise Pilot120Error(f"{candidates[0]} record_id mismatch")
        # Refuse if file embeds private/historical keys
        leaked = sorted(set(obj) & {"pilot_gold", "owner_route", "qa_capability_class"})
        if leaked:
            raise Pilot120Error(f"{rid} submission contains forbidden keys {leaked}")
        dump_json(dest / f"{rid}.json", obj)
        imported.append(rid)
    progress = annotation_progress(paths)
    compute_final_protocol_agreement(paths)
    write_status(paths)
    return {"role": role, "imported": len(imported), "progress": progress}


def validate_annotation_file(annotation_path: Path, input_path: Path) -> list[str]:
    schema = load_json(
        project_root()
        / "annotations"
        / "manual_kappa_v7_final_protocol"
        / "briefs"
        / "output_schema_v7.json"
    )
    import jsonschema

    obj = load_json(annotation_path)
    inp = load_json(input_path)
    errors: list[str] = []
    try:
        jsonschema.validate(obj, schema)
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    if obj.get("record_id") != inp.get("record_id"):
        errors.append("record_id mismatch vs input")
    return errors


def _safe_div(n: float, d: float) -> float | None:
    if d == 0:
        return None
    return n / d


def _prf(y_true: Sequence[str], y_pred: Sequence[str], labels: Iterable[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for lab in labels:
        tp = sum(t == lab and p == lab for t, p in zip(y_true, y_pred))
        fp = sum(t != lab and p == lab for t, p in zip(y_true, y_pred))
        fn = sum(t == lab and p != lab for t, p in zip(y_true, y_pred))
        prec = _safe_div(tp, tp + fp)
        rec = _safe_div(tp, tp + fn)
        f1 = None if prec is None or rec is None or (prec + rec) == 0 else 2 * prec * rec / (prec + rec)
        out[lab] = {"precision": prec, "recall": rec, "f1": f1, "support": sum(t == lab for t in y_true)}
    f1s = [v["f1"] for v in out.values() if v["f1"] is not None and v["support"] > 0]
    return {"per_class": out, "macro_f1": (sum(f1s) / len(f1s) if f1s else None)}


def evaluate_predictions(
    predictions_path: Path,
    *,
    config_path: Path | None = None,
    paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    paths = paths or default_paths()
    assert_evaluation_only("evaluate")
    config = load_json(config_path or paths["config"])
    gold_path = paths["root"] / config["gold_jsonl"]
    if not gold_path.exists():
        raise Pilot120Error(
            f"gold not frozen/available at {gold_path}; complete annotation gates first"
        )
    gold_rows = {r["record_id"]: r for r in load_jsonl(gold_path)}
    preds_list = load_jsonl(predictions_path)
    # Never drop failed predictions from denominators
    pred_by_id: dict[str, dict[str, Any]] = {}
    duplicates = []
    for row in preds_list:
        rid = str(row.get("record_id") or "")
        if rid in pred_by_id:
            duplicates.append(rid)
        pred_by_id[rid] = row
    if duplicates:
        raise Pilot120Error(f"duplicate predictions for: {duplicates[:10]}")

    ids = expected_record_ids(paths)
    y_true_term: list[str] = []
    y_pred_term: list[str] = []
    y_true_cap: list[str] = []
    y_pred_cap: list[str] = []
    schema_valid = 0
    failures = 0
    exact_set = 0
    # multilabel micro counts
    tp = fp = fn = 0
    per_label = Counter()
    per_label_tp = Counter()
    per_label_fp = Counter()
    per_label_fn = Counter()
    latency = []
    tokens = []
    confusion: dict[str, Counter] = {t: Counter() for t in TERMINALS}

    for rid in ids:
        g = gold_rows[rid]
        p = pred_by_id.get(rid)
        if p is None:
            failures += 1
            y_true_term.append(str(g["terminal_strategy"]))
            y_pred_term.append("<missing>")
            y_true_cap.append(str(g.get("capability_status")))
            y_pred_cap.append("<missing>")
            gt = set(g.get("ambiguity_types") or [])
            fn += len(gt)
            for lab in gt:
                per_label_fn[lab] += 1
            continue
        if p.get("error") or p.get("failed") is True:
            failures += 1
        else:
            schema_valid += 1
        gt_term = str(g["terminal_strategy"])
        pr_term = str(p.get("terminal_strategy") or "<missing>")
        y_true_term.append(gt_term)
        y_pred_term.append(pr_term)
        confusion.setdefault(gt_term, Counter())[pr_term] += 1
        y_true_cap.append(str(g.get("capability_status")))
        y_pred_cap.append(str(p.get("capability_status") or "<missing>"))
        gt = set(g.get("ambiguity_types") or [])
        pr = set(p.get("ambiguity_types") or [])
        if gt == pr:
            exact_set += 1
        tp += len(gt & pr)
        fp += len(pr - gt)
        fn += len(gt - pr)
        for lab in gt | pr:
            per_label[lab] += 1
            if lab in gt & pr:
                per_label_tp[lab] += 1
            elif lab in pr - gt:
                per_label_fp[lab] += 1
            elif lab in gt - pr:
                per_label_fn[lab] += 1
        if "latency_ms" in p:
            latency.append(float(p["latency_ms"]))
        if "tokens" in p:
            tokens.append(float(p["tokens"]))

    term_metrics = _prf(y_true_term, y_pred_term, sorted(set(y_true_term) | set(y_pred_term)))
    cap_metrics = _prf(y_true_cap, y_pred_cap, sorted(set(y_true_cap) | set(y_pred_cap)))
    micro_p = _safe_div(tp, tp + fp)
    micro_r = _safe_div(tp, tp + fn)
    micro_f1 = (
        None
        if micro_p is None or micro_r is None or (micro_p + micro_r) == 0
        else 2 * micro_p * micro_r / (micro_p + micro_r)
    )
    label_f1s = []
    per_label_out = {}
    for lab in sorted(set(per_label_tp) | set(per_label_fp) | set(per_label_fn)):
        p_ = _safe_div(per_label_tp[lab], per_label_tp[lab] + per_label_fp[lab])
        r_ = _safe_div(per_label_tp[lab], per_label_tp[lab] + per_label_fn[lab])
        f_ = None if p_ is None or r_ is None or (p_ + r_) == 0 else 2 * p_ * r_ / (p_ + r_)
        if f_ is not None:
            label_f1s.append(f_)
        per_label_out[lab] = {"precision": p_, "recall": r_, "f1": f_}

    report = {
        "n_gold": EXPECTED_N,
        "n_predictions_rows": len(preds_list),
        "terminal_strategy": {
            "accuracy": sum(t == p for t, p in zip(y_true_term, y_pred_term)) / EXPECTED_N,
            "macro_f1": term_metrics["macro_f1"],
            "per_class": term_metrics["per_class"],
            "confusion_matrix": {k: dict(v) for k, v in confusion.items()},
        },
        "ambiguity_types": {
            "micro_f1": micro_f1,
            "macro_f1": (sum(label_f1s) / len(label_f1s) if label_f1s else None),
            "exact_set_accuracy": exact_set / EXPECTED_N,
            "per_label": per_label_out,
        },
        "capability_status": {
            "accuracy": sum(t == p for t, p in zip(y_true_cap, y_pred_cap)) / EXPECTED_N,
            "macro_f1": cap_metrics["macro_f1"],
            "per_class": cap_metrics["per_class"],
        },
        "operational": {
            "schema_valid_rate": schema_valid / EXPECTED_N,
            "failure_error_rate": failures / EXPECTED_N,
            "latency_ms_mean": (sum(latency) / len(latency) if latency else None),
            "tokens_mean": (sum(tokens) / len(tokens) if tokens else None),
            "denominator": EXPECTED_N,
            "note": "Failed/missing predictions remain in denominators.",
        },
        "config": str((config_path or paths["config"]).as_posix()),
        "gold_sha256": sha256_file(gold_path),
        "predictions_sha256": sha256_file(predictions_path),
    }
    return report
