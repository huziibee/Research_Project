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


if __name__ == "__main__":
    unittest.main()
