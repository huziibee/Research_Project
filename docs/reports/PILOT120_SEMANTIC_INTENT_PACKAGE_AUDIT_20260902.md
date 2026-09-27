# Pilot-120 semantic-intent package adversarial audit

## Verified inputs

- `pilot120_intent_evaluation_20260902.zip` SHA-256 is `541f2990305a54ccabee9f2e24c77da5b1597b54453956374c97f74b47ab3116`.
- All 138 supplied `SHA256SUMS` entries verified with zero mismatches.
- `validation/FINAL_AUDIT.json` reports 18/18 checks passing.
- The supplied blind-only bundle SHA-256 is `f05389490b629cbea1eb8d63613a7e72adaf08972423dcb2299d4b47748e18e3`. Its pass-1, pass-2, and combined packet hashes equal the corresponding full-package files.
- The T39 normalised `intent_summary` remains `None`. Retrospective SGC is therefore **observable semantic-goal trace correctness**, never a claim about hidden model intent.

## Independent audit findings

1. **Blindness: PASS.** All 240 packet rows use opaque `IE-...` identifiers. The only top-level fields are candidate trace/excerpt, two pre-T39 references, source/context, scope, and command-copy policy. Mechanical checks found no system/model/condition, route, CPC, ambiguity, performance, or record-ID fields. Each pass has 120 distinct source cases; the opposite condition is in the other pass only.
2. **Command-copy protection: PASS.** Normalised exact source-command copies in prepared excerpts: `0/240`.
3. **Frozen-artifact protection: PASS.** No T39/T41 file was written. The repaired manager, frozen CPC policy, and T41 final-gold hashes remain unchanged.
4. **Byte-rebuild qualification: FAIL for cross-platform byte identity, PASS for content identity.** On Windows the deterministic rebuild reproduced the six data JSONL files byte-for-byte, but `build_audit.json` and `speech_act_results.json` acquired CRLF line endings from `Path.write_text`, whereas archived outputs use LF. Parsed JSON content is equal. This is documented rather than silently regenerated; judging uses the shipped hashed material.
5. **Reporting gap: fixed in integration overlay.** The supplied finalizer computes SGC/FIC and route matrices, but not the required indirect-request slice, layered first-observable failure allocation, or record-level route-error ledger. The overlay scorer adds these without changing the metric.
6. **Governance qualification: BLOCKED for official-correctness claims.** `configs/research/research_contract_v1.json` requires a deterministic primary evaluator and forbids a generative LLM as the primary official judge; `configs/evaluation/evaluator_policy_v1.json` explicitly says no LLM judge may determine official correctness. The two blind model judges are therefore an explicitly user-authorized, prediction-blind exploratory addendum. They cannot become official final correctness without an approved protocol deviation and the required adjudication authority.

## Run isolation

The cluster job accepts only the separately supplied blind bundle, guide, prompt, schema, and synthetic calibration. It has no sealed mapping/result input. Each Judge A/B pass starts and shuts down a separate vLLM server to maintain fresh contexts. Judge A uses pinned Gemma-4-26B-A4B-it and Judge B uses pinned GLM-4.7-Flash.

## 2026-09-08 Judge-A transport repair

Gemma completed 74 sequential API requests in recovery job `50868`, but emitted an opaque evaluation ID copied from a synthetic calibration example. The runner rejected it (`decision_id_mismatch`) and wrote no partial judgment file. This is an identifier-rendering failure, not a semantic decision. The recovery runner now validates every required semantic field and deterministically assigns the opaque ID of the one packet row sent in that sequential request. It does not use the sealed mapping, system identity, route, CPC, or any outcome.
