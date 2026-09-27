# Dataset-native diagnosis and action register — 2026-09-11

## How to use this register

Each item starts from an observed source-data fact, not a score. The proposed
reason is a hypothesis until a frozen output analysis tests it. Actions marked
**now** are measurement repairs that do not change an in-flight model prompt,
input, threshold, or source label. Actions marked **future** require a new,
versioned experiment.

## Confirmed source-data facts

| Dataset | Confirmed fact | Why it changes interpretation |
|---|---|---|
| VAGUE | 1,677 perfectly paired command-only/caption records; no repeated full effective inputs; one repeated command has two different targets and two different captions. Literal gold-slot availability is subject: command 1,622/caption 742, action: command 7/caption 122, object: command 48/caption 1,402. | The caption comparison is a credible within-record context contrast, but any caption gain may be dominated by object grounding: 83.6% of target object strings occur literally in captions. Command-only is intentionally underdetermined for at least one observed case. |
| AmbiK | 1,000 unique effective inputs; every record has exactly one type: 425 commonsense, 420 preference, 155 safety-precondition. | The present packet evaluates a three-class source-mapped type decision, not multi-type ambiguity recovery. Raw accuracy can hide failure on the 15.5% safety class. |
| CLARA | 5,222 paired full/blind source records; all full rows have both scene and capability text; blind rows have neither. 3,154 rows belong to 670 repeated exact effective-input groups; 9 repeated groups have conflicting source targets. | The ablation changes two information sources at once. Row-level estimates are correlated, and exact-input/source-target conflicts cap deterministic recoverability for affected rows. |
| CLARA | Labels are coupled: `True → clarify` occurs 1,560 times; `unknown → no strategy` occurs 1,913 times; the remaining 1,749 records are `False/capable/execute`. | A high three-field exact score can partly reflect recovering a shared latent source template. Report each component and the joint score, never call them independent corroboration. |
| Indirect Requests | 906 source records span train=246, validation=272, test=388. Every ambiguous case (162) has non-empty missing slots; every non-ambiguous case (744) has none. 906 rows collapse to 452 exact effective inputs, with no target conflicts. | This is a highly coupled binary source mapping with repeated scenarios. The trivial `False / [] / []` joint prediction scores 744/906 (82.1%), so overall accuracy alone is not informative. |

## Hypotheses, tests, and actions

| Priority | Hypothesis and grounded reason | Discriminating analysis after output freeze | Action if supported |
|---|---|---|---|
| P0 | **CLARA full-context lift comes mainly from the capability line, not scene grounding.** The packet removes scene and capability together, while source labels directly encode capability/routing. | Stratify paired full-minus-blind change by robot type, label class, and command template. Compare cases where capability status changes the correct strategy with cases where ambiguity alone changes it. | **Future:** 2×2 factorial: command only, scene only, capability only, both. Report main effects and interaction; do not infer them from the current two-arm study. |
| P0 | **CLARA headline accuracy may be inflated by repeated exact inputs.** 60.4% of rows are in repeated full-input groups. | Report declared row-level score plus a unique-input sensitivity restricted to the 2,729? exact-input groups with internally consistent targets; list the 9 conflicting groups separately. | **Now:** add duplicate-aware sensitivity and a fixed source-inconsistency ledger. **Future:** de-duplicate before a confirmatory study or sample one fixed representative per group. |
| P0 | **Indirect Requests can look strong through majority-class and label coupling rather than pragmatic inference.** 744/906 are non-ambiguous and missing-slot presence is perfectly tied to ambiguity; the modal joint target is itself 744/906. | Per-class recall, balanced accuracy, positive-class precision/recall, and unique-input sensitivity; inspect errors only after the result hash is frozen. | **Now:** make positive-class/macro diagnostics mandatory and compare against the 82.1% modal-joint baseline. **Future:** add paraphrased, counterfactual pairs where surface form is held but missing information changes. |
| P1 | **VAGUE caption gains may be lexical object grounding rather than resolution of a pragmatic ambiguity.** Target objects occur literally in 1,402/1,677 captions but only 48 commands; action words are rare in both (122 and 7). | Break paired change into subject/action/object and compare caption gain when the target object is literally present versus absent; blind-review a fixed sample of caption-only wins. | **Now:** add slot-level and lexical-availability diagnostic. **Future:** contrast natural caption, minimally edited counterfactual caption, and irrelevant caption under a pre-registered protocol. |
| P1 | **VAGUE command-only failures can be irreducible rather than model failures.** One identical command has different correct targets under different captions (door versus doorway). | Identify command collisions and report them separately; do not count contradictory command-only targets as ordinary semantic failures. | **Now:** retain collision ledger. **Future:** create a controlled ambiguity subset with human validation of what is recoverable without context. |
| P1 | **AmbiK performance may conceal safety-precondition weakness.** Safety has only 155 examples versus roughly 420 in each other class. | Per-class recall/precision, macro recall, confusion matrix, and Wilson intervals by class. | **Now:** make macro and per-type results required alongside exact accuracy. **Future:** stratified sampling or a larger independently labeled safety set; no threshold tuning from this run. |
| P1 | **AmbiK label names are not being trivially exposed.** The literal-label screen found 0/1,000 appearances of the expected type names in command/context. | This is already a negative screen; inspect a fixed error sample and source mapping provenance after scoring. | **Future:** human audit a preregistered sample of mapped types before stronger claims. |
| P2 | **A Gemma/GLM difference could be runtime/schema handling rather than reasoning.** Early malformed JSON and an unavailable-GPU node have already occurred. | Compare schema-validity, retry count, elapsed generation, and score only for coverage-complete, same-contract outputs on the approved runtime. | **Now:** transport manifest and invalid-row ledger are required. **Future:** schema-constrained decoding at first generation and node preflight before submission. |
| P0 | **T39 over-asking is not a missing-thought problem.** All 120 full-manager records have a closed `<think>` block; 118/120 of those traces are schema-filling; `intent_summary` is null on 120/120. | Already tested on frozen `raw_output` via `outputs/t39_reasoning_ledger_20260911.jsonl`. 57/75 gold-execute-to-clarify asks are for scene-licensed slots. | **Now:** query the ledger by cluster. **Future:** persist filled CPC/`intent_summary` on new runs; prompt for “what job, using which scene facts” before ambiguity labels. |

