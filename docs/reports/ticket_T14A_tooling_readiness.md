# T14A Tooling Readiness Report

**Date:** 2026-07-22  
**Status:** tooling ready against synthetic labels only

## Implemented

- Immutable package loading helpers
- Independent A/B submission validation
- Progress / missing-annotation calculation
- Record-set equality checks
- Field-level comparison and disagreement extraction
- Confusion matrices for key categorical fields
- Raw percent agreement
- Cohen’s kappa for categorical labels
- Multi-label Jaccard for ambiguity types
- CPC slot agreement
- Adjudication queue format
- Gold-export gate that refuses incomplete/unresolved/invalid adjudication
- Synthetic gold export path that refuses calibration/main partitions in this task

Module: `src/ambiguity_manager/annotation/agreement.py`  
Tests: `tests/test_t14a_annotation_tooling.py`

## Explicit non-claims

- No supervisor labels exist.
- Human annotation has **not** started.
- Adjudicator identity (`ADJ-01`) remains unresolved.
- Final gold export remains gated.
- No real calibration/main record was exported as gold.

## Next

Await supervisor calibration review and T14B availability. Keep T14A synthetic
tests green while annotation is pending.
