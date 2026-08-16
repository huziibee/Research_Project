# T28 Handover (R5 recovery)

T28 integrity is **unblocked**. The historical R4 `canonical_hash_mismatch` root cause was **text-mode transfer of authoritative CRLF JSONL** (git-archive / newline conversion). The binary-safe content-addressed bundle now verifies identically locally and on the cluster.

## Integrity

- Canonical SHA-256: `1e51cac046e014a6b890b10a155d22e32e01aa276d4507a10ad4f86abcf9942a`
- Permitted-view SHA-256: `34b551c37c8f97c24c1263a2cc12a9497e65f754924f1404c47055999f04ea22`
- Train/dev manifests: `eb73488a...` / `6b2b3b3a...`
- Counts: 11,294 source-train, 2,396 source-dev (task manifests 10,774 / 2,284)
- Remote CPU verify: `VERIFY_PASSED` (`outputs/t28_r5/evidence/cpu_slurm_verify.json`)
- Local integrity report: `outputs/t28_r5/evidence/local_integrity_report.json`

## Training

Job `22733` (`t28-full-train-20260728T222000Z-r5-retry5`) reached **step 1500 / 1500** and wrote the adapter + full checkpoint under:

`/home-mscluster/mbangie/t12-hpc/runs/t28-full-train/t28-full-train-20260728T222000Z-r5-retry5/`

The Slurm job later hit the 24h wall during post-train evaluation; the adapter itself is present.

Adapter safetensors SHA-256: `5801fdade1e533018ee5e7ffe4fed2f83860e515ea8c469853fc49b15d3ddecd`

## Checkpoint selection

`selected_adapter` remains **false** until source-dev evaluation and the frozen selection policy complete. Source-dev eval job **30250** was submitted after fixing the manifest→permitted-view join (`KeyError: record`). Pilot-120 was **not** used.

Handoff packet for the Pilot-120 evaluator: `outputs/t28_r5/evidence/t28_pilot120_handoff.json`

## Do not

- Bypass SHA-256 gates
- Regenerate corpus on the cluster
- Train/select with Pilot-120 or protected final gold
- Start T29/T30 without separate approval

## 2026-08-17 early-pilot continuation

- The non-protected Pilot-120 direct-base / provisional-adapter paired run is complete at 120/120. It is evaluation-only and cannot select the adapter. The provisional adapter was lower than direct base on the recorded paired early metrics, so this is integrity evidence, not a performance pass.
- The former T31+ "missing artifact" report was a lookup error: job `43646` completed and wrote `t31plus_early_postprocess_preflight.json` with `WAITING_FOR_FULL_EARLY_T30_MATRIX`.
- The three missing early systems are now implemented as a single GPU matrix: `degree_based_router` and `full_type_risk_aware_manager` share one full-context model-generated analysis; `context_blind_manager` gets a separately generated context-ablated analysis. The frozen Pilot gold is not supplied to model prompts and is read only after predictions are materialized for scoring.
- T29/T30 early gate now recognizes the actual canonical system id `full_type_risk_aware_manager` and moves to `T29_T30_EARLY_COMPLETE_NON_PROTECTED` only when all three manager artifacts are 120/120, schema-valid, and error-free. T31+ then emits `READY_FOR_T31PLUS_EARLY_ANALYSIS`.
- T28's sole adapter failure is isolated: `clara:1170::predict_cpc_v1` generated an endlessly repeated `tool` value until the 4,915-token cap, despite the intended 64-character CPC bound. The R5 retry retains constrained JSON, model, adapter, scale, prompts, and source-dev membership, and adds only inference-time anti-repetition guards (`repetition_penalty=1.08`, `no_repeat_ngram_size=4`). The full recovery composer is corrected to accept this exact-one-call routing-eval repair.
