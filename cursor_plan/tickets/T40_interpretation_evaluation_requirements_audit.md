# T40 — Interpretation evaluation requirements audit

**Status:** APPROVED_PROTOCOL_AUDIT_ONLY

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

Do not alter Pilot-120, sample/annotate new data, or run model inference. A
single-ambiguity study or +80 extension requires a separately authorised
protocol.
