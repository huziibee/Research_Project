# Licence web audit — 11 September 2026

Live checks of official pages/APIs. Does **not** invent clearances.
Internal academic use remains covered by T28-R3. Public / official
training-permission flips still require explicit exact-artifact grants.

## Summary

| Source | Online finding today | Register action |
|---|---|---|
| Original CoDraw | **CC BY-NC 4.0** LICENSE present on facebookresearch/CoDraw | Dependency terms pinned |
| CoDraw-iCR v2 | **RESOLVED 2026-09-11:** OSF TSV hash match + OSF `license.txt` CC BY-NC 4.0 | **Verified** — see `LICENCE_EXACT_ARTIFACT_RESOLUTION_20260911.md` |
| IndirectRequests | HF README still has **two** YAML licence blocks: `apache-2.0` **and** `mit` | Conflict confirmed, still unresolved |
| Schema-Guided Dialogue (dependency) | **CC BY-SA 4.0** (LICENSE.txt) | Dependency pinned; ShareAlike complicates Apache/MIT claim |
| AmbiK | GitHub LICENSE **404**; HF mirror has **no** licence tag | Still unresolved |
| VAGUE / vague-bench | HF card has **no** licence field; GitHub README cites data only | Still unresolved |
| CLARA / SaGC (`agument.json`) | GitHub has **no** licence API entry | Still unresolved |

## Detail

### Original CoDraw — resolved dependency terms

- URL: https://github.com/facebookresearch/CoDraw
- LICENSE file retrieved 2026-09-11: Creative Commons Attribution-NonCommercial 4.0
- Implication: non-commercial academic use of original CoDraw material is allowed with attribution; commercial / unrestricted public weight release is not.

### CoDraw-iCR v2 — still not exact-artifact clear

- Local README already claimed CC BY-NC 4.0 but referenced `license.txt` was missing.
- Papers and later work cite CC BY-NC 4.0 for the iCR annotations.
- OSF `gcjhz` was not confirmed in this audit as hosting a standalone LICENSE file that hashes to our TSV.
- Keep `training_permission: unresolved` for the exact local TSV until that file is recovered or authors confirm.

### IndirectRequests — conflict still live

Fetched https://huggingface.co/datasets/msamogh/indirect-requests/raw/main/README.md on 2026-09-11.
The file contains **two** YAML frontmatters in one README:

1. `license: apache-2.0`
2. later `license: mit`

HF API `cardData.license` currently returns `apache-2.0`, but the raw README conflict remains.
SGD dependency is clearly **CC BY-SA 4.0**. ShareAlike on inherited dialogue material is not automatically compatible with a pure Apache/MIT story for a derivative that redistributes adapted text.
**Do not mark IndirectRequests verified.**

### AmbiK — still no licence file

- https://raw.githubusercontent.com/cog-model/AmbiK-dataset/main/LICENSE → 404
- HF `IvAnastasia/AmbiK` API: no `license` in `cardData` / tags
- Paper/repo invite research use by availability, but that is not an SPDX grant for the exact CSV

### VAGUE — still no licence field

- HF `HazelNam/vague-bench` API: no licence in card
- Dataset also inherits VCR / Ego4D source constraints
- Stay unresolved

### CLARA / SaGC — still no licence

- GitHub `jeongeun980906/CLARA-Dataset` licence endpoint 404 / no licence
- Do not confuse with unrelated commercial “Clara” products

## What this means for “making the adapter official”

Online search **cannot** finish AmbiK / VAGUE / CLARA / IndirectRequests / CoDraw-iCR exact-artifact clearance tonight.
It **does** strengthen the non-commercial academic story for CoDraw-family material and pins SGD as CC BY-SA 4.0.

Recommended claim boundary stays:

> Trained under T28-R3 internal academic approval. Dataset licence identifiers for several sources remain unresolved. No public adapter release.

## Evidence updates

- `docs/licences/evidence/codraw_icr_v2.json` — add CoDraw LICENSE pin note
- `docs/licences/evidence/indirect_requests.json` — record dual-frontmatter reconfirm + SGD CC BY-SA 4.0
- This report is the audit trail
