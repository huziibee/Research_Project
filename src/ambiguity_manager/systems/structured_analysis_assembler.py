"""Deterministic StructuredAnalysis assembly from T27C task predictions.

Assembler version: structured_analysis_assembler_v1

Combines independently validated task outputs with existing deterministic
components (classification aggregate + DeterministicRouter). Never trusts raw
unvalidated model text, never fabricates unsupported fields, and never lets the
model override routing or safety findings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from ambiguity_manager.schema.v2.records import (
    CPC,
    CandidateInterpretationFrame,
    SelectedInterpretation,
    UnresolvedSlot,
)
from ambiguity_manager.schema.v2.taxonomies import (
    AmbiguityType,
    CapabilityStatus,
    RiskLevel,
    RouteLabel,
)
from ambiguity_manager.systems.classification import (
    apply_classification_aggregate,
    derive_ambiguity_fields,
)
from ambiguity_manager.systems.contracts import AnalysisProvenance, StructuredAnalysis
from ambiguity_manager.systems.routing import DeterministicRouter, apply_router_decision

ASSEMBLER_VERSION = "structured_analysis_assembler_v2"
DEFAULT_ASSEMBLY_POLICY = {
    "policy_id": "t27d_assembly_requirement_policy_v1",
    "required_for_structural_object": [],
    "required_for_complete": ["predict_cpc_v1", "predict_ambiguity_v1"],
    "optional_model_enrichments": [
        "predict_intent_v1",
        "predict_interpretations_v1",
        "predict_risk_capability_v1",
    ],
    "fail_safe_defaults": {
        "intent": {"speech_act": None, "intent_summary": None},
        "cpc": "CPC.empty_unknown()",
        "ambiguity": {"ambiguity_present": None, "ambiguity_types": []},
        "risk_capability": {"risk_level": "unknown", "capability_status": "unknown"},
        "interpretations": {"candidate_interpretations": [], "selected_interpretation": None},
    },
}


class StructuredAnalysisAssemblerError(RuntimeError):
    """Raised when assembly cannot proceed safely."""


@dataclass
class FieldProvenance:
    field_path: str
    source_kind: str  # task | deterministic_rule | default | unsupported
    source_id: str
    output_hash: str | None = None
    assembly_rule: str | None = None
    conflict_status: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "output_hash": self.output_hash,
            "assembly_rule": self.assembly_rule,
            "conflict_status": self.conflict_status,
        }


@dataclass
class AssemblyResult:
    status: str  # assembled_complete | assembled_partial_fail_safe | unavailable_* | conflict | validation_failed
    analysis: StructuredAnalysis | None
    field_provenance: list[FieldProvenance] = field(default_factory=list)
    accepted_task_hashes: dict[str, str] = field(default_factory=dict)
    content_hash: str | None = None
    failures: list[str] = field(default_factory=list)
    router_decision: dict[str, Any] | None = None
    production_schema_valid: bool = False
    semantic_safety_accepted: bool = False
    notes: list[str] = field(default_factory=list)
    completeness_map: dict[str, str] = field(default_factory=dict)
    task_states: dict[str, str] = field(default_factory=dict)
    metric_eligibility: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "analysis": self.analysis.to_dict() if self.analysis is not None else None,
            "field_provenance": [p.to_dict() for p in self.field_provenance],
            "accepted_task_hashes": dict(self.accepted_task_hashes),
            "content_hash": self.content_hash,
            "failures": list(self.failures),
            "router_decision": self.router_decision,
            "production_schema_valid": self.production_schema_valid,
            "semantic_safety_accepted": self.semantic_safety_accepted,
            "notes": list(self.notes),
            "completeness_map": dict(self.completeness_map),
            "task_states": dict(self.task_states),
            "metric_eligibility": dict(self.metric_eligibility),
            "assembler_version": ASSEMBLER_VERSION,
        }


class StructuredAnalysisAssembler:
    def __init__(
        self,
        *,
        field_registry: Mapping[str, Any],
        task_registry: Mapping[str, Any],
        router: DeterministicRouter | None = None,
        analysis_variant: str = "full_context",
        base_model_identity: str | None = None,
        adapter_identity: str | None = None,
        input_hash: str | None = None,
        assembly_policy: Mapping[str, Any] | None = None,
    ) -> None:
        self.field_registry = field_registry
        self.task_registry = task_registry
        self.router = router or DeterministicRouter()
        self.analysis_variant = analysis_variant
        self.base_model_identity = base_model_identity
        self.adapter_identity = adapter_identity
        self.input_hash = input_hash
        self.version = ASSEMBLER_VERSION
        self.assembly_policy = dict(assembly_policy or DEFAULT_ASSEMBLY_POLICY)

    def assemble(
        self,
        *,
        record_id: str,
        task_results: Sequence[Any],
    ) -> AssemblyResult:
        failures: list[str] = []
        notes: list[str] = []
        provenance: list[FieldProvenance] = []
        accepted: dict[str, Any] = {}
        accepted_hashes: dict[str, str] = {}
        task_states: dict[str, str] = {}
        completeness: dict[str, str] = {}

        # Index and validate task results.
        by_task: dict[str, Any] = {}
        for result in task_results:
            task_id = getattr(result, "task_id", None) or result.get("task_id")
            if task_id in by_task:
                return AssemblyResult(
                    status="conflict",
                    analysis=None,
                    failures=[f"duplicate_task_result:{task_id}"],
                )
            by_task[str(task_id)] = result

        all_task_ids = [str(t["task_id"]) for t in self.task_registry.get("tasks") or []]
        hard_failures: list[str] = []
        for task_id in all_task_ids:
            result = by_task.get(task_id)
            if result is None:
                task_states[task_id] = "task_absent"
                notes.append(f"task_absent:{task_id}")
                continue
            if not _accepted(result):
                task_states[task_id] = "task_rejected"
                failures.append(f"task_rejected:{task_id}")
                continue
            version = _attr(result, "task_version")
            expected = _task_version(self.task_registry, task_id)
            if version != expected:
                task_states[task_id] = "task_corrupt"
                hard_failures.append(f"task_version_mismatch:{task_id}:{version}!={expected}")
                continue
            parsed = _attr(result, "parsed_output")
            if not isinstance(parsed, dict):
                task_states[task_id] = "task_corrupt"
                hard_failures.append(f"task_empty_output:{task_id}")
                continue
            task_states[task_id] = "accepted"
            accepted[task_id] = parsed
            out_hash = _attr(result, "output_hash")
            if out_hash:
                accepted_hashes[task_id] = str(out_hash)

        if hard_failures:
            return AssemblyResult(
                status="unavailable_corrupt_input",
                analysis=None,
                failures=hard_failures,
                notes=notes,
                accepted_task_hashes=accepted_hashes,
                task_states=task_states,
            )
        if not accepted:
            return AssemblyResult(
                status="unavailable_no_core_prediction",
                analysis=None,
                failures=["no_accepted_task_predictions"],
                notes=notes,
                task_states=task_states,
            )

        analysis = StructuredAnalysis()

        # 1) Intent: optional; never infer speech_act from free text.
        if "predict_intent_v1" in accepted:
            intent = accepted["predict_intent_v1"]
            analysis.speech_act = intent.get("speech_act")
            analysis.intent_summary = intent.get("intent_summary")
            completeness.update({"speech_act": "strong_prediction", "intent_summary": "weak_prediction"})
            provenance.extend([
                FieldProvenance(
                    "speech_act",
                    "task",
                    "predict_intent_v1",
                    accepted_hashes.get("predict_intent_v1"),
                    "copy_from_task",
                ),
                FieldProvenance(
                    "intent_summary",
                    "task",
                    "predict_intent_v1",
                    accepted_hashes.get("predict_intent_v1"),
                    "copy_optional_from_task",
                ),
            ])
        else:
            analysis.speech_act = None
            analysis.intent_summary = None
            notes.append("intent_prediction_unavailable")
            completeness.update({"speech_act": "task_rejected_or_absent", "intent_summary": "task_rejected_or_absent"})

        # 2) CPC
        if "predict_cpc_v1" in accepted:
            cpc_payload = accepted["predict_cpc_v1"]["cpc"]
            analysis.cpc = CPC.from_dict(cpc_payload)
            provenance.append(FieldProvenance("cpc", "task", "predict_cpc_v1", accepted_hashes.get("predict_cpc_v1"), "copy_from_task"))
            completeness["cpc"] = "strong_prediction"
        else:
            analysis.cpc = CPC.empty_unknown()
            analysis.findings = list(analysis.findings) + ["cpc_prediction_unavailable"]
            completeness["cpc"] = "task_rejected_or_absent"

        # 3) Ambiguity
        if "predict_ambiguity_v1" in accepted:
            amb = accepted["predict_ambiguity_v1"]
            analysis.ambiguity_present = bool(amb.get("ambiguity_present"))
            analysis.ambiguity_types = [AmbiguityType(t) for t in (amb.get("ambiguity_types") or [])]
            primary = amb.get("primary_ambiguity_type")
            if primary is None and analysis.ambiguity_types:
                primary = analysis.ambiguity_types[0].value
            analysis.primary_ambiguity_type = AmbiguityType(primary) if primary else None
            unresolved_raw = amb.get("unresolved_slots") or []
            analysis.unresolved_slots = [UnresolvedSlot.from_dict(item) for item in unresolved_raw]
            for path in (
            "ambiguity_present",
            "ambiguity_types",
            "primary_ambiguity_type",
            "unresolved_slots",
        ):
                provenance.append(
                FieldProvenance(
                    path,
                    "task",
                    "predict_ambiguity_v1",
                    accepted_hashes.get("predict_ambiguity_v1"),
                    "copy_from_task",
                )
                )
            completeness.update({"ambiguity_present": "strong_prediction", "ambiguity_types": "strong_prediction", "primary_ambiguity_type": "strong_prediction", "unresolved_slots": "strong_prediction"})
        else:
            analysis.ambiguity_present = None
            analysis.ambiguity_types = []
            analysis.primary_ambiguity_type = None
            analysis.unresolved_slots = []
            analysis.findings = list(analysis.findings) + ["ambiguity_prediction_unavailable"]
            notes.append("ambiguity_prediction_unavailable_fail_safe")
            completeness.update({"ambiguity_present": "task_rejected_or_absent", "ambiguity_types": "task_rejected_or_absent", "primary_ambiguity_type": "task_rejected_or_absent", "unresolved_slots": "task_rejected_or_absent"})

        # 4) Optional interpretations
        if "predict_interpretations_v1" in accepted:
            interp = accepted["predict_interpretations_v1"]
            try:
                analysis.candidate_interpretations = [
                    CandidateInterpretationFrame.from_dict(item)
                    for item in (interp.get("candidate_interpretations") or [])
                ]
                selected = interp.get("selected_interpretation")
                analysis.selected_interpretation = (
                    SelectedInterpretation.from_dict(selected) if selected else None
                )
            except Exception as exc:  # noqa: BLE001
                # Optional model enrichment must never make the complete
                # record unavailable. Preserve the core/ambiguity result and
                # route fail-safe with an explicit retained failure.
                analysis.candidate_interpretations = []
                analysis.selected_interpretation = None
                failures.append(f"optional_interpretations_invalid:{type(exc).__name__}")
                notes.append("optional_interpretations_invalid_fail_safe")
                completeness.update({"candidate_interpretations": "task_rejected_or_absent", "selected_interpretation": "task_rejected_or_absent"})
            else:
                provenance.append(
                    FieldProvenance(
                        "candidate_interpretations",
                        "task",
                        "predict_interpretations_v1",
                        accepted_hashes.get("predict_interpretations_v1"),
                        "copy_from_task_if_present",
                    )
                )
                completeness.update({"candidate_interpretations": "strong_prediction", "selected_interpretation": "strong_prediction"})
                provenance.append(
                    FieldProvenance(
                        "selected_interpretation",
                        "task",
                        "predict_interpretations_v1",
                        accepted_hashes.get("predict_interpretations_v1"),
                        "copy_from_task_if_present",
                    )
                )
        else:
            notes.append("missing_optional_interpretations_forbid_silent_resolve")
            analysis.findings = list(analysis.findings) + ["interpretation_prediction_unavailable"]
            completeness.update({"candidate_interpretations": "task_rejected_or_absent", "selected_interpretation": "task_rejected_or_absent"})
            provenance.append(
                FieldProvenance(
                    "candidate_interpretations",
                    "default",
                    "empty_list",
                    None,
                    "optional_task_absent",
                )
            )

        # 5) Optional risk/capability — missing → UNKNOWN (never safe/capable)
        if "predict_risk_capability_v1" in accepted:
            risk = accepted["predict_risk_capability_v1"]
            analysis.risk_relevant = bool(risk.get("risk_relevant"))
            rl = risk.get("risk_level")
            analysis.risk_level = RiskLevel(rl) if rl is not None else RiskLevel.UNKNOWN
            cs = risk.get("capability_status")
            analysis.capability_status = (
                CapabilityStatus(cs) if cs is not None else CapabilityStatus.UNKNOWN
            )
            for path in ("risk_relevant", "risk_level", "capability_status"):
                provenance.append(
                    FieldProvenance(
                        path,
                        "task",
                        "predict_risk_capability_v1",
                        accepted_hashes.get("predict_risk_capability_v1"),
                        "copy_if_task_present",
                    )
                )
            completeness.update({"risk_relevant": "strong_prediction", "risk_level": "strong_prediction", "capability_status": "strong_prediction"})
        else:
            analysis.risk_level = RiskLevel.UNKNOWN
            analysis.capability_status = CapabilityStatus.UNKNOWN
            analysis.risk_relevant = True
            analysis.findings = list(analysis.findings) + [
                "risk_missing_treated_as_unknown",
                "capability_missing_treated_as_unknown",
            ]
            notes.append("missing_risk_capability_set_unknown_block_execute")
            completeness.update({"risk_relevant": "deterministic_unknown", "risk_level": "deterministic_unknown", "capability_status": "deterministic_unknown"})
            for path in ("risk_relevant", "risk_level", "capability_status"):
                provenance.append(
                    FieldProvenance(
                        path,
                        "default",
                        "unknown_fail_safe",
                        None,
                        "copy_if_present_else_unknown",
                    )
                )

        # Unsupported fields stay empty/null — never fabricate.
        analysis.supporting_evidence = []
        analysis.resolution_method = None
        analysis.resolution_evidence = []
        analysis.resolved_slots = []
        analysis.context_sampling_uncertainty = None
        for path, rule in (
            ("supporting_evidence", "leave_empty"),
            ("resolution_method", "leave_null"),
            ("resolution_evidence", "leave_empty"),
            ("resolved_slots", "context_resolve_if_available"),
            ("context_sampling_uncertainty", "compute_uncertainty_if_available"),
        ):
            provenance.append(
                FieldProvenance(path, "unsupported", "unsupported_for_t27c", None, rule)
            )

        # Classification derive (compound_* from types; reconcile present)
        if "predict_ambiguity_v1" in accepted:
            aggregate = derive_ambiguity_fields(analysis)
            analysis = apply_classification_aggregate(analysis, aggregate)
        else:
            analysis.compound_ambiguity = False
            analysis.compound_ambiguity_count = 0
        provenance.append(
            FieldProvenance(
                "compound_ambiguity",
                "deterministic_rule",
                "classification.derive_ambiguity_fields",
                None,
                "derive_after_ambiguity_task",
            )
        )
        provenance.append(
            FieldProvenance(
                "compound_ambiguity_count",
                "deterministic_rule",
                "classification.derive_ambiguity_fields",
                None,
                "derive_after_ambiguity_task",
            )
        )

        # If interpretations missing under ambiguity, ensure we do not silent-resolve.
        if "predict_interpretations_v1" not in accepted and analysis.ambiguity_present:
            notes.append("ambiguity_without_interpretations")

        # Router (authoritative)
        decision = self.router.route(analysis)
        # Block silently_resolve when interpretations were not accepted.
        if (
            "predict_interpretations_v1" not in accepted
            and decision.recommended_strategy == RouteLabel.SILENTLY_RESOLVE
        ):
            from ambiguity_manager.systems.routing import RouterDecision

            decision = RouterDecision(
                recommended_strategy=RouteLabel.CLARIFY,
                strategy_sequence=[],
                matched_rule_id="t27c_missing_interpretations_fail_safe",
                considered_rules=list(decision.considered_rules)
                + ["t27c_missing_interpretations_fail_safe"],
                clarification_targets=decision.clarification_targets
                or [t.value for t in analysis.ambiguity_types],
                notes=list(decision.notes) + ["missing_optional_interpretations"],
            )
        analysis = apply_router_decision(analysis, decision)
        for path in (
            "recommended_strategy",
            "strategy_sequence",
            "clarification_targets",
            "rejection_reason",
        ):
            provenance.append(
                FieldProvenance(
                    path,
                    "deterministic_rule",
                    decision.matched_rule_id,
                    None,
                    "apply_router_decision",
                )
            )

        analysis.analysis_provenance = AnalysisProvenance(
            provider_id="t27c_task_conditioned_assembler",
            provider_version=ASSEMBLER_VERSION,
            analysis_id=f"{record_id}:{self.analysis_variant}",
            method="task_conditioned_assembly_v1",
            notes=(
                f"variant={self.analysis_variant};"
                f"base={self.base_model_identity};"
                f"adapter={self.adapter_identity}"
            ),
        )
        provenance.append(
            FieldProvenance(
                "analysis_provenance",
                "deterministic_rule",
                "write_provenance",
                None,
                "write_provenance",
            )
        )

        content_hash = sha256_hex(
            canonical_json_bytes(
                {
                    "accepted_task_output_hashes": accepted_hashes,
                    "deterministic_rule_config_identities": {
                        "assembler_version": ASSEMBLER_VERSION,
                        "router_matched_rule": decision.matched_rule_id,
                        "field_registry_id": self.field_registry.get("registry_id"),
                        "task_registry_id": self.task_registry.get("registry_id"),
                    },
                    "input_hash": self.input_hash,
                    "analysis_variant": self.analysis_variant,
                    "assembler_version": ASSEMBLER_VERSION,
                    "analysis": analysis.to_dict(),
                }
            )
        )

        production_schema_valid = True
        semantic_safety_accepted = True
        try:
            # Round-trip through StructuredAnalysis.from_dict as structural check.
            StructuredAnalysis.from_dict(analysis.to_dict())
        except Exception as exc:  # noqa: BLE001
            production_schema_valid = False
            semantic_safety_accepted = False
            failures.append(f"production_schema_invalid:{exc}")

        # Unsupported commitment: selected interpretation without candidates etc.
        if analysis.selected_interpretation and not analysis.candidate_interpretations:
            semantic_safety_accepted = False
            failures.append("unsupported_silent_commitment:selected_without_candidates")
            analysis.unsupported_specificity = list(analysis.unsupported_specificity) + [
                "selected_without_candidates"
            ]

        # Unknown risk/capability must not execute.
        if analysis.recommended_strategy == RouteLabel.EXECUTE and (
            analysis.risk_level in (None, RiskLevel.UNKNOWN)
            or analysis.capability_status in (None, CapabilityStatus.UNKNOWN)
        ):
            semantic_safety_accepted = False
            failures.append("execute_with_unknown_risk_or_capability")

        failures.extend([f for f in failures if f not in hard_failures])
        for task_id, task_state in task_states.items():
            if task_state != "accepted":
                notes.append(f"task_failure_retained:{task_id}:{task_state}")
        complete = production_schema_valid and not failures and all(
            task_states.get(t) == "accepted" for t in self.assembly_policy.get("required_for_complete", [])
        )
        status = "assembled_complete" if complete else (
            "assembled_partial_fail_safe" if production_schema_valid else "validation_failed"
        )
        if failures and not production_schema_valid:
            status = "validation_failed"
        elif failures and production_schema_valid:
            # Still assembled object but not fully accepted.
            status = "assembled_partial_fail_safe"
            semantic_safety_accepted = False

        return AssemblyResult(
            status=status,
            analysis=analysis,
            field_provenance=provenance,
            accepted_task_hashes=accepted_hashes,
            content_hash=content_hash,
            failures=failures,
            router_decision=decision.to_dict(),
            production_schema_valid=production_schema_valid,
            semantic_safety_accepted=semantic_safety_accepted and status == "assembled_complete" and not failures,
            notes=notes,
            completeness_map=completeness,
            task_states=task_states,
            metric_eligibility={
                "intent": task_states.get("predict_intent_v1") == "accepted",
                "cpc": task_states.get("predict_cpc_v1") == "accepted",
                "ambiguity": task_states.get("predict_ambiguity_v1") == "accepted",
                "interpretations": task_states.get("predict_interpretations_v1") == "accepted",
                "risk_capability": task_states.get("predict_risk_capability_v1") == "accepted",
            },
        )


def _attr(obj: Any, name: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def _accepted(obj: Any) -> bool:
    if hasattr(obj, "accepted"):
        return bool(obj.accepted)
    return str(_attr(obj, "final_status")) == "accepted"


def _task_version(registry: Mapping[str, Any], task_id: str) -> str:
    for task in registry.get("tasks") or []:
        if task.get("task_id") == task_id:
            return str(task.get("task_version") or "1.0.0")
    raise StructuredAnalysisAssemblerError(f"unknown_task_in_registry:{task_id}")
