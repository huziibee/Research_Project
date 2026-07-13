"""Tests for T12 Stage D-Final Qwen3 renderer and response-mode probe policy."""

from __future__ import annotations

import copy
import importlib
import json
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ambiguity_manager.governance.hashing import sha256_hex
from ambiguity_manager.model.prediction_contract import model_semantic_output_schema_hash
from ambiguity_manager.model.qwen3_renderer import (
    Qwen3ChatTemplateRenderer,
    Qwen3RendererError,
    RunScopedVerifiedRenderer,
)
from ambiguity_manager.model.response_mode import ResponseModeStatus
from ambiguity_manager.model.response_mode_probe import (
    RunScopedResponseModeVerification,
    create_run_scoped_verification,
    evaluate_probe_candidate,
    load_response_mode_probe_policy,
    select_response_mode,
    verification_matches_run,
)
from ambiguity_manager.model.structured_decode import (
    load_structured_decode_contract,
    structured_decode_contract_hash,
)
from ambiguity_manager.schema.v2.taxonomies import CPCSlotStatus, RouteLabel

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_REPO = "Qwen/Qwen3-8B"
REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
CONTAINER_SHA = "d404bdf414e1b8f2d5af1568d0565d4e2da8435f26325b281fb28b9597c548d1"


@dataclass
class FakeTokenizer:
    apply_calls: list[dict[str, Any]] = field(default_factory=list)

    def apply_chat_template(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        self.apply_calls.append({"messages": copy.deepcopy(messages), "kwargs": dict(kwargs)})
        suffix = ""
        if kwargs.get("enable_thinking") is False:
            suffix = "|enable_thinking=False"
        body = "\n".join(f"{item['role']}: {item['content']}" for item in messages)
        if kwargs.get("add_generation_prompt"):
            body += "\nassistant:"
        return body + suffix


def _fake_tokenizer_factory(**_kwargs: Any) -> FakeTokenizer:
    return FakeTokenizer()


def _renderer(**overrides: Any) -> Qwen3ChatTemplateRenderer:
    defaults = {
        "snapshot_path": REPO_ROOT / "tests" / "tmp_tokenizer_snapshot",
        "model_repository": MODEL_REPO,
        "immutable_revision": REVISION,
        "tokenizer_factory": _fake_tokenizer_factory,
    }
    defaults.update(overrides)
    return Qwen3ChatTemplateRenderer(**defaults)


def _messages() -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "Turn on the desk lamp."},
    ]


def _empty_cpc() -> dict[str, Any]:
    slot = {"value": None, "status": CPCSlotStatus.UNKNOWN.value}
    return {name: dict(slot) for name in (
        "action", "actor", "object", "object_attributes", "destination",
        "spatial_relation", "quantity", "time", "recipient", "tool",
        "conditions", "constraints", "negation",
    )}


def _valid_semantic_json() -> str:
    payload = {
        "cpc": _empty_cpc(),
        "speech_act": None,
        "intent_summary": None,
        "candidate_interpretations": [],
        "selected_interpretation": None,
        "unresolved_slots": [],
        "supporting_evidence": [],
        "ambiguity_present": False,
        "ambiguity_types": [],
        "primary_ambiguity_type": None,
        "compound_ambiguity": False,
        "compound_ambiguity_count": 0,
        "risk_relevant": False,
        "risk_level": None,
        "capability_status": None,
        "recommended_strategy": RouteLabel.EXECUTE.value,
        "strategy_sequence": [],
        "clarification_question": None,
        "clarification_subtype": None,
        "clarification_targets": [],
        "rejection_reason": None,
        "resolved_slots": [],
        "resolution_method": None,
        "resolution_evidence": [],
        "context_sampling_uncertainty": None,
    }
    return json.dumps(payload, sort_keys=True)


def _structured_decode_metadata() -> dict[str, Any]:
    contract = load_structured_decode_contract()
    return {
        "contract_hash": structured_decode_contract_hash(contract),
        "schema_hash": model_semantic_output_schema_hash(),
        "required_vllm_version": contract.required_vllm_version,
        "detected_vllm_version": contract.required_vllm_version,
        "completions_per_request": 1,
        "construction_status": "constructed",
    }


