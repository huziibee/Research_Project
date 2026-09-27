# Mechanism deep dive — 2026-09-11

This analysis uses frozen Pilot-120 T39 semantic-intent rows and the prepared
dataset-native source packets. It does not score queued dataset-native model
outputs and does not modify T39/T41.

Reproducible artifact: `outputs/mechanism_deep_dive_20260911.json`
SHA-256: `0c20c08496564d533c6dbeb075ce94740e47fb74f9be73f15b8a2e244ad663e0`

## What “wrong turn, right result” can currently mean

It can mean one of two different things:

1. **Correct observable goal + wrong route.** The system’s visible interpretation
   of the user goal passed SGC, but the terminal strategy did not match gold.
2. **Environment task success despite an upstream mistake.** Frozen T39 has no
   execution log. This is `NOT_COMPUTED`. The new future contract
   `FutureTaskOutcomeV2` refuses to mint task success from route correctness.

For the full manager, (1) is common and (2) is unavailable.

| Cell | Full manager | What it actually is |
|---|---:|---|
| SGC correct, route wrong | 83/120 | Visible goal recovered; interaction decision still fails |
| SGC wrong, route correct | 3/120 | Gold was already `clarify` or `reject`; the manager never executed |
| SGC and speech-act correct, route wrong | 50/120 | Layer 3: downstream of both goal and communicative force |
| Predicted `execute` | 0/120 | The full manager never takes the execute route |

Context-blind and full manager both send **75/76 gold-execute** cases to
`clarify` (98.7%). The degree router is the only frozen system that actually
executes (29/76). The interesting dissociation is therefore not “the robot did
the job anyway.” It is: **the manager often understands the requested action
and still refuses to act.**

Paired full-versus-blind:

- SGC: +15.0 pp
- FIC: +0.83 pp

Context helps the visible goal trace. It barely helps the conjunction of goal
plus speech-act plus route.

## Frozen T39 record mechanisms

### Indirect requests (n=29)

| System | SGC | SAA | Route | FIC |
|---|---:|---:|---:|---:|
| Context-blind | 19 | 0 | 5 | 0 |
| Degree router | 29 | 1 | 14 | 1 |
| Full manager | 29 | 1 | 5 | 1 |

Indirect commands are almost always scored as some other speech act
(`directive_command`, `conditional_directive`, `information_question`). The
goal paraphrase can still be right. Example:

- CA-0012 command: “Would it help to move the marked linen cart…?”
- Gold speech act: `indirect_request`; predicted: `directive_command`
- Gold route: `execute`; predicted: `clarify`
- Goal reference: move the PENDING-tagged linen cart at the next idle slot

That is a Layer 2 failure: goal visible, force and route wrong.

### Layer 3 (goal and speech-act right, route still wrong)

These are template-like execute cases that still get clarified:

- CA-0026 “Move the selected return item to its assigned destination shortly.”
- CA-0032 / CA-0035 same template with water jug / prescription tote

The manager names the move and still asks. Fuzzy temporal (`shortly`) and
object marking (`selected`, `MOVE` tag) are present in gold; frozen T39 does
not emit CPC/resolution evidence, so this cannot be blamed on a router in
isolation. Layer 4 remains `NOT_COMPUTED`.

### Accidental route correctness is not lucky execution

The three full-manager SGC-wrong/route-correct rows are CA-0083 (gold reject),
CA-0133 (gold clarify), and CA-0552 (gold clarify). Because the full manager
never predicts `execute`, a lucky correct route can only happen on
clarify/reject gold.

## Dataset-native source mechanisms

These studies are exploratory weak-source-label diagnostics. They are not T42
and not official Pilot-120 scores.

### VAGUE: figurative command → concrete triplet

The scientific task is not generic intent. Each item has an **indirect**
command, a **direct** rewrite, a caption, and a gold `(subject, action, object)`.

Example: “why not let everyone have a turn at being the all-seeing oracle?”
maps to `(person1, hand over, binocular)` because the caption shows binoculars.
The surface trap is “act like a fortune teller.”

Lexical recoverability:

| Slot | Literal in command | Literal in caption |
|---|---:|---:|
| subject | 1622/1677 | 742/1677 |
| action | 7/1677 | 122/1677 |
| object | 52/1677 | 1402/1677 |
| all three | **1/1677 (0.06%)** | 51/1677 (3.0%) |

