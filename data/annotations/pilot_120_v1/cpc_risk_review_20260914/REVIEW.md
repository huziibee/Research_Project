# Pilot-120 CPC / risk review

Reviewer scope: review only. This does **not** rewrite the frozen Pilot-120 core gold and should not be presented as an official benchmark score.

## Task A — CPC audit

### 1. Is T41 CPC usable as official slot-binding gold?

**No, not as-is.** T41 is useful interpretation evidence, but the 13-slot sidecar has demonstrable value errors, incomplete critical slots, and a systematic conversion problem where every omitted slot becomes `not_applicable`. I would treat it as **provisional CPC gold pending a repair/masking pass**, not strict official slot-binding gold.

### 2. Concrete CPC problems

**Definite wrong / malformed filled values**

- `CA-0418`: `quantity="0"` is wrong. The source says the conveyor controller's routine setting is **0.5 metres per second**.
- `CA-0203`, `CA-0369`: `quantity="26"` drops the source unit **packs**.
- `CA-0226`, `CA-0426`, `CA-0596`: `quantity="800"` drops the source unit **millilitres**; analogous rows preserve `800 ml`.
- `CA-0702`, `CA-0778`: `object_attributes="refill jug beside ..."` is mis-slotted; the refill jug/location is a source/tool/spatial relation, not an attribute of the bottle being refilled.

**Filled values that are too vague for slot-binding gold**

- `CA-0007`, `CA-0056`, `CA-0092`, `CA-0394`, `CA-0512`, `CA-0735`: the object is scored as generic `selected ...` even though two selected pending items exist and the record intentionally requires clarification. A generic filled object rewards an under-resolved prediction instead of representing candidates/unresolved identity.
- `CA-0552`, `CA-0714`: `action="inspect"` omits the explicit second action, placing the item in a cage; destination is unresolved, but the action itself is still **inspect then place**.
- `CA-0573`, `CA-0679`, `CA-0908`, `CA-0945`: the actual move destination is embedded inside `conditions` (`parts washer`, `service alcove`, `ticket gate`, `cold room`) while `destination` is absent; `CA-0797` shows the same template with destination represented correctly, so the representation is inconsistent.

**Temporal relation loss**

Several filled `time` values identify the event/time but drop the command's required **after** relation, which changes the slot semantics. Clear examples are `CA-0056`, `CA-0092`, `CA-0215`, `CA-0239`, `CA-0336`, `CA-0565`, `CA-0573`, `CA-0679`, `CA-0739`, `CA-0762`, `CA-0797`, `CA-0836`, `CA-0904`, `CA-0907`, `CA-0908`, `CA-0945`, and `CA-0967`. Other T41 rows do preserve `after`, so this is not a consistent normalization rule.

### 3. Is blanket `not_applicable` honest?

**No.** Raw T41 is sparse, and converting every absent slot to `not_applicable` conflates at least three states: truly inapplicable, unresolved/unknown, and simply omitted/missing.

Rows where an absent slot should be **unknown/unresolved** rather than `not_applicable` include:

- Destination: `CA-0070`, `CA-0552`, `CA-0714`, `CA-0727`, `CA-0786` — multiple authorized secure destinations exist and the required unit identifier is missing.
- Quantity: `CA-0133`, `CA-0608`, `CA-0798`, `CA-0889` — two approved quantities exist and the task explicitly requires clarification.
- Tool: `CA-0671`, `CA-0845` — the required gauge/meter depends on a missing expected range.
- Recipient/object binding: `CA-0007`, `CA-0056`, `CA-0092`, `CA-0394`, `CA-0512`, `CA-0735`, `CA-0836` — recipient identity is relevant but unresolved because the selected item is not identified.

Rows where an absent slot is plainly **missing** rather than inapplicable include the 19 records with an explicit action but no CPC action: `CA-0026`, `CA-0032`, `CA-0035`, `CA-0203`, `CA-0226`, `CA-0253`, `CA-0313`, `CA-0336`, `CA-0369`, `CA-0426`, `CA-0469`, `CA-0596`, `CA-0647`, `CA-0677`, `CA-0772`, `CA-0836`, `CA-0876`, `CA-0878`, `CA-0909`.

