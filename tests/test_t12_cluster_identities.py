"""Tests for T12 cluster immutable selection identities."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiguity_manager.model.cluster.identities import (
    IMMUTABLE_SELECTION_REL,
    load_immutable_selection,
    validate_immutable_selection,
)
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root
SELECTION_PATH = ROOT / IMMUTABLE_SELECTION_REL

MODEL_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
CONTAINER_SHA = "d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1"


class T12ClusterIdentitiesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.selection = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))

    def test_immutable_selection_loads(self) -> None:
        loaded = load_immutable_selection(ROOT)
        self.assertEqual(loaded.model_repository, "Qwen/Qwen3-8B")

    def test_exact_model_revision(self) -> None:
        self.assertEqual(self.selection["model_revision"], MODEL_REVISION)

    def test_exact_tokenizer_revision(self) -> None:
        self.assertEqual(self.selection["tokenizer_revision"], MODEL_REVISION)

    def test_exact_container_sha(self) -> None:
        self.assertEqual(self.selection["container_sha256"], CONTAINER_SHA)

    def test_exact_container_size(self) -> None:
        self.assertEqual(self.selection["container_size_bytes"], 7657443328)

    def test_malformed_sha_rejected(self) -> None:
        bad = dict(self.selection)
        bad["container_sha256"] = "abc"
        errors = validate_immutable_selection(bad)
        self.assertTrue(errors)

    def test_wrong_container_size_rejected(self) -> None:
        bad = dict(self.selection)
        bad["container_size_bytes"] = 1
        errors = validate_immutable_selection(bad)
        self.assertTrue(errors)

    def test_provisional_candidate_status(self) -> None:
        self.assertEqual(
            self.selection["candidate_status"],
            "provisionally_selected_for_cluster_validation",
        )


if __name__ == "__main__":
    unittest.main()
