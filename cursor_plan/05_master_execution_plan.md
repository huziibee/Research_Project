# 05 — Master Execution Plan

## Status boundary

T00–T09 are complete and must not be rerun. The corrected unfinished sequence is T10–T38.

No calendar schedule constrains this plan. Progress is controlled by evidence-based stage gates.

## Phase 1 — Reconcile the completed foundation

### T10 — Canonical schema v2 and migration

Resolve the completed T01 schema conflicts without rerunning T00–T09. Define schema v2, CPC mapping, resolved-slot fields, canonical enums, and migrations for all completed outputs.

### T11 — Research contract and governance

Freeze the non-dataset proposal alignment, seven mandatory systems, mandatory fine-tuning, text-only scope, AI-use log, ethics determination, and licence registers before new human/model work.

**Gate:** schema v2 and the research/governance contract pass.

## Phase 2 — Cluster model foundation

### T12 — Cluster-native text-model stack (Stages A–I)

Forward-migrate T12 from `b4865b3` to a cluster-native architecture on branch `feature/t12-cluster-redesign`. Historical local WSL/RTX 3070 work is preserved on `archive/t12-local-wsl-slice4`.

**Active contract:** `cursor_plan/tickets/T12_cluster_model_stack_setup.md`
**ADR:** `docs/decisions/ADR_T12_cluster_inference_architecture.md`
**Superseded local ticket:** `cursor_plan/tickets/T12_local_text_model_and_training_stack_setup.md`

**Cluster-validation model (provisional, Stages A–H):**

- `Qwen/Qwen3-8B` @ `b968826d9c46dd6066d109eabc6255188de91218`
- Apptainer `vllm-openai-v0.20.1.sif` (SHA-256 pinned in ADR)
- `model_licence_register.selected_model` remains `null` until Stage I

**Stage summary:**

| Stage | Scope |
|---|---|
| A | Preservation ADR, supersede local ticket, planning contracts, CPU tests |
| B | Cluster manifests, immutable identities, historical evidence relocation |
| C | vLLM batch backend, Slurm preflight, shards and resume |
| D | Full schema-v2 prompt, Qwen3 thinking disablement, structured JSON decoding |
| E | 10/10 fixture synthetic correctness bake-off |
| F | Separate training environment; LoRA feasibility (zero optimiser steps) |
| G | 100–500 record synthetic benchmark, interruption and recovery |
| H | Result publication, archival, email/GitHub notification |
| I | Final acceptance, runbook, local cleanup gate (no automatic deletion) |

**Dependency note:** T12 normally follows T11 PASS. **DEV-20260711-001** authorises narrow pre-T12 preparatory work while T11's annotation ethics gate remains pending; T11 verdict stays **BLOCKED** and T12 completion does not satisfy T11.

**Governance boundary (Stages A–H):** synthetic fixtures and synthetic corpora only; no full research-pool execution; no T13/T14 progression; no protected data.

**Local cleanup:** Qwen2.5 local weights and T12-specific environments become eligible for deletion only after Stage I acceptance, via a separate gated cleanup task. Code, tests, manifests, and Git history are preserved.

**Gate:** cluster-validated base model with reproducible batch inference, structured decoding evidence, LoRA feasibility, benchmark recovery, and publication pipeline; `selected_model` set in Stage I only.

## Phase 3 — Human-gold benchmark

### T13–T15

- T13: annotation handbook, CPC/interpretation schema, design cells, LLM-assisted scenario authoring.
- T14: blind double annotation, agreement, adjudication, gold build, and human semantic-comparison subset.
- T15: group-safe splits, leakage checks, protected data, and machine-enforced eligibility.

**Gate:** trusted gold, agreement evidence, protected splits, and eligibility manifest exist.

## Phase 4 — Manager components and seven systems

### T16–T23

- T16: direct base-LLM structured baseline.
- T17: candidate interpretation generator.
- T18: context-sampling uncertainty.
- T19: ambiguity/risk/capability classifier and deterministic router.
- T20: context resolver and actual silent-resolution values.
- T21: external safety-interface loop without replacing internal risk/capability prediction.
- T22: targeted clarification and face-preserving rejection generation.
- T23: integrate and smoke-test all seven mandatory systems, including the exact degree-based baseline.

**Gate:** every system emits canonical schema-v2 predictions on non-test fixtures.

## Phase 5 — Evaluation infrastructure

### T24–T26

- T24: official deterministic evaluator for intent, CPC, candidates, ambiguity, risk, capability, resolution, routes, clarification, rejection, safety, and efficiency.
- T25: **stretch/nonblocking** human-calibrated semantic verifier.
- T26: immutable experiment runner and provenance plumbing; no protected final runs.

**Gate:** hand-calculated fixtures pass, eligibility is enforced, and run manifests are complete.

## Phase 6 — Mandatory supervised adaptation

### T27–T28

- T27: mandatory local QLoRA/LoRA smoke training.
- T28: mandatory full train/dev-only fine-tuning and checkpoint selection.

**Gate:** the proposed manager adapter exists and is loadable on the exact base model.

## Phase 7 — Freeze and protected execution

### T29–T30

- T29: freeze the existing research contract, all seven systems, adapter, prompts, context-sampling method, degree thresholds, route policy, eligibility, metrics, costs, statistics, and hashes.
- T30: run all seven mandatory systems on every eligible protected split and calculate official deterministic results.

**Gate:** complete immutable protected run matrix.

## Phase 8 — Confirmatory analysis

### T31–T33

- T31: cost-sensitive evaluation.
- T32: confidence intervals, paired tests, effect sizes, and correction.
- T33: component and 2x2 architecture/adaptation ablations.

## Phase 9 — Stretch robustness

### T34–T35

- T34: **stretch/nonblocking** robustness challenge suite.
- T35: **stretch/nonblocking** repeated-run stability.

These tickets may end `NOT_APPLICABLE` or `BLOCKED_NONCRITICAL` without preventing a core research PASS, but their status must be reported.

## Phase 10 — Evidence and audit

### T36–T38

- T36: layered failure analysis.
- T37: report tables, diagrams, reproducibility package, and AI-use disclosure support.
- T38: final integrity audit.

## Build versus run distinction

- T16–T23 build and smoke-test systems.
- T24–T26 build scoring and execution infrastructure.
- T27–T28 train the proposed model.
- T30 actually performs protected execution and gathers final results.

## Immediate stop conditions

Stop and report `FAIL` or `BLOCKED` when:

- T00–T09 artifacts are recreated rather than migrated;
- schema v2 is not authoritative;
- mandatory fine-tuning is skipped;
- context-sampling uncertainty is referenced but not implemented;
- silent resolution selects a route without producing/scoring resolved values;
- any of the seven mandatory systems is omitted;
- protected data is accessed before T29;
- metric eligibility is not enforced;
- an LLM judge replaces deterministic official scoring;
- provenance, hashes, or access logs are missing.
