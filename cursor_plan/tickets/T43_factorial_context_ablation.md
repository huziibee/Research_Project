# T43 — Factorial scene/dialogue/capability context ablation

**Status:** CPU_PREPARATION_VERIFIED; INFERENCE_NOT_QUEUED; RESULTS_NOT_COMPUTED

Estimate separately pre-registered scene, dialogue and capability context
effects with a paired `2^3` availability matrix. Systems, model revisions,
adapter, prompt, decoding and the existing T39 terminal/ambiguity/capability
evaluator are frozen from T39; only the specified context inputs vary. T43 does
not adopt T41's newly frozen interpretation measurement-output contract unless a
separate T43 protocol revision is frozen before inference. Dialogue estimates
are limited to naturally dialogue-present records.

**Acceptance:** byte/token input verifier; eight-condition manifest; paired
analysis with multiplicity policy; support gates; no causal/source-specific
claim unless all protocol gates pass.

## CPU-only preparation record (2026-09-01)

The versioned policy is
`configs/evaluation/pilot120_t43_factorial_context_policy_v1.json`; its
generator/verifier is `scripts/pilot120_t43_factorial_context.py`; and the
operator protocol is `docs/protocols/T43_FACTORIAL_CONTEXT_MANIFEST_PROTOCOL.md`.
They generate all eight availability cells (`S1_D1_C1` through `S0_D0_C0`)
without modifying frozen Pilot data or running inference.

The verifier compares every retained field's exact UTF-8 JSON source token,
source order, 120-record denominator and frozen source hash. It records prompt,
rendered-input and token-ID fields as explicit `NOT_COMPUTED` placeholders
during CPU preparation; a later runtime attestation must provide auditable
bytes/hashes for all 960 record-condition inputs. The dialogue effect is
pre-registered only on the 44 naturally dialogue-present records; empty
histories are not recoded as an intervention.

Static readiness is **not** execution readiness. Before any cluster inference:

1. T39's final reproducibility audit and T40 must be terminal.
2. Bind the unchanged T39 system/model/adapter/decode/prompt-renderer/tokenizer
   and evaluator bytes to the manifest.
3. Verify the runtime's prompt/render/token attestation, run all eight cells,
   then apply the pre-registered paired support and Holm-multiplicity audit.

Until those artifacts exist, all isolated context effects remain
`NOT_COMPUTED` and no cluster submission is authorised by this ticket.
