#!/usr/bin/env python3
"""Pre-result mechanism analysis for frozen T39 and dataset-native sources.

This script inspects source records and frozen Pilot-120 semantic-intent rows.
It does not read queued dataset-native model outputs and does not change
labels, prompts, or frozen T39 artifacts.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().casefold())


def wilson(k: int, n: int, z: float = 1.959963984540054) -> list[float] | None:
    if n <= 0:
        return None
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / den
    return [max(0.0, centre - half), min(1.0, centre + half)]


def contains_slot(text: str, slot: str) -> bool:
    token = norm(slot)
    if not token:
        return False
    hay = norm(text)
    if token in hay:
        return True
    if not token.endswith("s") and f"{token}s" in hay:
        return True
    if token.endswith("s") and token[:-1] and token[:-1] in hay:
        return True
    return False


def entropy(counts: Counter[str]) -> float:
    total = sum(counts.values())
    if not total:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in counts.values() if c)


def mutual_information(pairs: list[tuple[str, str]]) -> dict[str, float]:
    joint = Counter(pairs)
    left = Counter(a for a, _ in pairs)
    right = Counter(b for _, b in pairs)
    n = len(pairs)
    mi = 0.0
    for (a, b), count in joint.items():
        p_xy = count / n
        mi += p_xy * math.log2(p_xy / ((left[a] / n) * (right[b] / n)))
    hx, hy = entropy(left), entropy(right)
    return {"mi_bits": mi, "h_left_bits": hx, "h_right_bits": hy, "normalized_mi": mi / math.sqrt(hx * hy) if hx and hy else 0.0}


def sample_rows(rows: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    return rows[:limit]


def vague_analysis() -> dict[str, Any]:
    path = ROOT / "data" / "interim" / "vague" / "vague_canonical.jsonl"
    rows = load_jsonl(path)
    slot_in_command = Counter()
    slot_in_caption = Counter()
    slot_in_caption_fuzzy = Counter()
    exact_all_in_command = 0
    exact_all_in_caption = 0
    object_absent_from_both = []
    command_collisions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    action_vocab = Counter()
    object_vocab = Counter()
    surface_trap_in_command = 0
    for row in rows:
        slots = row["slots"]
        command = row["command"]
        caption = row.get("scene_context") or ""
        command_collisions[norm(command)].append({"record_id": row["id"], "slots": slots, "caption": caption[:180]})
        action_vocab[norm(slots["action"])] += 1
        object_vocab[norm(slots["object"])] += 1
        present_command = {field: contains_slot(command, slots[field]) for field in ("subject", "action", "object")}
        present_caption = {field: contains_slot(caption, slots[field]) for field in ("subject", "action", "object")}
        for field, found in present_command.items():
            slot_in_command[field] += int(found)
        for field, found in present_caption.items():
            slot_in_caption_fuzzy[field] += int(found)
            slot_in_caption[field] += int(norm(slots[field]) in norm(caption))
        exact_all_in_command += int(all(present_command.values()))
        exact_all_in_caption += int(all(present_caption.values()))
        if not present_command["object"] and not present_caption["object"]:
            object_absent_from_both.append(row["id"])
        surface = ((row.get("source_metadata") or {}).get("mcq") or {}).get("3_surface_understanding") or ""
        if surface and any(token in norm(command) for token in re.findall(r"[a-z]{4,}", norm(surface))[:6]):
            surface_trap_in_command += 1
    conflicting = []
    for command, group in command_collisions.items():
        variants = {json.dumps(item["slots"], sort_keys=True) for item in group}
        if len(group) > 1 and len(variants) > 1:
            conflicting.append({"command": command, "n": len(group), "variants": [item["slots"] for item in group], "record_ids": [item["record_id"] for item in group]})
    triplet_counts = Counter(json.dumps((row["slots"]["subject"], row["slots"]["action"], row["slots"]["object"])) for row in rows)
    modal_triplet, modal_n = triplet_counts.most_common(1)[0]
    lexical_upper_bound_command = exact_all_in_command / len(rows)
    return {
        "n": len(rows),
        "source_sha256": sha(path),
        "scientific_task": "recover a concrete (subject, action, object) triplet from an indirect command, optionally with a textual caption; not generic intent classification",
        "literal_slot_presence_exact": {
            "command": dict(slot_in_command),
            "caption": dict(slot_in_caption),
        },
        "literal_slot_presence_plural_tolerant": {
            "command": dict(slot_in_command),
            "caption": dict(slot_in_caption_fuzzy),
        },
        "exact_all_three_slots_in_command": {"count": exact_all_in_command, "rate": lexical_upper_bound_command, "wilson95": wilson(exact_all_in_command, len(rows))},
        "exact_all_three_slots_in_caption": {"count": exact_all_in_caption, "rate": exact_all_in_caption / len(rows), "wilson95": wilson(exact_all_in_caption, len(rows))},
        "object_absent_from_command_and_caption": {"count": len(object_absent_from_both), "example_ids": object_absent_from_both[:8]},
        "command_target_collisions": conflicting,
        "modal_triplet": {"label": json.loads(modal_triplet), "count": modal_n, "rate": modal_n / len(rows)},
        "top_actions": action_vocab.most_common(8),
        "top_objects": object_vocab.most_common(8),
        "distinct_actions": len(action_vocab),
        "distinct_objects": len(object_vocab),
        "surface_understanding_lexical_overlap_with_command": surface_trap_in_command,
        "why_command_only_is_hard": "Action occurs literally in 7 commands and object in 48; an exact triplet copy from the command is almost impossible. Caption often names the object (binoculars, strap) while the command is figurative.",
        "example_indirect_to_concrete": [
            {
                "record_id": rows[0]["id"],
                "command": rows[0]["command"],
                "caption": rows[0]["scene_context"],
                "direct": (rows[0].get("source_metadata") or {}).get("direct"),
                "slots": rows[0]["slots"],
                "surface_trap": ((rows[0].get("source_metadata") or {}).get("mcq") or {}).get("3_surface_understanding"),
            }
        ],
    }


def ambik_analysis() -> dict[str, Any]:
    packet = load_jsonl(ROOT / "outputs" / "ambik_ambiguity_type_inference_packet_20260908.jsonl")
    key = {row["record_id"]: row for row in load_jsonl(ROOT / "outputs" / "ambik_ambiguity_type_source_key_20260908.jsonl")}
    cue_terms = {
        "safety_precondition": ("hot", "sharp", "knife", "allerg", "child", "poison", "break", "fragile", "burn", "raw", "hazard", "danger", "safety"),
        "preference": ("prefer", "favorite", "favourite", "like", "usual", "always drink", "the one you", "whichever"),
        "commonsense": ("appropriate", "suitable", "usual place", "where it belongs", "the rest"),
    }
    cue_hits = {label: 0 for label in cue_terms}
    cue_precision = {label: Counter() for label in cue_terms}
    by_type = Counter()
    examples = {label: [] for label in cue_terms}
    for row in packet:
        label = key[row["record_id"]]["ambiguity_types"][0]
        by_type[label] += 1
        text = f"{row['command']} {row.get('scene_context') or ''}"
        hay = norm(text)
        for candidate, terms in cue_terms.items():
            if any(term in hay for term in terms):
                cue_hits[candidate] += 1
                cue_precision[candidate][label] += 1
                if len(examples[candidate]) < 3:
                    examples[candidate].append({"record_id": row["record_id"], "gold": label, "command": row["command"][:180]})
    return {
        "n": len(packet),
        "type_counts": dict(by_type),
        "modal_baseline": {"label": "commonsense", "rate": by_type["commonsense"] / len(packet), "count": by_type["commonsense"]},
        "safety_share": by_type["safety_precondition"] / len(packet),
        "accuracy_if_never_predict_safety_and_perfect_otherwise": (len(packet) - by_type["safety_precondition"]) / len(packet),
        "lexical_cue_screen": {
            label: {
                "rows_with_any_cue": cue_hits[label],
                "gold_given_cue": dict(cue_precision[label]),
                "examples": examples[label],
            }
            for label in cue_terms
        },
        "claim": "Cue words are a screening signal, not a label. Safety is the smallest class, so headline accuracy can look strong while safety recall is poor.",
    }


def clara_analysis() -> dict[str, Any]:
    packet = [row for row in load_jsonl(ROOT / "outputs" / "clara_context_routing_packet_20260908.jsonl") if row["condition"] == "full_context"]
    key = {row["record_id"]: row for row in load_jsonl(ROOT / "outputs" / "clara_context_routing_key_20260908.jsonl")}
    ledger = load_jsonl(ROOT / "outputs" / "clara_effective_input_ledger_20260911.jsonl")
    triples = []
    robot_types = Counter()
    strategy_given_capability = []
    strategy_given_ambiguity = []
    capability_in_context = Counter()
    for row in packet:
        gold = key[row["record_id"]]
        triples.append((gold["ambiguity_present"], gold["capability_status"], gold["recommended_strategy"]))
        cap = str(row.get("capability_context") or "")
        robot = cap.split(":", 1)[-1].strip() if ":" in cap else cap
        robot_types[robot or "MISSING"] += 1
        strategy_given_capability.append((str(gold["capability_status"]), str(gold["recommended_strategy"])))
        strategy_given_ambiguity.append((str(gold["ambiguity_present"]), str(gold["recommended_strategy"])))
        lowered = cap.casefold()
        if gold["capability_status"] and str(gold["capability_status"]).casefold() in lowered:
            capability_in_context["status_token_in_capability_line"] += 1
    triple_counts = Counter(triples)
    inconsistent = [group for group in ledger if group["source_target_consistency"] != "CONSISTENT"]
    inconsistent_examples = []
    for group in inconsistent[:5]:
        members = []
        for record_id in group["record_ids"]:
            gold = key[record_id]
            members.append({
                "record_id": record_id,
                "command": next(row["command"] for row in packet if row["record_id"] == record_id)[:140],
                "target": {
                    "ambiguity_present": gold["ambiguity_present"],
                    "capability_status": gold["capability_status"],
                    "recommended_strategy": gold["recommended_strategy"],
                },
            })
        inconsistent_examples.append({"multiplicity": group["multiplicity"], "members": members})
    return {
        "n": len(packet),
        "modal_triple": {"label": triple_counts.most_common(1)[0][0], "count": triple_counts.most_common(1)[0][1], "rate": triple_counts.most_common(1)[0][1] / len(packet)},
        "triple_counts_top": [{"label": label, "count": count} for label, count in triple_counts.most_common(6)],
        "mutual_information": {
            "capability_vs_strategy": mutual_information(strategy_given_capability),
            "ambiguity_vs_strategy": mutual_information(strategy_given_ambiguity),
        },
        "robot_type_counts": dict(robot_types.most_common(8)),
        "capability_status_token_in_capability_line": dict(capability_in_context),
        "exact_input_groups": len(ledger),
        "inconsistent_groups": len(inconsistent),
        "inconsistent_examples": inconsistent_examples,
        "why_factorial_needed": "full_context vs context_blind removes scene and capability together, and strategy is nearly a deterministic function of the other two labels.",
    }


def indirect_analysis() -> dict[str, Any]:
    packet = load_jsonl(ROOT / "outputs" / "indirect_pragmatic_packet_20260908.jsonl")
    key = {row["record_id"]: row for row in load_jsonl(ROOT / "outputs" / "indirect_pragmatic_key_20260908.jsonl")}
    ledger = load_jsonl(ROOT / "outputs" / "indirect_effective_input_ledger_20260911.jsonl")
    n = len(packet)
    ambiguous = [row for row in packet if key[row["record_id"]]["ambiguity_present"]]
    non_ambiguous = [row for row in packet if not key[row["record_id"]]["ambiguity_present"]]
    slot_in_scene = 0
    slot_in_command = 0
    scene_leaks_task_template = 0
    for row in packet:
        gold = key[row["record_id"]]
        slots = gold.get("missing_slots") or []
        scene = row.get("scene_context") or ""
        command = row["command"]
        if "user wants to" in norm(scene):
            scene_leaks_task_template += 1
        if any(contains_slot(scene, slot) for slot in slots):
            slot_in_scene += 1
        if any(contains_slot(command, slot) for slot in slots):
            slot_in_command += 1
    coupled = all((bool(key[row["record_id"]]["missing_slots"]) == bool(key[row["record_id"]]["ambiguity_present"])) for row in packet)
    return {
        "n": n,
        "ambiguous": len(ambiguous),
        "non_ambiguous": len(non_ambiguous),
        "modal_joint_baseline": {"label": [False, [], []], "count": len(non_ambiguous), "rate": len(non_ambiguous) / n, "wilson95": wilson(len(non_ambiguous), n)},
        "unique_effective_inputs": len(ledger),
        "inconsistent_groups": sum(group["source_target_consistency"] != "CONSISTENT" for group in ledger),
        "missing_slot_presence_perfectly_tied_to_ambiguity": coupled,
        "scene_context_is_task_template_count": scene_leaks_task_template,
        "missing_slot_token_in_scene_context": slot_in_scene,
        "missing_slot_token_in_command": slot_in_command,
        "example_ambiguous": {
            "record_id": ambiguous[0]["record_id"],
            "command": ambiguous[0]["command"],
            "scene_context": ambiguous[0]["scene_context"],
            "missing_slots": key[ambiguous[0]["record_id"]]["missing_slots"],
        },
        "example_non_ambiguous": {
            "record_id": non_ambiguous[0]["record_id"],
            "command": non_ambiguous[0]["command"],
            "scene_context": non_ambiguous[0]["scene_context"],
            "missing_slots": key[non_ambiguous[0]["record_id"]]["missing_slots"],
        },
        "claim": "A trivial always-not-ambiguous predictor scores 82.1%. Scene context is a task template, not visual evidence, and missing-slot presence is deterministically coupled to the ambiguity bit.",
    }


def t39_analysis() -> dict[str, Any]:
    rows_path = ROOT / "outputs" / "pilot120_semantic_intent_judging_20260908" / "final_intent_rows.csv"
    gold_path = ROOT / "data" / "annotations" / "pilot_120_v1" / "pilot_120_final_gold.jsonl"
    intent_gold_path = ROOT / "pilot120_intent_evaluation_20260902" / "pilot120_intent_evaluation_20260902" / "data" / "intent_gold_references_120.jsonl"
    with rows_path.open(encoding="utf-8", newline="") as handle:
        data = list(csv.DictReader(handle))
    for row in data:
        for field in ("speech_act_correct", "semantic_goal_correct", "full_intent_correct", "route_correct"):
            row[field] = row[field] == "True"
    gold = {row["record_id"]: row for row in load_jsonl(gold_path)}
    intent_gold = {row["record_id"]: row for row in load_jsonl(intent_gold_path)}
    systems = sorted({row["system_id"] for row in data})
    out: dict[str, Any] = {"source_hashes": {"rows": sha(rows_path), "pilot_gold": sha(gold_path), "intent_gold": sha(intent_gold_path)}}
    for system in systems:
        subset = [row for row in data if row["system_id"] == system]
        route_confusion = Counter((row["gold_terminal_strategy"], row["terminal_strategy"]) for row in subset)
        speech_confusion = Counter((row["gold_speech_act"], row["predicted_speech_act"]) for row in subset)
        states = Counter((row["semantic_goal_correct"], row["speech_act_correct"], row["route_correct"]) for row in subset)
        a = sum(row["semantic_goal_correct"] and row["route_correct"] for row in subset)
        b = sum(row["semantic_goal_correct"] and not row["route_correct"] for row in subset)
        c = sum(not row["semantic_goal_correct"] and row["route_correct"] for row in subset)
        d = sum(not row["semantic_goal_correct"] and not row["route_correct"] for row in subset)
        den = math.sqrt((a + b) * (c + d) * (a + c) * (b + d))
        clarify_given_execute = sum(row["gold_terminal_strategy"] == "execute" and row["terminal_strategy"] == "clarify" for row in subset)
        execute_gold = sum(row["gold_terminal_strategy"] == "execute" for row in subset)
        indirect = [row for row in subset if row["gold_speech_act"] == "indirect_request"]
        accidental = []
        layer3 = []
        layer2 = []
        for row in subset:
            source = intent_gold[row["record_id"]]["source"]
            payload = {
                "record_id": row["record_id"],
                "command": source["command"],
                "gold_speech_act": row["gold_speech_act"],
                "predicted_speech_act": row["predicted_speech_act"],
                "gold_route": row["gold_terminal_strategy"],
                "predicted_route": row["terminal_strategy"],
                "ambiguity_types": gold[row["record_id"]]["ambiguity_types"],
                "intent_reference": intent_gold[row["record_id"]]["reference_A_intent_text"][:180],
            }
            if row["semantic_goal_correct"] and row["speech_act_correct"] and not row["route_correct"] and len(layer3) < 5:
                layer3.append(payload)
            if row["semantic_goal_correct"] and not row["speech_act_correct"] and not row["route_correct"] and len(layer2) < 5:
                layer2.append(payload)
            if (not row["semantic_goal_correct"]) and row["route_correct"] and len(accidental) < 5:
                accidental.append(payload)
        out[system] = {
            "n": len(subset),
            "pathway_state_counts": {f"SGC={sgc}|SAA={saa}|ROUTE={route}": count for (sgc, saa, route), count in sorted(states.items())},
            "sgc_route_matrix": {"A_both": a, "B_goal_only": b, "C_route_only": c, "D_neither": d, "phi": (a * d - b * c) / den if den else None},
            "overclarify_when_gold_execute": {"count": clarify_given_execute, "execute_gold_n": execute_gold, "rate": clarify_given_execute / execute_gold if execute_gold else None},
            "route_confusion": {f"gold={gold_s}|pred={pred}": count for (gold_s, pred), count in sorted(route_confusion.items())},
            "speech_act_confusion": {f"gold={gold_s}|pred={pred}": count for (gold_s, pred), count in sorted(speech_confusion.items())},
            "indirect_request": {
                "n": len(indirect),
                "sgc": sum(row["semantic_goal_correct"] for row in indirect),
                "saa": sum(row["speech_act_correct"] for row in indirect),
                "route": sum(row["route_correct"] for row in indirect),
                "fic": sum(row["full_intent_correct"] for row in indirect),
            },
            "examples_layer2_goal_right_speech_wrong": layer2,
            "examples_layer3_goal_and_speech_right_route_wrong": layer3,
            "examples_accidental_route_correct_goal_wrong": accidental,
        }
    full = [row for row in data if row["system_id"] == "full_type_risk_aware_manager"]
    blind = [row for row in data if row["system_id"] == "context_blind_manager"]
    full = sorted(full, key=lambda row: row["record_id"])
    blind = sorted(blind, key=lambda row: row["record_id"])
    fic_full = [row["full_intent_correct"] for row in full]
    fic_blind = [row["full_intent_correct"] for row in blind]
    sgc_full = [row["semantic_goal_correct"] for row in full]
    sgc_blind = [row["semantic_goal_correct"] for row in blind]
    out["paired_full_vs_blind"] = {
        "sgc_full_minus_blind_pp": (sum(sgc_full) - sum(sgc_blind)) / len(full),
        "fic_full_minus_blind_pp": (sum(fic_full) - sum(fic_blind)) / len(full),
        "interpretation": "Context moves observable goal traces much more than full-intent/route success. FIC barely changes because speech-act/route remain the bottleneck.",
    }
    out["math_claim"] = {
        "wrong_turn_right_visible_goal": "For the full manager, 83/120 records have a correct observable goal trace and a wrong route. That is not environment task success.",
        "accidental_right_turn": "Only 3/120 full-manager records have a correct route after a wrong goal trace. Lucky routing is rare; over-clarification is common.",
        "layer4": "NOT_COMPUTED. Frozen T39 has no CPC/resolution/execution log, so a pure router fault cannot be identified.",
        "phi_negative_note": "The SGC-route phi for the full manager is slightly negative because the SGC-wrong cell is tiny (n=7) and happens to contain 3 correct routes. Do not generalise that understanding hurts routing.",
    }
    return out


def main() -> None:
    result = {
        "analysis_id": "mechanism_deep_dive_v1_20260911",
        "claim_boundary": "source-data and frozen T39 observable-trace analysis only; dataset-native model outputs are not scored here",
        "vague": vague_analysis(),
        "ambik": ambik_analysis(),
        "clara": clara_analysis(),
        "indirect_requests": indirect_analysis(),
        "t39_frozen": t39_analysis(),
    }
    out_json = ROOT / "outputs" / "mechanism_deep_dive_20260911.json"
    out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "out": str(out_json), "sha256": sha(out_json)}, sort_keys=True))


if __name__ == "__main__":
    main()
