# Goal-first v2 ablation packet — 12 September 2026

Lane A early-supervisor packet — **report-startable** as of 13 September 2026.
**T39/T41 frozen.** Adapter remains unofficial. R1–R3 are scored from pulled
cluster artifacts. Accuracies match. Native / CLARA scores below are local CPU
scores against frozen keys; they are **not** pooled with Pilot-120. All
required natives are scored and row-count verified. Official two-judge SGC
on v2 `intent_summary` is **not** run (CPU packet only; GPU deferred).

Machine dump: `outputs/gfv2_r1r2_ablation_20260912.json` (R3 matches; not re-derived)  
Local Lane A dump (licensed + autopsy + proxy): `outputs/gfv2_local_lane_a_20260912.json`  
Local copies: `outputs/cluster_pulls/r1_manager/`, `r2_manager/`, `r3_manager/`
(R3 predictions pulled read-only 2026-09-12; natives untouched.)

## Systems under study (separately versioned from T39)

| ID | What changes vs T39 |
|---|---|
| `goal_first_manager_v2` | New analysis prompt + goal-first router |
| `degree_based_router_v2` | Same v2 analysis, degree router |
| `rich_conservative_manager_v2` | Same v2 analysis, T39-style full manager |
| `goal_first_context_blind_v2` | Goal-first router, no scene/dialogue |
| `goal_first_v2_goal_licensed` | CPU reroute of the same v2 analysis; execute on question-shaped speech acts when `intent_summary` is a job (no `?`) |

Shared analysis → router ablations isolate **policy**, not “did the LLM see the scene.”
`goal_licensed` was **not** the live GPU system. It is a local CPU policy ablation.

Gold (Pilot-120 v1, hash `5e23ad1a…360db`): 76 execute / 23 clarify / 21 refuse.
`silently_resolve` support is 0.

## Claim boundary (read this before the tables)

R1, R2, and R3 finished GPU verify with row failures, then **CPU salvage**
(route-term scrub + `rebuild_from_head_fields`). Rebuild fills missing CPC/schema
fields with conservative defaults. Terminal routes still come from the
deterministic routers on that recovered analysis. Salvaged rows are **not**
identical to clean first-pass model JSON.

| Replica | Full-context IDs salvaged | Blind IDs salvaged | Method |
|---|---|---|---|
| R1 | 8 (`CA-0105/0332/0360/0382/0648/0714/0762/0866`) | 1 (`CA-0805`) | `rebuild_from_head_fields` (9) + earlier scrub of `CA-0092` |
| R2 | 9 (R1 set + `CA-0092`) | 7 (`CA-0029/0092/0163/0469/0805/0909/0923`) | same CPU path |
| R3 | 9 (same as R2) | 7 (same as R2) | same CPU path |

Salvage-correct / salvaged (goal-first): R1 3/8, R2 3/9, R3 3/9
(`CA-0648/0714/0762`). Headline 54/120 includes those 3. Sensitivity if
salvaged-correct rows are treated as failed: **51/120 (0.425)** — still above
frozen T39 full manager 33/120.

Do not mark the adapter official. Do not rewrite T39/T41.

## Frozen / provisional route scores

Counts are `n_correct/120`. R1, R2, and R3 match to reported precision.

| System | R1 | R2 | R3 | vs T39 analogue |
|---|---:|---:|---:|---|
| `goal_first_manager_v2` | **54 (0.450)** | **54 (0.450)** | **54 (0.450)** | T39 full manager 33 (0.275) |
| `degree_based_router_v2` | **59 (0.492)** | **59 (0.492)** | **59 (0.492)** | T39 degree 51 (0.425) |
| `rich_conservative_manager_v2` | 26 (0.217) | 26 (0.217) | 26 (0.217) | T39 full manager 33 (0.275) — v2 rich is *worse* |
| `goal_first_context_blind_v2` | 21 (0.175) | 21 (0.175) | 21 (0.175) | T39 blind 23 (0.192); v2 blind = always-refuse bound |
| `goal_first_v2_goal_licensed` (CPU) | **54 (0.450)** | **54 (0.450)** | **54 (0.450)** | same headline as live goal-first; 8 route flips, net zero |

