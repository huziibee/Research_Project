"""Strategy-D per-field loss-mask training-target packaging (T15 policy, T27 use).

Implements ``configs/data/training_target_policy_v1.json`` strategy D
("combination_with_explicit_per_field_loss_masks"): package one multi-field
training target per record, where every field group carries its own
per-record loss weight derived from that record's eligibility status in
``data/development/source_splits_v1/record_manifest.jsonl``. A masked-out
field group is never converted into a negative or fabricated label; it is
excluded from the loss computation graph for that record by carrying a zero
loss weight, while its raw (possibly absent) field values are left untouched
for inspection.

CPU-only. Does not import torch, transformers, peft, bitsandbytes, or
accelerate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ambiguity_manager.paths import ProjectPaths

POLICY_REL = "configs/data/training_target_policy_v1.json"
POLICY_STRATEGY = "D"


class TrainingTargetPackagingError(RuntimeError):
    """Raised when a training-target package cannot be built per strategy D."""


@dataclass(frozen=True)
class FieldGroupTarget:
    field_group: str
    eligibility_task: str
    loss_type: str
    eligibility_status: str
    loss_weight: float
    masked: bool
    fields: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_group": self.field_group,
            "eligibility_task": self.eligibility_task,
            "loss_type": self.loss_type,
            "eligibility_status": self.eligibility_status,
            "loss_weight": self.loss_weight,
            "masked": self.masked,
            "fields": dict(self.fields),
        }


@dataclass(frozen=True)
class TrainingTargetPackage:
    record_id: str
    field_groups: tuple[FieldGroupTarget, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "field_groups": [group.to_dict() for group in self.field_groups],
        }

    @property
    def active_field_groups(self) -> tuple[FieldGroupTarget, ...]:
        return tuple(group for group in self.field_groups if not group.masked)

    @property
    def is_fully_masked(self) -> bool:
        return all(group.masked for group in self.field_groups)


def _default_policy_path() -> Path:
    return ProjectPaths.from_repo_root().configs / "data" / "training_target_policy_v1.json"


def load_training_target_policy_strict(path: Path | None = None) -> dict[str, Any]:
    """Load and structurally validate the frozen strategy-D policy."""
    resolved = path or _default_policy_path()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if payload.get("strategy") != POLICY_STRATEGY:
        raise TrainingTargetPackagingError(f"training_target_policy.strategy must be {POLICY_STRATEGY!r}")
    field_groups = payload.get("field_groups")
    if not isinstance(field_groups, list) or not field_groups:
        raise TrainingTargetPackagingError("training_target_policy.field_groups must be a non-empty list")
    mask_policy = payload.get("mask_policy") or {}
    status_to_weight = mask_policy.get("status_to_loss_weight")
    if not isinstance(status_to_weight, dict) or not status_to_weight:
        raise TrainingTargetPackagingError(
            "training_target_policy.mask_policy.status_to_loss_weight must be a non-empty object"
        )
    for group_spec in field_groups:
        for required in ("field_group", "eligibility_task", "loss_type", "source_fields"):
            if required not in group_spec:
                raise TrainingTargetPackagingError(f"field_group entry missing {required!r}: {group_spec}")
    return payload


def _extract_field(record: dict[str, Any], field_name: str) -> Any:
    if field_name.endswith(".*"):
        base = field_name[:-2]
        return record.get(base)
    return record.get(field_name)


def build_training_target_package(
    record: dict[str, Any],
    eligibility: dict[str, str],
    *,
    policy: dict[str, Any] | None = None,
) -> TrainingTargetPackage:
    """Build one multi-field-group training target package for ``record``.

    ``eligibility`` must be the per-task eligibility mapping for this record
    (as produced by ``data/development/source_splits_v1/record_manifest.jsonl``,
    one of ``eligible`` / ``weakly_eligible`` / ``ineligible`` / ``unavailable``).

    Invariant: a masked field group (``loss_weight == 0.0``) never has its raw
    field values rewritten into a fabricated negative/none label; the raw
    values (which may already be null/empty) are preserved unchanged so a
    caller can inspect them, but the zero weight must exclude the group from
    the loss graph for this record.
    """
    resolved_policy = policy or load_training_target_policy_strict()
    status_to_weight: dict[str, float] = {
        str(k): float(v) for k, v in resolved_policy["mask_policy"]["status_to_loss_weight"].items()
    }

    groups: list[FieldGroupTarget] = []
    for group_spec in resolved_policy["field_groups"]:
        field_group = str(group_spec["field_group"])
        eligibility_task = str(group_spec["eligibility_task"])
        loss_type = str(group_spec["loss_type"])
        status = eligibility.get(eligibility_task)
        if status is None:
            raise TrainingTargetPackagingError(
                f"record missing eligibility status for task {eligibility_task!r} "
                f"(field_group {field_group!r})"
            )
        status = str(status)
        if status not in status_to_weight:
            raise TrainingTargetPackagingError(
                f"unknown eligibility status {status!r} for task {eligibility_task!r}"
            )
        weight = status_to_weight[status]
        fields = {name: _extract_field(record, name) for name in group_spec["source_fields"]}
        groups.append(
            FieldGroupTarget(
                field_group=field_group,
                eligibility_task=eligibility_task,
                loss_type=loss_type,
                eligibility_status=status,
                loss_weight=weight,
                masked=weight == 0.0,
                fields=fields,
            )
        )

    record_id = str(record.get("id") or record.get("record_id") or "")
    if not record_id:
        raise TrainingTargetPackagingError("record must carry an 'id' or 'record_id' for packaging")
    return TrainingTargetPackage(record_id=record_id, field_groups=tuple(groups))


def assert_never_fabricates_negative_label(package: TrainingTargetPackage) -> None:
    """Guard the packaging-level strategy-D invariant.

    This cannot inspect a downstream loss implementation, but it asserts
    that masking is expressed purely via a zero loss weight, never by
    silently flipping a status to something that would let a caller treat
    an unavailable/ineligible field as a concrete negative training signal.
    """
    for group in package.field_groups:
        if group.eligibility_status in ("unavailable", "ineligible") and group.loss_weight != 0.0:
            raise TrainingTargetPackagingError(
                f"field_group {group.field_group!r} with status {group.eligibility_status!r} "
                "must carry loss_weight 0.0 (unavailable/ineligible must never be trained as negative)"
            )
        if group.masked and group.loss_weight != 0.0:
            raise TrainingTargetPackagingError(
                f"masked field_group {group.field_group!r} must carry loss_weight 0.0"
            )
        if not group.masked and group.loss_weight <= 0.0:
            raise TrainingTargetPackagingError(
                f"active field_group {group.field_group!r} must carry a positive loss_weight"
            )


def batch_loss_mask_summary(packages: list[TrainingTargetPackage]) -> dict[str, Any]:
    """Aggregate per-field-group active/masked counts across a batch (smoke shape check)."""
    summary: dict[str, dict[str, int]] = {}
    for package in packages:
        for group in package.field_groups:
            bucket = summary.setdefault(group.field_group, {"active": 0, "masked": 0})
            bucket["masked" if group.masked else "active"] += 1
    return {
        "record_count": len(packages),
        "field_groups": summary,
    }