class T12Qwen3RendererTests(unittest.TestCase):
    def test_module_imports_without_transformers(self) -> None:
        for name in list(sys.modules):
            if name.startswith("transformers"):
                del sys.modules[name]
        module = importlib.import_module("ambiguity_manager.model.qwen3_renderer")
        source = (REPO_ROOT / "src" / "ambiguity_manager" / "model" / "qwen3_renderer.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import transformers", source)
        self.assertNotIn("import torch", source)
        self.assertNotIn("import vllm", source)
        self.assertTrue(hasattr(module, "Qwen3ChatTemplateRenderer"))

    def test_unsupported_chat_roles_rejected(self) -> None:
        renderer = _renderer()
        with self.assertRaises(Qwen3RendererError):
            renderer.render_candidate(
                [{"role": "assistant", "content": "nope"}],
                mode="default",
            )

    def test_repository_revision_mismatch_rejected(self) -> None:
        with self.assertRaises(Qwen3RendererError):
            _renderer(model_repository="Qwen/Qwen2.5-1.5B-Instruct")

    def test_default_candidate_arguments_are_exact(self) -> None:
        renderer = _renderer()
        tokenizer = _fake_tokenizer_factory()
        renderer._tokenizer = tokenizer  # noqa: SLF001
        renderer._observed_tokenizer_hashes = {"tokenizer.json": "a" * 64}
        evidence = renderer.render_candidate(_messages(), mode="default")
        call = tokenizer.apply_calls[-1]["kwargs"]
        self.assertTrue(call["tokenize"] is False)
        self.assertTrue(call["add_generation_prompt"] is True)
        self.assertNotIn("enable_thinking", call)
        self.assertEqual(evidence.response_mode_status, ResponseModeStatus.UNVERIFIED.value)

    def test_enable_thinking_false_uses_exact_api(self) -> None:
        renderer = _renderer()
        tokenizer = _fake_tokenizer_factory()
        renderer._tokenizer = tokenizer  # noqa: SLF001
        renderer._observed_tokenizer_hashes = {"tokenizer.json": "a" * 64}
        renderer.render_candidate(_messages(), mode="enable_thinking_false")
        call = tokenizer.apply_calls[-1]["kwargs"]
        self.assertEqual(call.get("enable_thinking"), False)

    def test_generation_prompt_enabled(self) -> None:
        renderer = _renderer()
        tokenizer = _fake_tokenizer_factory()
        renderer._tokenizer = tokenizer  # noqa: SLF001
        renderer._observed_tokenizer_hashes = {"tokenizer.json": "a" * 64}
        evidence = renderer.render_candidate(_messages(), mode="default")
        self.assertIn("assistant:", evidence.rendered_prompt_text)

    def test_candidate_rendering_never_marks_verification(self) -> None:
        renderer = _renderer()
        renderer._tokenizer = _fake_tokenizer_factory()  # noqa: SLF001
        renderer._observed_tokenizer_hashes = {"tokenizer.json": "a" * 64}
        evidence = renderer.render_candidate(_messages(), mode="default")
        self.assertEqual(evidence.response_mode_status, ResponseModeStatus.UNVERIFIED.value)

    def test_hashes_deterministic(self) -> None:
        renderer = _renderer()
        renderer._tokenizer = _fake_tokenizer_factory()  # noqa: SLF001
        renderer._observed_tokenizer_hashes = {"tokenizer.json": "a" * 64}
        first = renderer.render_candidate(_messages(), mode="default")
        second = renderer.render_candidate(_messages(), mode="default")
        self.assertEqual(first.abstract_message_hash, second.abstract_message_hash)
        self.assertEqual(first.rendered_prompt_hash, second.rendered_prompt_hash)

    def test_messages_not_mutated(self) -> None:
        renderer = _renderer()
        renderer._tokenizer = _fake_tokenizer_factory()  # noqa: SLF001
        renderer._observed_tokenizer_hashes = {"tokenizer.json": "a" * 64}
        messages = _messages()
        original = copy.deepcopy(messages)
        renderer.render_candidate(messages, mode="default")
        self.assertEqual(messages, original)


