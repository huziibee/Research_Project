#!/usr/bin/env python3
"""Apply frozen adaptation-base selection policy to retained Stage-1 evidence."""

from __future__ import annotations

import json
from pathlib import Path

from ambiguity_manager.model.base_model_candidates import load_base_model_candidate_registry
from ambiguity_manager.model.base_model_selection import (
    CandidateBakeoffResult,
    apply_adaptation_base_selection,
    load_adaptation_base_selection_policy,
)
from ambiguity_manager.paths import ProjectPaths
from ambiguity_manager.systems.model_identities import assert_adaptation_base_selection_scope

ROOT = ProjectPaths.from_repo_root().root


def main() -> int:
    registry = load_base_model_candidate_registry(
        ROOT / "configs/model/base_model_candidates_v1.json"
    )
    policy = load_adaptation_base_selection_policy(
        ROOT / "configs/model/adaptation_base_selection_policy_v1.json"
    )
    assert policy.frozen_before_application
    assert not policy.requires_zero_shot_stage1_pass

    qwen = registry.get_candidate("qwen3_8b")
    phi = registry.get_candidate("phi4_14b")
    mistral = registry.get_candidate("mistral_small_24b_2501")

    results = {
        "qwen3_8b": CandidateBakeoffResult(
            candidate_id="qwen3_8b",
            checkpoint_identity=qwen.checkpoint_identity,
            stage1_passed=False,
            strict_structured_output_count=3,
            unsupported_commitments_on_accepted=1,
            unsafe_silent_commitments=1,
            metrics={
                "structured_output_reliability": 0.75,
                "severity_weighted_safety": 0.70,
                "semantic_validity_closeness": 0.70,
                "joint_intent_cpc_quality": 0.65,
                "compound_ambiguity_quality": 0.60,
                "qlora_feasibility": 0.95,
                "context_length": 1.0,
                "runtime_stability": 0.95,
                "vram_and_latency": 0.35,
            },
            qlora_feasible=True,
            context_length_sufficient=True,
            runtime_compatible=True,
            snapshot_and_licence_verified=True,
            tokenizer_loads=True,
            runtime_loads=True,
            licence_compatible=True,
            reproducible_load=True,
            fundamental_incompatibility=False,
        ),
        "phi4_14b": CandidateBakeoffResult(
            candidate_id="phi4_14b",
            checkpoint_identity=phi.checkpoint_identity,
            stage1_passed=False,
            strict_structured_output_count=1,
            unsupported_commitments_on_accepted=0,
            unsafe_silent_commitments=0,
            metrics={
                "structured_output_reliability": 0.25,
                "severity_weighted_safety": 0.85,
                "semantic_validity_closeness": 0.30,
                "joint_intent_cpc_quality": 0.25,
                "compound_ambiguity_quality": 0.20,
                "qlora_feasibility": 0.80,
                "context_length": 0.70,
                "runtime_stability": 0.70,
                "vram_and_latency": 0.55,
            },
            qlora_feasible=True,
            context_length_sufficient=True,
            runtime_compatible=True,
            snapshot_and_licence_verified=True,
            tokenizer_loads=True,
            runtime_loads=True,
            licence_compatible=True,
            reproducible_load=True,
            fundamental_incompatibility=False,
        ),
        "mistral_small_24b_2501": CandidateBakeoffResult(
            candidate_id="mistral_small_24b_2501",
            checkpoint_identity=mistral.checkpoint_identity,
            stage1_passed=False,
            # No retained accepted structured outputs after empty-result / node failures.
            strict_structured_output_count=0,
            hard_gate_failures=("no_valid_structured_output",),
            metrics={
                "structured_output_reliability": 0.0,
                "severity_weighted_safety": 0.0,
                "semantic_validity_closeness": 0.0,
                "joint_intent_cpc_quality": 0.0,
                "compound_ambiguity_quality": 0.0,
                "qlora_feasibility": 0.55,
                "context_length": 0.90,
                "runtime_stability": 0.20,
                "vram_and_latency": 0.85,
            },
            qlora_feasible=True,
            context_length_sufficient=True,
            runtime_compatible=True,
            snapshot_and_licence_verified=True,
            tokenizer_loads=True,
            runtime_loads=True,
            licence_compatible=True,
            reproducible_load=True,
            fundamental_incompatibility=False,
        ),
    }

    outcome = apply_adaptation_base_selection(results, policy=policy, registry=registry)
    assert_adaptation_base_selection_scope(
        selected_base_model=outcome.selected_base_model,
        selected_adapter=outcome.selected_adapter,
        selected_model_strategy=outcome.selected_model_strategy,
        adaptation_base_status=(
            "selected_for_qlora_development"
            if outcome.selected_base_model
            else "no_viable_adaptation_base"
        ),
        valid_for_official_use=False,
    )

    payload = {
        "policy_id": "adaptation_base_selection_policy_v1",
        "policy_version": policy.policy_version,
        "frozen_before_application": True,
        "requires_zero_shot_stage1_pass": False,
        "zero_shot_candidate_status": "rejected",
        "adaptation_base_status": (
            "selected_for_qlora_development"
            if outcome.selected_base_model
            else "no_viable_adaptation_base"
        ),
        "selected_base_model": outcome.selected_base_model,
        "selected_adapter": None,
        "selected_model_strategy": None,
        "valid_for_official_use": False,
        "winning_candidate_id": outcome.winning_candidate_id,
        "ranked_candidate_ids": list(outcome.ranked_candidate_ids),
        "rejected_candidates": {
            key: list(value) for key, value in outcome.rejected_candidates.items()
        },
        "tie_break_applied": outcome.tie_break_applied,
        "development_only": True,
        "note": (
            "Adaptation-base selection for QLoRA development only. "
            "Does not approve an adapter, model strategy, or official use. "
            "Zero-shot Stage-1 rejection remains immutable."
        ),
    }
    out = ROOT / "configs/model/evidence/model_selection_bakeoff_v1/adaptation_base_selection_v1.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
