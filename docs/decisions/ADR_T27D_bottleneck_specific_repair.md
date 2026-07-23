# ADR T27D: bottleneck-specific repair and eligibility-aware assembly

## Status

Accepted for T27D; final gate blocked.

## Context

Job 10065 showed that CPC was accepted 12/12 in both modes, while ambiguity was accepted 0/12 in both modes. Intent and risk/capability were not justified as structural requirements by production safety or dependable supervision. The prior assembler therefore imposed an artificial all-or-nothing gate.

## Decision

Use `t27d_assembly_requirement_policy_v1` and `structured_analysis_assembler_v2` with optional intent, interpretations, and risk/capability; deterministic UNKNOWN defaults remain fail-safe. CPC remains one unchanged task because the audit did not identify it as the bottleneck. Missing ambiguity remains null/unknown, records the unavailability finding, and blocks execute and silent resolution.

Do not retrain the five-task design broadly. Reuse the verified technical adapter for one inference-only diagnostic and one sealed smoke. The ambiguity task is the only candidate for a later task-specific repair.

## Evidence

The diagnostic completed 160/160 calls and the sealed smoke completed 120/120 calls. Both produced production-schema-valid partial analyses, but ambiguity remained 0/16 diagnostic and 0/12 sealed for both base and adapter. The frozen sealed criterion requiring at least 6 CPC-plus-ambiguity records and one complete assembly therefore fails.

## Consequences

T27 remains blocked and T28 may not begin. The adapter remains unselected, no model strategy is selected, and official use remains false. A future attempt must be ambiguity-specific and must preserve fail-safe routing, fresh-set separation, and frozen thresholds.
