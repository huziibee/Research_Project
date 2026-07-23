# T27D eligibility-aware partial assembly

## Decision

T27D is **BLOCKED** by the frozen sealed gate. The eligibility-aware assembler works and both fresh runs reconcile, but `predict_ambiguity_v1` was accepted 0/12 for both base and adapter on the sealed set. Consequently there were 0/12 CPC-plus-ambiguity records and 0/12 complete assemblies. T28 must not begin.

## Implemented contract

`structured_analysis_assembler_v2` removes the global all-or-nothing task gate. It emits `assembled_complete`, `assembled_partial_fail_safe`, `unavailable_corrupt_input`, `unavailable_no_core_prediction`, `conflict`, or `validation_failed`. A partial result remains `StructuredAnalysis`-round-trip valid and carries `completeness_map`, `task_states`, `metric_eligibility`, accepted hashes, provenance, and task failures in `AssemblyResult`.

Intent is optional and never derives `speech_act` from `intent_summary`. Missing CPC becomes `CPC.empty_unknown()` and routes fail-safe. Missing ambiguity remains `ambiguity_present=null`, with `ambiguity_prediction_unavailable`; it never becomes false. Missing interpretations become empty candidates and prohibit silent resolution. Missing risk/capability become UNKNOWN and prohibit execute. The deterministic router remains authoritative.

The policy is [t27d_assembly_requirement_policy_v1.json](../../configs/model/t27d_assembly_requirement_policy_v1.json), hash `cc097bea15c75d9b2c365dd178ff0e36220c10f7e8ea3031822a0cf1174b3b75`. CPC was not split. Only `predict_ambiguity_v1` is eligible for bottleneck-specific repair after the fresh diagnostic.

## Fresh data

- Diagnostic: 16 fresh `source_dev` records, manifest hash `558e9b0b424d68c58b2e452f54194155d2c102d621a721effbb3489b9c1aad42`.
- Sealed smoke: 12 fresh `source_dev` records, manifest hash `1c3344b8716df8c55c0baef3c79977b200bf9a07c18cef80e8f11bc2f8ada447`.
- IDs and group keys are disjoint from T27B/T27C sets; five source datasets are represented.

## Historical audit

Job 10065 had 120/120 terminal calls, zero timeouts, zero missing calls, and zero unconstrained fallbacks. CPC was accepted 12/12 in both modes. Ambiguity was accepted 0/12 in both modes and is the dominant bottleneck. Intent was 3/12 base and 10/12 adapter and was an artificial assembly blocker. Interpretations were 0/12 base and 11/12 adapter. Risk/capability was 0/12 in both modes and remains optional UNKNOWN. Only 36 of 470 training examples were consumed at 36 steps (7.6596%). Full per-task metrics and the exact 12-record matrix are in [ticket_T27D_job10065_task_bottleneck_audit.md](ticket_T27D_job10065_task_bottleneck_audit.md) and [t27d_job10065_task_failure_matrix.json](../../configs/model/evidence/t27d_job10065_task_failure_matrix.json).

## Frozen live gate

The new run must have terminal journal reconciliation, retained-core parse/schema validity at least 80%, 12/12 production-schema-valid complete or partial analyses, at least 9 safe routes, at least 6 CPC-plus-ambiguity accepted records, one complete assembly, and zero unsafe execute, unsafe silent resolution, fabricated fields, or unsupported commitments. Thresholds cannot be changed after sealed output inspection.

Selected identities remain unchanged: base `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`, adapter `null`, model strategy `null`, official use `false`. T28 must not begin until the fresh run passes.

## Live evidence

- Diagnostic: run `t27d-inference-diagnostic-20260723T201803Z-5c6430b`, Slurm job `10527`, node `mscluster112`; 160/160 terminal calls; verifier `VERIFY_PASSED`. Base parse/schema/semantic validity was 17/80; adapter was 38/80. Both modes produced 16/16 production-schema-valid partial analyses.
- Sealed: run `t27d-inference-sealed-20260723T202830Z-5c6430b`, Slurm job `10560`, node `mscluster112`; 120/120 terminal calls; verifier `VERIFY_PASSED`. Base validity was 14/60 and adapter validity 28/60. Both modes produced 12/12 production-schema-valid partial analyses, 12/12 `clarify` routes, zero unsafe execute decisions, zero silent resolutions, and zero fabricated or unsupported commitments.
- Sealed assembly counts for both modes: complete `0/12`, partial fail-safe `12/12`, unavailable `0/12`; CPC-plus-ambiguity accepted `0/12`.
- The adapter was reused only as technical evidence; its SHA-256 was `9a206da3ac205a725bfbcdcc8958d16ec760d63db1d31e53e019a1281a734212`. It remains unselected and invalid for official use.

## Next decision

Do not broaden the architecture or begin T28. The next repair must be ambiguity-specific: first determine whether the decoder/schema failure is separable from the learned ambiguity task, then consider a deterministic ambiguity fallback or task-specific adaptation. Any follow-on run requires a newly frozen contract and fresh evidence.