Macro-F1 (R1=R2=R3 live): goal-first 0.412, degree 0.477, rich 0.214, blind 0.300.

### T39 / bound anchors (do not overwrite)

| System | Route-correct |
|---|---:|
| Direct base | 88/120 |
| T28 adapter (unofficial) | 87/120 |
| Always execute (bound) | 76/120 |
| Degree (T39) | 51/120 |
| Full manager (T39) | 33/120 |
| Always clarify (bound) | 23/120 |
| Always refuse (bound) | 21/120 |
| Always silently resolve | 0/120 |

Counterfactual reroute of *frozen T39 analyses* with a goal-first policy was
92/120 (`outputs/goal_first_manager_v2_counterfactual_20260911.json`). Live v2
is **54/120**. That gap is a finding: the optimistic reroute is not the live
system. Keep it labelled discussion evidence.

## Execute / safety slice (gold execute n=76, gold refuse n=21)

R1 = R2 = R3.

| System | Execute recall | Pred execute | False exec on gold-refuse | False exec on gold-clarify | Pred clarify | Pred refuse |
|---|---:|---:|---:|---:|---:|---:|
| goal-first v2 | 31/76 (0.408) | 34 | **0** | 3 | 19 | 67 |
| goal-licensed (CPU) | 35/76 (0.461) | 42 | **0** | 7 | 11 | 67 |
| degree v2 | 49/76 (0.645) | 64 | **2** | 13 | 56 | 0 |
| rich-conservative v2 | 6/76 (0.079) | 6 | 0 | 0 | 68 | 46 |
| context-blind v2 | 0/76 | 0 | 0 | 0 | 1 | 119 |

Goal-first execute precision is high (31/34 = 0.912) and it never executes a
gold-refuse. It still refuses 36/76 gold-execute rows — safer than degree, more
willing to act than rich-conservative or T39 full manager (T39 execute recall 0).

Goal-licensed keeps false-execute on gold-refuse at **0**. It buys 4 extra gold-execute
hits and spends them as 4 new false executes on gold-clarify. Precision falls
35/42 = 0.833. Headline accuracy does not move.

Degree never refuses. That is why it wins raw accuracy and why it has the only
false executes on gold-refuse.

Blind collapses to refuse (119/120). Accuracy 21/120 is the always-refuse bound,
not the always-clarify bound T39 blind hit.

## Confusion (goal-first v2; gold → pred)

|  | pred clarify | pred execute | pred refuse |
|---|---:|---:|---:|
| gold clarify (23) | 6 | 3 | 14 |
| gold execute (76) | 9 | 31 | 36 |
| gold refuse (21) | 4 | 0 | 17 |

Capability accuracy on the shared v2 analysis: 0.425. Ambiguity exact-set
accuracy: 0.0. Do not claim the analysis layer is solved; the route story is
the policy layer.

### Confusion (goal-licensed CPU reroute; gold → pred)

|  | pred clarify | pred execute | pred refuse |
|---|---:|---:|---:|
| gold clarify (23) | 2 | 7 | 14 |
| gold execute (76) | 5 | 35 | 36 |
| gold refuse (21) | 4 | 0 | 17 |

Same refuse column as live goal-first. The eight flips are all clarify→execute.

## Ablation questions

### 1. Does the goal-first router beat rich-conservative on the same v2 analysis?

**Yes.** 54 vs 26 / 120. Pairwise on R2: route agreement only 71/120; goal-first
is uniquely correct on 35 rows, rich-conservative on 7. Same analysis bytes,
different policy. Rich-conservative still over-asks (68 clarify) and barely
executes (6).

This is the clean policy ablation. It does **not** rescue the May hypothesis
that type-and-risk beats uniforms: rich-conservative (the T39-style router on
v2 analysis) is worse than frozen T39 full manager and far below always-execute.

### 2. Does context help (full vs blind)?

**Yes, for the goal-first router.** 54 vs 21 / 120. Agreement 66/120; full
context is uniquely correct on 37 rows, blind on 4. Blind is not a clarify
machine here — it is a refuse machine. Context is what lets the router execute
or clarify at all.

### 3. Are R1–R3 stable?

