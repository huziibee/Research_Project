# T28 hash-gate re-verification — 11 September 2026

## Result

**HASH_GATE_NOW_PASSES** on the current cluster frozen-input tree.

This does **not** flip `valid_for_official_use` to true. It only closes the
July R4 remote byte-mismatch blocker for the frozen archive that currently
lives on the cluster.

## Environment checked

- Host: `wits-mscluster`
- Tree: `/home-mscluster/mbangie/t28_frozen_inputs/dbba6c1bdbb796b133abc63436b4a5ca4f8e08c89e4eca1be34d8000f49bae5b/inputs`

## Authoritative SHA-256 vs recomputed

| Artifact | Expected | Observed |
|---|---|---|
| `weak_pool_canonical.jsonl` | `1e51cac046e014a6b890b10a155d22e32e01aa276d4507a10ad4f86abcf9942a` | match |
| `t28_permitted_train_dev.jsonl` | `34b551c37c8f97c24c1263a2cc12a9497e65f754924f1404c47055999f04ea22` | match |
| `source_train_task_manifest.jsonl` | `eb73488a19eb98770ea8ac18986c91d02cd8ca418608340da65394ac66582407` | match |
| `source_dev_task_manifest.jsonl` | `6b2b3b3ac1f3682636e1a5bd4ac0bd635660827febfc4c4230cdd5a537a4e2a4` | match |

## Relation to jobs 22708 / 22710 / 22715 and R5

Those July R4 attempts failed before model load (`canonical_hash_mismatch` /
run-identity). Root cause was later diagnosed as text-mode CRLF transfer of the
JSONL corpus. **T28-R5 already recovered the hash gate** (local + remote
`VERIFY_PASSED` under `outputs/t28_r5/evidence/`). This 2026-09-11 check only
reconfirms the live frozen tree still matches; it is not a new recovery.

## What this does **not** claim

- No new training was started.
- No adapter was promoted.
- Dataset licence register entries remain unresolved for published
  training/redistribution/adapter-release rights.
- Early Pilot package
  `.../early_pilot_package_excluding_clara1170_v1` stays
  `valid_for_official_use=false` /
  `selection_status=provisional_for_pilot_early_evaluation_only`.

## Next honest steps toward official

1. Keep using the early Pilot adapter for non-official Pilot-120 / goal-first
   evidence (current lane).
2. For official T28: either (a) send the prepared author-permission packets and
   record replies, or (b) keep the claim as internal-academic-only under the
   existing T28-R3 decision and never claim open-licence clearance.
3. Only after a frozen selection policy passes against a clean-load package may
   `selected_adapter` and `valid_for_official_use` flip.
