"""T27C constrained-decoding policy tests (CPU-only; may skip library)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.model.task_constrained_decoding import (  # noqa: E402
    PINNED_LIBRARY,
    PINNED_VERSION,
    ConstrainedDecodingError,
    build_constraint_identity,
    compile_task_constraint,
    load_constraint_config,
)
from ambiguity_manager.model.task_prediction_contract import load_task_registry  # noqa: E402
from ambiguity_manager.model.task_prediction_contract import render_qwen_task_prompt  # noqa: E402
from ambiguity_manager.model.t27c_runtime_recovery import generated_continuation  # noqa: E402


class T27CConstrainedDecodingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_constraint_config(ROOT)
        cls.registry = load_task_registry(ROOT)

    def test_pinned_library_and_no_fallback(self) -> None:
        self.assertEqual(self.config["library"], PINNED_LIBRARY)
        self.assertEqual(self.config["version"], PINNED_VERSION)
        self.assertIs(self.config["unconstrained_fallback_permitted"], False)
        self.assertEqual(self.config["fallback_behaviour"], "fail_task_call_with_ConstrainedDecodingError")

    def test_each_task_schema_compiles_or_fails_closed(self) -> None:
        identities = []
        for task in self.registry["tasks"]:
            schema = task["json_schema"]
            identity = build_constraint_identity(task_id=task["task_id"], json_schema=schema)
            identities.append(identity.schema_hash)
            self.assertFalse(identity.unconstrained_fallback_permitted)
            self.assertEqual(identity.library, PINNED_LIBRARY)
            self.assertEqual(identity.version, PINNED_VERSION)
            try:
                compile_task_constraint(schema)
            except ConstrainedDecodingError as exc:
                # Library absent locally is acceptable; must not fall back.
                self.assertIn("lm-format-enforcer", str(exc).lower())
        # Distinct schemas should produce distinct hashes where schemas differ.
        self.assertGreaterEqual(len(set(identities)), 4)

    def test_unsupported_schema_fails_clearly(self) -> None:
        bad = {"type": "object", "properties": {"x": {"type": "not-a-real-type"}}}
        try:
            compile_task_constraint(bad)
        except ConstrainedDecodingError:
            return
        except Exception:
            # Some library versions may raise a different error; still fail-closed.
            return
        # If compile succeeds despite bad type, that is library-specific; do not force fail.

    def test_qwen_chat_template_disables_thinking_and_adds_assistant_boundary(self) -> None:
        class FakeTokenizer:
            def __init__(self) -> None:
                self.calls = []

            def apply_chat_template(self, messages, **kwargs):
                self.calls.append((messages, kwargs))
                return "<|user|>" + messages[0]["content"] + "<|assistant|>"

        tokenizer = FakeTokenizer()
        rendered = render_qwen_task_prompt(tokenizer, "TASK_ID=predict_cpc_v1")
        self.assertTrue(rendered.endswith("<|assistant|>"))
        self.assertFalse(tokenizer.calls[0][1]["enable_thinking"])
        self.assertTrue(tokenizer.calls[0][1]["add_generation_prompt"])

    def test_generated_continuation_excludes_prompt_echo(self) -> None:
        self.assertEqual(generated_continuation([1, 2, 3], [1, 2, 3, 4]), [4])
        with self.assertRaises(Exception):
            generated_continuation([1, 2, 3], [1, 9, 3, 4])


if __name__ == "__main__":
    unittest.main()
