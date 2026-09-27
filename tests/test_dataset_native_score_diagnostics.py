import importlib.util
from pathlib import Path


def load(name: str):
    path = Path(__file__).parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


diag = load("dataset_native_score_diagnostics.py")
native = load("score_native_context.py")
vague = load("score_vague_goal_intent.py")
ambik = load("score_ambik_ambiguity_type.py")


def test_modal_baseline_and_unique_input_sensitivity():
    labels = [("a",), ("a",), ("b",)]
    baseline = diag.modal_joint_baseline(labels)
    assert baseline["modal_count"] == 2
    assert abs(baseline["rate"] - 2 / 3) < 1e-12
    scored = [
        {"record_id": "r1", "condition": "full_context", "correct": True},
        {"record_id": "r2", "condition": "full_context", "correct": False},
        {"record_id": "r3", "condition": "full_context", "correct": True},
    ]
    ledger = [
        {"record_ids": ["r1", "r1b"], "source_target_consistency": "CONSISTENT"},
        {"record_ids": ["r2", "r2b"], "source_target_consistency": "CONFLICTING"},
        {"record_ids": ["r3"], "source_target_consistency": "CONSISTENT"},
    ]
    result = diag.unique_input_sensitivity(scored, ledger, condition="full_context")
    assert result["excluded_inconsistent_groups"] == 1
    assert result["correct"] == 2
    assert result["scored_rows"] == 2


def test_native_context_reports_baseline_and_positive_class():
    key = []
    predictions = []
    for i in range(4):
        record_id = f"indirect:{i}"
        present = i == 0
        gold = {
            "record_id": record_id,
            "source_fingerprint_sha256": record_id,
            "ambiguity_present": present,
            "ambiguity_types": ["pragmatic"] if present else [],
            "missing_slots": ["slot"] if present else [],
        }
        key.append(gold)
        predictions.append({**gold, "condition": "source_native_context", "ambiguity_present": False, "ambiguity_types": [], "missing_slots": []})
    result = native.score_rows("indirect", key, predictions)
    assert result["modal_joint_baseline"]["modal_count"] == 3
    assert result["ambiguity_present_confusion"]["false_negative"] == 1
    assert result["ambiguity_present_confusion"]["true_negative"] == 3


def test_vague_modal_baseline_survives_synthetic_packet():
    gold = []
    predictions = []
    slots_a = {"subject": "person1", "action": "move", "object": "box"}
    slots_b = {"subject": "person1", "action": "move", "object": "cup"}
    for i in range(1677):
        record_id = f"row-{i}"
        slots = slots_a if i < 20 else slots_b
        for condition in ("command_only", "command_plus_textual_caption"):
            gold.append({"record_id": record_id, "condition": condition, "source_fingerprint_sha256": record_id, "source_target": {"slots": slots}})
            guessed = slots if condition == "command_plus_textual_caption" else {**slots, "object": "wrong"}
            predictions.append({"record_id": record_id, "condition": condition, "source_fingerprint_sha256": record_id, "goal_triplet": guessed})
    result = vague.score_rows(gold, predictions)
    assert result["modal_joint_baseline"]["modal_count"] == 1657
    assert result["conditions"]["command_only"]["rate"] == 0


def test_ambik_macro_and_interval_are_present():
    key = []
    prediction = []
    types = ["preference"] * 425 + ["commonsense"] * 420 + ["safety_precondition"] * 155
    for i, label in enumerate(types):
        row = {"record_id": str(i), "source_fingerprint_sha256": str(i), "ambiguity_types": [label]}
        key.append(row)
        prediction.append(dict(row))
    prediction[0]["ambiguity_types"] = ["commonsense"]
    result = ambik.score_rows(key, prediction)
    assert result["correct"] == 999
    assert "macro_exact_set_recall" in result
    assert result["modal_joint_baseline"]["modal_count"] == 425
