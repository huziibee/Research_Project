# T12 Stage D1C1 — Bounded Generation Pipeline and Attempt Evidence

**Stage:** D1C1 (orchestration only; no cluster integration, no live generation)
**Branch:** `feature/t12-cluster-redesign`
**Starting SHA:** `a33b0f717c0c6a8d632a317f0401176fa1792994`
**Date:** 2026-07-11
**Governance:** DEV-20260711-001 (synthetic-only preparatory work; T11 remains BLOCKED)

## Scope

Stage D1C1 delivers CPU-only:

- model-neutral bounded generation-attempt pipeline (`run_generation_pipeline`);
- deterministic regeneration orchestration (max 3 attempts from frozen policy);
- deterministic local JSON extraction/repair via existing `parser.py`;
- strict semantic-schema validation and canonical prediction assembly;
- mandatory unsupported-silent-commitment integrity checks via existing `integrity.py`;
- complete raw-attempt evidence ledger;
- injected fake renderer and generator boundaries for CPU tests;
- frozen pipeline contract (v1.1.0 after hardening).

## Non-scope

- Qwen3 chat-template rendering or `enable_thinking` selection;
- response-mode verification (`ResponseModeStatus` remains unverified in production);
- vLLM engine start, model/tokenizer load, or real structured decoding;
- cluster batch runner integration;
- Slurm templates, SSH, or Apptainer;
- semantic correctness scoring (deferred to Stage E);
- T19 route precedence or `route_policy_gate.py`;
- Stage D1C2, D2, or Stage E.

## Initial failing tests (red phase — initial implementation)

Before implementation:

```text
python -m unittest tests.test_t12_attempt_evidence -v
ModuleNotFoundError: No module named 'ambiguity_manager.model.attempt_evidence'

python -m unittest tests.test_t12_repair_prompt -v
ModuleNotFoundError: No module named 'ambiguity_manager.model.repair_prompt'

python -m unittest tests.test_t12_generation_pipeline -v
ModuleNotFoundError: No module named 'ambiguity_manager.model.generation_pipeline'
```

## Hardening red evidence (pre-hardening contract gaps)

Before hardening, the initial D1C1 implementation permitted these gaps (now closed):

| Gap | Pre-hardening behaviour | Hardening test evidence |
|---|---|---|
| Optional integrity context | `integrity_context: dict \| None = None`; pipeline reached renderer/generator without context | `test_missing_integrity_context_rejects_before_rendering` |
| Conditional integrity check | `if request.integrity_context is not None: count_unsupported_commitments(...)` | `test_integrity_check_runs_with_empty_declarations` |
| Silent resolve without declarations | `silently_resolve` could accept when no support declarations supplied | `test_unsupported_silent_resolution_fails_with_empty_declarations` |
| Generic generation failure repairable | `GENERATION_FAILURE` in `REPAIRABLE_FAILURES`; unclassified errors retried | `test_unclassified_generator_error_non_retryable` |
| Unknown errors consume 3 attempts | Unclassified `generation_error_type` fell through to repairable path | `test_unknown_exception_does_not_consume_three_attempts` |
| Semantic status ambiguity | `semantic_acceptance_status = "structural_only"` could imply semantic pass | `test_no_semantic_correctness_pass_recorded` |

## Input contract

`GenerationPipelineRequest` requires:

| Field | Requirement |
|---|---|
| `caller_request_id` | Non-empty; canonical request ID |
| `synthetic` | Must be `true` |
| `command` | Non-empty; preserved byte-for-byte |
| `label_eligibility` | Mandatory runner-supplied `LabelEligibility` |
| `provenance_policy` | Mandatory explicit `PredictionProvenancePolicy` |
| `source_dataset` | Runner context for assembly |
| `integrity_context` | **Mandatory** immutable `PipelineIntegrityContext` with explicit `support_declarations` |
| Optional context | `scene_context`, `dialogue_history`, `capability_context` |

`PipelineIntegrityContext`:

- no `None` default;
- defensively copied into canonical JSON at construction;
- empty `support_declarations` lists are valid and mean “no commitments currently supported”;
- never inferred from model output;
- hash recorded in result and attempt evidence (`integrity_context_hash`).

Absent or malformed integrity context → `rejected_non_retryable`, zero renderer calls, zero generator calls, no fabricated attempt entries.

## Mandatory integrity check

After every successful canonical assembly:

1. `count_unsupported_commitments()` runs exactly once (unconditional);
2. mandatory integrity context is supplied;
3. count and details recorded in attempt evidence;
4. count must equal zero before structural acceptance.

Empty support declarations still execute the check; unsupported silent commitments fail.

## Generator-failure taxonomy

**Repairable model-output conditions only:**

- empty successful response text (`empty_generation_output`);
- malformed successful response text (JSON extraction/parse failures);
- semantic-schema / assembly / unsupported-commitment failures;
- explicitly typed `transient_output_production_failure`.

**Non-retryable (immediate stop after discovery):**

- `backend_dependency_failure`, `backend_configuration_failure`, `backend_startup_failure`;
- `engine_failure`, `unknown_exception`, `unclassified_generator_error`;
- structured-decode, response-mode, contract/schema mismatch;
- policy corruption, programming errors.

No catch-all repairable exception path. Unknown generator exceptions are caught, sanitized, recorded, and stop regeneration. Arbitrary exceptions are never classified as repairable.

