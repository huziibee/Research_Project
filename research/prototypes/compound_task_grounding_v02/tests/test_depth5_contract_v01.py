"""Five-round interactive task-state contract tests; synthetic fixtures only."""
import unittest
from compound_manager.pipeline import FixtureModel, run_dialogue


def synthetic_spec(n):
    variables = {
        f"v{i}": {
            "options": [
                {"value": "A", "evidence": f"value {i} A"},
                {"value": "B", "evidence": f"value {i} B"},
            ],
            "question": f"Which value for v{i}: A or B?",
            "grounded": None,
        }
        for i in range(1, n + 1)
    }
    return {
        "schema_version": "0.1",
        "record_id": f"SYN-DEPTH-{n}",
        "utterance": "Configure the fixture using the specified settings.",
        "context_evidence": [],
        "lookups": {},
        "variables": variables,
        "templates": [{
            "actions": [{
                "id": "A1",
                "op": "CONFIGURE",
                "args": {name: {"$var": name} for name in variables},
                "after": [],
            }]
        }],
    }


def synthetic_source(spec):
    evidence = " ".join(
        option["evidence"]
        for var in spec["variables"].values()
        for option in var["options"]
    )
    return {
        "record_id": spec["record_id"],
        "command": spec["utterance"],
        "scene_context": evidence,
        "dialogue_history": [],
    }


class DepthFiveContractTests(unittest.TestCase):
    def run_case(self, n, answers):
        spec = synthetic_spec(n)
        model = FixtureModel({spec["record_id"]: spec})
        return run_dialogue(synthetic_source(spec), model, answers, max_questions=5)

    def test_five_sequential_answers_complete_task(self):
        state = self.run_case(5, [f"v{i}=B" for i in range(1, 6)])
        self.assertEqual(state["status"], "action_ready")
        self.assertEqual(state["turns_used"], 5)
        self.assertEqual(state["termination"], "action_ready")
        self.assertEqual(len(state["spec"]["answer_history"]), 5)
        self.assertEqual(
            state["verdict"]["complete_task"]["actions"][0]["args"],
            {f"v{i}": "B" for i in range(1, 6)},
        )

    def test_sixth_required_question_hits_depth_cap(self):
        state = self.run_case(6, [f"v{i}=B" for i in range(1, 7)])
        self.assertEqual(state["status"], "needs_clarification")
        self.assertEqual(state["turns_used"], 5)
        self.assertEqual(state["termination"], "depth_cap")
        self.assertFalse(state["verdict"]["action_ready"])
        self.assertEqual(state["verdict"]["blocking_variables"], ["v6"])
        self.assertEqual(state["verdict"]["distinct_tasks"], 2)

    def test_no_answer_creates_no_progress(self):
        state = self.run_case(5, [])
        self.assertEqual(state["status"], "needs_clarification")
        self.assertEqual(state["turns_used"], 0)
        self.assertEqual(state["spec"].get("answer_history", []), [])

    def test_invalid_answer_is_not_credited(self):
        state = self.run_case(5, ["v1=C", "v1=B"])
        self.assertEqual(state["status"], "needs_clarification")
        self.assertEqual(state["turns_used"], 0)
        self.assertIn("ambiguous_or_unrecognized_answer", state["answer_error"])

    def test_cannot_set_six_round_budget(self):
        spec = synthetic_spec(6)
        with self.assertRaisesRegex(ValueError, "max_questions_out_of_range"):
            run_dialogue(
                synthetic_source(spec),
                FixtureModel({spec["record_id"]: spec}),
                [],
                max_questions=6,
            )


if __name__ == "__main__":
    unittest.main()
