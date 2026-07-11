"""Pinned vLLM 0.20.1 structured-output adapter for T12 Stage D1B2."""

from __future__ import annotations

import importlib
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.model.prediction_contract import DERIVATION_VERSION

DEFAULT_CONTRACT_REL = Path("configs") / "model" / "t12_structured_decode_contract.json"
REQUIRED_VLLM_VERSION = "0.20.1"
REQUIRED_SCHEMA_HASH = "232235fec53ee38eafcd714fd53664b250e848a6b0f75fca1ff7ec903b08cfb4"


class StructuredDecodeError(Exception):
    """Base error for structured-output adapter operations."""


class VllmUnavailableError(StructuredDecodeError):
    """Raised when vLLM cannot be imported for real parameter construction."""


class WrongVllmVersionError(StructuredDecodeError):
    """Raised when the detected vLLM version does not match the pinned contract."""


class MissingApiClassError(StructuredDecodeError):
    """Raised when a required pinned-runtime class is absent."""


class MissingApiFieldError(StructuredDecodeError):
    """Raised when a required pinned-runtime constructor field is absent."""


class SchemaIdentityMismatchError(StructuredDecodeError):
    """Raised when the committed semantic schema identity does not match the contract."""


class SchemaInvalidError(StructuredDecodeError):
    """Raised when the semantic schema fails Draft 2020-12 meta-validation."""


class ParameterConstructionError(StructuredDecodeError):
    """Raised when pinned parameter construction fails."""


@dataclass(frozen=True)
class StructuredDecodeContract:
    contract_version: str
    stage: str
    required_vllm_version: str
    sampling_params_module: str
    sampling_params_class: str
    structured_outputs_module: str
    structured_outputs_class: str
    structured_output_field_name: str
    schema_parameter_name: str
    semantic_schema_relpath: str
    semantic_schema_sha256: str
    derivation_version: str
    completions_per_request: int
    lossy_schema_adaptation_permitted: bool
    unconstrained_fallback_permitted: bool
    guided_decoding_permitted: bool
    d1b1_evidence_relpath: str
    response_mode_status: str
    engine_time_schema_compilation_status: str
    live_output_verification_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "stage": self.stage,
            "required_vllm_version": self.required_vllm_version,
            "sampling_params_module": self.sampling_params_module,
            "sampling_params_class": self.sampling_params_class,
            "structured_outputs_module": self.structured_outputs_module,
            "structured_outputs_class": self.structured_outputs_class,
            "structured_output_field_name": self.structured_output_field_name,
            "schema_parameter_name": self.schema_parameter_name,
            "semantic_schema_relpath": self.semantic_schema_relpath,
            "semantic_schema_sha256": self.semantic_schema_sha256,
            "derivation_version": self.derivation_version,
            "completions_per_request": self.completions_per_request,
            "lossy_schema_adaptation_permitted": self.lossy_schema_adaptation_permitted,
            "unconstrained_fallback_permitted": self.unconstrained_fallback_permitted,
            "guided_decoding_permitted": self.guided_decoding_permitted,
            "d1b1_evidence_relpath": self.d1b1_evidence_relpath,
            "response_mode_status": self.response_mode_status,
            "engine_time_schema_compilation_status": self.engine_time_schema_compilation_status,
            "live_output_verification_status": self.live_output_verification_status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StructuredDecodeContract:
        errors = validate_structured_decode_contract(payload)
        if errors:
            raise StructuredDecodeError("; ".join(errors))
        return cls(
            contract_version=str(payload["contract_version"]),
            stage=str(payload["stage"]),
            required_vllm_version=str(payload["required_vllm_version"]),
            sampling_params_module=str(payload["sampling_params_module"]),
            sampling_params_class=str(payload["sampling_params_class"]),
            structured_outputs_module=str(payload["structured_outputs_module"]),
            structured_outputs_class=str(payload["structured_outputs_class"]),
            structured_output_field_name=str(payload["structured_output_field_name"]),
            schema_parameter_name=str(payload["schema_parameter_name"]),
            semantic_schema_relpath=str(payload["semantic_schema_relpath"]),
            semantic_schema_sha256=str(payload["semantic_schema_sha256"]),
            derivation_version=str(payload["derivation_version"]),
            completions_per_request=int(payload["completions_per_request"]),
            lossy_schema_adaptation_permitted=bool(payload["lossy_schema_adaptation_permitted"]),
            unconstrained_fallback_permitted=bool(payload["unconstrained_fallback_permitted"]),
            guided_decoding_permitted=bool(payload["guided_decoding_permitted"]),
            d1b1_evidence_relpath=str(payload["d1b1_evidence_relpath"]),
            response_mode_status=str(payload["response_mode_status"]),
            engine_time_schema_compilation_status=str(payload["engine_time_schema_compilation_status"]),
            live_output_verification_status=str(payload["live_output_verification_status"]),
        )


