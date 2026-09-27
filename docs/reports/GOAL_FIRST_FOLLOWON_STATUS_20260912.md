# Goal-first follow-on status — 12 September 2026

Live snapshot after GLM CLARA flush and 53188 exit. Times below are **cluster
local** (`mscluster`, ~UTC) unless marked otherwise.

## Jobs

| Job | Role | State | Notes |
|---:|---|---|---|
| **53188** | `gf-followon` | **FAILED 2:0** | 15h36m on `mscluster110`; expected `REQUIRED_FAILED` after three native hard-fails |
| **53191** | `gf-followon-score` | cancelled | `afterok` never satisfied; scored locally instead |
| **53192** | `clara-native` backup | **CANCELLED+** 3:22 | `afterany` started a few minutes; follow-on CLARA already 10444/10444 both systems |
| **53420** | `gf-native-retry` | **FAILED 2:0** | started 09:56:42 on `mscluster112` (53236 ended early); 18m30s. Gemma Indirect + GLM Indirect **906/906**; GLM AmbiK failed again at `ambik:211` |
| **54066** | `gf-native-retry` | **FAILED 2:0** | 75s; skip-if-complete held. Raw payload was `{"ambiguity_types": []}` at `ambik:211` |
| **54070** | `gf-native-retry` | **COMPLETED 0:0** | 3m on 112; GLM AmbiK **1000/1000** after empty-list abstention accepted |
| 53189 | R1 GPU repair | cancelled | CPU salvage already `VERIFY_PASSED` |
| 53190 | R1 audit | COMPLETED | earlier |

Output root: `/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b`  
Code: `/home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911`  
Native pack: `/home-mscluster/mbangie/t12-hpc/code/followon-native-20260911`  
R1: `/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911/manager`

## Required task list (`tasks.json`, 10 tasks)

| Task | Required | Status (this snapshot) |
|---|---|---|
| `v2_R2` | yes | **done** (`exit 0`, then CPU salvage → `VERIFY_PASSED`) |
| `v2_R3` | yes | **done** (`exit 0` @ 120/120, then CPU salvage → `VERIFY_PASSED`) |
| `gemma4_vague` | yes | **done** 3354/3354 (`exit 0`, 735s) |
| `gemma4_ambik` | yes | **done** 1000/1000 (`exit 0`, 176s) |
| `gemma4_indirect` | yes | **done** 906/906 on **53420** (`exit 0`, 533s) |
| `gemma4_clara` | **yes** | **done** 10444/10444 (`exit 0`, 2020s) |
| `glm47_vague` | yes | **done** 3354/3354 (`exit 0`, 932s) |
| `glm47_ambik` | yes | **done** 1000/1000 on **54070** (`exit 0`, 180s); 37 empty abstentions including `ambik:211` |
| `glm47_indirect` | yes | **done** 906/906 on **53420** (`exit 0`, 286s) |
| `glm47_clara` | **yes** | **done** 10444/10444 (flush at end; ~14586 HTTP posts including retries) |

## Replica health

- **R2 / R3:** unchanged. `VERIFY_PASSED` after CPU salvage. Accuracies
  0.450 / 0.492 / 0.217 / 0.175. Routes R1=R2=R3 **120/120**. Salvage claim
  boundary unchanged. Do not redo salvage.
- **CLARA:** both systems written and verified locally (5222 IDs × 2 conditions).
- **53188 exit 2** was required-task failure, not a CLARA miss.

## Native schema diagnosis (retry 53420)

- **Gemma Indirect:** first-row schema was valid; runner then `KeyError: condition`
  because `indirect.jsonl` has no `condition`. Default `source_native_context` is
  on the cluster runner.
- **GLM AmbiK `ambik:211`:** packet line 211; gold `["commonsense"]`; Gemma
  `["preference"]`. 210 prior rows parsed. **54066** logged the raw
  completion: `{"ambiguity_types": []}`. Not an alias miss — GLM abstained.
  Runner now records `[]` (and unknown-only lists) as abstention; scorer
  treats `[]` as incorrect. **No gold fill.** 54070 wrote 1000 rows (37
  empties, including 211).
