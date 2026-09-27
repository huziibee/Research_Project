# Early supervisor brief — Lane A writing start (13 September 2026)

This is the page Mohammed can start the written report from. It sits on top of
`EARLY_SUPERVISOR_BRIEF_20260911.md`. Frozen T39/T41 numbers in that file are
**not** rewritten. The adapter stays unofficial. Do not pool native scores
with Pilot-120.

Lane A is **report-startable**. It is not “all science closed.” Official
two-judge SGC, remaining licences, and Lane B/C are listed at the end as
honest leftovers — not invented closures.

## What to write first (claim order)

1. **Frozen T39:** type-and-risk full manager over-asks (33/120; 0 predicted
   execute). Degree is the only frozen system that actually acts (51/120).
   Goal traces on leftover think-text were already high (~113/120). Failure is
   **acting**, not “the model has no idea.”
2. **Live goal-first v2 is a new system**, not a T39 rewrite. Three matching
   replicas. Policy, not “the new prompt alone,” moves the number.
3. **Natives are diagnostics**, scored against majority / unique-input
   baselines. They do not rescue a type-and-risk manager claim.
4. **Safety:** live goal-first never false-executes a gold-refuse. Degree does
   (2 rows). That trade-off is the finding.
5. **Do not** tell the meeting Pilot-120 gold is James/Rosman. Do not mint
   physical task success from route labels. Do not call the adapter official.

## Frozen vs live (do not mix)

| Lane | Status | What the report may treat as closed |
|---|---|---|
| **Frozen T39 / T41** | Frozen. Do not rerun or overwrite. | Early routing study. Full manager 33/120. Degree 51/120. Direct base 88/120. Adapter 87/120 and `valid_for_official_use=false`. CPC empty on T39. |
| **Live goal-first v2** | R1=R2=R3 scored (post-salvage). | 54 / 59 / 26 / 21 / 120. `goal_licensed` CPU reroute still 54/120. |
| **Source natives** | All required files complete and scored. | Weak-label recoveries vs majority. **Not** Pilot-120. |
| **CLARA** | Both models 10444/10444. **Do not rerun.** | Exploratory weak labels only. |
| **Official two-judge SGC on v2 `intent_summary`** | **Not run.** CPU packet prepared; GPU deferred. | Exploratory lexical proxy 112/120 is **not** official SGC. |
| **Licences** | CoDraw-iCR **CC BY-NC 4.0 verified**. AmbiK / VAGUE / CLARA / IndirectRequests **unresolved**. | Internal T28-R3 academic use only. |
| **Adapter** | Unofficial. | Hash OK; selection still blocked. |

Counterfactual reroute of *frozen T39 analyses* (92/120) is discussion
evidence only. Live v2 is **54/120**. Say that gap out loud.

## Live v2 (Pilot-120 gold, n=120)

Gold: 76 execute / 23 clarify / 21 refuse. `silently_resolve` support is 0.
R1 = R2 = R3 route agreement **120/120** on all four live systems.

| System | Route-correct | vs T39 analogue |
|---|---:|---|
| `goal_first_manager_v2` | **54/120 (0.450)** | T39 full manager 33/120 |
| `degree_based_router_v2` | **59/120 (0.492)** | T39 degree 51/120 |
| `rich_conservative_manager_v2` | 26/120 (0.217) | worse than T39 full manager |
| `goal_first_context_blind_v2` | 21/120 (0.175) | always-refuse bound |
| `goal_first_v2_goal_licensed` (CPU only) | **54/120** | 8 clarify→execute flips, net zero |

Headline 54/120 is **post-salvage**. CPU salvage recovered truncated JSON
after each replica (`rebuild_from_head_fields`). Salvaged rows are not clean
first-pass model JSON. Salvage-correct goal-first IDs are
`CA-0648/0714/0762`. Harsh reading that zeros those three: **51/120** — still
above T39 full manager.

| System | Pred execute | Gold-execute recall | False exec / gold-refuse |
|---|---:|---:|---:|
| goal-first v2 | 34 | 31/76 | **0** |
| goal-licensed (CPU) | 42 | 35/76 | **0** |
| degree v2 | 64 | 49/76 | **2** |
| rich-conservative v2 | 6 | 6/76 | 0 |
| context-blind v2 | 0 | 0/76 | 0 |

Of the 30 rows degree gets and goal-first misses, **24** are `known_incapable`
on the analysis — a capability-label miss, not a missing polite-question rule.
`goal_licensed` does not close the 54 vs 59 gap.

Still below direct base (88/120) and far below the 92/120 T39-analysis
counterfactual.

## Natives (complete; weak vs majority)

Verified 2026-09-13 on cluster
`/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b/native`
and on the local pull. Expected row counts match. Skip-if-complete left the
already-good files byte-identical (Gemma VAGUE/AmbiK/CLARA, GLM VAGUE/CLARA).
CLARA was not rerun.

Dump: `outputs/followon_native_scores_20260912/followon_native_score_summary.json`