@dataclass(frozen=True)
class StructuredDecodeMetadata:
    contract_hash: str
    schema_hash: str
    sampling_params_module: str
    sampling_params_class: str
    structured_outputs_module: str
    structured_outputs_class: str
    structured_output_field_name: str
    schema_parameter_name: str
    required_vllm_version: str
    detected_vllm_version: str | None
    completions_per_request: int
    construction_status: str
    response_mode_status: str
    engine_time_schema_compilation_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_hash": self.contract_hash,
            "schema_hash": self.schema_hash,
            "sampling_params_module": self.sampling_params_module,
            "sampling_params_class": self.sampling_params_class,
            "structured_outputs_module": self.structured_outputs_module,
            "structured_outputs_class": self.structured_outputs_class,
            "structured_output_field_name": self.structured_output_field_name,
            "schema_parameter_name": self.schema_parameter_name,
            "required_vllm_version": self.required_vllm_version,
            "detected_vllm_version": self.detected_vllm_version,
            "completions_per_request": self.completions_per_request,
            "construction_status": self.construction_status,
            "response_mode_status": self.response_mode_status,
            "engine_time_schema_compilation_status": self.engine_time_schema_compilation_status,
        }


@dataclass(frozen=True)
class StructuredDecodeBuildResult:
    sampling_params: Any
    metadata: StructuredDecodeMetadata


