# Post-T39 science-closure programme

## Decision

The current supervisor handover is an **interim evidence brief**, not the final
supervisor results document. The final document may be assembled only after
T39, T40, T41, T42, T43 and T44 each has a frozen protocol where applicable, an
auditable terminal artifact, and an explicit `PASS`, `FAIL`, or `NOT_COMPUTED`
result. Here *terminal* means an audited artifact records the outcome; an
unavailable or failed metric remains visibly `NOT_COMPUTED` with its evidence
gap, rather than being omitted. A task is not made “complete” by a larger model
run or by filling a table with proxy values.

T39/T40 remain unchanged: frozen Pilot-120 v1, fixed models and decoding, no
tuning, no model selection, no deferred `+80` expansion, and no 1,000-record
study. Preparatory, non-inference work starts now: protocol drafting, source
licensing, source audits, annotation materials, and manifest tooling. Scoring,
inference, and claim-bearing annotation execution begin only after the named
T39 reproducibility-audit and T40 audit artifacts are terminal; no additional
cluster inference is submitted before T39's final audit is present.

## Closure ledger

| Workstream | Closes these current gaps | Independent evidence needed | Earliest cluster work |
|---|---|---|---|
| T39 — Pilot-120 v1 reproducibility/evidence atlas | reproducibility, recomputable ambiguity/capability F1, evidence-only slices, all base/adapter disagreements, error taxonomy and descriptive all-context comparison | Five isolated replay roots, runtime provenance, eligible metric reports, evidence atlas and reproducibility audit | Current fixed Pilot-120 batch |
| T40 — interpretation requirements audit | metric-availability audit; a definitive record of which existing Pilot fields cannot support interpretation claims | Immutable audit of current gold/output fields plus future schema/review requirements | CPU-only current batch |
| T41 — interpretation-quality study | intent/CPC exactness, candidate-set quality, resolution value, clarification/rejection target and wording correctness, silent-resolution value | Immutable sidecar gold; two blinded annotations; adjudication and agreement; a frozen structured-output measurement contract | Score existing compatible outputs, then run the frozen measurement contract only where an output field is absent |
| T42 — single-ambiguity study | performance only on its pre-registered one-ambiguity corpus and eligible strata | New, separately frozen one-ambiguity corpus stratified by ambiguity type, gold route, capability and high-cost safety cases | Fixed-system paired evaluation after the corpus freeze |
| T43 — factorial context study | scene-only, dialogue-only and capability-only effects; causal context claims | Pre-registered `2^3` context intervention matrix, paired record analysis, dialogue-availability strata and no prompt/model/tuning change | Eight fixed-context conditions for the specified manager systems after T39 closes |
| T44 — independent confirmation | narrow held-out-corpus generalisation only | Family-disjoint source corpus and gold, held-out before any result inspection, with immutable source/gold/protocol manifests | Full fixed-system confirmation evaluation after its freeze |

## T41 — interpretation-quality study

1. Keep Pilot-120 source/gold immutable. Create a separately versioned
   annotation sidecar, never an in-place edit, and record a source-to-sidecar
   manifest.
2. Define the target schema from T40: intent plus evidence spans; CPC
   slot/value structure plus spans; candidates and admissibility; resolution
   value; clarification/rejection target and wording criteria; silent-resolution
   permission, value, evidence, and safety rationale.
3. Use two annotators blinded to each other and to system identity/predictions;
   publish per-field agreement, adjudication decisions, unresolved cases, and
   an immutable annotation manifest.
4. Before scoring, freeze a measurement-output contract. A system without a
   required output field is `NOT_COMPUTED` for that field, not imputed from its
   terminal route. The contract cannot change a manager, adapter, prompt,
   decoder, threshold, or selected model.
5. Report each field's exact-match/F1/structured validity, target correctness,
   and wording judgement separately. Do not collapse wording quality into route
   accuracy.

## T42 — single-ambiguity study

1. Build a new corpus in which every record has exactly one adjudicated,
   unresolved ambiguity instance of exactly one type, with no secondary
   ambiguity instance. It is a new frozen study, not a relabelled subset of
   Pilot-120 and not the deferred `+80` records.
