# Pilot-120: frozen evaluation and public metadata

Pilot-120 v1 is a 120-case, evaluation-only set of ambiguous commands. Its
source was capability-context repaired and its gold was pilot adjudicated by
the historical dual-annotation process. It is **not** a final-protocol human
reannotation. Do not train, tune, select a model, or rewrite historical T39/T41
evidence using these 120 records.

## Frozen identity

The internal full-text files are at
`data/annotations/pilot_120_v1/source_canonical.jsonl` and
`data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl`. They each contain
120 unique IDs in frozen order. The controlling files are
`data/annotations/pilot_120_v1/GOLD_POLICY.json`,
`data/annotations/pilot_120_v1/frozen/FROZEN_MANIFEST.json`, and
`configs/evaluation/pilot_120_v1.json`.

| File | SHA-256 verified 2026-09-27 |
| --- | --- |
| Source JSONL | `f33b1e29f1e8aa256a475f07213aa07247def47d8e2148d54a472a40b71b05c9` |
| Gold JSONL | `5e23ad1a92ff1873c8f039a8ce560a111dd6fb6b8ae8c11d6cf34dbfa1c360db` |
| Gold policy | `3c1f0a4d43c29996062a4a2ecd321e4023a38f5fad950801f96e07e23aac4a34` |
| Frozen manifest | `c61489101bfbc6cf0222538107abd272b50ce59c2f2a4292e95773f686d60230` |

The full source and gold contain derived upstream text. Their inclusion in a
historical Git commit is not evidence of public redistribution permission.
A public release should include this page, the hashes, protocol, code, and
aggregate results, while access to the text itself remains rights-controlled.
The machine-readable public metadata is in `docs/pilot120_public_manifest.json`.
Do not download a newer upstream version and claim it reproduces this frozen
set. Dataset origins and rights evidence are listed in `docs/DATASETS.md` and
`configs/licences/dataset_licence_register.json`.

## Verify an authorised local copy

On PowerShell, from the repository root:

```powershell
(Get-FileHash -Algorithm SHA256 -LiteralPath 'data/annotations/pilot_120_v1/source_canonical.jsonl').Hash.ToLower()
(Get-FileHash -Algorithm SHA256 -LiteralPath 'data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl').Hash.ToLower()
```

Both values must match the table. The evaluation policy keeps failed and
missing predictions in the denominator. The freeze hash proves file identity;
it does not establish independent scientific validity or dataset rights.

## Result families

| Family | Meaning | Status |
| --- | --- | --- |
| Historical T39/T41 | Frozen base/adapter and interpretation evidence | Preserve; do not rerun or edit |
| T0.7 matched baseline | Six-system routing table plus two-judge official intent | Completed 2026-09-27; archive verified locally |
| One-turn clarify recovery | Separate replay and answered clarification study | Keep the three failed empty-route cases in its denominator |
| ABLE IX temperatures | Five-temperature, five-seed Goal-First exploratory study | Jobs queued 2026-09-27; do not present as completed |

The completed T0.7 counts are:

| System | Exact routing /120 | Official intent /120 |
| --- | ---: | ---: |
| Raw Qwen | 96 | 106 |
| Fine-Tune | 92 | 112 |
| Goal-First | 56 | 117 |
| Degree | 57 | 117, inherited Goal-First intent |
| Timid | 29 | 117, inherited Goal-First intent |
| Context-Blind | 21 | 119 |

The T0.7 archive is
`outputs/t07_matched_baseline_completion_20260927_FINAL.zip` in the local
research checkout. SHA-256:
`34ca50e034ca37b617068bb50c734d12fa26282fb5eec563c11ead700163e491`.
It contains raw case-level material and is **not a public release asset**.
The three failed clarify-recovery cases CA-0702, CA-0733, and CA-0778 are
retained in that package. T0.3 is excluded from the official T0.7 package;
the separate matched-depth-5 control has not run.

The T41 closure ZIP remains frozen at SHA-256
`aea638cf05eab66610429e69f0d88f112eb09b4bd5582bb0d1b23d0a6dd3c21a`.
Any future T42+ work needs a new versioned protocol and fresh provenance.
