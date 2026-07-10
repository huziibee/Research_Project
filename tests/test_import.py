"""Package import smoke test. Run with ``python -m unittest``."""

from __future__ import annotations

import unittest


class ImportTests(unittest.TestCase):
    def test_import_ambiguity_manager(self) -> None:
        import ambiguity_manager

        self.assertTrue(ambiguity_manager.__version__)


if __name__ == "__main__":
    unittest.main()