class T12ResponseModeProbePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_response_mode_probe_policy()
        cls.contract = load_structured_decode_contract()
        cls.contract_hash = structured_decode_contract_hash(cls.contract)
        cls.schema_hash = model_semantic_output_schema_hash()
        cls.metadata = _structured_decode_metadata()
        from ambiguity_manager.model.cluster.identities import load_immutable_selection

        cls.immutable = load_immutable_selection()

    def _evaluate(self, raw_output: str, *, mode: str = "default", generation_status: str = "success"):
        return evaluate_probe_candidate(
            candidate_mode=mode,
            rendered_prompt_hash="a" * 64,
            raw_output=raw_output,
            generation_status=generation_status,
            finish_reason="stop",
            engine_request_id="engine-1",
            model_repository=MODEL_REPO,
            model_revision=REVISION,
            schema_hash=self.schema_hash,
            contract_hash=self.contract_hash,
            policy=self.policy,
            contract=self.contract,
            immutable=self.immutable,
            structured_decode_metadata=self.metadata,
        )

    def test_valid_exact_json_object_passes(self) -> None:
        result = self._evaluate(_valid_semantic_json())
        self.assertTrue(result.passed)
        self.assertEqual(result.direct_json_parse_status, "success")
        self.assertEqual(result.raw_object_status, "single_object")
        self.assertEqual(result.local_repair_attempts, 0)

    def test_trailing_comma_fails(self) -> None:
        raw = _valid_semantic_json()[:-1] + ",}"
        result = self._evaluate(raw)
        self.assertFalse(result.passed)
        self.assertEqual(result.direct_json_parse_status, "failed")

    def test_fenced_json_fails(self) -> None:
        result = self._evaluate("```json\n" + _valid_semantic_json() + "\n```")
        self.assertFalse(result.passed)

    def test_python_literals_fail(self) -> None:
        result = self._evaluate('{"cpc": {}, "recommended_strategy": "execute", "ambiguity_present": True}')
        self.assertFalse(result.passed)

    def test_outer_object_isolation_required(self) -> None:
        result = self._evaluate("note " + _valid_semantic_json())
        self.assertFalse(result.passed)

    def test_semantic_schema_invalid_exact_json_fails(self) -> None:
        result = self._evaluate('{"cpc": {}}')
        self.assertFalse(result.passed)
        self.assertEqual(result.semantic_schema_status, "invalid")

    def test_repair_count_zero_for_passing_probe(self) -> None:
        result = self._evaluate(_valid_semantic_json())
        self.assertTrue(result.passed)
        self.assertEqual(result.local_repair_attempts, 0)
        self.assertEqual(result.local_repair_log, ())

    def test_candidate_order_is_frozen(self) -> None:
        self.assertEqual(self.policy.candidate_order, ("default", "enable_thinking_false"))

    def test_first_passing_mode_wins(self) -> None:
        passing_default = self._evaluate(_valid_semantic_json(), mode="default")
        failing_other = self._evaluate("bad", mode="enable_thinking_false", generation_status="failure")
        selected = select_response_mode([failing_other, passing_default], policy=self.policy)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.candidate_mode, "default")

    def test_failed_default_permits_second_candidate(self) -> None:
        failing_default = self._evaluate("bad", mode="default", generation_status="failure")
        passing_second = self._evaluate(_valid_semantic_json(), mode="enable_thinking_false")
        selected = select_response_mode([failing_default, passing_second], policy=self.policy)
        self.assertEqual(selected.candidate_mode, "enable_thinking_false")

    def test_neither_passing_blocks_run(self) -> None:
        first = self._evaluate("bad", mode="default", generation_status="failure")
        second = self._evaluate("bad", mode="enable_thinking_false", generation_status="failure")
        self.assertIsNone(select_response_mode([first, second], policy=self.policy))

    def test_thinking_markers_fail(self) -> None:
        raw = "<think>reason</think>" + _valid_semantic_json()
        result = self._evaluate(raw)
        self.assertFalse(result.passed)
        self.assertTrue(result.thinking_markers_present)

    def test_prose_contamination_fails(self) -> None:
        raw = "note: " + _valid_semantic_json()
        result = self._evaluate(raw)
        self.assertFalse(result.passed)
        self.assertTrue(result.prose_before_json)

    def test_run_scoped_verification_identity_complete(self) -> None:
        selected = self._evaluate(_valid_semantic_json())
        verification = create_run_scoped_verification(
            selected=selected,
            tokenizer_artefact_hashes={"tokenizer.json": "a" * 64},
            measurement_timestamp="2026-07-11T20:00:00Z",
            container_sha=CONTAINER_SHA,
            evidence_run_id="run-001",
            policy=self.policy,
        )
        payload = verification.to_dict()
        for key in (
            "model_repository",
            "immutable_revision",
            "tokenizer_artefact_hashes",
            "response_mode",
            "rendered_prompt_hash",
            "probe_output_hash",
            "semantic_schema_hash",
            "structured_decode_contract_hash",
            "probe_checks",
            "measurement_timestamp",
            "container_sha",
            "evidence_run_id",
            "status",
        ):
            self.assertIn(key, payload)
        self.assertEqual(verification.status, "verified_for_run")

    def test_verification_cannot_be_reused_for_another_run(self) -> None:
        selected = self._evaluate(_valid_semantic_json())
        verification = create_run_scoped_verification(
            selected=selected,
            tokenizer_artefact_hashes={"tokenizer.json": "a" * 64},
            measurement_timestamp="2026-07-11T20:00:00Z",
            container_sha=CONTAINER_SHA,
            evidence_run_id="run-001",
            policy=self.policy,
        )
        self.assertFalse(
            verification_matches_run(
                verification,
                evidence_run_id="run-002",
                model_repository=MODEL_REPO,
                immutable_revision=REVISION,
                container_sha=CONTAINER_SHA,
                tokenizer_artefact_hashes={"tokenizer.json": "a" * 64},
                semantic_schema_hash=self.schema_hash,
                structured_decode_contract_hash=self.contract_hash,
                response_mode="default",
            )
        )

    def test_verification_cannot_be_reused_for_another_model(self) -> None:
        selected = self._evaluate(_valid_semantic_json())
        verification = create_run_scoped_verification(
            selected=selected,
            tokenizer_artefact_hashes={"tokenizer.json": "a" * 64},
            measurement_timestamp="2026-07-11T20:00:00Z",
            container_sha=CONTAINER_SHA,
            evidence_run_id="run-001",
            policy=self.policy,
        )
        self.assertFalse(
            verification_matches_run(
                verification,
                evidence_run_id="run-001",
                model_repository="Other/Model",
                immutable_revision=REVISION,
                container_sha=CONTAINER_SHA,
                tokenizer_artefact_hashes={"tokenizer.json": "a" * 64},
                semantic_schema_hash=self.schema_hash,
                structured_decode_contract_hash=self.contract_hash,
                response_mode="default",
            )
        )

    def test_different_container_sha_fails(self) -> None:
        selected = self._evaluate(_valid_semantic_json())
        verification = create_run_scoped_verification(
            selected=selected,
            tokenizer_artefact_hashes={"tokenizer.json": "a" * 64},
            measurement_timestamp="2026-07-11T20:00:00Z",
            container_sha=CONTAINER_SHA,
            evidence_run_id="run-001",
            policy=self.policy,
        )
        self.assertFalse(
            verification_matches_run(
                verification,
                evidence_run_id="run-001",
                model_repository=MODEL_REPO,
                immutable_revision=REVISION,
                container_sha="0" * 64,
                tokenizer_artefact_hashes={"tokenizer.json": "a" * 64},
                semantic_schema_hash=self.schema_hash,
                structured_decode_contract_hash=self.contract_hash,
                response_mode="default",
            )
        )

    def test_different_tokenizer_hashes_fail(self) -> None:
        selected = self._evaluate(_valid_semantic_json())
        verification = create_run_scoped_verification(
            selected=selected,
            tokenizer_artefact_hashes={"tokenizer.json": "a" * 64},
            measurement_timestamp="2026-07-11T20:00:00Z",
            container_sha=CONTAINER_SHA,
            evidence_run_id="run-001",
            policy=self.policy,
        )
        self.assertFalse(
            verification_matches_run(
                verification,
                evidence_run_id="run-001",
                model_repository=MODEL_REPO,
                immutable_revision=REVISION,
                container_sha=CONTAINER_SHA,
                tokenizer_artefact_hashes={"tokenizer.json": "b" * 64},
                semantic_schema_hash=self.schema_hash,
                structured_decode_contract_hash=self.contract_hash,
                response_mode="default",
            )
        )

    def test_different_schema_or_contract_hash_fails(self) -> None:
        selected = self._evaluate(_valid_semantic_json())
        verification = create_run_scoped_verification(
            selected=selected,
            tokenizer_artefact_hashes={"tokenizer.json": "a" * 64},
            measurement_timestamp="2026-07-11T20:00:00Z",
            container_sha=CONTAINER_SHA,
            evidence_run_id="run-001",
            policy=self.policy,
        )
        self.assertFalse(
            verification_matches_run(
                verification,
                evidence_run_id="run-001",
                model_repository=MODEL_REPO,
                immutable_revision=REVISION,
                container_sha=CONTAINER_SHA,
                tokenizer_artefact_hashes={"tokenizer.json": "a" * 64},
                semantic_schema_hash="0" * 64,
                structured_decode_contract_hash=self.contract_hash,
                response_mode="default",
            )
        )

    def test_selected_mode_mismatch_fails(self) -> None:
        selected = self._evaluate(_valid_semantic_json())
        verification = create_run_scoped_verification(
            selected=selected,
            tokenizer_artefact_hashes={"tokenizer.json": "a" * 64},
            measurement_timestamp="2026-07-11T20:00:00Z",
            container_sha=CONTAINER_SHA,
            evidence_run_id="run-001",
            policy=self.policy,
        )
        self.assertFalse(
            verification_matches_run(
                verification,
                evidence_run_id="run-001",
                model_repository=MODEL_REPO,
                immutable_revision=REVISION,
                container_sha=CONTAINER_SHA,
                tokenizer_artefact_hashes={"tokenizer.json": "a" * 64},
                semantic_schema_hash=self.schema_hash,
                structured_decode_contract_hash=self.contract_hash,
                response_mode="enable_thinking_false",
            )
        )

    def test_failed_probe_cannot_create_verified_evidence(self) -> None:
        selected = self._evaluate("bad", generation_status="failure")
        self.assertFalse(selected.passed)
        self.assertIsNone(
            select_response_mode([selected], policy=self.policy)
        )


