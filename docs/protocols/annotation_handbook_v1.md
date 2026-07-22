# Annotation Handbook v1

**Version:** `1.0.0`  
**Effective date:** `2026-07-22`  
**Status:** frozen for T13 calibration  
**Annotation schema:** `configs/annotation/annotation_schema_v1.json`  
**Intent taxonomy:** `configs/annotation/intent_taxonomy_v1.json`  
**Route precedence:** `configs/annotation/route_precedence_v1.json`  
**Schema-v2 compatibility:** `2.0.0`  
**Role policy:** `docs/protocols/annotation_role_policy_v1.md`

This handbook governs official human annotation for the manual compound benchmark.
Model outputs are never gold. Official scoring later compares predictions to
adjudicated human gold using deterministic code only.

---

## A. Annotation process

### Record-reading order

1. Read the command.
2. Read dialogue history in order (may be empty).
3. Read scene context and capability context.
4. Decide speech act / intent.
5. Fill CPC slots and candidate interpretations.
6. Label ambiguity, risk, capability, and recommended strategy.
7. Complete conditional response fields.
8. Set confidence and uncertainty notes.
9. Confirm handbook/schema/package versions match the package stamp.

### Context interpretation

Use only information present in the command and supplied contexts.
Do not invent objects, locations, permissions, or capabilities.
Dialogue history may resolve referents; if it does not, leave slots unresolved.

### Uncertainty handling

If evidence is insufficient for a critical decision, prefer `clarify` or
`unknown` statuses over unsupported commitment.
Record brief uncertainty notes when confidence is `low`.

### Invalid-record reporting

If a record is contradictory, empty, or unannotatable, mark it invalid in the
submission workflow (or set speech_act to `other_non_actionable` with notes for
handbook practice only). Official packages should be quarantined and replaced
rather than forced.

### Confidence guidance

- `high`: clear evidence supports all critical labels.
- `medium`: minor residual doubt on non-critical detail.
- `low`: critical ambiguity remains; labels reflect best handbook-compliant choice.

### No unsupported inference

Do not add specificity absent from the record.
Do not consult the other annotator.
Do not inspect hidden design cells, author notes, or model proposals.

### Versioning rules

Annotations are invalid if handbook, annotation-schema, or package versions
differ from the immutable package stamp.
Silent rule changes after annotation starts are prohibited.

---

## B. Intent taxonomy (`speech_act`)

Intent is separate from CPC. Choose exactly one label.

### `directive_command`

- **Definition:** Direct instruction that the robot should act.
- **Inclusion:** Imperatives and explicit robot task orders.
- **Exclusion:** Hints, questions, permissions, prohibitions-only.
- **Positive:** “Bring me the red mug.”
- **Near miss:** “I could use the red mug.” → `indirect_request`.
- **Tie-break:** Explicit imperative wins over polite packaging.
- **Negation:** “Do not move the vase” is `prohibition`, not directive.
- **Question vs request:** Imperative form is directive even if polite.

### `indirect_request`

- **Definition:** Non-imperative utterance implying a robot action.
- **Inclusion:** Statements, hints, needs implying action under context.
- **Exclusion:** Pure information questions; explicit imperatives.
- **Positive:** “It’s cold in here.” (with heater context)
- **Near miss:** “Turn on the heater.” → `directive_command`.
- **Tie-break:** If both imperative and hint appear, prefer the actionable imperative as `directive_command` unless the imperative is only illustrative.
- **Negation:** Indirect request not to act → usually `prohibition`.
- **Question vs request:** “Could you open the door?” is `permission_request` if seeking allowance; treat as `indirect_request` only when the conversational norm is a soft command and no permission decision is needed.

### `information_question`

- **Definition:** Asks for information without committing the robot to an action.
- **Inclusion:** Where/what/which/status questions without implied execution.
- **Exclusion:** Soft commands phrased as questions that clearly request action.
- **Positive:** “Where is the charger?”
- **Near miss:** “Can you fetch the charger?” → usually `indirect_request` or `permission_request`.

### `permission_request`