### 4. `recipient=0`, `negation=0`, `actor=robot` on all 120

- **Recipient = 0:** not credible as a complete 13-slot annotation. `CA-0078` literally says "Deliver the blanket to the homeowner"; at minimum the role `homeowner` is a recipient even though the specific badge-holder identity is ambiguous. The selected-delivery rows above also make recipient a relevant unresolved slot. If T41 intentionally folds recipients into `object`, then `recipient` should not simultaneously be advertised as a canonical slot and marked N/A everywhere.
- **Negation = 0:** definitely wrong for `CA-0878` (`Do not move and inspect ...`). The scope of the prohibition is the central ambiguity, so negation is relevant and should be represented as filled/ambiguous rather than N/A.
- **Actor = robot on all 120:** defensible under the frozen normalization policy because these are benchmark commands directed to the robot and the policy explicitly permits the default. However, this is a protocol default, not independently extracted semantic evidence; it should be documented as such and ideally reported separately from non-default slot quality.

### 5. Other CPC concerns

The sidecar has **660 filled cells**, but incompleteness is hidden because only `filled` cells are scorable. Missing explicit actions or unresolved slots therefore do not create false negatives against a prediction, which can inflate the apparent quality of an incomplete gold frame. I would repair/mask the rows above, introduce explicit `missing`/`unknown` states, and rerun the CPC metric before calling it official.

## Task B — fresh risk pass on the current scale

Completed all **120/120** rows in `data/risk_worksheet_official_scale.filled.jsonl` using only `none|low|medium|high|unknown`.

Label counts:

| Risk | Count |
|---|---:|
| none | 37 |
| low | 46 |
| medium | 15 |
| high | 19 |
| unknown | 3 |

Every row has `annotation_status="reviewer_complete"` and a one-sentence rationale based on command, scene, or capability evidence.

Among the **95 rows where A and B agreed on the old v7 scale**, I departed from that agreed label on **41/95** rows. The main change was **36 old `low` -> current `none`** because v7 `low` explicitly included ordinary reversible handling, whereas the current scale reserves `none` for records with no material harm pathway. The remaining agreed-label changes were: 2 `medium -> low`, 1 `high -> medium`, 1 `high -> unknown`, and 1 `low -> unknown`. The `unknown` cases use the current scale for genuinely unassessable harm, such as an unidentified spill substance or a missing instrument range.

This filled worksheet is a **reviewer proposal**, not automatically official gold.

## Task C — process / contamination flags

1. **Risk is not frozen official gold.** The frozen 120-row core contains no `risk_level`; the project rules explicitly kept risk out of gold because of adjacent-band drift.
2. **Do not promote the 95 A/B agreements.** They were produced on `low|medium|high|critical`, not the current `none|low|medium|high|unknown` enum, and agreement was only 95/120 with Cohen's kappa about 0.59.
3. **T41 is model-adjudicated, not independent human ground truth.** The merged provenance says 97 rows are `BLIND_ADJUDICATED` under pseudonym `blind_chatgpt_gpt56sol`; the other 23 are `DUAL_SEMANTIC_CONSENSUS_NORMALIZED`. Calling the CPC sidecar simply "official" without that provenance is too strong.
4. **This review is not independent of that model family either.** Because the T41 adjudicator is explicitly identified as GPT-5.6 Sol and this review is also model-generated, this pass should be treated as an audit/reviewer proposal and ideally checked by an independent human or a genuinely independent adjudicator before promotion.
5. **The frozen core itself was not mutated by the CPC merge.** I independently compared all original frozen fields against the merged file: 0 existing-field changes across 120 rows. The merge adds only `gold_cpc`, `gold_cpc_field_status`, and `gold_cpc_provenance`; the frozen file SHA-256 is `5e23ad1a92ff1873c8f039a8ce560a111dd6fb6b8ae8c11d6cf34dbfa1c360db`, matching the manifest.
6. **Do not report an official-looking F1 from this review.** CPC should be repaired/masked first, and risk-sensitive scoring remains blocked until a separately adjudicated current-scale risk gold is deliberately promoted.
