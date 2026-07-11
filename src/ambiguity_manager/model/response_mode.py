"""Fail-closed response-mode verification contract for Qwen3 chat rendering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

D1A_RESPONSE_MODE_STATUS = "unverified_until_pinned_runtime_inspection"
IMMUTABLE_SELECTION_REL = Path("configs") / "model" / "immutable_selection.json"


class ResponseModeStatus(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    UNSUPPORTED = "unsupported"
    INCOMPATIBLE_REVISION = "incompatible_revision"


class ResponseModeError(Exception):
    """Raised when response-mode verification blocks generation-ready rendering."""


@dataclass(frozen=True)
class ModelResponseModeIdentity:
    model_repository: str
    immutable_revision: str


class ResponseModeVerifier:
    """Fail-closed interface for future Qwen3 response-mode verification."""

    def __init__(self, identity: ModelResponseModeIdentity) -> None:
        self._identity = identity
        self._status = ResponseModeStatus.UNVERIFIED

    @property
    def status(self) -> ResponseModeStatus:
        return self._status

    @property
    def identity(self) -> ModelResponseModeIdentity:
        return self._identity

    def check_identity(self) -> None:
        expected = _load_immutable_selection_identity()
        if self._identity.model_repository != expected.model_repository:
            raise ResponseModeError(
                f"model repository mismatch: expected {expected.model_repository!r}, "
                f"got {self._identity.model_repository!r}"
            )
        if self._identity.immutable_revision != expected.immutable_revision:
            raise ResponseModeError(
                f"immutable revision mismatch: expected {expected.immutable_revision!r}, "
                f"got {self._identity.immutable_revision!r}"
            )

    def require_generation_ready(self) -> None:
        self.check_identity()
        if self._status != ResponseModeStatus.VERIFIED:
            raise ResponseModeError(
                "generation-ready prompt rendering blocked: "
                f"response_mode_status={self._status.value}; "
                f"expected={D1A_RESPONSE_MODE_STATUS}"
            )


def _repo_root() -> Path:
    from ambiguity_manager.paths import repo_root

    return repo_root()


def _load_immutable_selection_identity() -> ModelResponseModeIdentity:
    path = _repo_root() / IMMUTABLE_SELECTION_REL
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ModelResponseModeIdentity(
        model_repository=str(payload["model_repository"]),
        immutable_revision=str(payload["model_revision"]),
    )


def load_default_response_mode_verifier() -> ResponseModeVerifier:
    return ResponseModeVerifier(_load_immutable_selection_identity())
