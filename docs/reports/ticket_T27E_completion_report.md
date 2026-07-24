# Ticket completion report

## Ticket

- ID: T27E
- Title: Ambiguity-Specific Structured Prediction Recovery

## Preconditions checked

- T27D was verified BLOCKED; T28 was not executed.
- Base remained `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`.
- `selected_adapter=null`, `selected_model_strategy=null`, and
  `valid_for_official_use=false` remained unchanged.
- T27D evidence verified CPC 12/12 and ambiguity 0/12 in both modes, with
  bounded/incomplete JSON and no fallback, unknown-field, enum, nested-type, or
  empty-output category.
- Ambiguity supervision was verified as 68 strong examples; prior total-task
  exposure was 36/470.
- Missing ambiguity remained null/unknown and the deterministic router and CPC
  path were not changed.
- No protected, source_holdout, T13 calibration, supervisor, future manual, or
  model-selection data was used.

## Data isolation

- Diagnostic: `data/development/t27e_diagnostic_dev_v1/manifest.json`, 16 rows.
- Sealed: `data/development/t27e_final_smoke_v1/manifest.json`, 12 rows.
- Both are `source_dev`, disjoint by source ID and group key from all prior T27
  through T27D sets and model-selection fixtures. The available fresh pool had
  no remaining eligible Clara source_dev rows after exclusions; the manifests
  record balance over the four remaining eligible datasets.
- Diagnostic manifest SHA-256: `2d4a8bfafc89fa74f0b5a4bcc9878e4bcb79cf10b333223c5b69890bad842a5f`.
- Sealed manifest SHA-256: `51919985d55b80a14c7f17d8e3813ca140e2612ef7cf4383c0a4bb7dae437267`.

## Tests written first

- `tests/test_t27e_ambiguity_recovery.py` was written before implementation.
- Initial test command: `python -m pytest tests/test_t27e_ambiguity_recovery.py -q`.
- Initial failure: active environment lacks pytest (`No module named pytest`).
- Available checks passed: compileall for `src`, `scripts`, and `tests`; custom
  contract assertions; `git diff --check`; cluster profile dry-runs; diagnostic
  operator `VERIFY_PASSED`.

## Forensic diagnosis

The verified diagnostic was job 13600, run
`t27e-ambiguity-diagnostic-20260724T082352Z-2245217`, source commit
`224521769d973ca34d3887d694c73c21a6af0bc9`, archive SHA-256
`64dadc55ae8ecc5546e31037509bae9dcc9667047dc269807662e1b4a6f255d9`, and
evidence SHA-256
`bbcbc7b39c7f2668674b496837f772ff391f14e9166035156ef69c4b1e4a7e4d`.

| Contract | Mode | Calls | Parse/schema/semantic accepted | EOS | Fallbacks |
|---|---:|---:|---:|---:|---:|
| Current schema | base | 16 | 0/16 | 16/16 | 0 |
| Current schema | adapter | 16 | 0/16 | 16/16 | 0 |
| Minimal required schema | base | 16 | 16/16 | 16/16 | 0 |
| Minimal required schema | adapter | 16 | 16/16 | 16/16 | 0 |

Current schema hash was `4702734e2ef3072d6cabbfc0d28e1b2a631e076a6cf6d7ab172adee0a09d4ad2`;
minimal schema hash was `d0d124efc89d50834bce444be8ee5b92b512721c663461d3409b745aa2be3987`.
Current prompts were 503-625 rendered tokens; minimal prompts were 325-447.
Current outputs generated 23-39 tokens and ended with EOS while incomplete at
the optional `primary_ambiguity_type` key. Minimal outputs generated 17-28
tokens and ended with complete JSON. EOS/PAD were 151645/151643. Constraint
initialisation was 64/64 and unconstrained fallback was 0/64.

Target analysis: existing ambiguity targets were 48-203 serialized token/char
units (median 97); minimal required-field targets were 48-68 (95th percentile
60). The 96-token minimal bound was frozen before sealed execution.

Classification: Path A, structural/decoder-contract repair. The diagnostic
proves that constrained generation is mechanically capable of completing the
ambiguity task when optional unsupported fields are removed. Path B was not run;
there was no evidence requiring ambiguity-specific adaptation. No CPC or router
change was made.

## Sealed result

The frozen sealed run was job 13727, run
`t27e-ambiguity-sealed-20260724T085440Z-383c450`, with source commit
`383c450f74a2ce96f3106dd85920ac10d8bc717a` and archive SHA-256
`3e5b0ba952f453941eb0309c1c9d63b5ea1201e14ee8eef005a6b2968c338a8e`.
Slurm reported completion, but the operator could not reconcile a result
directory. Runtime logs showed lm-format-enforcer 0.10.12 rejecting unchanged
nullable-enum schemas in optional intent, interpretations, and risk/capability
tasks. No sealed result artifact, task journal, assembly result, or acceptance
count was available. The one-run policy prohibits rerun.

Therefore sealed ambiguity acceptance, CPC-plus-ambiguity count, assembly count,
route-safety count, and per-record acceptance are `NOT_COMPUTED`, not zeroed or
fabricated. The ambiguity repair itself remains supported by the diagnostic;
the ticket gate is blocked by sealed runtime reconciliation and unchanged
optional-task decoder incompatibility.

## Changed files

- `cursor_plan/tickets/T27E_ambiguity_specific_recovery.md`
- `configs/model/t27e_ambiguity_recovery_v1.json`
- `configs/cluster/t12_job_profiles.json`
- `scripts/build_t27e_datasets.py`
- `scripts/t27e_ambiguity_diagnostic.py`
- `scripts/t27e_ambiguity_sealed.py`
- `src/ambiguity_manager/model/t27e_ambiguity_recovery.py`
- `src/ambiguity_manager/model/task_constrained_decoding.py`
- `src/ambiguity_manager/model/qlora_task_conditioned_smoke.py`
- `src/ambiguity_manager/model/cluster/job_operator.py`
- `tests/test_t27e_ambiguity_recovery.py`
- T27E manifests, matrices, diagnostic evidence, run manifests, and failure evidence under `data/development/t27e_*` and `configs/model/evidence/`.

Commits: `dc6775a`, `b6ba2d4`, `fda0dac`, `fc7127d`, `f200348`, `383c450`.

## Policy/config hashes

- Final T27E policy SHA-256: `b3ec15b5605abbe31672bc440be4c2870eeffa1f24b56565434a034e8d8035f7`.
- Task registry SHA-256: `0426f24c507286617aa91448857590806086348d577301a018e929321766b22e`.
- T27C constrained-decoding config SHA-256: `1918a90e56e2f72e0893f8209312035dbf4986637531da29b7bab5f0e3c6304a`.
- Final sealed task matrix SHA-256: `754cc4cc47b6353cc150c0b7b3ea9dbf6be00491236e0f4a3b5cf132423cb5ca`.
- Adapter evidence identity: source commit `6419cfc479c7cf53d347c3343b6e2a859cad946b`, SHA-256 `9a206da3ac205a725bfbcdcc8958d16ec760d63db1d31e53e019a1281a734212`; technical evidence only.

## Stage gate

**BLOCKED.** The ambiguity-specific structural diagnosis and repair are
supported, but the mandatory sealed gate is not evaluable because the single
sealed run did not produce reconciled journal/result artifacts and the unchanged
optional schemas triggered a constrained-decoder runtime error. T28 may not
begin. No adapter was selected and official use remains false.
