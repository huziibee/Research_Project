# Manual κ / Final-Protocol v7 — Pilot-120

**Protocol:** `final_protocol_v7` (`configs/annotation/final_protocol_v7.json`)  
**Handbook:** `docs/protocols/annotation_handbook_v1.md`  
**Evaluation set:** `pilot_120_v1`  
**Status:** final-protocol workflow ready; **Pilot-120 not frozen** (subset + supervisor annotations missing)

## Critical independence requirement

Final-protocol annotators **MUST NOT** read or use:

- previous pilot annotator A labels
- previous pilot annotator B labels
- previous pilot gold labels
- private owner QA labels
- prior adjudication decisions

They may use only:

- the finalized annotation handbook / `final_protocol_v7`
- permitted record evidence: `record_id`, `command`, `scene_context`, `dialogue_history`, `capability_context`, `schema_version`, `group_id`

Blind packages are produced by:

```bash
python3 -m ambiguity_manager.evaluation.pilot_120_cli prepare-blind
```

## Canonical label targets

- `terminal_strategy` (alias field: `recommended_strategy`)
- `ambiguity_types` (multilabel)
- `capability_status`
- `capability_interpretation`
- `risk_level`
- `speech_act`

Plus freeze contracts:

- `capability_evidence_class` ∈ {A,B,C,D} with **D = 0** on Pilot-120
- `one_path_determinacy = true` for 120/120

## Agreement

Compute with:

```bash
python3 -m ambiguity_manager.evaluation.pilot_120_cli agreement
```

Report terminal-strategy Cohen’s κ, raw agreement, disagreement count; multilabel exact-set / Jaccard / macro binary F1; capability agreement.

Historical pilot agreement must remain labeled only as:

`pilot_annotation_agreement`

Do not force final-protocol κ to match the prior ~0.95 pilot figure.

## Adjudication

Preserve ANN-A raw, ANN-B raw, disagreement records, adjudication decisions + rationale, and final gold.  
Do not modify record evidence merely to make annotation easier.

## Freeze

```bash
python3 -m ambiguity_manager.evaluation.pilot_120_cli freeze
```

Freeze refuses unless gates close. On success, artefacts land under `data/annotations/pilot_120_v1/` with SHA-256 hashes and evaluation-only designation.

## Evaluation handoff

After freeze:

```bash
python3 -m ambiguity_manager.evaluation.pilot_120_cli evaluate \
  --config configs/evaluation/pilot_120_v1.json \
  --predictions <PREDICTIONS.jsonl>
```

The evaluator must not need pilot annotation files, private owner QA, or adjudication rationale—only frozen gold + config.

## Current blocker

The repaired 120-record `source_canonical.jsonl` is not in this repository, so independent final-protocol annotation cannot be executed against the intended subset yet. Full-1000 remains deferred.
