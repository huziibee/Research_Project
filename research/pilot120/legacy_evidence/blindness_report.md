# Blindness and contamination audit

Evidence basis: preserved brief, protocol, raw A/B JSON, adjudication packets, and adjudicator brief.

| actor | classification | evidence | limit |
|---|---|---|---|
| Annotator A (Grok) | LIKELY_BLIND | Brief prohibits model outputs, prior labels, sibling records, and gold. | No runtime transcript proves compliance. |
| Annotator B (Claude/GLM eras) | LIKELY_BLIND | Same one-record isolation brief; roster documents the model-era split. | No runtime transcript proves compliance. |
| Adjudicator | NOT_BLIND to A/B | Packets contain both annotator answers and disagreement context. | Intentional adjudication exposure. |
| A/B vs T39 outputs | UNKNOWN | No prediction/result fields found in preserved A/B inputs or brief. | Absence is not proof about external sessions. |

The final-protocol scaffold is not completed reannotation: its A/B directories are empty and agreement is `not_started`.