def validate_structured_decode_contract(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = (
        "contract_version",
        "stage",
        "required_vllm_version",
        "sampling_params_module",
        "sampling_params_class",
        "structured_outputs_module",
        "structured_outputs_class",
        "structured_output_field_name",
        "schema_parameter_name",
        "semantic_schema_relpath",
        "semantic_schema_sha256",
        "derivation_version",
        "completions_per_request",
        "lossy_schema_adaptation_permitted",
        "unconstrained_fallback_permitted",
        "guided_decoding_permitted",
        "d1b1_evidence_relpath",
        "response_mode_status",
        "engine_time_schema_compilation_status",
        "live_output_verification_status",
    )
    for key in required:
        if key not in payload:
            errors.append(f"structured_decode_contract.{key} is required")
    if payload.get("required_vllm_version") != REQUIRED_VLLM_VERSION:
        errors.append(f"structured_decode_contract.required_vllm_version must be {REQUIRED_VLLM_VERSION}")
    if payload.get("semantic_schema_sha256") != REQUIRED_SCHEMA_HASH:
        errors.append("structured_decode_contract.semantic_schema_sha256 mismatch")
    if payload.get("derivation_version") != DERIVATION_VERSION:
        errors.append(f"structured_decode_contract.derivation_version must be {DERIVATION_VERSION}")
    if payload.get("completions_per_request") != 1:
        errors.append("structured_decode_contract.completions_per_request must be 1")
    if payload.get("lossy_schema_adaptation_permitted") is True:
        errors.append("structured_decode_contract.lossy_schema_adaptation_permitted must be false")
    if payload.get("unconstrained_fallback_permitted") is True:
        errors.append("structured_decode_contract.unconstrained_fallback_permitted must be false")
    if payload.get("guided_decoding_permitted") is True:
        errors.append("structured_decode_contract.guided_decoding_permitted must be false")
    if payload.get("structured_output_field_name") != "structured_outputs":
        errors.append("structured_decode_contract.structured_output_field_name must be structured_outputs")
    if payload.get("schema_parameter_name") != "json":
        errors.append("structured_decode_contract.schema_parameter_name must be json")
    return errors


def structured_decode_contract_hash(contract: StructuredDecodeContract) -> str:
    return sha256_hex(canonical_json_bytes(contract.to_dict()))


def load_structured_decode_contract(path: Path | str | None = None) -> StructuredDecodeContract:
    from ambiguity_manager.paths import repo_root

    target = Path(path) if path is not None else repo_root() / DEFAULT_CONTRACT_REL
    if not target.is_file():
        raise StructuredDecodeError(f"structured_decode_contract_missing:{target}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    return StructuredDecodeContract.from_dict(payload)


def _canonical_schema_export(schema: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in schema.items() if not str(key).startswith("_")}


def validate_semantic_schema_document(schema: dict[str, Any]) -> None:
    export = _canonical_schema_export(schema)
    try:
        Draft202012Validator.check_schema(export)
    except SchemaError as exc:
        raise SchemaInvalidError(f"semantic schema failed Draft 2020-12 validation: {exc}") from exc


def load_verified_semantic_schema(
    contract: StructuredDecodeContract,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    from ambiguity_manager.paths import repo_root as default_repo_root

    root = repo_root or default_repo_root()
    schema_path = root / contract.semantic_schema_relpath
    if not schema_path.is_file():
        raise SchemaIdentityMismatchError(f"semantic_schema_missing:{schema_path}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    export = _canonical_schema_export(schema)
    observed_hash = sha256_hex(canonical_json_bytes(export))
    if observed_hash != contract.semantic_schema_sha256:
        raise SchemaIdentityMismatchError(
            f"semantic schema hash mismatch: expected {contract.semantic_schema_sha256}, got {observed_hash}"
        )
    derivation_version = export.get("derivation_version")
    if derivation_version != contract.derivation_version:
        raise SchemaIdentityMismatchError(
            f"derivation version mismatch: expected {contract.derivation_version}, got {derivation_version!r}"
        )
    validate_semantic_schema_document(export)
    return export


def _import_vllm_module() -> Any:
    try:
        return importlib.import_module("vllm")
    except ImportError as exc:
        raise VllmUnavailableError(
            "vLLM is not installed; structured-output construction requires the pinned cluster container"
        ) from exc


def _resolve_vllm_version(
    vllm_module: Any,
    *,
    detected_vllm_version: str | None,
) -> str:
    if detected_vllm_version is not None:
        return detected_vllm_version
    return str(getattr(vllm_module, "__version__", ""))


def _resolve_class(
    module_path: str,
    class_name: str,
    *,
    injected_class: type[Any] | None,
    resolver: Callable[[Any], type[Any] | None] | None,
    error_label: str,
) -> type[Any]:
    if injected_class is not None:
        return injected_class
    if resolver is not None:
        resolved = resolver(None)
        if resolved is None:
            raise MissingApiClassError(f"{error_label} is absent")
        return resolved
    module = importlib.import_module(module_path.rsplit(".", 1)[0])
    resolved = getattr(module, class_name, None)
    if resolved is None:
        raise MissingApiClassError(f"{error_label} is absent from {module_path}")
    return resolved


def _require_constructor_field(cls: type[Any], field_name: str, *, error_label: str) -> None:
    try:
        signature = inspect.signature(cls.__init__)
    except (TypeError, ValueError) as exc:
        raise MissingApiFieldError(f"{error_label} constructor is not inspectable") from exc
    if field_name not in signature.parameters:
        raise MissingApiFieldError(f"{error_label} is missing required field {field_name!r}")


def build_structured_sampling_params(
    generation_config: dict[str, Any],
    structured_decode_contract: StructuredDecodeContract,
    *,
    repo_root: Path | None = None,
    sampling_params_class: type[Any] | None = None,
    structured_outputs_class: type[Any] | None = None,
    detected_vllm_version: str | None = None,
    sampling_params_resolver: Callable[[Any], type[Any] | None] | None = None,
    structured_outputs_resolver: Callable[[Any], type[Any] | None] | None = None,
) -> StructuredDecodeBuildResult:
    contract = structured_decode_contract
    if contract.unconstrained_fallback_permitted:
        raise StructuredDecodeError("unconstrained fallback is not permitted")
    if contract.lossy_schema_adaptation_permitted:
        raise StructuredDecodeError("lossy schema adaptation is not permitted")
    if contract.guided_decoding_permitted:
        raise StructuredDecodeError("guided decoding is not permitted")

    schema_dict = load_verified_semantic_schema(contract, repo_root=repo_root)
    schema_hash = sha256_hex(canonical_json_bytes(schema_dict))
    contract_hash = structured_decode_contract_hash(contract)

    needs_lazy_vllm = (
        sampling_params_class is None
        and sampling_params_resolver is None
        and structured_outputs_class is None
        and structured_outputs_resolver is None
    )
    resolved_version: str | None = detected_vllm_version
    if needs_lazy_vllm:
        vllm_module = _import_vllm_module()
        resolved_version = _resolve_vllm_version(vllm_module, detected_vllm_version=detected_vllm_version)
        if resolved_version != contract.required_vllm_version:
            raise WrongVllmVersionError(
                f"vLLM version mismatch: expected {contract.required_vllm_version}, got {resolved_version}"
            )
    elif detected_vllm_version is not None and detected_vllm_version != contract.required_vllm_version:
        raise WrongVllmVersionError(
            f"vLLM version mismatch: expected {contract.required_vllm_version}, got {detected_vllm_version}"
        )

    structured_cls = _resolve_class(
        contract.structured_outputs_module,
        contract.structured_outputs_class,
        injected_class=structured_outputs_class,
        resolver=structured_outputs_resolver,
        error_label=contract.structured_outputs_class,
    )
    sampling_cls = _resolve_class(
        contract.sampling_params_module,
        contract.sampling_params_class,
        injected_class=sampling_params_class,
        resolver=sampling_params_resolver,
        error_label=contract.sampling_params_class,
    )

    _require_constructor_field(
        structured_cls,
        contract.schema_parameter_name,
        error_label=contract.structured_outputs_class,
    )
    _require_constructor_field(
        sampling_cls,
        contract.structured_output_field_name,
        error_label=contract.sampling_params_class,
    )

    generation = dict(generation_config)
    temperature = float(generation.get("temperature", 0.1))
    top_p = float(generation.get("top_p", 1.0))
    max_tokens = int(generation.get("max_tokens", 2048))

    try:
        structured_outputs = structured_cls(**{contract.schema_parameter_name: schema_dict})
        sampling_params = sampling_cls(
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            n=contract.completions_per_request,
            **{contract.structured_output_field_name: structured_outputs},
        )
    except StructuredDecodeError:
        raise
    except Exception as exc:  # noqa: BLE001 - construction failure must be explicit
        raise ParameterConstructionError(
            f"structured sampling parameter construction failed: {exc}"
        ) from exc

    metadata = StructuredDecodeMetadata(
        contract_hash=contract_hash,
        schema_hash=schema_hash,
        sampling_params_module=contract.sampling_params_module,
        sampling_params_class=contract.sampling_params_class,
        structured_outputs_module=contract.structured_outputs_module,
        structured_outputs_class=contract.structured_outputs_class,
        structured_output_field_name=contract.structured_output_field_name,
        schema_parameter_name=contract.schema_parameter_name,
        required_vllm_version=contract.required_vllm_version,
        detected_vllm_version=resolved_version,
        completions_per_request=contract.completions_per_request,
        construction_status="constructed",
        response_mode_status=contract.response_mode_status,
        engine_time_schema_compilation_status=contract.engine_time_schema_compilation_status,
    )
    return StructuredDecodeBuildResult(sampling_params=sampling_params, metadata=metadata)


def structured_decode_error_to_backend_message(exc: StructuredDecodeError) -> str:
    if isinstance(exc, VllmUnavailableError):
        return f"structured_decode_vllm_unavailable:{exc}"
    if isinstance(exc, WrongVllmVersionError):
        return f"structured_decode_wrong_vllm_version:{exc}"
    if isinstance(exc, MissingApiClassError):
        return f"structured_decode_missing_api_class:{exc}"
    if isinstance(exc, MissingApiFieldError):
        return f"structured_decode_missing_api_field:{exc}"
    if isinstance(exc, SchemaIdentityMismatchError):
        return f"structured_decode_schema_identity_mismatch:{exc}"
    if isinstance(exc, SchemaInvalidError):
        return f"structured_decode_schema_invalid:{exc}"
    if isinstance(exc, ParameterConstructionError):
        return f"structured_decode_parameter_construction_failed:{exc}"
    return f"structured_decode_failed:{exc}"
