# T43 CPU-only factorial context-manifest protocol

## Status and boundary

This is a preparatory protocol for T43, not a result or an inference job. It
creates a hash-bound `2^3` input manifest from the immutable Pilot-120 v1
source. It does not alter the source or gold, load a model, render a manager
prompt, tokenize an input, submit a cluster job, or support a scientific claim.

T43 cannot start inference until T39's final reproducibility audit and T40's
availability audit are terminal, and an execution binding records the unchanged
T39 manager implementation, model revision, selected adapter identity,
generation/decode policy, prompt-renderer bytes, tokenizer snapshot bytes and
evaluator bytes. A prepared manifest is not that binding.

## The eight conditions

The condition matrix has one availability bit for each source:

- `S`: `scene_context`
- `D`: `dialogue_history`
- `C`: `capability_context`

`S1_D1_C1` is full context and `S0_D0_C0` is all-context removal. The other
six rows are the one- and two-source removals. Every condition retains the
same `record_id` and `command`; an unavailable text context becomes `null` and
an unavailable dialogue history becomes `[]`.

The frozen source has 120 non-empty scene contexts, 120 non-empty capability
contexts and 44 naturally non-empty dialogue histories. The matrix therefore
contains 960 condition inputs. The dialogue main effect uses only the 44
naturally dialogue-present records. Empty histories are recorded in the matrix
for completeness but are explicitly ineligible for a dialogue-effect estimate:
an empty source is not evidence of a removal intervention.

## Byte and runtime attestations

For each condition, the manifest stores:

1. The exact canonical input payload and its SHA-256.
2. Base64-encoded UTF-8 JSON tokens and SHA-256 values for every retained
   source field. These tokens are extracted from the frozen JSONL line, so
   escaping and textual representation are checked rather than only the parsed
   value.
3. Explicit `NOT_COMPUTED` placeholders for prompt input, rendered prompt,
   token IDs and token count. They are intentionally not fabricated during
   CPU-only preparation.

At runtime, one JSONL attestation per record-condition must contain the exact
canonical input bytes plus prompt, rendered-input and token-ID bytes (all
base64-encoded) with SHA-256 values and token count. The verifier rejects a
missing, duplicate, altered or self-inconsistent attestation. It proves the
runtime used the manifest input bytes; the separate execution binding proves
which frozen renderer/tokenizer produced the attested bytes.

## Preregistered analysis

For each source, compare available versus removed while holding the other two
flags fixed. A record has four matched factorial contrasts; they are averaged
within that record before analysis, so the unit remains the record rather than
four pseudo-replicates. The confirmatory outcomes are terminal-route
correctness and the existing asymmetric terminal cost. The six resulting tests
(three sources by two outcomes) use a two-sided, record-level paired bootstrap
(10,000 replicates; seed `20260901`; 95% interval) and Holm correction at
alpha 0.05.

A source needs at least 15 eligible records and at least 10 non-zero
within-record effects for inferential testing. A thinner view is count-only.
All pairwise condition contrasts and source interactions are descriptive unless
a later frozen revision pre-registers a separate multiplicity family.

Even if every gate passes, T43 only estimates source availability effects on
the fixed Pilot-120 input/system/prompt-token contract. It does not establish
generalisation, real-world safety, single-ambiguity performance, interpretive
quality or a reason to tune a model or manager.

## CPU commands

Create the prospective manifest and then independently verify its source-byte
relationship:

```powershell
python scripts/pilot120_t43_factorial_context.py build --output outputs/t43_cpu_preparation/t43_factorial_manifest.json
python scripts/pilot120_t43_factorial_context.py verify --manifest outputs/t43_cpu_preparation/t43_factorial_manifest.json --output outputs/t43_cpu_preparation/t43_static_verification.json
```

Both commands are CPU-only. They must not be treated as permission to submit
the eventual inference study.