## Concrete measurement changes approved before results

These changes are additive diagnostics. They do not alter prompts, data,
predictions, source labels, or the declared primary exact-match score:

1. Add AmbiK per-class metrics, macro recall, and a confusion matrix.
2. Add CLARA/Indirect per-field scores, class-sensitive diagnostics, and the
   paired full-versus-blind transition table for CLARA.
3. Add an exact-effective-input duplicate/source-conflict ledger and a
   unique-input sensitivity analysis. The original row-level result remains
   visible; neither result is silently substituted for the other.
4. Add VAGUE slot-level paired transitions and target-token availability as a
   mechanism diagnostic, clearly labelled non-causal.
5. Add declared modal-baseline comparisons: AmbiK 42.5% (`commonsense`),
   CLARA 36.6% (`False/unknown/no strategy`), Indirect Requests 82.1%
   (`False/[]/[]`), and VAGUE 1.2% (most frequent exact triplet, 20/1,677).

The pre-results ledgers are frozen at:

- `outputs/clara_effective_input_ledger_20260911.jsonl` — 2,738 exact-input
  groups, nine source-inconsistent groups; SHA-256
  `cc1800224e9d2c9b580868174efe6d9e8833208a6df1a421b058aa1876d27de9`.
- `outputs/indirect_effective_input_ledger_20260911.jsonl` — 452 exact-input
  groups, no source-inconsistent groups; SHA-256
  `1633b4b2d6d200b3f42abe69ce957740fda0e8d53df5b49e97f4dcd54ed98829`.

## Source facts sharpened on 2026-09-11

These remain source-data facts, not model scores:

- VAGUE: all three gold slots occur literally in the command in 1/1677 records. Caption object presence is 1402/1677 exact. 273 records name the object in neither source.
- CLARA: the 5,222 labels occupy only three joint states. Strategy determines ambiguity and capability (`I(X; strategy) = H(X)` for both). Nine exact-input groups disagree with themselves (e.g. “Cook breakfast” labeled both execute and clarify).
- Indirect Requests: 906/906 scene strings are “User wants to…” task templates. Ambiguity and missing-slot presence remain perfectly coupled. Majority class is 744/906.
- Frozen T39 full manager: 0 predicted `execute` actions; 75/76 gold-execute cases are sent to `clarify`. The 83 SGC-correct/route-wrong cells are over-clarification, not proven task completion.
- AmbiK safety-word cues fire on 575 rows but recover only 94 safety golds (near base rate). There is no cheap lexical type shortcut.

Mechanism report: `docs/reports/MECHANISM_DEEP_DIVE_20260911.md`.
Run-reasoning ledger: `docs/reports/T39_REASONING_LEDGER_20260911.md` (thinking was in frozen `raw_output`; 118/120 traces are schema-filling, not action-planning).

## Interpretation discipline

No hypothesis becomes a finding merely because its pattern is plausible. Once a
full output is complete, hash it first; run the locked diagnostics; then report
which hypotheses were supported, contradicted, or unresolved. A future
intervention is justified only by the matching evidence in this register—not by
a post-hoc preference for a better score.