- **GLM Indirect `train:234`:** gold is `ambiguity_present=false`,
  `ambiguity_types=[]`. Old validator required exactly `["pragmatic"]`.
  Validator now accepts `[]` or `["pragmatic"]`, drops blank slots, defaults
  `condition`. CLARA validation left strict.

Successful files are not overwritten (`output_exists` + skip-if-complete).

## Local scores (majority / unique-input; not pooled with Pilot-120)

Machine dump: `outputs/followon_native_scores_20260912/followon_native_score_summary.json`

| System / task | n | Exact / joint | Majority | Note |
|---|---:|---:|---:|---|
| Gemma VAGUE command-only | 1677 | 1 (0.0006) | 0.012 | 1179 distinct gold triplets |
| Gemma VAGUE + caption | 1677 | 13 (0.0078) | 0.012 | caption helps vs command-only (p=0.0018) |
| GLM VAGUE command-only | 1677 | 2 (0.0012) | 0.012 | |
| GLM VAGUE + caption | 1677 | 10 (0.0060) | 0.012 | caption helps (p=0.039) |
| Gemma AmbiK | 1000 | 321 (0.321) | 0.425 | **below** majority `["commonsense"]` |
| GLM AmbiK | 1000 | 231 (0.231) | 0.425 | 37 empty abstentions; safety-heavy (772) |
| Gemma Indirect joint | 906 | 0 (0.000) | 0.821 | always `ambiguity_present=true`; unique-input 0/452 |
| GLM Indirect joint | 906 | 1 (0.001) | 0.821 | same always-on pattern; unique-input 0/452 |
| Gemma CLARA joint | 10444 | 1231 (0.118) | 0.366 | unique-input full 0.146 / blind 0.054 |
| GLM CLARA joint | 10444 | 3383 (0.324) | 0.366 | unique-input full 0.367 / blind 0.353 |

CLARA field rates (row-weighted): Gemma strategy 0.362 / capability 0.144;
GLM capability 0.662 / strategy 0.359. Exploratory weak labels only. Do not
fold into Pilot-120 54/120.

All required natives exist. Do not pool these scores with Pilot-120 54/120.

## Queue diagnosis (natives complete 10:44 cluster)

Not a QOS lock. Account `general` has only `normal` (no `mss_biggpu`). Every
`biggpu` job shows Priority=1. Reason=`Priority` means FIFO behind earlier
eligible jobs, not a stuck submit.

Usable nodes are **110–112** (106–109 excluded; 108 down). All three busy:

| Node | Occupant | Time left (limit) | Next pending that can take it |
|---|---|---|---|
| 110 | 53389 `rnb_val_reason` | ~21h | 53399 `afriberta` 2h (`Resources`) |
| 111 | 53065 `leaa-txl-sweep` | ~43h | — |
| 112 | 53236 `ties-bigGPU-debug` | ~38h | scheduler’s 53420 start estimate |

53420 started ~23h early when 53236 left 112. 54066 exposed the empty-list
payload. 54070 completed AmbiK. Do not overwrite complete natives.

## Cadence

- Native GPU retries are finished. No further exclusive GPU submit unless a
  complete file is later found corrupt.
- 2026-09-13 cluster `wc -l` on the live tree: all eight files at expected
  rows (31408 total). Local pull
  `outputs/cluster_pulls/followon_natives_20260912b` matches. Pre-retry
  VAGUE/AmbiK/CLARA files are SHA-256 identical to the later pull
  (skip-if-complete held).
- Official two-judge SGC on v2 `intent_summary` was **not** submitted.
  `squeue` at ~13:03 cluster: 110=`53414 clcm` (~2d20h left), 111=`53065
  leaa-txl-sweep` (~1d3h left), 112=`54071 knots-bigGPU-debug` (~1d23h left).
  CPU packet only: `outputs/gfv2_intent_summary_sgc_packet_20260913/`.
  `mbangie` had no queued GPU job.
