import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("vague_scorer", Path(__file__).parents[1] / "scripts" / "score_vague_goal_intent.py")
scorer = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(scorer)


def prepared_rows():
    gold = []
    predictions = []
    slots = {"subject": "person1", "action": "move", "object": "box"}
    for i in range(1677):
        record_id = f"row-{i}"
        for condition in ("command_only", "command_plus_textual_caption"):
            gold.append({"record_id": record_id, "condition": condition, "source_fingerprint_sha256": record_id, "source_target": {"slots": slots}})
            guessed = slots if condition == "command_plus_textual_caption" else {**slots, "object": "wrong"}
            predictions.append({"record_id": record_id, "condition": condition, "source_fingerprint_sha256": record_id, "goal_triplet": guessed})
    return gold, predictions


def test_scores_goal_triplet_and_paired_caption_gain():
    gold, predictions = prepared_rows()
    result = scorer.score_rows(gold, predictions)
    assert result["conditions"]["command_only"]["rate"] == 0
    assert result["conditions"]["command_plus_textual_caption"]["rate"] == 1


def test_rejects_duplicate_prediction_evaluation_id():
    gold, predictions = prepared_rows()
    predictions.append(predictions[-1])
    try:
        scorer.score_rows(gold, predictions)
    except ValueError as exc:
        assert str(exc) == "prediction_duplicate_evaluation_id"
    else:
        raise AssertionError("duplicate prediction IDs must be rejected")
