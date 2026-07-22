# 08 — Manual Gold Benchmark Programme

This document governs T13–T15. Public/source dataset details are handled by the current repository and T15 eligibility manifest; they are not inherited from the old proposal dataset section.

## Objective

Create a human-adjudicated benchmark that can judge both **what the command means** and **what the system should do next**.

## Planning target

- Calibration: 24 records (handbook/interface refinement; not automatic official gold).
- Initial main target: 300 adjudicated records.
- Optional expansion toward 400 only if a coverage audit identifies underfilled design cells and supervisor workload allows it.
- Do not freeze 400 merely because an older draft mentioned it.
- Counts are planning targets, not fabricated achievements. Record actual funnel counts.

## Required record structure

Each gold record should support, when applicable:

```json
{
  "schema_version": "2.x",
  "command": "string",
  "scene_context": "string | null",
  "dialogue_history": ["string"],
  "capability_context": "string | null",
  "gold_intent": "string | null",
  "gold_cpc_frame": {
    "action": "string | null",
    "actor": "string | null",
    "object": "string | null",
    "destination": "string | null",
    "spatial_relation": "string | null",
    "quantity": "string | number | null",
    "time": "string | null",
    "recipient": "string | null",
    "tool": "string | null",
    "conditions": ["string"],
    "constraints": ["string"]
  },
  "gold_valid_interpretations": [],
  "gold_uniquely_resolvable": false,
  "gold_unresolved_slots": [],
  "gold_supporting_evidence": [],
  "gold_ambiguity_types": [],
  "gold_risk_level": "none | low | medium | high | unknown | null",
  "gold_capability_status": "capable | conditional | incapable | unknown | null",
  "gold_route": "execute | clarify | silently_resolve | face_preserving_rejection | multi_step",
  "gold_strategy_sequence": [],
  "gold_clarification_targets": [],
  "gold_rejection_reason": "string | null",
  "gold_resolved_slots": {},
  "group_id": "string",
  "provenance": {}
}
```

## Interpretation rules

Do not force one arbitrary gold meaning when several are plausible. Distinguish:

- the known intended interpretation, if available;
- all materially valid interpretations under supplied evidence;
- whether one is uniquely supported;
- unresolved slots;
- unsupported additions;
- resolved values that a safe silent-resolution policy may choose.

## Information structure

Annotators must separately label:

- speech act / intent;
- CPC/action arguments;
- supplemental contextual evidence used for reference resolution;
- ambiguity, risk, capability, route, and response target.

## Authoring rules

- Use a frozen design-cell matrix rather than open-ended generation.
- Prefer human-authored seeds and controlled transforms first.
- A local LLM may optionally draft candidates later; it is not required for T13 and never supplies gold.
- If used, store model, revision, quantisation, prompt hash, seed, and timestamp.
- Hide proposed labels and critiques from blind annotators.
- Human authors must accept/edit/reject every candidate before annotation.
- Run exact, normalised, and context-command duplicate checks in T13; heavier semantic checks only if later justified.
- Keep generated siblings under one `group_id`.

## Human roles and governance

- Author/reviewer (`AUTHOR-01`): Mohammed Bangie — screens scenarios; must not be ANN-A/ANN-B.
- Annotator A (`ANN-A`): Steven James — independently labels blind records.
- Annotator B (`ANN-B`): Benjamin Rosman — independently labels blind records.
- Adjudicator (`ADJ-01`): unresolved until T14 policy approval; must retain both originals.

Record role overlap. Before collection, T11 must document the institutional/supervisor determination on ethics, consent, personal data, compensation if any, pseudonymisation, storage, and deletion.

## Agreement

Report at minimum:

- raw agreement;
- Cohen's kappa for categorical fields;
- per-label binary kappa and macro kappa for ambiguity labels;
- Jaccard and exact-set agreement;
- CPC/slot field agreement;
- agreement on unique resolvability and unresolved slots;
- risk, capability, route, and strategy-sequence agreement;
- prevalence and per-category counts.

If the pilot gate fails, revise the handbook and annotate a fresh calibration subset.

## Ticket mapping

- T13: guidelines, schemas, design cells, human seeds, calibration packages (24), main-pool readiness (300 target); optional LLM authoring deferred.
- T14A: tooling on synthetic labels; T14B: double annotation; T14C: adjudication and final gold.
- T15: group-aware splits, leakage checks, eligibility manifest, protected benchmark freeze.
- Parallel: T16–T24 interfaces/synthetic fixtures may proceed while annotation is pending (`DEC-20260722-001`).
