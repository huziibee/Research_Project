"""Repository smoke test for governance validation CLI."""

from __future__ import annotations

import subprocess
import sys
import unittest

from ambiguity_manager.governance.validation import validate_repository_governance
from ambiguity_manager.paths import ProjectPaths


class TestGovernanceRepoSmoke(unittest.TestCase):
    def test_repository_governance_validation_passes(self) -> None:
        paths = ProjectPaths.from_repo_root()
        errors = validate_repository_governance(paths.root)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_validate_governance_script_exit_zero(self) -> None:
        import os

        paths = ProjectPaths.from_repo_root()
        env = os.environ.copy()
        env["PYTHONPATH"] = "src"
        result = subprocess.run(
            [sys.executable, str(paths.root / "scripts" / "validate_governance.py")],
            cwd=paths.root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
