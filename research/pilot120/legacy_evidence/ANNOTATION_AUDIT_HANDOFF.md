# Pilot-120 Historical Annotation Audit Handoff

This package preserves the historical annotation tree from Git commit `8e430ab` and adds current frozen Pilot-120 alignment evidence plus mechanically derived ledgers. No annotation values were created or modified.

## Direct answers

- **A. Raw independent annotations:** YES. A: `annotations/manual_kappa_v7/annotator_a_grok/` (120 records). B: `annotations/manual_kappa_v7/annotator_b_claude/` (120 records). B is documented as 70 Claude-era and 50 GLM-era records.
- **B. Final adjudicated annotation:** YES. `annotations/manual_kappa_v7/gold/` (120 records), with JSONL exports and manifests.
- **C. Exact annotation prompts:** YES for preserved v7 brief/handbook/schema and adjudicator brief; runtime/API transcripts are missing.
- **D. Agreement code/results:** PARTIAL. Reports and kappa outputs are preserved; relevant repository implementation is copied under `repository_context/`.
- **E. Meaning of 80%:** Historical artifacts report **Cohen's kappa and raw percentage agreement separately**; no universal 0.80 kappa gate is evidenced in the preserved result. Core gold fields are `terminal_strategy` and `ambiguity_types`.
- **F. Historical pooled results:** n=120 paired=120; terminal κ=0.953313448320581, raw=0.975; capability κ=0.8331788693234476, raw=0.9; primary κ=0.7331902169746224, raw=0.7583333333333333; recommended κ=0.5108529501681442, raw=0.6666666666666666; risk κ=0.5937161430119177, raw=0.7916666666666666; validity κ=0.0, raw=0.9916666666666667.
- **G. Adjudication selection:** 39 preserved packet records; historical report states 3 terminal and 30 ambiguity-type-set disagreements. Mechanical top-level ledger rows: 846.
- **H. Distinct adjudicator:** YES, a distinct Claude packet-adjudicator role; A/B answers were exposed. Human-gate documents are preserved.
- **I. Exact frozen T39 alignment:** PARTIAL; ID/order and hashes are compared in `pilot_alignment/alignment_report.json` without silent remapping.
- **J. A/B blindness:** LIKELY_BLIND from the preserved brief, not independently verified; adjudicator intentionally NOT_BLIND to A/B; T39-output exposure UNKNOWN.
- **K. Fields covered:** `inventory/annotation_field_inventory.csv`; raw nested structures remain in original JSON.
- **L. Missing:** `MISSING_ARTIFACTS.md`.

## Preservation and verification

Historical files were extracted from Git without semantic rewriting. Derived ledgers are clearly labelled. Manifest and SHA-256 list are under `provenance/`.