2. Pre-register sampling strata, minimum support, exclusions, safety-cost
   policy, sample-size/precision rationale, double annotation and adjudication.
3. Audit and exclude every Pilot-120 record, paraphrase lineage and scenario
   family; every T44 record/lineage/family; and any future T41 *new source
   material*. T41 currently creates a Pilot sidecar only, not a confirmation
   dataset. Freeze the exclusion ledger, source, gold, record order and
   inference configuration before predictions.
4. Run the same fixed systems with the already fixed decoding; analyse terminal,
   ambiguity and capability outcomes by single type and capability/route strata.
   Thin strata remain count-only.

## T43 — factorial context study

1. Freeze the systems, prompts, model revisions, selected adapter, decoding and
   the existing T39 terminal/ambiguity/capability evaluator. The intervention
   changes only the availability of scene, dialogue and capability context.
   T43 does not automatically adopt T41's later interpretation
   measurement-output contract; doing so would require a separately frozen
   T43 protocol revision before inference.
2. Evaluate the complete paired `2^3` matrix: full context; each one-source
   removal; each two-source removal; and all-context removal. Record exact input
   bytes and tokens for every condition.
3. Use paired record-level contrasts with a pre-registered multiplicity policy.
   Dialogue effects are estimated only in records with dialogue; lack of dialogue
   is not treated as dialogue removal.
4. Report source-specific effects only if the frozen factorial analysis passes
   its input and support gates. Otherwise retain `NOT_COMPUTED`; no causal claim
   follows from T39's all-context contrast alone.

## T44 — independent confirmation

1. Obtain/licence a new source corpus with no record, paraphrase lineage or
   scenario-family overlap with Pilot-120, T42, or any future T41 *new source
   material* (the current T41 Pilot sidecar creates none). Freeze and audit an
   explicit exclusion ledger for all three dimensions.
2. Before label review, freeze the source and pre-register the exact T41 field
   coverage set (if any), field-level denominators/eligibility rules, and
   evaluator version. Double annotate and adjudicate the terminal, ambiguity
   and capability gold; where those pre-registered T41 fields are in scope, use
   its gold schema and independent blinded review. Excluded or missing fields
   remain `NOT_COMPUTED`.
3. Hold this corpus out from all protocol development and error-atlas review.
   The exact same fixed system bundle and pre-registered evaluator are used.
4. The only permitted generalisation is narrow: to this held-out, predeclared,
   eligible corpus/family set under the unchanged systems and evaluator, and
   only when denominator, hashes, eligibility, field coverage and
   family-disjointness all pass. It is not a real-world robot-safety or general
   superiority claim. A failed or partial confirmation remains `NOT_COMPUTED`;
   the protected/official evaluation gate remains separately blocked.

## Parallel execution and cluster schedule

During the current three-day T39 run: complete T41–T44 protocols, licensing,
source audits, annotation materials, power/precision calculations and immutable
manifest tooling. These are preparatory activities only: do not run their
scoring, inference, claim-bearing annotation execution, or alter T39.

After `t39_reproducibility_audit.json` and T40 have terminal artifacts, submit
the approved closure workstreams in parallel where their frozen inputs exist:

- T41 annotation/sidecar validation and T42 corpus construction run in parallel
  on CPU/human-review lanes.
- T43 factorial inference may use the cluster once its condition manifest and
  input-byte verifier pass.
- T44 source/annotation work runs independently; its cluster confirmation job
  starts only after the family-disjoint freeze.

No supervisor-facing result table is final until the T39+T40+T41+T42+T43+T44
terminal-artifact crosswalk is linked. Each unavailable or failed measure is
shown as `NOT_COMPUTED` with its precise evidence gap; none is silently omitted.

## Final supervisor-document gate

The final document must include: all frozen dataset and code hashes; job IDs and
statuses; system definitions; metric eligibility; raw denominators; uncertainty
and paired analyses; error taxonomies; every failed/recovered job; all
limitations; and a T39+T40+T41+T42+T43+T44 claim-to-artifact crosswalk. It must
distinguish empirical findings, descriptive associations, causal estimates, and
unavailable claims.