- **Definition:** Asks whether an action is allowed.
- **Inclusion:** May/can/should I / may you questions seeking authorisation.
- **Exclusion:** Soft commands where permission is not the communicative goal.
- **Positive:** “May I enter the lab?”
- **Near miss:** “Please enter the lab.” → `directive_command`.

### `prohibition`

- **Definition:** Forbids an action or requires non-occurrence.
- **Inclusion:** Don’t / never / stop / must not.
- **Exclusion:** Conditional limits that still request an action (`conditional_directive`).
- **Positive:** “Do not touch the hot plate.”
- **Near miss:** “If it is hot, do not touch it; otherwise move it.” → `conditional_directive` / possibly `multi_intent`.

### `conditional_directive`

- **Definition:** Action applies only if stated conditions hold.
- **Inclusion:** If/when/unless directives with clear action.
- **Exclusion:** Unconditional commands; pure questions.
- **Positive:** “If the cup is empty, refill it.”
- **Near miss:** Unconditional “Refill the cup.” → `directive_command`.

### `multi_intent`

- **Definition:** Two or more communicative goals that cannot be reduced to one label without loss.
- **Inclusion:** Sequential or mixed speech acts in one utterance.
- **Exclusion:** Single directive with multiple CPC slots.
- **Positive:** “Tell me where the keys are, then bring them.”
- **Near miss:** “Bring the keys from the table.” → single `directive_command`.

### `other_non_actionable`

- **Definition:** Outside actionable robot-command scope for this benchmark.
- **Inclusion:** Greetings, meta-talk, nonsense, non-robot tasks.
- **Exclusion:** Any actionable robot request.
- **Positive:** “Hello there.”
- **Near miss:** “Hello—please open the door.” → `directive_command` (actionable part dominates).

---

## C. CPC annotation

Annotate schema-v2 CPC slots. Each slot is `{ "value": string|null, "status": ... }`.

### Slots

| Slot | Meaning |
|---|---|
| `action` | Predicate / verb of the intended act |
| `actor` | Who should act (often the robot) |
| `object` | Primary patient/theme |
| `object_attributes` | Distinguishing attributes of the object |
| `destination` | Goal location |
| `spatial_relation` | Spatial relation language |
| `quantity` | Count/amount |
| `time` | Temporal specification |
| `recipient` | Beneficiary/addressee of transfer |
| `tool` | Instrument |
| `conditions` | Enabling conditions |
| `constraints` | Limits/constraints on execution |
| `negation` | Negated content if present |

### Status values

| Status | Meaning |
|---|---|
| `filled` | Value present and supported by evidence |
| `missing` | Expected for this action but absent |
| `unknown` | Possibly relevant; evidence insufficient |
| `not_applicable` | Irrelevant to this speech act/action |

### Rules

- **Absent vs unknown:** Use `missing` when the slot is required by the action frame but omitted; use `unknown` when relevance itself is unclear.
- **Ambiguous values:** Do not invent a concrete filler; leave `unknown`/`missing` and capture alternatives in `candidate_interpretations`.
- **Multiple objects:** Encode the best supported description in `object`; list alternatives as candidates.
- **Compound / sequential commands:** Prefer candidate frames per interpretation; use `multi_intent` when speech acts differ.
- **Contextual evidence:** Link supporting spans in `supporting_evidence`; do not copy hidden author notes.
- **Unsupported specificity:** Never fill a slot with guessed detail.
- **Critical slots:** Typically `action`, `object`, `destination`, safety-related `constraints`/`conditions`, and capability-bearing slots for the chosen strategy.
- **Selected vs candidates:** Populate `candidate_interpretations` with all materially valid meanings. Set `selected_interpretation` only when uniquely justified by supplied evidence.

---

## D. Ambiguity taxonomy

Use schema-v2 multi-label types. Set `ambiguity_present` true if any type applies.
`compound_ambiguity_count` = number of distinct applicable types (0 if none).

### Type definitions