## Semantic-correctness status

D1C1 performs structural acceptance only. Field renamed to `semantic_correctness_status` with frozen value:

```text
not_evaluated
```

- structurally accepted results: `structural_validity_status = valid`, `semantic_correctness_status = not_evaluated`;
- rejected results also record `not_evaluated` (semantic correctness was not assessed);
- final `accepted` means “accepted by the Stage D structural and integrity gate,” not “semantically correct”;
- Stage E owns semantic correctness evaluation.

## Verified-renderer boundary

`GenerationReadyRenderer.render(messages) -> GenerationReadyPromptEnvelope` records rendered text, hashes, model identity, response-mode identity/status, renderer identity/version.

Pipeline fails before generation unless response mode is verified, repository/revision match immutable selection, rendered prompt is non-empty, and hashes are valid.

## Structured-decode readiness boundary

`StructuredDecodeReadiness` verified against frozen structured-decode contract. Absent or mismatched readiness causes zero generator calls.

## Attempt policy enforcement

Max 3 attempts (1 initial + 2 regeneration). Attempt indexes `0, 1, 2`; kinds `initial, regeneration, regeneration`.

## Attempt-ledger schema

`AttemptEvidenceEntry` records all prior fields plus:

- `semantic_correctness_status` (`not_evaluated` in D1C1);
- `integrity_context_hash` (deterministic SHA-256 of canonical integrity JSON).

Raw output never replaced by repaired text. Engine request ID diagnostic only.

## Pipeline stages

Per attempt: prompt build → render → readiness verify → generate once → parse/repair → semantic validate → assemble → canonical validate → **unconditional integrity check** → accept or classify repairability.

## Repair-prompt contract

Unchanged from initial D1C1: bounded regeneration prompts preserve caller context, include prior validation failures, and require complete replacement semantic objects.

## Structural acceptance boundary

Acceptance requires successful generation, parse/assembly success, schema-v2 validity, zero unsupported commitments, caller ID and command preserved. Semantic correctness is explicitly **not evaluated**.

## Final result contract

`GenerationPipelineResult` adds `integrity_context_hash`. Final statuses: `accepted`, `rejected_after_attempts`, `rejected_non_retryable`.

## Caller-ID and engine-ID treatment

Caller `request_id` canonical. `engine_request_id` diagnostic only in attempt entries; absent from canonical prediction.

## No T19 implementation

No route precedence or `route_policy_gate.py`. `t19_routing_deferred` remains true.

## No-cluster / no-model statement

No SSH, Slurm, Apptainer, vLLM engine, model weights, or tokenizer accessed.

## Frozen pipeline contract

**Path:** `configs/model/t12_generation_pipeline_contract.json`
**Contract version:** `1.1.0`

**Authoritative identity (portable):**

| Method | SHA-256 |
|---|---|
| `canonical_json_sha256_v1` | `786cf6e7213fa3519ba7797464c25495f790cdf4ebc0c139c433168bd703b758` |

**Historical raw-byte digests (diagnostic only; not cross-platform authoritative):**

| Form | SHA-256 |
|---|---|
| LF raw bytes | `94eb2d777fb6e9bbebc90b7c8d727cec2e2bebfcf0acbcd276144f2c71d34b64` |
| CRLF raw bytes | `1c4543e29121ce1e390ea60d91c51530cb180f8624d1e7932c4d9524a186599b` |

Contract semantics were unchanged across these representations; only file-byte encoding differed.

Records mandatory integrity context, unconditional integrity check, non-retryable unknown generator failures, and `semantic_correctness_status_not_evaluated: not_evaluated`.

## Tests and exact results (post-hardening)

```powershell
$env:PYTHONPATH = "src"
python -m unittest tests.test_t12_attempt_evidence -v          → OK (6)
python -m unittest tests.test_t12_repair_prompt -v               → OK (10)
python -m unittest tests.test_t12_generation_pipeline -v       → OK (66)
python -m unittest tests.test_t12_prediction_contract -v       → OK (54)
python -m unittest tests.test_t12_prompt_builder -v              → OK (19)
python -m unittest tests.test_t12_generation_policy -v           → OK (11)
python -m unittest tests.test_t12_response_mode -v               → OK (7)
python -m unittest tests.test_t12_structured_decode -v           → OK (21)
python -m unittest tests.test_t12_vllm_batch_backend -v          → OK (32)
python -m unittest tests.test_t12_stage_d1b1_runtime_evidence -v → OK (22)
python -m unittest discover -s tests -p "test_t12_*.py"          → OK (670, skipped=2)
python -m unittest tests.test_governance_*                       → OK (31)
python -c "import sys; import ambiguity_manager.model; print('torch' in sys.modules, 'transformers' in sys.modules, 'vllm' in sys.modules)"
# False False False
git diff --check → clean (no output)
```

## Remaining requirements for D1C2 and D2

**D1C2:** production Qwen3 renderer; wire pipeline into cluster batch runner.

**D2:** live engine-time schema compilation; live structured-output smoke; response-mode verification.

## Explicit non-claims

D1C1 does **not** claim:

- response mode is verified in production;
- engine-time schema compilation passed;
- live generation passed;
- semantic correctness passed or evaluated;
- Stage D is complete;
- Stage E is ready.
