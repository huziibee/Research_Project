"""T27B structured-emission recovery datasets.

Builds:
- t27b_diagnostic_dev_v1 (12 source_dev, diagnostic only)
- t27b_final_smoke_v1 (8 sealed source_dev)
- qlora_structured_emission_recovery_v1 (128 source_train)

CPU-only. Does not import torch/transformers/peft/bitsandbytes/accelerate/vllm/requests.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ambiguity_manager.data.model_selection_set import CALIBRATION_ID_RE, FUTURE_MANUAL_ID_RES
from ambiguity_manager.data.source_splits import (
    FORBIDDEN_DATASETS,
    PRIMARY_ALLOWED_DATASETS,
)
from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.io_guard import resolve_writable_path
from ambiguity_manager.model.full_schema_envelope import (
    FULL_SCHEMA_ENVELOPE_ID,
    FullSchemaEnvelopeError,
    build_full_schema_envelope,
    load_envelope_policy,
)
from ambiguity_manager.model.full_schema_token_masking import (
    DeterministicCharTokenizer,
    build_masked_sequence_from_envelope,
)
from ambiguity_manager.model.qlora_smoke_data import (
    CATEGORY_SPECS,
    categorize_entry,
    load_record_manifest_rows,
)
from ambiguity_manager.model.qlora_task_aligned_smoke_data import (
    STRUCTURED_TARGET_STRONG,
    STRUCTURED_TARGET_TASK,
    build_split_pool,
)
from ambiguity_manager.model.t27b_prompt_contract import build_t27b_inference_prompt
from ambiguity_manager.model.training_target_packaging import load_training_target_policy_strict
from ambiguity_manager.paths import ProjectPaths

PROGRAMME_ID = "t27b_structured_emission_recovery_v1"
PROGRAMME_VERSION = "1.0.0"
SEED = 20260723

DIAGNOSTIC_DIR_REL = "data/development/t27b_diagnostic_dev_v1"
FINAL_SMOKE_DIR_REL = "data/development/t27b_final_smoke_v1"
TRAIN_DIR_REL = "data/development/qlora_structured_emission_recovery_v1"

TARGET_DIAGNOSTIC_COUNT = 12
TARGET_FINAL_COUNT = 8
TARGET_TRAIN_COUNT = 128

# Hard floors so the 128-set cannot collapse to one primary dataset.
MIN_TRAIN_PER_DATASET: dict[str, int] = {
    "ambik": 20,
    "clara": 20,
    "codraw_icr_v2": 20,
    "indirect_requests": 8,
    "vague": 8,
}
MIN_DISTINCT_TRAIN_DATASETS = 3

JOB6059_VAL_IDS: frozenset[str] = frozenset(
    {"clara:1003", "clara:1180", "clara:1349", "codraw_icr_v2:4784"}
)

MODEL_SELECTION_SET_REL = "data/development/model_selection_v1/record_ids.json"


class T27BDatasetError(RuntimeError):
    """Raised when T27B datasets cannot be built safely."""


def _root(root: Path | None) -> Path:
    return root if root is not None else ProjectPaths.from_repo_root().root


def _digest(seed: int, key: str) -> str:
    return hashlib.sha256(f"{seed}:{key}".encode("utf-8")).hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    target = resolve_writable_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [canonical_json_bytes(row).decode("utf-8") for row in rows]
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    target = resolve_writable_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json_bytes(payload).decode("utf-8") + "\n", encoding="utf-8")


def _assert_no_leakage_id(record_id: str) -> None:
    if record_id in JOB6059_VAL_IDS:
        raise T27BDatasetError(f"job6059_val_id_forbidden:{record_id}")
    if CALIBRATION_ID_RE.match(record_id):
        raise T27BDatasetError(f"calibration_id_forbidden:{record_id}")
    if any(pattern.match(record_id) for pattern in FUTURE_MANUAL_ID_RES):
        raise T27BDatasetError(f"future_manual_id_forbidden:{record_id}")


def _load_model_selection_ids(root: Path) -> set[str]:
    path = root / MODEL_SELECTION_SET_REL
    if not path.is_file():
        alt = root / "data/development/model_selection_v1/manifest.json"
        if alt.is_file():
            payload = json.loads(alt.read_text(encoding="utf-8"))
            ids = payload.get("record_ids") or payload.get("ids") or []
            return {str(x) for x in ids}
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {str(x) for x in payload}
    ids = payload.get("record_ids") or payload.get("ids") or []
    return {str(x) for x in ids}


def _try_envelope_only(
    entry: dict[str, Any],
    *,
    envelope_policy: dict[str, Any],
    training_policy: dict[str, Any],
    require_production_validation: bool = False,
) -> Any | None:
    try:
        return build_full_schema_envelope(
            entry["record"],
            entry["eligibility"],
            policy=envelope_policy,
            training_policy=training_policy,
            require_production_validation=require_production_validation,
            emit_segments=require_production_validation,
        )
    except (FullSchemaEnvelopeError, Exception):
        return None


def _attach_mask_diagnostics(entry: dict[str, Any]) -> dict[str, Any]:
    # Re-build with full production validation before masking selected examples.
    envelope = build_full_schema_envelope(
        entry["record"],
        entry["eligibility"],
        require_production_validation=True,
    )
    entry["_envelope"] = envelope
    prompt = build_t27b_inference_prompt(entry["record"])
    tok = DeterministicCharTokenizer()
    masked = build_masked_sequence_from_envelope(
        prompt=prompt,
        envelope=envelope,
        tokenizer=tok,
        # DeterministicCharTokenizer is 1 char ≈ 1 token; use a wide budget for
        # CPU density diagnostics. Live training uses a real tokenizer at 1024.
        max_seq_len=8192,
        pad_token_id=int(tok.pad_token_id),
    )
    return masked.diagnostics


def _annotate_pool(
    pool: list[dict[str, Any]],
    *,
    seed: int,
    envelope_policy: dict[str, Any],
    training_policy: dict[str, Any],
    forbidden_ids: set[str],
    forbidden_groups: set[str],
    model_selection_ids: set[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in pool:
        rid = str(entry["id"])
        if rid in forbidden_ids or rid in model_selection_ids or rid in JOB6059_VAL_IDS:
            continue
        if entry["group_key"] in forbidden_groups:
            continue
        _assert_no_leakage_id(rid)
        if entry["source_dataset"] in FORBIDDEN_DATASETS:
            continue
        if entry["source_dataset"] not in PRIMARY_ALLOWED_DATASETS:
            continue
        if entry["eligibility"].get(STRUCTURED_TARGET_TASK) not in STRUCTURED_TARGET_STRONG:
            continue
        envelope = _try_envelope_only(
            entry,
            envelope_policy=envelope_policy,
            training_policy=training_policy,
            require_production_validation=False,
        )
        if envelope is None:
            continue
        annotated = dict(entry)
        annotated["_categories"] = categorize_entry(entry)
        annotated["_digest"] = _digest(seed, rid)
        annotated["_envelope"] = envelope
        annotated["_supervised_count"] = len(envelope.supervised_fields)
        annotated["_strong_count"] = len(
            [n for n in envelope.supervised_fields if n not in envelope.weakly_eligible_fields]
        )
        out.append(annotated)
    return out


def _with_diagnostics(
    entries: list[dict[str, Any]],
    *,
    fillers: list[dict[str, Any]] | None = None,
    target_count: int | None = None,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    rejected: set[str] = set()
    queue = list(entries)
    spare = list(fillers or [])
    goal = target_count if target_count is not None else len(entries)
    while len(enriched) < goal and (queue or spare):
        nxt = queue.pop(0) if queue else spare.pop(0)
        rid = str(nxt["id"])
        if rid in rejected or any(str(e["id"]) == rid for e in enriched):
            continue
        used_groups = {str(e["group_key"]) for e in enriched}
        if str(nxt["group_key"]) in used_groups:
            rejected.add(rid)
            continue
        try:
            item = dict(nxt)
            item["_diagnostics"] = _attach_mask_diagnostics(item)
            enriched.append(item)
        except Exception:
            rejected.add(rid)
            continue
    return enriched


def _try_envelope(
    entry: dict[str, Any],
    *,
    envelope_policy: dict[str, Any],
    training_policy: dict[str, Any],
) -> tuple[Any, dict[str, Any]] | None:
    envelope = _try_envelope_only(
        entry,
        envelope_policy=envelope_policy,
        training_policy=training_policy,
        require_production_validation=True,
    )
    if envelope is None:
        return None
    tmp = dict(entry)
    tmp["_envelope"] = envelope
    try:
        return envelope, _attach_mask_diagnostics(tmp)
    except Exception:
        return None


def _pick_by_predicates(
    candidates: list[dict[str, Any]],
    needs: list[tuple[str, Any]],
    *,
    target_count: int,
) -> list[dict[str, Any]]:
    ordered = sorted(candidates, key=lambda e: (e["_digest"], e["id"]))
    picks: list[dict[str, Any]] = []
    used: set[str] = set()
    used_groups: set[str] = set()
    for _label, pred in needs:
        for entry in ordered:
            rid = str(entry["id"])
            gk = str(entry["group_key"])
            if rid in used or gk in used_groups:
                continue
            if pred(entry):
                picks.append(entry)
                used.add(rid)
                used_groups.add(gk)
                break
    for entry in ordered:
        if len(picks) >= target_count:
            break
        rid = str(entry["id"])
        gk = str(entry["group_key"])
        if rid in used or gk in used_groups:
            continue
        picks.append(entry)
        used.add(rid)
        used_groups.add(gk)
    if len(picks) < target_count:
        raise T27BDatasetError(f"insufficient_picks:{len(picks)}<{target_count}")
    return picks[:target_count]


def _final_smoke_needs() -> list[tuple[str, Any]]:
    return [
        ("clear", lambda e: e["record"].get("ambiguity_present") is False),
        ("clear2", lambda e: e["record"].get("ambiguity_present") is False),
        ("ambiguous", lambda e: e["record"].get("ambiguity_present") is True),
        ("ambiguous2", lambda e: e["record"].get("ambiguity_present") is True),
        (
            "compound_or_context",
            lambda e: bool(e["record"].get("compound_ambiguity"))
            or ("contextual" in (e["record"].get("ambiguity_types") or []))
            or ("spatial" in (e["record"].get("ambiguity_types") or [])),
        ),
        (
            "compound_or_context2",
            lambda e: bool(e["record"].get("compound_ambiguity"))
            or ("contextual" in (e["record"].get("ambiguity_types") or []))
            or ("spatial" in (e["record"].get("ambiguity_types") or [])),
        ),
        (
            "capability_sensitive",
            lambda e: e["eligibility"].get("capability") in ("eligible", "weakly_eligible")
            or e["record"].get("capability_status") is not None,
        ),
        (
            "risk_sensitive",
            lambda e: e["eligibility"].get("risk") in ("eligible", "weakly_eligible")
            or e["record"].get("risk_relevant") is True
            or e["record"].get("risk_level") is not None,
        ),
    ]


def _select_train(
    pool: list[dict[str, Any]],
    *,
    target_count: int,
) -> list[dict[str, Any]]:
    scored2: list[tuple[Any, ...]] = []
    for entry in pool:
        strong = int(entry.get("_strong_count") or 0)
        total = int(entry.get("_supervised_count") or 0)
        if total <= 0:
            continue
        tier = 0 if entry["eligibility"][STRUCTURED_TARGET_TASK] == "eligible" else 1
        scored2.append((-strong, -total, tier, entry["_digest"], entry))
    scored2.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    ordered = [item[4] for item in scored2]
    if not ordered:
        raise T27BDatasetError("empty_scored_train_pool")

    by_dataset: dict[str, list[dict[str, Any]]] = {}
    for entry in ordered:
        by_dataset.setdefault(str(entry["source_dataset"]), []).append(entry)

    available_datasets = sorted(
        ds for ds in by_dataset if ds in PRIMARY_ALLOWED_DATASETS and by_dataset[ds]
    )
    if len(available_datasets) < MIN_DISTINCT_TRAIN_DATASETS:
        raise T27BDatasetError(
            f"insufficient_distinct_train_datasets:{available_datasets}"
        )

    selected_ids: list[str] = []
    selected_set: set[str] = set()

    def _take(entry: dict[str, Any]) -> None:
        rid = str(entry["id"])
        if rid in selected_set or len(selected_ids) >= target_count:
            return
        selected_ids.append(rid)
        selected_set.add(rid)

    # 1) Enforce per-dataset floors for every available primary dataset.
    for dataset in available_datasets:
        floor = int(MIN_TRAIN_PER_DATASET.get(dataset, 8))
        floor = min(floor, len(by_dataset[dataset]), target_count)
        taken = 0
        for entry in by_dataset[dataset]:
            if taken >= floor or len(selected_ids) >= target_count:
                break
            before = len(selected_ids)
            _take(entry)
            if len(selected_ids) > before:
                taken += 1
        if taken < min(floor, len(by_dataset[dataset])):
            raise T27BDatasetError(
                f"insufficient_dataset_floor:{dataset}:{taken}<{floor}"
            )

    # 2) Category × dataset coverage round-robin.
    for spec in CATEGORY_SPECS:
        for dataset in available_datasets:
            if len(selected_ids) >= target_count:
                break
            for entry in by_dataset[dataset]:
                if str(entry["id"]) in selected_set:
                    continue
                if spec.category_id not in entry["_categories"]:
                    continue
                _take(entry)
                break

    # 3) Round-robin fill across datasets to preserve balance.
    pointers = {ds: 0 for ds in available_datasets}
    progress = True
    while len(selected_ids) < target_count and progress:
        progress = False
        for dataset in available_datasets:
            if len(selected_ids) >= target_count:
                break
            rows = by_dataset[dataset]
            while pointers[dataset] < len(rows):
                entry = rows[pointers[dataset]]
                pointers[dataset] += 1
                if str(entry["id"]) in selected_set:
                    continue
                _take(entry)
                progress = True
                break

    if len(selected_ids) < target_count:
        raise T27BDatasetError(
            f"insufficient_train_records:{len(selected_ids)}<{target_count}"
        )
    by_id = {str(e["id"]): e for e in ordered}
    selected = [by_id[rid] for rid in selected_ids]
    datasets_present = sorted({str(e["source_dataset"]) for e in selected})
    if len(datasets_present) < MIN_DISTINCT_TRAIN_DATASETS:
        raise T27BDatasetError(f"train_dataset_diversity_failed:{datasets_present}")
    return selected


def _interleave_by_dataset(pool: list[dict[str, Any]], *, seed: int) -> list[dict[str, Any]]:
    """Stable round-robin over primary datasets so scans are not single-dataset dominated."""
    buckets: dict[str, list[dict[str, Any]]] = {ds: [] for ds in sorted(PRIMARY_ALLOWED_DATASETS)}
    for entry in pool:
        ds = str(entry["source_dataset"])
        if ds in buckets:
            buckets[ds].append(entry)
    for ds, rows in buckets.items():
        rows.sort(
            key=lambda e: (
                0 if e["eligibility"].get(STRUCTURED_TARGET_TASK) == "eligible" else 1,
                -sum(
                    1
                    for k in (
                        "speech_act",
                        "intent_summary",
                        "cpc",
                        "ambiguity_present",
                        "recommended_strategy",
                        "candidate_interpretations",
                    )
                    if e["record"].get(k) not in (None, [], {})
                ),
                _digest(seed, str(e["id"])),
            )
        )
    interleaved: list[dict[str, Any]] = []
    pointers = {ds: 0 for ds in buckets}
    active = [ds for ds, rows in buckets.items() if rows]
    while active:
        next_active: list[str] = []
        for ds in active:
            idx = pointers[ds]
            rows = buckets[ds]
            if idx < len(rows):
                interleaved.append(rows[idx])
                pointers[ds] = idx + 1
                if pointers[ds] < len(rows):
                    next_active.append(ds)
        active = next_active
    return interleaved


def _record_row(entry: dict[str, Any], *, split: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    row = {
        "id": entry["id"],
        "group_key": entry["group_key"],
        "source_dataset": entry["source_dataset"],
        "split": split,
        "eligibility": entry["eligibility"],
        "category_tags": sorted(entry.get("_categories") or []),
        "record": entry["record"],
        "envelope_id": FULL_SCHEMA_ENVELOPE_ID,
        "supervised_fields": list(entry["_envelope"].supervised_fields),
        "per_field_supervision": dict(entry["_envelope"].per_field_supervision),
    }
    if extra:
        row.update(extra)
    return row


def _training_example_row(entry: dict[str, Any]) -> dict[str, Any]:
    envelope = entry["_envelope"]
    prompt = build_t27b_inference_prompt(entry["record"])
    return {
        "training_example_id": f"t27b:{entry['id']}",
        "source_record_id": entry["id"],
        "source_dataset": entry["source_dataset"],
        "group_key": entry["group_key"],
        "split": "source_train",
        "input_prompt": prompt,
        "envelope_id": envelope.envelope_id,
        "canonical_json": envelope.canonical_json,
        "target_hash": envelope.target_hash,
        "supervised_fields": list(envelope.supervised_fields),
        "weakly_eligible_fields": list(envelope.weakly_eligible_fields),
        "unavailable_fields": list(envelope.unavailable_fields),
        "per_field_supervision": dict(envelope.per_field_supervision),
        "field_spans": [span.to_dict() for span in envelope.field_spans],
        "segment_kinds_summary": dict(Counter(seg.kind for seg in envelope.segments)),
        "loss_mask_diagnostics": dict(entry["_diagnostics"]),
        "prompt_contract_version": "t27b_full_schema_prompt_v1",
    }


def _field_coverage(entries: list[dict[str, Any]]) -> dict[str, Any]:
    coverage: dict[str, dict[str, int]] = {}
    for entry in entries:
        env = entry["_envelope"]
        for name, status in env.per_field_supervision.items():
            bucket = coverage.setdefault(
                name, {"supervised": 0, "weakly_supervised": 0, "unavailable_masked": 0}
            )
            bucket[status] = bucket.get(status, 0) + 1
    return coverage


def _enum_coverage(entries: list[dict[str, Any]]) -> dict[str, Any]:
    enums: dict[str, Counter[str]] = {
        "speech_act": Counter(),
        "recommended_strategy": Counter(),
        "risk_level": Counter(),
        "capability_status": Counter(),
        "primary_ambiguity_type": Counter(),
    }
    for entry in entries:
        fields = entry["_envelope"].fields
        for key in enums:
            if entry["_envelope"].per_field_supervision.get(key) not in {
                "supervised",
                "weakly_supervised",
            }:
                continue
            val = fields.get(key)
            if val is None:
                continue
            if isinstance(val, str):
                enums[key][val] += 1
    return {key: dict(sorted(counter.items())) for key, counter in enums.items()}


def _supervision_density(entries: list[dict[str, Any]]) -> dict[str, Any]:
    diags = [dict(e["_diagnostics"]) for e in entries]
    pcts = sorted(float(d.get("supervised_percentage") or 0.0) for d in diags)
    mean_pct = round(sum(pcts) / max(1, len(pcts)), 4)
    n = len(pcts)

    def _percentile(sorted_vals: list[float], q: float) -> float:
        if not sorted_vals:
            return 0.0
        if len(sorted_vals) == 1:
            return round(sorted_vals[0], 4)
        idx = (len(sorted_vals) - 1) * q
        lo = int(idx)
        hi = min(lo + 1, len(sorted_vals) - 1)
        frac = idx - lo
        return round(sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac, 4)

    nonpad_pcts: list[float] = []
    for d in diags:
        total = float(d.get("total_tokens") or 0.0)
        pad = float(d.get("padding_masked") or 0.0)
        supervised = float(d.get("target_supervised_tokens") or 0.0)
        denom = max(1.0, total - pad)
        nonpad_pcts.append(100.0 * supervised / denom)
    nonpad_pcts.sort()
    return {
        "example_count": n,
        "mean_supervised_token_percentage": mean_pct,
        "median_supervised_token_percentage": _percentile(pcts, 0.5),
        "p10_supervised_token_percentage": _percentile(pcts, 0.1),
        "p90_supervised_token_percentage": _percentile(pcts, 0.9),
        "min_supervised_token_percentage": round(min(pcts, default=0.0), 4),
        "max_supervised_token_percentage": round(max(pcts, default=0.0), 4),
        "mean_supervised_token_percentage_excluding_padding": round(
            sum(nonpad_pcts) / max(1, len(nonpad_pcts)), 4
        ),
        "mean_semantic_supervised_tokens": round(
            sum(float(d.get("semantic_supervised") or 0.0) for d in diags) / max(1, len(diags)),
            4,
        ),
        "mean_structural_supervised_tokens": round(
            sum(float(d.get("structural_supervised") or 0.0) for d in diags) / max(1, len(diags)),
            4,
        ),
        "tokenizer_note": (
            "CPU density uses DeterministicCharTokenizer; live training uses the real "
            "base tokenizer at configs/model/qlora_structured_emission_recovery_v1.json "
            "sequence.max_seq_len."
        ),
        "per_example": diags,
    }


def build_all_t27b_datasets(root: Path | None = None, *, publish: bool = True) -> dict[str, Any]:
    effective = _root(root)
    seed = SEED
    envelope_policy = load_envelope_policy(effective / "configs/model/full_schema_envelope_policy_v1.json")
    training_policy = load_training_target_policy_strict(
        effective / "configs/data/training_target_policy_v1.json"
    )
    model_selection_ids = _load_model_selection_ids(effective)

    # Leakage anchors: never share groups with holdout.
    all_manifest = load_record_manifest_rows(effective)
    holdout_groups = {str(r["group_key"]) for r in all_manifest if r["split"] == "source_holdout"}

    train_pool_raw = build_split_pool(effective, split="source_train")
    dev_pool_raw = build_split_pool(effective, split="source_dev")

    # Seal final + diagnostic from source_dev first (IDs frozen before any eval),
    # then select train excluding those IDs/groups plus holdout / job6059 / model-sel.
    annotated_dev = _annotate_pool(
        dev_pool_raw,
        seed=seed + 1,
        envelope_policy=envelope_policy,
        training_policy=training_policy,
        forbidden_ids=set(JOB6059_VAL_IDS),
        forbidden_groups=set(holdout_groups),
        model_selection_ids=model_selection_ids,
    )
    if len(annotated_dev) < TARGET_FINAL_COUNT + TARGET_DIAGNOSTIC_COUNT:
        raise T27BDatasetError(
            f"insufficient_envelope_dev_pool:{len(annotated_dev)}"
        )

    sealed_picks = _pick_by_predicates(
        annotated_dev,
        _final_smoke_needs(),
        target_count=TARGET_FINAL_COUNT,
    )
    sealed_fillers = [
        e
        for e in sorted(annotated_dev, key=lambda x: (x["_digest"], x["id"]))
        if str(e["id"]) not in {str(x["id"]) for x in sealed_picks}
    ]
    sealed = _with_diagnostics(
        sealed_picks, fillers=sealed_fillers, target_count=TARGET_FINAL_COUNT
    )
    if len(sealed) < TARGET_FINAL_COUNT:
        raise T27BDatasetError(f"insufficient_sealed_after_validation:{len(sealed)}")
    sealed_ids = {str(e["id"]) for e in sealed}
    sealed_groups = {str(e["group_key"]) for e in sealed}
    if len({e["source_dataset"] for e in sealed}) < 2:
        # Try to repair by swapping in another dataset if possible.
        other = [
            e
            for e in annotated_dev
            if str(e["id"]) not in sealed_ids
            and str(e["group_key"]) not in sealed_groups
            and e["source_dataset"] not in {x["source_dataset"] for x in sealed}
        ]
        if other and sealed:
            replacement = sorted(other, key=lambda e: (e["_digest"], e["id"]))[0]
            sealed = _with_diagnostics(
                sealed[:-1] + [replacement],
                fillers=other[1:],
                target_count=TARGET_FINAL_COUNT,
            )
            sealed_ids = {str(e["id"]) for e in sealed}
            sealed_groups = {str(e["group_key"]) for e in sealed}
    if len({e["source_dataset"] for e in sealed}) < 2:
        raise T27BDatasetError("final_smoke_requires_ge_2_datasets")

    diagnostic_candidates = [
        e
        for e in annotated_dev
        if str(e["id"]) not in sealed_ids and str(e["group_key"]) not in sealed_groups
    ]
    diagnostic_picks = _pick_by_predicates(
        diagnostic_candidates,
        [
            ("clear", lambda e: e["record"].get("ambiguity_present") is False),
            ("ambiguous", lambda e: e["record"].get("ambiguity_present") is True),
            (
                "compound_or_context",
                lambda e: bool(e["record"].get("compound_ambiguity"))
                or ("contextual" in (e["record"].get("ambiguity_types") or [])),
            ),
            (
                "capability_or_risk",
                lambda e: e["eligibility"].get("capability") in ("eligible", "weakly_eligible")
                or e["eligibility"].get("risk") in ("eligible", "weakly_eligible"),
            ),
        ],
        target_count=TARGET_DIAGNOSTIC_COUNT,
    )
    diagnostic = _with_diagnostics(
        diagnostic_picks,
        fillers=[
            e
            for e in diagnostic_candidates
            if str(e["id"]) not in {str(x["id"]) for x in diagnostic_picks}
        ],
        target_count=TARGET_DIAGNOSTIC_COUNT,
    )
    if len(diagnostic) < TARGET_DIAGNOSTIC_COUNT:
        raise T27BDatasetError(f"insufficient_diagnostic_after_validation:{len(diagnostic)}")
    diagnostic_ids = {str(e["id"]) for e in diagnostic}
    diagnostic_groups = {str(e["group_key"]) for e in diagnostic}

    # Prefer oversampling train selection pool then validating selected only.
    # Interleave by dataset so the scan prefix cannot collapse to one source.
    train_pool_raw = _interleave_by_dataset(train_pool_raw, seed=seed)
    # Annotate a generous interleaved prefix then select; expand if needed.
    train_scan = train_pool_raw[: max(TARGET_TRAIN_COUNT * 40, 2000)]
    annotated_train = _annotate_pool(
        train_scan,
        seed=seed,
        envelope_policy=envelope_policy,
        training_policy=training_policy,
        forbidden_ids=sealed_ids | diagnostic_ids | set(JOB6059_VAL_IDS),
        forbidden_groups=sealed_groups | diagnostic_groups | holdout_groups,
        model_selection_ids=model_selection_ids,
    )
    if len(annotated_train) < TARGET_TRAIN_COUNT:
        # Fall back to full pool if the prefix was too sparse.
        annotated_train = _annotate_pool(
            train_pool_raw,
            seed=seed,
            envelope_policy=envelope_policy,
            training_policy=training_policy,
            forbidden_ids=sealed_ids | diagnostic_ids | set(JOB6059_VAL_IDS),
            forbidden_groups=sealed_groups | diagnostic_groups | holdout_groups,
            model_selection_ids=model_selection_ids,
        )
    train_selected = _select_train(annotated_train, target_count=TARGET_TRAIN_COUNT)
    # Validate+mask selected; if some fail validation, top up from remaining pool.
    validated: list[dict[str, Any]] = []
    rejected_ids: set[str] = set()
    candidate_queue = list(train_selected)
    extras = [e for e in annotated_train if str(e["id"]) not in {str(x["id"]) for x in train_selected}]
    extras.sort(key=lambda e: ( -int(e.get("_strong_count") or 0), e["_digest"], e["id"]))
    while len(validated) < TARGET_TRAIN_COUNT and (candidate_queue or extras):
        if candidate_queue:
            nxt = candidate_queue.pop(0)
        else:
            nxt = extras.pop(0)
        rid = str(nxt["id"])
        if rid in rejected_ids:
            continue
        try:
            diag = _attach_mask_diagnostics(nxt)
        except Exception:
            rejected_ids.add(rid)
            continue
        item = dict(nxt)
        item["_diagnostics"] = diag
        validated.append(item)
    if len(validated) < TARGET_TRAIN_COUNT:
        raise T27BDatasetError(
            f"insufficient_validated_train_records:{len(validated)}<{TARGET_TRAIN_COUNT}"
        )
    train_selected = validated[:TARGET_TRAIN_COUNT]
    train_ids = {str(e["id"]) for e in train_selected}
    train_groups = {str(e["group_key"]) for e in train_selected}

    if train_ids & sealed_ids or train_ids & diagnostic_ids:
        raise T27BDatasetError("train_overlaps_eval_ids")
    if train_groups & sealed_groups or train_groups & diagnostic_groups:
        raise T27BDatasetError("train_overlaps_eval_groups")
    if sealed_ids & diagnostic_ids:
        raise T27BDatasetError("sealed_diagnostic_id_overlap")
    if sealed_groups & diagnostic_groups:
        raise T27BDatasetError("sealed_diagnostic_group_overlap")
    if train_groups & holdout_groups:
        raise T27BDatasetError("train_holdout_group_overlap")

    # Materialise rows
    sealed_rows = [
        _record_row(
            e,
            split="source_dev",
            extra={
                "sealed": True,
                "diagnostic_only": False,
                "valid_for_final_t27b_gate": True,
                "seal_status": "sealed",
            },
        )
        for e in sorted(sealed, key=lambda x: str(x["id"]))
    ]
    diagnostic_rows = [
        _record_row(
            e,
            split="source_dev",
            extra={
                "sealed": False,
                "diagnostic_only": True,
                "valid_for_final_t27b_gate": False,
            },
        )
        for e in sorted(diagnostic, key=lambda x: str(x["id"]))
    ]
    train_rows = [
        _record_row(e, split="source_train")
        for e in sorted(train_selected, key=lambda x: str(x["id"]))
    ]
    example_rows = [
        _training_example_row(e)
        for e in sorted(train_selected, key=lambda x: str(x["id"]))
    ]

    leakage_report = {
        "train_record_count": len(train_rows),
        "final_smoke_count": len(sealed_rows),
        "diagnostic_count": len(diagnostic_rows),
        "train_ids": sorted(train_ids),
        "final_smoke_ids": sorted(sealed_ids),
        "diagnostic_ids": sorted(diagnostic_ids),
        "job6059_val_ids_excluded": sorted(JOB6059_VAL_IDS),
        "group_overlap_train_final": [],
        "group_overlap_train_diagnostic": [],
        "group_overlap_final_diagnostic": [],
        "group_overlap_train_holdout": [],
        "model_selection_overlap": sorted(
            (train_ids | sealed_ids | diagnostic_ids) & model_selection_ids
        ),
        "calibration_overlap": [],
        "future_manual_overlap": [],
        "source_holdout_records_used": 0,
        "passed": True,
    }

    train_field_coverage = _field_coverage(train_selected)
    train_enum_coverage = _enum_coverage(train_selected)
    train_density = _supervision_density(train_selected)
    target_segments_summary = {
        "envelope_id": FULL_SCHEMA_ENVELOPE_ID,
        "example_count": len(example_rows),
        "mean_segments": round(
            sum(sum(ex["segment_kinds_summary"].values()) for ex in example_rows)
            / max(1, len(example_rows)),
            4,
        ),
        "kind_totals": dict(
            Counter(
                kind
                for ex in example_rows
                for kind, count in ex["segment_kinds_summary"].items()
                for _ in range(int(count))
            )
        ),
    }

    min_mean = float(
        (envelope_policy.get("minimum_useful_supervision") or {}).get(
            "min_mean_supervised_token_percentage", 12.0
        )
    )
    # Soft check: report if below, but structural supervision should push above 12%.
    density_note = (
        "meets_minimum"
        if train_density["mean_supervised_token_percentage"] >= min_mean
        else "below_minimum_useful_supervision"
    )

    diagnostic_dir = effective / DIAGNOSTIC_DIR_REL
    final_dir = effective / FINAL_SMOKE_DIR_REL
    train_dir = effective / TRAIN_DIR_REL

    diagnostic_manifest = {
        "programme_id": PROGRAMME_ID,
        "dataset_id": "t27b_diagnostic_dev_v1",
        "ticket": "T27B",
        "split": "source_dev",
        "record_count": len(diagnostic_rows),
        "record_ids": [r["id"] for r in diagnostic_rows],
        "diagnostic_only": True,
        "valid_for_final_t27b_gate": False,
        "seal_status": "unsealed_diagnostic",
        "development_only": True,
        "valid_for_official_use": False,
        "seed": seed,
        "excluded_sources": [
            "source_holdout",
            "source_train",
            "model_selection_development_set_v1",
            "t13_calibration",
            "future_manual_namespace",
            "job6059_validation_ids",
            "t27b_final_smoke_v1",
            "qlora_structured_emission_recovery_v1",
        ],
    }
    final_manifest = {
        "programme_id": PROGRAMME_ID,
        "dataset_id": "t27b_final_smoke_v1",
        "ticket": "T27B",
        "split": "source_dev",
        "record_count": len(sealed_rows),
        "record_ids": [r["id"] for r in sealed_rows],
        "sealed": True,
        "seal_status": "sealed",
        "frozen_before_live_run": True,
        "valid_for_final_t27b_gate": True,
        "diagnostic_only": False,
        "development_only": True,
        "valid_for_official_use": False,
        "seed": seed,
        "coverage_targets": {
            "clear": 2,
            "ambiguous": 2,
            "compound_or_context": 2,
            "capability_sensitive": 1,
            "risk_sensitive": 1,
            "min_datasets": 2,
        },
        "datasets": sorted({r["source_dataset"] for r in sealed_rows}),
        "excluded_sources": [
            "source_holdout",
            "model_selection_development_set_v1",
            "t13_calibration",
            "future_manual_namespace",
            "job6059_validation_ids",
        ],
    }
    train_manifest = {
        "programme_id": PROGRAMME_ID,
        "dataset_id": "qlora_structured_emission_recovery_v1",
        "ticket": "T27B",
        "split": "source_train",
        "record_count": len(train_rows),
        "training_example_count": len(example_rows),
        "record_ids": [r["id"] for r in train_rows],
        "envelope_id": FULL_SCHEMA_ENVELOPE_ID,
        "prompt_contract": "t27b_full_schema_prompt_v1",
        "development_only": True,
        "valid_for_official_use": False,
        "seed": seed,
        "datasets": sorted({r["source_dataset"] for r in train_rows}),
        "supervision_density_note": density_note,
        "mean_supervised_token_percentage": train_density["mean_supervised_token_percentage"],
        "excluded_sources": [
            "source_holdout",
            "source_dev",
            "model_selection_development_set_v1",
            "t13_calibration",
            "future_manual_namespace",
            "job6059_validation_ids",
            "t27b_diagnostic_dev_v1",
            "t27b_final_smoke_v1",
        ],
    }

    result = {
        "diagnostic_manifest": diagnostic_manifest,
        "final_manifest": final_manifest,
        "train_manifest": train_manifest,
        "leakage_report": leakage_report,
        "sealed_ids": sorted(sealed_ids),
        "diagnostic_ids": sorted(diagnostic_ids),
        "train_ids": sorted(train_ids),
        "supervision_density_report": train_density,
    }

    if not publish:
        return result

    for directory in (diagnostic_dir, final_dir, train_dir):
        directory.mkdir(parents=True, exist_ok=True)

    _write_jsonl(diagnostic_dir / "records.jsonl", diagnostic_rows)
    _write_json(diagnostic_dir / "leakage_report.json", leakage_report)
    _write_json(diagnostic_dir / "field_coverage_report.json", _field_coverage(diagnostic))

    _write_jsonl(final_dir / "records.jsonl", sealed_rows)
    _write_json(final_dir / "leakage_report.json", leakage_report)
    _write_json(final_dir / "field_coverage_report.json", _field_coverage(sealed))

    _write_jsonl(train_dir / "records.jsonl", train_rows)
    _write_jsonl(train_dir / "training_examples.jsonl", example_rows)
    _write_json(train_dir / "leakage_report.json", leakage_report)
    _write_json(train_dir / "field_coverage_report.json", train_field_coverage)
    _write_json(train_dir / "enum_coverage_report.json", train_enum_coverage)
    _write_json(train_dir / "supervision_density_report.json", train_density)
    _write_json(train_dir / "target_segments_summary.json", target_segments_summary)
    _write_json(
        train_dir / "source_lineage.json",
        {
            "programme_id": PROGRAMME_ID,
            "programme_version": PROGRAMME_VERSION,
            "seed": seed,
            "train_split": "source_train",
            "final_split": "source_dev",
            "diagnostic_split": "source_dev",
            "datasets_in_train": train_manifest["datasets"],
            "datasets_in_final": final_manifest["datasets"],
            "datasets_in_diagnostic": sorted({r["source_dataset"] for r in diagnostic_rows}),
        },
    )

    diagnostic_hashes = {
        "records_sha256": sha256_hex((diagnostic_dir / "records.jsonl").read_bytes()),
        "leakage_report_sha256": sha256_hex((diagnostic_dir / "leakage_report.json").read_bytes()),
        "field_coverage_report_sha256": sha256_hex(
            (diagnostic_dir / "field_coverage_report.json").read_bytes()
        ),
    }
    diagnostic_manifest["hashes"] = diagnostic_hashes
    diagnostic_manifest["manifest_hash"] = sha256_hex(canonical_json_bytes(diagnostic_manifest))
    _write_json(diagnostic_dir / "manifest.json", diagnostic_manifest)
    _write_json(
        diagnostic_dir / "hashes.json",
        {
            **diagnostic_hashes,
            "manifest_sha256": sha256_hex((diagnostic_dir / "manifest.json").read_bytes()),
        },
    )

    final_hashes = {
        "records_sha256": sha256_hex((final_dir / "records.jsonl").read_bytes()),
        "leakage_report_sha256": sha256_hex((final_dir / "leakage_report.json").read_bytes()),
        "field_coverage_report_sha256": sha256_hex(
            (final_dir / "field_coverage_report.json").read_bytes()
        ),
    }
    final_manifest["hashes"] = final_hashes
    final_manifest["manifest_hash"] = sha256_hex(canonical_json_bytes(final_manifest))
    _write_json(final_dir / "manifest.json", final_manifest)
    _write_json(
        final_dir / "hashes.json",
        {
            **final_hashes,
            "manifest_sha256": sha256_hex((final_dir / "manifest.json").read_bytes()),
        },
    )

    train_hashes = {
        "records_sha256": sha256_hex((train_dir / "records.jsonl").read_bytes()),
        "training_examples_sha256": sha256_hex((train_dir / "training_examples.jsonl").read_bytes()),
        "leakage_report_sha256": sha256_hex((train_dir / "leakage_report.json").read_bytes()),
        "field_coverage_report_sha256": sha256_hex(
            (train_dir / "field_coverage_report.json").read_bytes()
        ),
        "enum_coverage_report_sha256": sha256_hex(
            (train_dir / "enum_coverage_report.json").read_bytes()
        ),
        "supervision_density_report_sha256": sha256_hex(
            (train_dir / "supervision_density_report.json").read_bytes()
        ),
        "target_segments_summary_sha256": sha256_hex(
            (train_dir / "target_segments_summary.json").read_bytes()
        ),
        "source_lineage_sha256": sha256_hex((train_dir / "source_lineage.json").read_bytes()),
    }
    train_manifest["hashes"] = train_hashes
    train_manifest["manifest_hash"] = sha256_hex(canonical_json_bytes(train_manifest))
    _write_json(train_dir / "manifest.json", train_manifest)
    _write_json(
        train_dir / "hashes.json",
        {
            **train_hashes,
            "manifest_sha256": sha256_hex((train_dir / "manifest.json").read_bytes()),
        },
    )

    result["paths"] = {
        "diagnostic": str(diagnostic_dir),
        "final_smoke": str(final_dir),
        "train": str(train_dir),
    }
    result["diagnostic_manifest"] = diagnostic_manifest
    result["final_manifest"] = final_manifest
    result["train_manifest"] = train_manifest
    return result
