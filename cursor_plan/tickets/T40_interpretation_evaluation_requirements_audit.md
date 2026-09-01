# T40 — Interpretation evaluation requirements audit

**Status:** COMPLETE_NON_OFFICIAL — REQUIREMENTS AUDIT ONLY

## Goal

Document exactly why the frozen Pilot-120 v1 gold cannot score interpretation,
CPC, candidates, resolution values, clarification/rejection targets or wording,
and silent-resolution quality; define the future independent annotation schema
without creating labels or running inference.

## Required work

1. Inspect the frozen gold fields and write a machine-readable
   `NOT_COMPUTED` inventory.
2. Define required future fields: intent/evidence spans, CPC/evidence spans,
   candidate set/admissibility, resolution values, clarification targets and
   wording criteria, rejection targets and wording criteria, and silent
   resolution values/evidence.
3. Define two independent blinded annotators, adjudication, agreement reporting,
   immutable manifests, and family-disjoint confirmation data as requirements
   for a future study.

## Deliverable

Write `t40_interpretation_requirements_audit.json` with the missing-field
inventory and future data dictionary. Blinding means annotators cannot see each
other's labels or any system prediction; agreement and adjudication are
reported per field. Family-disjoint means no record, paraphrase lineage, or
shared scenario family crosses development and confirmation sets.

## Boundary

Do not alter Pilot-120, sample/annotate new data, or run model inference. T42
is the separately governed single-ambiguity study; no deferred `+80` extension
is part of the T39–T44 closure programme.

## Execution record

Attempt-3 job `48573` completed `0:0` and wrote
`/home-mscluster/mbangie/t28_r5_src/outputs/pilot_120/t39_20260901_78ce05d/t40_interpretation_requirements_audit.json`
with status `T40_INTERPRETATION_REQUIREMENTS_AUDIT_COMPLETE`. It confirms the
current gold lacks every interpretation target named above; it creates no
labels, metrics, or performance claim. T41 owns the separately frozen sidecar
study required to resolve those `NOT_COMPUTED` fields.