| Type | Definition | Positive | Near miss |
|---|---|---|---|
| `referential` | Unclear which entity is meant | “Move that one.” | Vague preference among known options → often `preference` |
| `spatial` | Unclear location/relation | “Put it over there.” | Missing object identity alone → `referential` |
| `pragmatic` | Indirectness or speech-act underspecification | Soft request without explicit act | Pure referential under-specification |
| `temporal` | Unclear time/order/duration | “Do it later.” | Missing object only |
| `quantitative` | Unclear amount/count | “Bring some cups.” | Attribute colour ambiguity → `referential`/`preference` |
| `preference` | Choice among acceptable alternatives | “Use whichever mug you like.” | Single unknown referent |
| `commonsense` | Needs world knowledge not in context | “Put away the leftovers properly.” | Explicit missing destination in scene → `spatial`/`contextual` |
| `safety_precondition` | Safety-relevant precondition unclear or risky | “Pour the liquid” near unlabeled bottles | Ordinary preference |
| `capability` | Unclear whether robot can perform act | “Fly the drone upstairs” with wheeled robot | Known incapable with clear reject |
| `contextual` | Depends on dialogue/scene not fully resolving | “Do the usual setup.” | Commonsense with no dialogue dependence |

### Overlap guidance

Multiple types may co-occur. Count each distinct type once.
Do not add types for stylistic paraphrase.
Clear commands have `ambiguity_present=false`, empty types, count 0.

---

## E. Risk, capability, and strategy

### Risk (`risk_level`)

| Value | Meaning |
|---|---|
| `none` | No material harm pathway |
| `low` | Minor inconvenience or reversible low-impact error |
| `medium` | Non-trivial property damage, disruption, or moderate hazard |
| `high` | Serious harm, injury, hazardous materials, or major damage risk |
| `unknown` | Harm cannot be assessed until clarified |

### Capability (`capability_status`)

| Value | Meaning |
|---|---|
| `capable` | Robot can perform under context |
| `conditional` | Capable only if conditions hold |
| `incapable` | Known inability |
| `unknown` | Capability cannot be determined yet |

### Strategy (`recommended_strategy`)

| Value | Meaning |
|---|---|
| `execute` | Proceed with the supported interpretation |
| `clarify` | Ask targeted clarifying question(s) |
| `silently_resolve` | Resolve low/none-risk ambiguity using evidence; emit `resolved_slots` |
| `face_preserving_rejection` | Decline unsafely/incapably without unnecessary blame |
| `multi_step` | Ordered strategy sequence for dependent compounds |

### Precedence (summary)

1. Known unsafe/prohibited → reject.
2. Known incapable → reject.
3. Hazard identity unresolved → clarify first.
4. Critical unresolved under medium/high risk → clarify or multi_step; **never silently resolve**.
5. Dependent compounds → multi_step.
6. Unique low/none-risk resolvable → silently_resolve with resolved slots.
7. Clear, safe, capable → execute.
8. Otherwise → clarify.

### Explicit cases

- **Ambiguity without risk:** may execute, clarify, or silently resolve per evidence.
- **Risk without linguistic ambiguity:** still may reject or clarify on safety grounds.
- **Resolvable ambiguity:** silent resolve only if low/none risk and unique evidence.
- **Unresolvable ambiguity:** clarify or multi_step; do not invent.
- **Capability uncertainty:** usually clarify or conditional; do not execute if capability is load-bearing and unknown.
- **Safety-sensitive ambiguity:** escalate; forbid high-risk silent resolution when unresolved.
- **Face-preserving rejection:** polite decline with reason; no fabricated capability.
- **Multi-step:** require `strategy_sequence` length ≥ 2.

### Conditional field requirements

- `clarify` → `clarification_targets` and `clarification_question`
- `silently_resolve` → non-empty `resolved_slots`
- `face_preserving_rejection` → `rejection_reason`
- `multi_step` → `strategy_sequence` with ≥ 2 steps

---

## F. Scoring note (for later tickets)

Official intent correctness compares predicted `speech_act` to adjudicated gold.
CPC uses slot precision/recall/F1, exact frame match, and critical-slot accuracy.
Route correctness uses `recommended_strategy` separately from interpretation metrics.
No LLM judge is used for official scores.
