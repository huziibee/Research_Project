"""Tests for T12 Stage D1A response-mode verification contract."""

from __future__ import annotations

import unittest
from pathlib import Path

from ambiguity_manager.model.response_mode import (
    D1A_RESPONSE_MODE_STATUS,
    ModelResponseModeIdentity,
    ResponseModeError,
    ResponseModeStatus,
    ResponseModeVerifier,
    load_default_response_mode_verifier,
)


class T12ResponseModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = ModelResponseModeIdentity(
            model_repository="Qwen/Qwen3-8B",
            immutable_revision="b968826d9c46dd6066d109eabc6255188de91218",
        )
        self.verifier = ResponseModeVerifier(self.identity)

    def test_initial_status_is_unverified(self) -> None:
        self.assertEqual(self.verifier.status, ResponseModeStatus.UNVERIFIED)

    def test_unverified_blocks_generation_ready_rendering(self) -> None:
        with self.assertRaises(ResponseModeError) as ctx:
            self.verifier.require_generation_ready()
        self.assertIn(D1A_RESPONSE_MODE_STATUS, str(ctx.exception))

    def test_d1a_status_constant(self) -> None:
        self.assertEqual(
            D1A_RESPONSE_MODE_STATUS,
            "unverified_until_pinned_runtime_inspection",
        )

    def test_wrong_repository_fails(self) -> None:
        wrong = ModelResponseModeIdentity(
            model_repository="Qwen/Qwen2.5-1.5B-Instruct",
            immutable_revision="b968826d9c46dd6066d109eabc6255188de91218",
        )
        verifier = ResponseModeVerifier(wrong)
        with self.assertRaises(ResponseModeError):
            verifier.check_identity()

    def test_wrong_revision_fails(self) -> None:
        wrong = ModelResponseModeIdentity(
            model_repository="Qwen/Qwen3-8B",
            immutable_revision="0" * 40,
        )
        verifier = ResponseModeVerifier(wrong)
        with self.assertRaises(ResponseModeError):
            verifier.check_identity()

    def test_default_loader_matches_immutable_selection(self) -> None:
        verifier = load_default_response_mode_verifier()
        self.assertEqual(verifier.status, ResponseModeStatus.UNVERIFIED)
        verifier.check_identity()

    def test_no_heavy_imports_in_module(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "ambiguity_manager"
            / "model"
            / "response_mode.py"
        ).read_text(encoding="utf-8")
        for forbidden in ("import torch", "import transformers", "import vllm"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
