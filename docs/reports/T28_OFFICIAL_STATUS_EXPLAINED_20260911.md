# Why the adapter is unofficial — and what actually fixes it

Date: 2026-09-11. Student-facing. Does not rewrite frozen T39/T41.

## Short answer

Having the **actual dataset files** on disk is necessary, but it is **not** what
the licence register was waiting for. The register already knew you had AmbiK,
IndirectRequests, VAGUE, CLARA, CoDraw. It was waiting for **explicit reuse
rights** for the exact artifacts (train / publish aggregates / release adapter
weights). That is a paperwork gate, not a “download again” gate.

Your current Pilot-120 / goal-first adapter is a **provisional early-pilot**
package. Its own manifest says:

- `selection_status`: `provisional_for_pilot_early_evaluation_only`
- `valid_for_official_use`: `false`
- `official_t28_selection_completed`: `false`

So it is allowed for early science. It is not the crowned official manager.

## The three gates, current truth

### 1. Licence / provenance — PARTIAL (not fixable by re-download)

| What people think | What the repo actually means |
|---|---|
| “I have the datasets” | Files + hashes are pinned |
| “So training is illegal?” | No. T28-R3 already approved **internal academic** train/dev/aggregate publish |
| “So why unresolved?” | Published licence identifiers / author grants for exact artifacts are still missing |
| “Can I flip the register to verified?” | **No** — that would fake clearance |

Already done:

- Evidence packs under `docs/licences/evidence/`
- Author request drafts under `docs/licences/author_permission_requests/`
- Internal-use decision: `docs/governance/decisions/T28-R3_internal_use_decision.json`
- Register marks `internal_academic_research_use: approved_with_conditions`

Still open if you want **official / public-facing** rights:

1. Send the six author packets (or get supervisor sign-off that internal-only is enough for the thesis and you will never release adapter weights).
2. Store replies under `docs/licences/evidence/`, hash them, update only the rights actually granted.
3. Keep `public_release_allowed=false` unless a reply explicitly allows adapter release.

**Recommended for your deadline:** stay on the T28-R3 internal-academic claim boundary. Do not wait on six author emails to finish the early report. Say clearly: datasets used under internal academic approval; no public adapter release; published licence IDs remain unresolved.

### 2. Canonical hash — FIXED today

July jobs `22710` / `22715` failed with `canonical_hash_mismatch` on the remote tree.

Recomputed on the live frozen tree today: **all four authoritative hashes match**.

Evidence: `docs/reports/T28_HASH_GATE_REVERIFY_20260911.md`.

This removes the old “bytes are wrong on the cluster” blocker. It does **not** auto-promote the adapter.

### 3. Official selection — still NOT DONE (by design of the early package)

Source of truth for official identity is
`configs/model/selected_identities_v1.json` (`selected_adapter=null`,
`valid_for_official_use=false`). The cluster early-pilot PEFT dir can say
`selected_adapter: true` for **Pilot wiring only**; that does not update the
official identities file.

Even with matching hashes and internal training permission, official selection requires:

1. A candidate with `adapter_eligible_for_selection=true` under
   `configs/model/t28_frozen_selection_policy_v1.json` (R6 full train still
   failed that bar), or a documented `no_adapter_final_strategy`
2. Clean-load verification of a package
3. Human-attested write of non-null `selected_adapter` into
   `selected_identities_v1.json` with `valid_for_official_use=true`
4. Pilot-120 must not be used to train, tune, or select

The early Pilot package was deliberately labelled provisional so Pilot-120 could proceed without pretending T28 closed.

Flipping that flag without the selection artifacts would be bad science.

## What we will not do

- Invent Apache/MIT clearances for AmbiK/CLARA/VAGUE/etc.
- Set `valid_for_official_use=true` on the early Pilot package tonight
- Restart T28 full training while goal-first jobs 53074/53081 own the GPU
- Claim the unofficial adapter is now official because hashes match

## Honest path options

**Option A — finish the honours with early Pilot evidence (recommended now)**  
Keep adapter unofficial. Report Pilot-120 + goal-first as early, non-official. Cite T28-R3 internal use. Hash gate re-verified. No James/Rosman annotation required.

**Option B — push for official adapter later**  
After 53081 finishes: run frozen selection against a clean-load package on matching hashes; keep licence claim as internal-academic unless author replies arrive; only then flip official flags.

**Option C — author emails**  
Send packets in `docs/licences/author_permission_requests/`. Slow. Needed mainly if you want public adapter release or stronger published-licence wording.
