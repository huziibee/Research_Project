# Remaining tickets and honest gaps — 11 September 2026

This is an operational remainder, not a claim that blocked tickets are done.
T39/T41 stay frozen. `valid_for_official_use` is still **false** for the
adapter used in Pilot-120.

## Two lanes (do not mix)

| Lane | What it is | Status |
|---|---|---|
| Early Pilot-120 science | Frozen T39/T41, n=120, five GPU replicas | Closed as *early* evidence. Not official T29–T38. |
| Official n=300 human-gold programme | T13–T15 annotation, T28 official adapter, T29–T38 freeze | Still open. Supervisors must annotate. |
| New systems | `goal_first_manager_v2` and dataset-native diagnostics | Separately versioned. Job 53074 is replica 1. |

## Ticket status (checked 2026-09-11)

| Ticket | Status | Blocker |
|---|---|---|
| T13 | PARTIAL | Calibration exists; main n=300 not annotated. Pilot-120 used dual-LLM gold, not James/Rosman |
| T14 | PARTIAL | Tooling ready; humans pending |
| T15 | PARTIAL | Protected splits wait on T14C |
| T16–T24 | PARTIAL | Code exists; official use blocked |
| T27 | DONE | Smoke sealed; adapter still null officially |
| T28 | PARTIAL | Hash gate DONE (R5 recovery + 2026-09-11 re-verify). Licence still unresolved for published/public claims. Official selection still BLOCKED: `configs/model/selected_identities_v1.json` has `selected_adapter=null` / `valid_for_official_use=false`. Early Pilot package is provisional only. See `T28_OFFICIAL_STATUS_EXPLAINED_20260911.md` |
| T29–T38 | BLOCKED | Official freeze never started |
| T39 | DONE (early) | Frozen; do not rerun |
| T40 | DONE | Proved CPC/intent metrics unavailable on T39 gold/prompt |
| T41 | DONE (early) | Frozen; 0/360 predicted CPC frames |
| T42 | BLOCKED | Needs a new independent source + blind annotation |
| T43 | PARTIAL | CPU manifest ready; GPU factorial not queued (do not start while 53074 runs) |
| T44 | PARTIAL | Held-out family-disjoint corpus not queued |
| T45 | DONE | Historical reconciliation only; not a generalised claim |
| Q41 | NOT_COMPUTED | Needs supervisor blind coding of interpretation fields |

## Proposal nails still missing (from May PDF)

1. TEACh/TEACh-DA as a scored official set — substituted, not faked.
2. Gold support for `silently_resolve` on Pilot-120 is **0/120**, so that PDF metric cannot be won here.
3. SafeAgentBench rejection stress-test — not run.
4. Context-sampling uncertainty as a live manager feature — used by the degree router, not the full conservative manager.
5. Double-annotation kappa on the unused n=300 set.

## What was closed locally today without touching T39

- Uniform always-* routing bounds on frozen gold (`outputs/uniform_route_bounds_pilot120_20260911.json`).
- Replica submit helper for v2 R2/R3 (`cluster/goal_first_v2/submit_replica.sh`). **Do not submit until 53074 verifies.**
- Early supervisor brief.

## What we will not fake-close

T42/T43/T44/Q41, official T13–T15 gold, and native full-run scores before hash freeze.
Launching those without new frozen inputs would be bad science.

## Repeated runs

T39 already has R1–R5. After goal-first v2 replica 1 verifies, submit R2 then R3
with the same code tree and a new output directory. Do not edit the prompt
between replicas. Do not read error clusters until hashes are frozen.

## July 2026 chat gaps (patched)

- T11 ethics: closed as ETHGOV-001 (supervisor-only, no clearance).
- Compressed T12 is not a substitute for official T29–T38.
- Human annotation by James/Rosman is still the remaining official-lane bottleneck.

## Stale inventory from the 2026-09-11 backlog scan

A parallel scan listed A4–A8 (goal-first v2, intent_summary prompt, scene licence, CPC emission) as unimplemented. That inventory is **wrong**. Those shipped as `goal_first_manager_v2` before job 53074. Do not re-implement them. Do not evaluate `goal_first_v1` as the live next system.

Still actually open from that scan:

- A10 execute-calibration bound (pre-register after v2 hashes freeze; do not fit on T39)
- B4 VAGUE caption-present vs absent gain split
- C1–C3 native experiments after hash freeze
- C5 CoDraw/ClariQ blind review
- Q41–Q44 / T13–T15 / official T28

T45 is **done** (CPU historical reconciliation only). The May PDF comparison that marked T45 unfinished was incorrect. Always-clarify / always-silent-resolve bounds are now scored on frozen gold (`outputs/uniform_route_bounds_pilot120_20260911.json`); they were never GPU systems in T39.