class T12RunScopedVerifiedRendererTests(unittest.TestCase):
    def test_verified_renderer_requires_verification_status(self) -> None:
        renderer = _renderer()
        renderer._tokenizer = _fake_tokenizer_factory()  # noqa: SLF001
        renderer._observed_tokenizer_hashes = {"tokenizer.json": "a" * 64}
        verification = RunScopedResponseModeVerification(
            model_repository=MODEL_REPO,
            immutable_revision=REVISION,
            tokenizer_artefact_hashes={"tokenizer.json": "a" * 64},
            response_mode="default",
            rendered_prompt_hash="a" * 64,
            probe_output_hash="b" * 64,
            semantic_schema_hash=model_semantic_output_schema_hash(),
            structured_decode_contract_hash=structured_decode_contract_hash(load_structured_decode_contract()),
            probe_checks={},
            measurement_timestamp="2026-07-11T20:00:00Z",
            container_sha=CONTAINER_SHA,
            evidence_run_id="run-001",
            status="verified_for_run",
        )
        verified = RunScopedVerifiedRenderer(base_renderer=renderer, verification=verification)
        envelope = verified.render(_messages())
        self.assertEqual(envelope.response_mode_status, ResponseModeStatus.VERIFIED.value)
        self.assertEqual(len(envelope.rendered_prompt_hash), 64)

    def test_tokenizer_hash_mismatch_blocks_verified_render(self) -> None:
        renderer = _renderer()
        renderer._tokenizer = _fake_tokenizer_factory()  # noqa: SLF001
        renderer._observed_tokenizer_hashes = {"tokenizer.json": "a" * 64}
        verification = RunScopedResponseModeVerification(
            model_repository=MODEL_REPO,
            immutable_revision=REVISION,
            tokenizer_artefact_hashes={"tokenizer.json": "b" * 64},
            response_mode="default",
            rendered_prompt_hash="a" * 64,
            probe_output_hash="b" * 64,
            semantic_schema_hash=model_semantic_output_schema_hash(),
            structured_decode_contract_hash=structured_decode_contract_hash(load_structured_decode_contract()),
            probe_checks={},
            measurement_timestamp="2026-07-11T20:00:00Z",
            container_sha=CONTAINER_SHA,
            evidence_run_id="run-001",
            status="verified_for_run",
        )
        verified = RunScopedVerifiedRenderer(base_renderer=renderer, verification=verification)
        with self.assertRaises(Qwen3RendererError):
            verified.render(_messages())


if __name__ == "__main__":
    unittest.main()