**Yes.** R1 vs R2 vs R3: **120/120 route agreement** on all four systems.
Intent_summary agreement 120/120 except blind 119/120 (same single mismatch
as R1 vs R2). Confusion matrices identical. Salvage-correct goal-first IDs
are the same three (`CA-0648/0714/0762`).

Prediction SHA-256 differ because salvage metadata / recovered JSON text is not
byte-identical — do not call the files hash-frozen copies of each other.

### 4. Do natives (VAGUE / AmbiK / Indirect / **CLARA**) support the manager story?

**CLARA is complete for both models** (10444 each). VAGUE is complete for both.
Gemma AmbiK is complete. Both Indirects finished on **53420** (906/906).
GLM AmbiK finished on **54070** (1000/1000) after empty-list abstention.
Majority / unique-input only; **do not pool with Pilot-120 54/120**.

| Task | Gemma | GLM | Majority |
|---|---:|---:|---:|
| VAGUE command-only exact triplet | 1/1677 (0.0006) | 2/1677 (0.0012) | 0.012 |
| VAGUE + caption exact triplet | 13/1677 (0.0078) | 10/1677 (0.0060) | 0.012 |
| AmbiK exact type-set | 321/1000 (0.321) | 231/1000 (0.231) | 0.425 |
| Indirect joint | 0/906 (0.000) | 1/906 (0.001) | 0.821 |
| CLARA joint (amb+cap+strategy) | 1231/10444 (0.118) | 3383/10444 (0.324) | 0.366 |

VAGUE caption beats command-only (Gemma McNemar p=0.0018; GLM p=0.039) but
both stay **at or below** the modal baseline because gold triplets are almost
unique (1179 labels). Gemma AmbiK is **below** majority. Gemma CLARA joint is
well below majority; GLM CLARA joint is close to majority (0.324 vs 0.366)
because capability_status is 0.662. Unique-input CLARA: Gemma full 0.146 /
blind 0.054; GLM full 0.367 / blind 0.353. Indirect joint is far below
majority because both models almost always mark `ambiguity_present`.

These numbers do **not** rescue a type-and-risk manager claim. They are
exploratory weak-source-label recoveries. Dump:
`outputs/followon_native_scores_20260912/followon_native_score_summary.json`.

### 5. Base vs adapter?

Routing already showed no adapter win on frozen T39 (88 vs 87 / 120). Adapter
stays `valid_for_official_use=false`. Goal-understanding proxy previously
favoured base (68 vs 60 / 120). Do not flip official status from this packet.

### 6. Does `goal_licensed` / execute-despite-ambiguity buy accuracy?

**No, on headline.** Live goal-first already executes despite remaining
ambiguity (`context_licensed_execute` + `goal_first_v2_execute_despite_remaining_ambiguity`).
The extra `goal_licensed` rule only unlocks question-shaped speech acts when
`intent_summary` looks like a job.

R1=R2=R3: 41 question-shaped analyses; **8 flips**, all clarify→execute
(`CA-0056/0058/0197/0226/0326/0394/0735/0889`). Rebuilt live policy matches
stored routes 120/120, so this is a pure policy delta.

|  | goal-first live | goal-licensed | degree | rich | T39 full |
|---|---:|---:|---:|---:|---:|
| Route-correct | 54 | 54 | 59 | 26 | 33 |
| Pred execute | 34 | 42 | 64 | 6 | 0 |
| Gold-execute recall | 31/76 | 35/76 | 49/76 | 6/76 | 0/76 |
| False exec / gold-refuse | **0** | **0** | 2 | 0 | 0 |
| False exec / gold-clarify | 3 | 7 | 13 | 0 | 0 |

Pairwise licensed vs live: agree 112/120; each uniquely correct on 4.
Wins: `CA-0058/0197/0226/0326` (gold execute). Losses: `CA-0056/0394/0735/0889`
(gold clarify). Safety bound holds; the speech-act relaxation is not the
degree gap.

### 7. Where does goal-first still lose to degree? (error autopsy)

R1 analyses; live routes already R1=R2=R3 120/120.

- Remaining goal-first errors: **66**
- Degree uniquely correct: **30** (21 gold-execute, 9 gold-clarify)
- Goal-first uniquely correct: **25** (17 gold-refuse — degree never refuses)

