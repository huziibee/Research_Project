#!/usr/bin/env python3
"""Audit prepared dataset-native records before result interpretation.

This is a data-quality/provenance audit. It makes no performance claim and does
not inspect model predictions. Literal token overlap is reported as a screening
signal, never as proof of leakage.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def norm(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().casefold())


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def counts(values: list[Any]) -> dict[str, int]:
    return dict(sorted(collections.Counter(json.dumps(value, sort_keys=True) if isinstance(value, (list, dict)) else str(value) for value in values).items()))


def duplicate_command_audit(records: list[dict[str, Any]], labels: dict[str, Any]) -> dict[str, Any]:
    by_command: dict[str, list[str]] = collections.defaultdict(list)
    for record in records:
        by_command[norm(record.get("command"))].append(str(record["record_id"]))
    duplicate_groups = {command: ids for command, ids in by_command.items() if command and len(ids) > 1}
    conflicting: list[dict[str, Any]] = []
    for command, ids in duplicate_groups.items():
        target_fingerprints = {digest(labels[record_id]) for record_id in ids}
        if len(target_fingerprints) > 1:
            conflicting.append({"record_ids": sorted(ids), "n_records": len(ids), "target_variants": len(target_fingerprints)})
    return {
        "unique_normalized_commands": len(by_command),
        "duplicate_command_group_count": len(duplicate_groups),
        "records_in_duplicate_command_groups": sum(len(ids) for ids in duplicate_groups.values()),
        "conflicting_target_duplicate_group_count": len(conflicting),
        "conflicting_target_examples_id_only": conflicting[:20],
    }


def duplicate_prompt_audit(records: list[dict[str, Any]], labels: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """Measure repeated effective inputs; used to pre-specify a sensitivity unit."""
    groups: dict[str, list[str]] = collections.defaultdict(list)
    for record in records:
        prompt = {field: record.get(field) for field in fields}
        groups[digest(prompt)].append(str(record["record_id"]))
    repeated = [ids for ids in groups.values() if len(ids) > 1]
    conflicts = [ids for ids in repeated if len({digest(labels[x]) for x in ids}) > 1]
    return {
        "effective_input_fields": list(fields),
        "unique_effective_inputs": len(groups),
        "repeated_effective_input_group_count": len(repeated),
        "records_in_repeated_effective_input_groups": sum(map(len, repeated)),
        "repeated_input_groups_with_conflicting_targets": len(conflicts),
        "example_repeated_input_ids": [sorted(ids) for ids in repeated[:20]],
    }


def literal_overlap(records: list[dict[str, Any]], labels: dict[str, Any], label_words: set[str], text_fields: tuple[str, ...]) -> dict[str, Any]:
    hits: list[str] = []
    per_word: collections.Counter[str] = collections.Counter()
    for record in records:
        text = " ".join(norm(record.get(field)) for field in text_fields)
        expected = labels[str(record["record_id"])]
        expected_words = set(re.findall(r"[a-z_]+", json.dumps(expected).casefold())) & label_words
        found = {word for word in expected_words if re.search(rf"(?<![a-z_]){re.escape(word)}(?![a-z_])", text)}
        if found:
            hits.append(str(record["record_id"]))
            per_word.update(found)
    return {
        "screen_definition": "literal expected-label token appears in supplied text; screening signal only, not proof of invalid leakage",
        "records_with_literal_expected_label_token": len(hits),
        "rate": len(hits) / len(records) if records else None,
        "token_counts": dict(sorted(per_word.items())),
        "example_record_ids": hits[:25],
    }


def vague(path: Path) -> dict[str, Any]:
    data = rows(path)
    by_id: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in data:
        by_id[str(row["record_id"])].append(row)
    bad_pairs = [record_id for record_id, pair in by_id.items() if {x.get("condition") for x in pair} != {"command_only", "command_plus_textual_caption"} or len(pair) != 2]
    source = [pair[0] for pair in by_id.values() if pair]
    label_map = {str(row["record_id"]): row["source_target"] for row in source}
    command_only = [row for row in data if row.get("condition") == "command_only"]
    with_caption = [row for row in data if row.get("condition") == "command_plus_textual_caption"]
    captions = [str(row.get("textual_caption") or "") for row in data if row.get("condition") == "command_plus_textual_caption"]
    target_shapes = counts([{"intent_goal": r["source_target"].get("intent_goal"), "slot_keys": sorted((r["source_target"].get("slots") or {}).keys())} for r in source])
    return {
        "prepared_rows": len(data), "source_records": len(by_id), "pair_integrity_failures": bad_pairs,
        "empty_caption_count": sum(not norm(caption) for caption in captions),
        "caption_identical_to_command_count": sum(norm(row.get("command")) == norm(row.get("textual_caption")) for row in data if row.get("condition") == "command_plus_textual_caption"),
        "caption_character_length": {"min": min(map(len, captions)), "median": sorted(map(len, captions))[len(captions)//2], "max": max(map(len, captions))},
        "target_shape_distribution": target_shapes,
        "command_duplicate_audit": duplicate_command_audit(command_only, label_map),
        "effective_input_duplicate_audits": {
            "command_only": duplicate_prompt_audit(command_only, label_map, ("command",)),
            "command_plus_textual_caption": duplicate_prompt_audit(with_caption, label_map, ("command", "textual_caption")),
        },
        "manual_review_ids": [str(row["record_id"]) for row in sorted(source, key=lambda r: len(str(r.get("textual_caption") or "")), reverse=True)[:10]],
    }


def keyed(packet_path: Path, key_path: Path, kind: str) -> dict[str, Any]:
    packet, key = rows(packet_path), rows(key_path)
    key_map = {str(row["record_id"]): row for row in key}
    if kind == "clara":
        full = [row for row in packet if row["condition"] == "full_context"]
        blind = [row for row in packet if row["condition"] == "context_blind"]
        full_ids, blind_ids = {str(x["record_id"]) for x in full}, {str(x["record_id"]) for x in blind}
        labels = {record_id: {field: key_map[record_id].get(field) for field in ("ambiguity_present", "capability_status", "recommended_strategy")} for record_id in key_map}
        label_words = {"true", "false", "supported", "unsupported", "execute", "clarify", "reject"}
        result: dict[str, Any] = {
            "packet_rows": len(packet), "source_records": len(key), "full_context_rows": len(full), "context_blind_rows": len(blind),
            "pair_id_set_mismatch": sorted(full_ids ^ blind_ids)[:25],
            "empty_scene_context_full": sum(not norm(x.get("scene_context")) for x in full),
            "empty_capability_context_full": sum(not norm(x.get("capability_context")) for x in full),
            "blind_context_nonnull_rows": sum(x.get("scene_context") is not None or x.get("capability_context") is not None for x in blind),
            "label_distributions": {field: counts([x.get(field) for x in key]) for field in ("ambiguity_present", "capability_status", "recommended_strategy")},
            "command_duplicate_audit": duplicate_command_audit(full, labels),
            "effective_input_duplicate_audit": duplicate_prompt_audit(full, labels, ("command", "scene_context", "capability_context")),
            "literal_label_token_screen": literal_overlap(full, labels, label_words, ("scene_context", "capability_context")),
            "manual_review_ids": [str(x["record_id"]) for x in sorted(full, key=lambda r: len(str(r.get("scene_context") or "")) + len(str(r.get("capability_context") or "")), reverse=True)[:10]],
        }
    elif kind == "ambik":
        labels = {record_id: {"ambiguity_types": key_map[record_id].get("ambiguity_types")} for record_id in key_map}
        label_words = {"commonsense", "preference", "safety_precondition"}
        result = {
            "packet_rows": len(packet), "source_records": len(key),
            "empty_scene_context_count": sum(not norm(x.get("scene_context")) for x in packet),
            "type_set_distribution": counts([x.get("ambiguity_types") for x in key]),
            "individual_type_frequency": dict(sorted(collections.Counter(t for x in key for t in x.get("ambiguity_types", [])).items())),
            "command_duplicate_audit": duplicate_command_audit(packet, labels),
            "effective_input_duplicate_audit": duplicate_prompt_audit(packet, labels, ("command", "scene_context")),
            "literal_label_token_screen": literal_overlap(packet, labels, label_words, ("command", "scene_context")),
            "manual_review_ids": [str(x["record_id"]) for x in sorted(packet, key=lambda r: len(str(r.get("scene_context") or "")), reverse=True)[:10]],
        }
    else:
        labels = {record_id: {field: key_map[record_id].get(field) for field in ("ambiguity_present", "ambiguity_types", "missing_slots")} for record_id in key_map}
        label_words = {"true", "false", "commonsense", "preference", "safety_precondition"}
        result = {
            "packet_rows": len(packet), "source_records": len(key),
            "empty_scene_context_count": sum(not norm(x.get("scene_context")) for x in packet),
            "label_distributions": {field: counts([x.get(field) for x in key]) for field in ("ambiguity_present", "ambiguity_types", "missing_slots")},
            "command_duplicate_audit": duplicate_command_audit(packet, labels),
            "effective_input_duplicate_audit": duplicate_prompt_audit(packet, labels, ("command", "scene_context")),
            "literal_label_token_screen": literal_overlap(packet, labels, label_words, ("command", "scene_context")),
            "manual_review_ids": [str(x["record_id"]) for x in sorted(packet, key=lambda r: len(str(r.get("scene_context") or "")), reverse=True)[:10]],
        }
    result["packet_key_id_mismatch"] = sorted({str(x["record_id"]) for x in packet} ^ set(key_map))[:25]
    return result


def markdown(report: dict[str, Any]) -> str:
    lines = ["# Dataset-native raw-data audit", "", "This is a pre-results source-data audit. It contains no model outputs or scores.", ""]
    for name, audit in report["datasets"].items():
        lines += [f"## {name}", "", f"- Records: {audit.get('source_records')}; prepared rows: {audit.get('prepared_rows', audit.get('packet_rows'))}."]
        if "pair_integrity_failures" in audit:
            lines.append(f"- Pair-integrity failures: {len(audit['pair_integrity_failures'])}.")
        if "pair_id_set_mismatch" in audit:
            lines.append(f"- Full/blind ID-set mismatch examples: {len(audit['pair_id_set_mismatch'])}.")
        duplicate = audit.get("command_duplicate_audit", {})
        lines.append(f"- Duplicate normalized-command groups: {duplicate.get('duplicate_command_group_count')}; groups with conflicting source targets: {duplicate.get('conflicting_target_duplicate_group_count')}.")
        effective = audit.get("effective_input_duplicate_audit", {})
        if effective:
            lines.append(f"- Unique effective inputs: {effective.get('unique_effective_inputs')}; repeated effective-input groups: {effective.get('repeated_effective_input_group_count')}; target conflicts among repeated inputs: {effective.get('repeated_input_groups_with_conflicting_targets')}.")
        else:
            for condition, condition_audit in audit.get("effective_input_duplicate_audits", {}).items():
                lines.append(f"- {condition}: {condition_audit.get('unique_effective_inputs')} unique effective inputs; {condition_audit.get('repeated_effective_input_group_count')} repeated groups; {condition_audit.get('repeated_input_groups_with_conflicting_targets')} target-conflicting groups.")
        screen = audit.get("literal_label_token_screen")
        if screen:
            lines.append(f"- Literal-label-token screen: {screen['records_with_literal_expected_label_token']}/{audit.get('source_records')} records. This is only a manual-review signal, not evidence of leakage.")
        lines.append(f"- Manual review IDs (longest provided context): {', '.join(audit['manual_review_ids'])}.")
        lines.append("")
    lines += ["## Interpretation rule", "", "A duplicate command with different source targets means command-only accuracy is conditional on supplied context, not that the dataset is invalid. Literal expected-label words in text can be legitimate task language; inspect those records before making a leakage claim.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vague", type=Path, required=True)
    parser.add_argument("--ambik-packet", type=Path, required=True); parser.add_argument("--ambik-key", type=Path, required=True)
    parser.add_argument("--clara-packet", type=Path, required=True); parser.add_argument("--clara-key", type=Path, required=True)
    parser.add_argument("--indirect-packet", type=Path, required=True); parser.add_argument("--indirect-key", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True); parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    report = {"audit_id": "dataset_native_raw_data_audit_v1", "prediction_inspected": False, "datasets": {
        "VAGUE": vague(args.vague),
        "AmbiK": keyed(args.ambik_packet, args.ambik_key, "ambik"),
        "CLARA": keyed(args.clara_packet, args.clara_key, "clara"),
        "Indirect Requests": keyed(args.indirect_packet, args.indirect_key, "indirect"),
    }}
    for path, content in ((args.json_output, json.dumps(report, indent=2, sort_keys=True) + "\n"), (args.markdown_output, markdown(report))):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content, encoding="utf-8", newline="\n")
    print(json.dumps({"status": "PASS", "json_sha256": hashlib.sha256(args.json_output.read_bytes()).hexdigest(), "datasets": list(report["datasets"])}, sort_keys=True))


if __name__ == "__main__":
    main()
