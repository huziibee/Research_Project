# T43 — Factorial scene/dialogue/capability context ablation

**Status:** APPROVED_POST_GATE_PROTOCOL_AND_EXECUTION

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