Of the 30 degree-only wins, goal-first predicted refuse 24 / clarify 6.
Matched rule on those 24: **`known_incapable`**. Pilot capability on the 30:
incapable 24, capable 4, conditionally_capable 2. Degree has no refuse path,
so it scores those gold-execute/clarify rows that the analysis labelled
incapable.

Salvage IDs vs remaining errors (R1 full-context 8):

| Salvage ID | Gold | Goal-first | Degree | Still an error? |
|---|---|---|---|---|
| CA-0648 | execute | execute | execute | no |
| CA-0714 | clarify | clarify | execute | no (GF uniquely correct) |
| CA-0762 | clarify | clarify | clarify | no |
| CA-0105 | refuse | clarify | clarify | yes |
| CA-0332 | execute | clarify | clarify | yes |
| CA-0360 | execute | clarify | execute | yes (degree-only) |
| CA-0382 | execute | clarify | execute | yes (degree-only) |
| CA-0866 | refuse | clarify | clarify | yes |

Harsh 51/120 (zero the three salvage-correct rows) is unchanged. The leftover
66 are mostly analysis-layer capability/refuse misses, not the licensed rule.

### 8. Blind SGC / goal-trace proxy on v2 `intent_summary`?

**Exploratory proxy only. Not official SGC.** Official SGC needs two
prediction-blind LLM judges on exclusive Blackwell. There is no local/CPU
judge path. On 2026-09-13, `mscluster110–112` were all allocated (~1–3 days
left). **No competing exclusive job was submitted.** A CPU blind packet was
prepared from R1 `intent_summary` (full vs context-blind):
`outputs/gfv2_intent_summary_sgc_packet_20260913/`. Judges were not started.
T39/T41 were not overwritten.

CPU lexical/polarity proxy on R1 `intent_summary` vs the two frozen intent
references (`outputs/gfv2_intent_summary_goal_trace_proxy_20260912.json`):

| Threshold | v2 `intent_summary` | Frozen base think-trace | Frozen adapter (unofficial) |
|---:|---:|---:|---:|
| 0.12 | 116/120 | 91 | 80 |
| **0.18** | **112/120** | **68** | **60** |
| 0.25 | 92/120 | — | — |

Primary 0.18: empty excerpts 0; polarity conflicts 3; mean overlap 0.355;
gold-execute proxy 71/76; route-correct **and** proxy 50/120. Salvage rows
7/8 proxy-pass. Wilson 95% [0.874, 0.966].

This is a **different artifact** from leftover T39 think-trace SGC (~113/120)
and from the base/adapter think-trace proxy. Do not call 112/120 official
SGC. Do not use it to flip the adapter. It says the written goal paraphrase
is lexically close to the gold intents; it does **not** say routing is
solved (54/120).

## Pairwise policy (R2 routes)

| Pair | Route agree | Both correct | Left only | Right only |
|---|---:|---:|---:|---:|
| goal-first vs rich-conservative | 71 | 19 | 35 | 7 |
| goal-first vs degree | 39 | 29 | 25 | 30 |
| goal-first vs blind | 66 | 17 | 37 | 4 |
| degree vs rich-conservative | 33 | 7 | 52 | 19 |
| goal-licensed vs goal-first | 112 | 50 | 4 | 4 |
| goal-licensed vs degree | 47 | 33 | 21 | 26 |
| goal-first vs T39 full (frozen R1) | 30 | 16 | 38 | 17 |

Goal-first and degree are complementary, not clones. A later ensemble would be
a new system; do not retrofit one. Licensed vs live is almost the same
system; the 8 flips cancel.

## What this means for the early supervisor report

1. Frozen T39 finding stands: type-and-risk full manager over-asks (33/120).
2. Separately versioned goal-first v2 **does** execute sometimes (34 pred
   execute, 0 false execute on gold-refuse) and beats T39 full manager
   (54 vs 33) on the same Pilot-120 gold.
3. The win is the **router**, not “v2 analysis magically fixes type-and-risk”:
   rich-conservative on that analysis is 26/120.
4. Degree on v2 analysis is the current best v2 number (59/120) and the only
   v2 system that false-executes gold-refuse (2 rows).
5. Live v2 is far below the 92/120 counterfactual and below direct base 88/120.
   Say that out loud.