Command-only exact-triplet copy is almost impossible. Any command-only score
above ~0% is pragmatic inference, not lexical overlap. Caption gains may still
be object grounding: 83.6% of gold objects occur literally in the caption.
273 records name the object in neither command nor caption; those are the
hard set.

One command collision is irreducible without context: the same utterance
“are we trying to air condition the entire neighborhood?” maps to `door` in
one clip and `doorway` in another.

Modal exact triplet `(person1, adjust, lamp)` is 20/1677 = 1.19%. A model that
always emits that triplet would look empty, not strong.

### AmbiK: three-class type recovery

Counts: commonsense 425, preference 420, safety 155. Modal baseline 42.5%.
A system that never predicted safety and got every other class right would
still score 84.5% accuracy. Macro recall and safety recall are mandatory.

Literal type-name leakage is 0/1000. Cheap safety-word cues (`hot`, `knife`,
`allerg`, …) fire on 575 rows but only 94 of those are safety gold (16.4%,
near the 15.5% base rate). There is no usable lexical shortcut here.

### CLARA: three templates, not three independent skills

All 5,222 labels collapse to three joint states:

| ambiguity_present | capability_status | recommended_strategy | n | share |
|---|---|---|---:|---:|
| false | unknown | null | 1913 | 36.6% |
| false | capable | execute | 1749 | 33.5% |
| true | capable | clarify | 1560 | 29.9% |

Mutual information: `I(capability; strategy) = H(capability)` and
`I(ambiguity; strategy) = H(ambiguity)`. Strategy determines the other two
fields. A high three-field exact score is a 3-class template recovery, not
corroboration from independent labels.

The current ablation removes scene and capability together. Nine exact-input
groups have incompatible source targets for the same command+context, e.g.
“Cook breakfast” and “clean the room” labeled both `clarify` and `execute`.
Row-weighted accuracy remains visible; unique-input sensitivity must be
reported beside it.

### Indirect Requests: 82.1% is the empty predictor

744/906 are non-ambiguous with empty missing slots. Ambiguity and missing-slot
presence are perfectly coupled. 906 rows collapse to 452 unique effective
inputs, all internally consistent.

Every `scene_context` is a task template beginning “User wants to…”, not visual
scene evidence. Example: biryani/samosa is labeled missing “Cuisine of food
served in the restaurant” even though the cuisine is in the command. The
source mapping is a slot schema, not a human gold of what a hearer lacks.

Headline accuracy without positive-class recall, balanced accuracy, and the
82.1% modal baseline is not interpretable.

## Actionable next experiments (new versioned studies only)

Do not retune in-flight prompts or labels from these facts.

1. **VAGUE object-cue control.** Split caption-present vs caption-absent object
   strings; add a pre-registered counterfactual-caption arm (relevant / irrelevant /
   object-name-ablated). Human-spot the 273 neither-source object cases.
2. **CLARA 2×2 factorial.** Command only, scene only, capability only, both.
   Score the 3-class template and each field, plus unique-input sensitivity and
   the 9-conflict ledger.
3. **Indirect positive-class protocol.** Primary metrics: ambiguous-class recall,
   missing-slot exact set, unique-input n=452, comparison vs 82.1% majority.
   Inspect whether cuisine/location already present in the command is still marked
   missing.
4. **T39 follow-on policy, not a T39 rerun.** Future manager must emit
   `intent_summary` and an independent `task_success` only when an environment
   ran. Add an execute-calibration study: same goal traces, explicit permission
   to execute when gold is execute and residual uncertainty is below a
   pre-registered bound. Never back-fit that bound on frozen T39.
5. **T42 strata from these mechanisms.** Preregister: indirect polite requests,
   fuzzy-temporal execute templates, VAGUE object-absent captions, AmbiK safety,
   CLARA same-input label conflicts. Do not convert current native scores into
   T42 evidence.

## Measurement code now in the repo

- Modal baselines, Wilson intervals, and unique-input sensitivity on the
  VAGUE/AmbiK/CLARA/Indirect scorers.
- Indirect confusion matrix now compares gold vs predicted labels, not vs
  field-correctness flags.
- `FutureTaskOutcomeV2` rejects `from_route_correctness`.
- Frozen T39 and T41 are untouched.
- Thinking traces from frozen `raw_output` are now in
  `outputs/t39_reasoning_ledger_20260911.jsonl`. Write-up:
  `docs/reports/T39_REASONING_LEDGER_20260911.md`.