Majority / unique-input only. **Do not pool with 54/120.**

| Task | Gemma | GLM | Majority | Reading |
|---|---:|---:|---:|---|
| VAGUE command-only exact triplet | 1/1677 | 2/1677 | 0.012 (20/1677) | Near zero. Gold triplets almost unique (1179 labels). |
| VAGUE + caption exact triplet | 13/1677 | 10/1677 | 0.012 | Caption helps vs command-only; still at or below majority. |
| AmbiK exact type-set | 321/1000 | 231/1000 | **0.425** | Both **below** majority `["commonsense"]`. |
| Indirect joint | **0/906** | **1/906** | **0.821** | Far below majority. Both almost always mark `ambiguity_present`. |
| CLARA joint (amb+cap+strategy) | 1231/10444 (0.118) | 3383/10444 (0.324) | 0.366 | Gemma well below; GLM close because capability 0.662. |

GLM AmbiK: 37 empty-list abstentions, including `ambik:211`. Empty list is
recorded as abstention and scored wrong. **Not gold-filled.**

These numbers do **not** support a type-and-risk manager claim. They are
exploratory weak-source-label recoveries.

## Goal understanding (write this carefully)

| Artifact | Score | Official? |
|---|---:|---|
| Leftover T39 think-trace two-judge SGC | ~113/120 | Exploratory addendum on T39 leftover text; T39 never filled `intent_summary` |
| Exploratory v2 lexical/polarity proxy on `intent_summary` | **112/120** @ 0.18 | **No.** CPU overlap vs two gold intent texts. |
| Frozen base / unofficial adapter think-trace proxy | 68 / 60 | **No.** |
| Official two-judge SGC on v2 `intent_summary` | **not run** | Packet built; GPU deferred (see below). |

112/120 says the written v2 paraphrase is lexically close to the gold
intents. It does **not** say routing is solved (54/120). Do not use it to
flip the adapter.

Official SGC needs two prediction-blind LLM judges (vLLM on exclusive
Blackwell, ~90 GiB). There is **no local/CPU judge path**. On 13 Sep 13:03
cluster, `mscluster110–112` were all allocated (remaining wall ~1–3 days:
`clcm` / `leaa-txl-sweep` / `knots-bigGPU-debug`). No competing exclusive
job was submitted. CPU packet:

`outputs/gfv2_intent_summary_sgc_packet_20260913/`

Judges were not started. T39/T41 were not touched.

## Licences (do not invent)

| Source | Status |
|---|---|
| CoDraw-iCR v2 | **Verified** CC BY-NC 4.0 (OSF TSV + `license.txt`) |
| Original CoDraw | CC BY-NC 4.0 dependency |
| SGD (Indirect dependency) | CC BY-SA 4.0 pinned; ShareAlike complicates derivatives |
| AmbiK / VAGUE / CLARA / IndirectRequests | **Unresolved.** Draft author emails exist. No SPDX grant invented. |

Report claim: trained under T28-R3 internal academic approval. No public
adapter release. CoDraw NC is the only source-native clearance that closed.

## What is frozen, what is live, what is leftover

**Frozen (do not touch):** T39 five GPU replicas; T41 CPC-empty finding;
Pilot-120 gold hash `5e23ad1a…360db`; unofficial adapter identity; leftover
T39 SGC addendum.

**Live v2 (separately versioned):** new analysis prompt + routers; R1–R3
post-salvage; `goal_licensed` CPU ablation; native Gemma/GLM
VAGUE/AmbiK/Indirect/CLARA scores.

**Not official / not done:** two-judge SGC on v2 `intent_summary`; adapter
`valid_for_official_use`; AmbiK/VAGUE/CLARA/Indirect licences; James/Rosman
n=300; T42–T44 / Q41; physical task success.

## Remaining blockers to start writing

Writing can start **now** on Methods + T39 findings + live v2 + native
ablations. These are the honest leftovers — none of them should stall the
first draft:

1. **Official two-judge SGC on v2 `intent_summary`** — packet ready; GPU
   deferred until 110–112 are free. Use 112/120 only as an exploratory proxy.
2. **Licences** — CoDraw NC only. Do not mark the other four verified.
3. **Lane B** (not required for this report): author clearances; T28
   selection eligibility; flip `selected_identities_v1` only with attestation.
4. **Lane C** (thesis stretch / future work): T13–T15 n=300, T42 new source,
   Q41 human coding, SafeAgentBench, TEACh substitute narrative.
5. **Salvage honesty** must stay in Methods: headline 54 includes 3
   salvage-correct rows; harsh 51/120.

Tables and dumps: `GOAL_FIRST_V2_ABLATION_PACKET_20260912.md`,
`GOAL_FIRST_FOLLOWON_STATUS_20260912.md`,
`outputs/gfv2_local_lane_a_20260912.json`,
`outputs/followon_native_scores_20260912/followon_native_score_summary.json`.
Frozen T39 story: `EARLY_SUPERVISOR_BRIEF_20260911.md`.
