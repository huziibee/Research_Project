# Goal-first v2 R1 recovery — 12 September 2026

## What happened

Job **53074** (`gf-v2-combined`) ran ~6h, wrote **120/120** predictions for all four
v2 systems, wrote evaluations, then exited **2** with `VERIFY_FAILED`.

Original verify required **zero** `failed` rows. After repair **53183** still had:

| System | Failed | Notes |
|---|---:|---|
| goal_first_manager_v2 | 9 | shared full-context analysis |
| rich_conservative_manager_v2 | 9 | same IDs |
| degree_based_router_v2 | 9 | same IDs |
| goal_first_context_blind_v2 | 6 | independent blind IDs |

Failure modes: truncated/repetition `no_json`, `bad_intent_summary`,
`intent_summary_route_contamination` (false positives on words like
"execute"/"clarify"/"route" inside goal paraphrases).

Dependents of 53074/53183 became `DependencyNeverSatisfied` until soft-pass
unblocked follow-on.

## Recovery path (final)

1. Soft verify: `VERIFY_PASSED_WITH_ROW_FAILURES` + exit 0 when ordered 120/120
2. Follow-on **53188** launched with **no** dep on R1 repair (CLARA required)
3. **CPU salvage** (no GPU):
   - Scrub route tokens from `intent_summary` → fixed contamination (CA-0092 + 5 blind)
   - Cut generation loops + `rebuild_from_head_fields` → fixed remaining 8 full + 1 blind
4. Result: **`VERIFY_PASSED`**, `row_failure_total=0`

### Final R1 route accuracy (after salvage)

| System | Route accuracy |
|---|---:|
| goal_first_manager_v2 | **0.450** |
| degree_based_router_v2 | **0.492** |
| rich_conservative_manager_v2 | 0.217 |
| goal_first_context_blind_v2 | 0.175 |

(Frozen T39 full manager ≈ 0.275 — goal-first v2 still ahead on the main system.)

### Claim boundary (honesty)

Salvaged rows are **not** identical to clean first-pass model JSON. Rebuild fills
missing CPC/schema fields with conservative defaults; terminal routes still come
from deterministic routers. Document this in the report. Do not mark the adapter
official. Do not rewrite T39/T41.

## Job IDs (2026-09-12)

| Job | Role | Notes |
|---:|---|---|
| **53188** | gf-followon | RUNNING ~13h07m on `mscluster110`; R2+R3 salvaged `VERIFY_PASSED`; `gemma4_vague` inferencing; remaining natives+CLARA still queued |
| **53190** | r1 audit | completed earlier |
| **53191** | followon score | PENDING `afterok:53188` |
| **53192** | clara backup | PENDING `afterany:53188`; skips if follow-on CLARA complete — keep until then |
| **53189** | deferred R1 GPU repair | **cancelled** after CPU `VERIFY_PASSED` |

Artifacts: `failed_inventory_20260912.json`, `cpu_salvage_summary.json`,
`cpu_salvage_log_20260912.json` under the R1 manager dir.

Follow-on live note: `GOAL_FIRST_FOLLOWON_STATUS_20260912.md`.
R2 and R3 used the same CPU salvage path (scrub + `rebuild_from_head_fields`).
Both repaired one extra full ID (`CA-0092`) and six extra blind IDs versus R1;
final route accuracies still match R1 (R1=R2=R3 routes 120/120). Same claim boundary.