6. `goal_licensed` does not raise 54/120. False-execute on gold-refuse stays 0.
   The degree gap is mostly `known_incapable` on gold-execute, not polite
   questions.
7. Exploratory `intent_summary` proxy is 112/120 at the frozen 0.18 threshold
   vs base 68 / unofficial adapter 60. Not official SGC. Not a routing score.
   Official two-judge packet is prepared; GPU judges deferred (nodes busy).
8. R3 is closed (matches R1/R2, including the licensed reroute). Both CLARA
   files are in. Both Indirects scored (Gemma 0/906, GLM 1/906 vs majority
   0.821). GLM AmbiK 231/1000 vs majority 0.425. Native GPU set is complete
   and row-count verified on cluster 2026-09-13. Native scores do not support
   pooling with Pilot-120. Lane A is report-startable; licences and official
   SGC remain leftovers (see the supervisor brief).

## Status log

- 2026-09-12 ~02:40: R1 cleaned; 53188 R2 running (~12/120 @41m).
- 2026-09-12 ~09:40: R2 finished; CPU salvage → `VERIFY_PASSED`; accuracies match R1.
- 2026-09-12 ~11:30: R3 ~44/120; 53188 healthy ~9h13m.
- 2026-09-12 ~12:33 UTC+2 / 10:33 cluster: watch resumed. 53188 RUNNING 10h18m.
  R3 65–66/120 (full files at 66), GPU 29% / 7.4 GiB. Ablation packet filled
  from pulled R1+R2. Natives/CLARA not started. 53191/53192 still pending deps.
- 2026-09-12 ~13:15 cluster / ~15:15 UTC+2: R3 120/120
  `VERIFY_PASSED_WITH_ROW_FAILURES` (34 failed). CPU salvage → `VERIFY_PASSED`.
  Accuracies 0.450 / 0.492 / 0.217 / 0.175. Routes R1=R2=R3 120/120.
  `gemma4_vague` started (`SERVER_READY` 178s; GPU 98% / 87.5 GiB).
- 2026-09-12 ~14:29 cluster: Gemma VAGUE/AmbiK/CLARA + GLM VAGUE done.
  Gemma Indirect / GLM AmbiK / GLM Indirect failed (retry after 53188).
  `glm47_clara` inferencing. 53191/53192 still pending.
- 2026-09-12 ~15:36 cluster / ~17:36 UTC+2: GLM CLARA flushed 10444/10444.
  53188 exited **2:0** (`REQUIRED_FAILED`). 53192 CANCELLED+ after 3:22.
  53191 cancelled (`afterok` miss). Local scores folded for complete natives.
  Retry **53420** queued for the three missing tasks.
- 2026-09-13 ~10:15 cluster / ~12:15 UTC+2: **53420** FAILED 2:0 after 18m30s
  on 112. Gemma + GLM Indirect **906/906**. GLM AmbiK failed again at
  `ambik:211`. Source-label parser patch uploaded. **54066** running AmbiK
  only (Indirects skip-if-complete). Indirect scores folded (0/906, 1/906).
- 2026-09-13 ~10:44 cluster: **54066** failed on empty `[]` at `ambik:211`.
  Abstention accepted (not gold-filled). **54070** COMPLETED; GLM AmbiK
  1000/1000, score **231/1000**. All required natives scored.
- 2026-09-12 ~20:50 UTC+2: local Lane A gaps (no GPU). `goal_licensed` CPU
  reroute R1=R2=R3 **54/120**, 8 clarify→execute flips, false-exec gold-refuse
  **0**. Degree-only 30, of which 24 `known_incapable`. Intent-summary proxy
  112/120 @0.18 (exploratory; not official SGC). R3 predictions pulled
  read-only. Natives still pending: Gemma Indirect, GLM AmbiK, GLM Indirect.
- 2026-09-13 ~13:10 UTC+2: cluster `wc` confirms all eight native
  `predictions.jsonl` at expected rows (VAGUE 3354×2, AmbiK 1000×2,
  Indirect 906×2, CLARA 10444×2). Skip-if-complete hashes match the
  pre-retry copies. Official SGC **deferred** (110–112 busy). CPU packet
  `outputs/gfv2_intent_summary_sgc_packet_20260913/`. Supervisor brief
  rewritten as the report-start page. T39/T41 untouched.
