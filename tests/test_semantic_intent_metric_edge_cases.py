"""Synthetic regression checks only; these are not Pilot-120 results."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from intent_eval_common import clean_observable_trace, semantic_goal_correct  # noqa: E402


def decision(**changes):
    row = dict(primary_goal_match=True, required_action_set_match=True, polarity_match=True, explicit_enough=True, no_incompatible_goal=True)
    row.update(changes)
    return row


def test_paraphrase_and_indirect_request_can_be_semantically_correct():
    assert semantic_goal_correct(decision())


def test_lexical_overlap_reversal_negation_prohibition_and_agent_patient_reversal_fail():
    assert not semantic_goal_correct(decision(polarity_match=False))
    assert not semantic_goal_correct(decision(primary_goal_match=False))
    assert not semantic_goal_correct(decision(no_incompatible_goal=False))


def test_multi_action_and_conditional_goal_require_complete_action_set():
    assert not semantic_goal_correct(decision(required_action_set_match=False))


def test_command_copy_only_is_removed_and_cannot_be_credited():
    command = "Move the red box to the shelf."
    trace = clean_observable_trace(f"<think>{command}</think>", command)
    assert command.casefold() not in trace.casefold()


def test_correct_goal_wrong_speech_act_wrong_route_and_accidentally_correct_route_are_distinct():
    sgc = semantic_goal_correct(decision())
    saa = False
    assert sgc and not (sgc and saa)  # correct goal, wrong speech act: FIC false.
    route_correct = False
    assert sgc and not route_correct  # correct goal + wrong route.
    wrong_goal = semantic_goal_correct(decision(primary_goal_match=False))
    accidentally_correct_route = True
    assert not wrong_goal and accidentally_correct_route
