"""Lazy Qwen3 chat-template renderer for T12 Stage D-Final."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.generation_pipeline import GenerationReadyPromptEnvelope
from ambiguity_manager.model.response_mode import ResponseModeStatus

RENDERER_IDENTITY = "t12-qwen3-chat-template-renderer"
RENDERER_VERSION = "1.0.0"
SUPPORTED_ROLES = frozenset({"system", "user"})
CANDIDATE_MODES = frozenset({"default", "enable_thinking_false"})
D1B1_EVIDENCE_REL = Path("configs") / "model" / "evidence" / "t12_stage_d1b1_pinned_runtime.json"
IMMUTABLE_SELECTION_REL = Path("configs") / "model" / "immutable_selection.json"

TokenizerFactory = Callable[..., Any]


class Qwen3RendererError(Exception):
    """Raised when Qwen3 renderer validation or rendering fails."""


@dataclass(frozen=True)
class Qwen3CandidateRenderEvidence:
    """Candidate render evidence; never implies verified response mode."""

    candidate_mode: str
    model_repository: str
    immutable_model_revision: str
    abstract_message_hash: str
    rendered_prompt_text: str
    rendered_prompt_hash: str
    response_mode_status: str
    response_mode_method_identity: str
    renderer_identity: str
    renderer_version: str
    tokenizer_artefact_hashes: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_mode": self.candidate_mode,
            "model_repository": self.model_repository,
            "immutable_model_revision": self.immutable_model_revision,
            "abstract_message_hash": self.abstract_message_hash,
            "rendered_prompt_text": self.rendered_prompt_text,
            "rendered_prompt_hash": self.rendered_prompt_hash,
            "response_mode_status": self.response_mode_status,
            "response_mode_method_identity": self.response_mode_method_identity,
            "renderer_identity": self.renderer_identity,
            "renderer_version": self.renderer_version,
            "tokenizer_artefact_hashes": dict(self.tokenizer_artefact_hashes),
        }


def _repo_root() -> Path:
    from ambiguity_manager.paths import repo_root

    return repo_root()


def _load_immutable_identity() -> tuple[str, str]:
    payload = json.loads((_repo_root() / IMMUTABLE_SELECTION_REL).read_text(encoding="utf-8"))
    return str(payload["model_repository"]), str(payload["model_revision"])


def _load_expected_tokenizer_hashes() -> dict[str, str]:
    payload = json.loads((_repo_root() / D1B1_EVIDENCE_REL).read_text(encoding="utf-8"))
    hashes = payload["tokenizer_inspection"]["artefact_hashes"]
    return {str(key): str(value) for key, value in hashes.items()}


def _validate_messages(messages: list[dict[str, str]]) -> None:
    if not messages:
        raise Qwen3RendererError("messages must be non-empty")
    for index, message in enumerate(messages):
        role = message.get("role")
        if role not in SUPPORTED_ROLES:
            raise Qwen3RendererError(f"unsupported role at index {index}: {role!r}")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise Qwen3RendererError(f"message content must be non-empty at index {index}")


def _message_hash(messages: list[dict[str, str]]) -> str:
    payload = [{"role": item["role"], "content": item["content"]} for item in messages]
    return sha256_hex(canonical_json_bytes({"messages": payload}))


def _mode_identity(mode: str) -> str:
    if mode == "default":
        return "qwen3_apply_chat_template_default"
    if mode == "enable_thinking_false":
        return "qwen3_apply_chat_template_enable_thinking_false"
    raise Qwen3RendererError(f"unsupported candidate mode: {mode!r}")


def _apply_template(
    tokenizer: Any,
    messages: list[dict[str, str]],
    *,
    mode: str,
) -> str:
    kwargs: dict[str, Any] = {
        "tokenize": False,
        "add_generation_prompt": True,
    }
    if mode == "enable_thinking_false":
        kwargs["enable_thinking"] = False
    elif mode != "default":
        raise Qwen3RendererError(f"unsupported candidate mode: {mode!r}")
    rendered = tokenizer.apply_chat_template(messages, **kwargs)
    if not isinstance(rendered, str):
        raise Qwen3RendererError("apply_chat_template must return a string when tokenize=False")
    return rendered


class Qwen3ChatTemplateRenderer:
    """Lazy-load pinned Qwen3 tokenizer and render candidate chat templates."""

    def __init__(
        self,
        *,
        snapshot_path: Path | str,
        model_repository: str,
        immutable_revision: str,
        expected_tokenizer_hashes: dict[str, str] | None = None,
        tokenizer_factory: TokenizerFactory | None = None,
    ) -> None:
        self._snapshot_path = Path(snapshot_path)
        self._model_repository = model_repository
        self._immutable_revision = immutable_revision
        self._expected_tokenizer_hashes = expected_tokenizer_hashes or _load_expected_tokenizer_hashes()
        self._tokenizer_factory = tokenizer_factory
        self._tokenizer: Any | None = None
        self._observed_tokenizer_hashes: dict[str, str] | None = None
        self._verify_identity()

    @property
    def tokenizer_artefact_hashes(self) -> dict[str, str]:
        if self._observed_tokenizer_hashes is None:
            raise Qwen3RendererError("tokenizer has not been loaded")
        return dict(self._observed_tokenizer_hashes)

    def _verify_identity(self) -> None:
        expected_repo, expected_revision = _load_immutable_identity()
        if self._model_repository != expected_repo:
            raise Qwen3RendererError(
                f"model repository mismatch: expected {expected_repo!r}, got {self._model_repository!r}"
            )
        if self._immutable_revision != expected_revision:
            raise Qwen3RendererError(
                f"immutable revision mismatch: expected {expected_revision!r}, got {self._immutable_revision!r}"
            )

    def load_tokenizer(self) -> None:
        if self._tokenizer is not None:
            return
        if self._tokenizer_factory is None and not self._snapshot_path.is_dir():
            raise Qwen3RendererError(f"tokenizer snapshot path missing: {self._snapshot_path}")
        if self._tokenizer_factory is not None:
            self._tokenizer = self._tokenizer_factory(
                snapshot_path=self._snapshot_path,
                model_repository=self._model_repository,
                immutable_revision=self._immutable_revision,
            )
            self._observed_tokenizer_hashes = dict(self._expected_tokenizer_hashes)
            return
        else:
            transformers = importlib.import_module("transformers")
            auto_tokenizer = getattr(transformers, "AutoTokenizer")
            self._tokenizer = auto_tokenizer.from_pretrained(
                str(self._snapshot_path),
                local_files_only=True,
                revision=self._immutable_revision,
                trust_remote_code=False,
            )
        self._observed_tokenizer_hashes = self._collect_tokenizer_hashes()

    def _collect_tokenizer_hashes(self) -> dict[str, str]:
        observed: dict[str, str] = {}
        for filename, expected_hash in self._expected_tokenizer_hashes.items():
            path = self._snapshot_path / filename
            if not path.is_file():
                raise Qwen3RendererError(f"tokenizer artefact missing: {filename}")
            observed_hash = sha256_hex(path.read_bytes())
            if observed_hash != expected_hash:
                raise Qwen3RendererError(
                    f"tokenizer artefact hash mismatch for {filename}: "
                    f"expected {expected_hash}, got {observed_hash}"
                )
            observed[filename] = observed_hash
        return observed

    def render_candidate(
        self,
        messages: list[dict[str, str]],
        *,
        mode: str,
    ) -> Qwen3CandidateRenderEvidence:
        if mode not in CANDIDATE_MODES:
            raise Qwen3RendererError(f"unsupported candidate mode: {mode!r}")
        copied = [{"role": item["role"], "content": item["content"]} for item in messages]
        _validate_messages(copied)
        self.load_tokenizer()
        rendered = _apply_template(self._tokenizer, copied, mode=mode)
        if not rendered.strip():
            raise Qwen3RendererError("rendered prompt is empty")
        return Qwen3CandidateRenderEvidence(
            candidate_mode=mode,
            model_repository=self._model_repository,
            immutable_model_revision=self._immutable_revision,
            abstract_message_hash=_message_hash(copied),
            rendered_prompt_text=rendered,
            rendered_prompt_hash=sha256_hex(rendered.encode("utf-8")),
            response_mode_status=ResponseModeStatus.UNVERIFIED.value,
            response_mode_method_identity=_mode_identity(mode),
            renderer_identity=RENDERER_IDENTITY,
            renderer_version=RENDERER_VERSION,
            tokenizer_artefact_hashes=self.tokenizer_artefact_hashes,
        )


class RunScopedVerifiedRenderer:
    """GenerationReadyRenderer backed by run-scoped response-mode verification."""

    def __init__(
        self,
        *,
        base_renderer: Qwen3ChatTemplateRenderer,
        verification: Any,
    ) -> None:
        from ambiguity_manager.model.response_mode_probe import (
            RunScopedResponseModeVerification,
            verification_matches_run,
        )

        if not isinstance(verification, RunScopedResponseModeVerification):
            raise Qwen3RendererError("verification must be RunScopedResponseModeVerification")
        self._base_renderer = base_renderer
        self._verification = verification
        self._matches_run = verification_matches_run

    def render(self, messages: list[dict[str, str]]) -> GenerationReadyPromptEnvelope:
        if self._verification.status != "verified_for_run":
            raise Qwen3RendererError(
                f"response mode not verified for run: status={self._verification.status!r}"
            )
        self._base_renderer.load_tokenizer()
        observed = self._base_renderer.tokenizer_artefact_hashes
        expected = self._verification.tokenizer_artefact_hashes
        if observed != expected:
            raise Qwen3RendererError("tokenizer artefact hash mismatch against run-scoped verification")
        candidate = self._base_renderer.render_candidate(
            messages,
            mode=self._verification.response_mode,
        )
        return GenerationReadyPromptEnvelope(
            rendered_prompt_text=candidate.rendered_prompt_text,
            abstract_message_hash=candidate.abstract_message_hash,
            rendered_prompt_hash=candidate.rendered_prompt_hash,
            model_repository=candidate.model_repository,
            immutable_model_revision=candidate.immutable_model_revision,
            response_mode_status=ResponseModeStatus.VERIFIED.value,
            response_mode_method_identity=candidate.response_mode_method_identity,
            renderer_identity=candidate.renderer_identity,
            renderer_version=candidate.renderer_version,
        )

    def usable_for_run(
        self,
        *,
        evidence_run_id: str,
        model_repository: str,
        immutable_revision: str,
        container_sha: str,
        tokenizer_artefact_hashes: dict[str, str],
        semantic_schema_hash: str,
        structured_decode_contract_hash: str,
        response_mode: str,
    ) -> bool:
        return self._matches_run(
            self._verification,
            evidence_run_id=evidence_run_id,
            model_repository=model_repository,
            immutable_revision=immutable_revision,
            container_sha=container_sha,
            tokenizer_artefact_hashes=tokenizer_artefact_hashes,
            semantic_schema_hash=semantic_schema_hash,
            structured_decode_contract_hash=structured_decode_contract_hash,
            response_mode=response_mode,
        )
