# Pilot-120 fix emit (wording + CPC + ambiguity tagging)

**Purpose.** Re-generate goal-first family predictions with:
- clarification generator **1.1.0** (copies “or” alternatives from `intent_summary` when candidates are empty)
- CPC parse repair: non-empty `value` + status `unknown` → `filled`
- stronger CPC prompt instruction
- **ambiguity fix:** constrained emit prompt now lists all Pilot-17 labels with short definitions and `action_order` discipline (111/120 R1 rows previously tagged with a prompt that omitted the vocabulary)

Then CPU-score official wording + CPC sidecars (and ambiguity lands in the usual eval JSON).

**Not on mega 54259.** Mega skips wording/CPC. This job is the fix path for wording/CPC and the ambiguity prompt repair.

**Honest ceiling.** Frozen v2 bags cannot be CPU-repaired to non-zero exact-set (contain-gold was 0/120). Soft overlap was already 62/120. Old manager with right vocab peaked at **8/120** exact-set. Treat any new non-zero as a new emit, not a patch of published 0/120.

**Submit (after SSH works), behind mega:**

```bash
bash cluster/pilot120_fix_emit_20260915/sync_and_submit.sh
```

Default dependency: `MEGA_JOB=54259`. Study default temperature **0.7** is emitted first; 0.0 second for continuity.
