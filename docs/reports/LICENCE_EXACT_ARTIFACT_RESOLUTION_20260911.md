# Exact-artifact licence resolution — 11 September 2026

Follow-on to `LICENCE_WEB_AUDIT_20260911.md`. Only flips where OSF/primary files
pin the exact local bytes.

## Verdict table

| Source | Exact artifact | Finding | Train (NC academic) | Publish aggregates | Release weights | Register |
|---|---|---|---|---|---|---|
| **CoDraw-iCR v2** | TSV sha `2ef3981f…` | OSF TSV hash **match**; OSF `license.txt` (pvzhg) sha `a8172813…` = **CC BY-NC 4.0**; README same | **Permitted** + attribution | **Permitted** NC | **NC only** (commercial banned) | **VERIFIED** |
| Original CoDraw (dep.) | facebook LICENSE | CC BY-NC 4.0 | Permitted NC | Permitted NC | NC only | dependency resolved |
| SGD (Indirect dep.) | LICENSE.txt | CC BY-SA 4.0 | Permitted with ShareAlike | ShareAlike | ShareAlike complications | dep. pinned |
| **IndirectRequests** | HF arrows | Dual YAML still `apache-2.0` **and** `mit`; SGD BY-SA | Unresolved | Unresolved | Unresolved | unresolved |
| **AmbiK** | CSV | No LICENSE (404); HF no licence; paper has no dataset grant | Unresolved | Unresolved | Unresolved | unresolved |
| **VAGUE** | parquet | HF no licence; GitHub no licence | Unresolved | Unresolved | Unresolved | unresolved |
| **CLARA** | `agument.json` | GitHub no licence | Unresolved | Unresolved | Unresolved | unresolved |

## CoDraw-iCR — what closed it

1. OSF node `gcjhz`, file `647ca5e9…` / `codraw-icr-v2.tsv` sha256 equals local TSV.
2. OSF `license.txt` guid `pvzhg` sha256 equals `docs/licences/evidence/codraw_icr_osf_license.txt`.
3. File copied to `data/raw/codraw-icr-v2/license.txt`.
4. README §License: annotation under CC BY-NC 4.0.

## Still paperwork (cannot invent)

AmbiK / VAGUE / CLARA / IndirectRequests still need author replies
(`docs/licences/author_permission_requests/`). Paper PDFs scanned today did not
supply dataset SPDX grants for those four.

## Adapter official?

**Still no.** CoDraw clearance helps one source only. Remaining blockers:

- Unresolved licences on AmbiK, VAGUE, CLARA, IndirectRequests
- Selection eligibility / `selected_adapter=null`
- `valid_for_official_use=false`

Internal academic use remains under T28-R3 for the mixed training set.
