"""Deterministic fake model backend for CPU-only tests."""

from __future__ import annotations

import json
import uuid
from typing import Any

from ambiguity_manager.model.parser import extract_and_repair_json
from ambiguity_manager.model.protocol import (
    GenerateJsonRequest,
    GenerateJsonResult,
    ModelRuntimeSpec,
    monotonic_ms,
)
from ambiguity_manager.schema.v2.validation import validate_canonical_record_v2


class FakeBackend:
    def __init__(self, runtime: ModelRuntimeSpec) -> None:
        self._runtime = runtime

    @property
    def runtime(self) -> ModelRuntimeSpec:
        return self._runtime

    def generate_json(self, request: GenerateJsonRequest) -> GenerateJsonResult:
        start = monotonic_ms()
        request_id = request.run_id or str(uuid.uuid4())
        raw_output = self._build_raw_output(request)
        parse_result = extract_and_repair_json(raw_output)
        schema_valid = False
        schema_errors: list[str] = []
        if parse_result.parsed_object is not None:
            try:
                validate_canonical_record_v2(parse_result.parsed_object)
                schema_valid = True
            except Exception as exc:  # noqa: BLE001 - surface validation errors
                schema_errors = [str(exc)]

        final_status = "success" if schema_valid else "schema_invalid"
        if parse_result.parsed_object is None:
            final_status = "parse_failed"

        return GenerateJsonResult.from_runtime(
            runtime=self._runtime,
            request_id=request_id,
            raw_output=parse_result.raw_output,
            extracted_json_text=parse_result.extracted_json_text,
            parsed_object=parse_result.parsed_object,
            schema_valid=schema_valid,
            schema_errors=schema_errors,
            repair_attempts=parse_result.repair_attempts,
            repair_log=parse_result.repair_log,
            final_status=final_status,
            latency_ms=monotonic_ms() - start,
            runtime_metadata={"backend_impl": "fake"},
        )

    def _build_raw_output(self, request: GenerateJsonRequest) -> str:
        fixture_id = request.fixture_id or "syn-000"
        payload = self._prediction_payload(fixture_id, request.messages)
        inner = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return f"```json\n{inner}\n```"

    def _prediction_payload(
        self,
        fixture_id: str,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        command = next(
            (message["content"] for message in messages if message["role"] == "user"),
            "Synthetic command.",
        )
        route = {
            "syn-001": "execute",
            "syn-002": "clarify",
            "syn-003": "silently_resolve",
            "syn-004": "face_preserving_rejection",
            "syn-005": "multi_step",
        }.get(fixture_id, "clarify")
        payload: dict[str, Any] = {
            "schema_version": "2.0.0",
            "id": f"pred:{fixture_id}",
            "record_class": "prediction",
            "source_dataset": "t12_synthetic",
            "command": command,
            "annotation_status": "weak_mapped",
            "label_confidence": "weak_derived",
            "label_eligibility": {
                "routing": True,
                "ambiguity": True,
                "risk": False,
                "capability": False,
                "clarification_decision": True,
                "clarification_target": False,
                "intent_slots": False,
                "rejection": False,
                "compound_sequence": False,
                "context_benefit": False,
            },
            "cpc": {
                "action": {"value": None, "status": "unknown"},
                "actor": {"value": None, "status": "unknown"},
                "object": {"value": None, "status": "unknown"},
                "object_attributes": {"value": None, "status": "unknown"},
                "destination": {"value": None, "status": "unknown"},
                "spatial_relation": {"value": None, "status": "unknown"},
                "quantity": {"value": None, "status": "unknown"},
                "time": {"value": None, "status": "unknown"},
                "recipient": {"value": None, "status": "unknown"},
                "tool": {"value": None, "status": "unknown"},
                "conditions": {"value": None, "status": "unknown"},
                "constraints": {"value": None, "status": "unknown"},
                "negation": {"value": None, "status": "unknown"},
            },
            "ambiguity_present": fixture_id != "syn-001",
            "ambiguity_types": [] if fixture_id == "syn-001" else ["referential"],
            "recommended_strategy": route,
            "prediction_metadata": {"model_id": self._runtime.model_id},
        }
        if route == "silently_resolve":
            payload.update(
                {
                    "selected_interpretation": {
                        "frame_id": f"pred:{fixture_id}:candidate:0",
                        "supporting_evidence": [{"source": "scene_context", "span": "blue mug"}],
                    },
                    "resolved_slots": [{"slot_name": "object", "value": "blue mug"}],
                    "resolution_method": "context_supported",
                    "resolution_evidence": [{"source": "scene_context", "span": "blue mug"}],
                    "candidate_interpretations": [
                        {
                            "frame_id": f"pred:{fixture_id}:candidate:0",
                            "text": "blue mug",
                            "cpc": payload["cpc"],
                        }
                    ],
                }
            )
        if route == "clarify":
            payload["clarification_targets"] = ["object"]
            payload["clarification_question"] = "Which object is intended?"
        if route == "face_preserving_rejection":
            payload["rejection_reason"] = "Requested action is not supported in this context."
        if route == "multi_step":
            payload["strategy_sequence"] = ["clarify", "execute"]
        return payload
