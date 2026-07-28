# T28-R2 — Resolve Dataset Licence and Immutable-Provenance Gate

## Result

**WAITING_FOR_PERMISSION.** Technical evidence collection, immutable local
artifact pinning, rights modelling, impact analysis, governance tests, and
author/institutional packets are complete. All five primary-view sources remain
unresolved for T28 training/development evaluation, so the training gate stays
closed. ClariQ is also unresolved in the authoritative register and remains
auxiliary-only.

## Repository and R1 preservation

- Original HEAD: `72025f8de977f68f7a20a6db15c130d2cc173c95`.
- T28-R1 recovery code/report commit: `b61dbf5`.
- T28-R1 recovered artifact commit: `38f551d`.
- T28-R1 technical result remains **BLOCKED** on licence/provenance; its
  technical substage passing does not change that result.
- T28-R2 final HEAD: the commit containing this report and handover (recorded
  by Git at completion).
- Unrelated T27E/T27F, annotation, archive, and raw-tree changes were preserved
  and were not bulk-committed.

The mandated R1 rerun passed before licence work: focused R1 tests 8/8; T15 plus
T28 contract tests 32/32; deterministic join/canary returned train 11,294,
dev 2,396, 13,058 valid targets, protected-loaded 0, canonical SHA-256
`1e51cac046e014a6b890b10a155d22e32e01aa276d4507a10ad4f86abcf9942a`, and
permitted-view SHA-256
`34b551c37c8f97c24c1263a2cc12a9497e65f754924f1404c47055999f04ea22`.

## Source decisions and primary evidence

| Source | Decision | Immutable local identity | Evidence finding |
| --- | --- | --- | --- |
| AmbiK | unresolved | repo commit `9d4f60d4224b4183cd35d11233d8114aeaefc2f6`; CSV hash in register | official repository/paper establish provenance, not exact-artifact reuse permission |
| IndirectRequests | unresolved | HF revision `5b9d22a`; local Arrow hashes in register | official card exposes conflicting Apache-2.0/MIT metadata; SGD dependency is CC BY-SA 4.0 and compatibility is unresolved |
| CoDraw-iCR v2 | unresolved | local v2 TSV hash in register; upstream release gap recorded | local README states CC BY-NC 4.0 but referenced licence file is absent; original CoDraw dependency unresolved |
| VAGUE | unresolved | local Parquet hash in register; upstream release gap recorded | official project/paper establish provenance, not sufficient exact-artifact terms |
| CLARA | unresolved | repo commit `608bfe85b749610385d75304c7265e8204b7a52e`; JSON hash in register | official project/repository identify `agument.json`, without an explicit dataset grant |
| ClariQ | unresolved, auxiliary | repo commit `46885a544581a0af8aff0681d29e4971807e2912`; train.tsv hash in register | official README identifies Qulac/TREC/ClueWeb-derived content without compatible exact-dataset terms |

Official references used were the [AmbiK repository](https://github.com/cog-model/AmbiK-dataset), [IndirectRequests dataset card](https://huggingface.co/datasets/msamogh/indirect-requests), [official SGD repository](https://github.com/google-research-datasets/dstc8-schema-guided-dialogue), [CoDraw repository](https://github.com/facebookresearch/CoDraw), [VAGUE project repository](https://github.com/Hazel-Heejeong-Nam/VAGUE), [CLARA project page](https://clararobot.github.io/), [CLARA dataset repository](https://github.com/jeongeun980906/CLARA-Dataset), and [ClariQ repository](https://github.com/aliannejadi/ClariQ). Papers support identity/provenance only where terms are absent.

## Dependencies

IndirectRequests → Schema-Guided Dialogue: inherited dialogue material and CC
BY-SA 4.0 terms require compatibility confirmation. CoDraw-iCR v2 → original
CoDraw: exact inherited material and terms are not pinned. ClariQ → Qulac,
TREC, and ClueWeb-derived material: dependency rights and redistribution
constraints remain unresolved. No top-level repository licence was treated as
overriding a dependency.

## Rights and packets

The complete 12-action machine-readable matrix is
`docs/licences/T28_dataset_rights_matrix.json`, with its human-readable form in
`docs/licences/T28_dataset_rights_matrix.md`. No raw records are cleared for
redistribution and adapter-weight release is unresolved for every source.

Evidence records with hashes are in `docs/licences/evidence/`. Six ready-to-send
packets and one consolidated action sheet are in
`docs/licences/author_permission_requests/`. No message was sent automatically.
The institutional packet is `docs/licences/T28_institutional_review_packet.md`;
it has no approver, authority, date, scope, conditions, or evidence document
yet, so no institutional approval is claimed.

## Impact analysis

`docs/licences/T28_licence_impact_analysis.md` and `.json` contain all required
non-mutating scenarios. Current primary sources: train 11,294, dev 2,396,
13,058 targets. Removing AmbiK: 10,594/2,246/12,208; IndirectRequests:
10,660/2,260/12,920; CoDraw-iCR v2: 6,371/1,339/7,078; VAGUE:
10,121/2,143/11,632; CLARA: 7,430/1,596/8,394. Explicitly licensed only,
verified-for-training only, and all-unresolved-removed scenarios have zero
records because no primary source is currently verified. No reduced corpus was
created.

## Tests and commands

Initial T28-R2 governance tests failed on the old register (missing fields,
rights matrix, evidence-hash and dependency gates). Final commands passed:

```text
PYTHONPATH=src python -m unittest tests.test_t28_r2_governance tests.test_governance_dataset_licence tests.test_t28_r1_source_join tests.test_t15_source_splits tests.test_t28_contract -v
PYTHONPATH=src python scripts/t28_r2_impact.py
PYTHONPATH=src python scripts/validate_t28_r2.py
PYTHONPATH=src python scripts/validate_governance.py
```

Final focused suite: 54 tests passed. The T28 gate validator reports
`WAITING_FOR_PERMISSION` and `training_allowed: false`. Hash and evidence
checks passed; T15 split membership, labels, groups, eligibility, and hashes
remain unchanged.

## Stop conditions

No base model was loaded. No T28 training, checkpoint selection, or adapter
release occurred. No protected data was accessed. T29 did not begin. T28 may
resume only after all primary sources have explicit compatible permission and
immutable provenance, the institutional/author actions are recorded, the
T28-R1 hash/canary/governance/protected-data recheck passes, and separate human
approval is granted.
