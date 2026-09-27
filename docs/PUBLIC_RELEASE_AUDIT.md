# Repository inclusion and rights audit

Snapshot: 2026-09-27. The owner asked for the frozen Pilot-120 cases and
case-level outputs to be recoverable from this repository before deleting the
local checkout. This audit separates byte preservation, scientific status,
and public redistribution rights.

## Included in the latest tree

- Source, final gold, policy, manifest, and official Pilot-120 annotation
  versions under `data/annotations/pilot_120_v1/`.
- A 120-link case index and generated per-case JSON records under
  `research/pilot120/`. Each record shows source, gold, six predictions,
  routing comparison, and official T0.7 intent judgment with provenance.
- The exact verified T0.7, T41, full-analysis, historical annotation, intent,
  and supporting officialization archives under `research/pilot120/artifacts/`.
- Code, tests, evaluation protocols, environment manifests, dataset source
  links, and rights records. The current tree excludes upstream raw payloads,
  Python virtual environments, local generated outputs, and coursework files.

Run `python scripts/release/check_repository.py` to verify tracked paths,
120 case links, SHA-256 of central artifacts, and ZIP CRC. Run
`python scripts/release/build_pilot120_cases.py` only when intentionally
regenerating browsable cases from the immutable inputs; compare Git diff before
committing its output. A strict metadata-only public-tree audit is preserved
at `scripts/release/check_strict_public_tree.py` and is expected to fail while
full-text Pilot-120 files are included.

## Rights and visibility

The GitHub repository
[`huziibee/Research_Project`](https://github.com/huziibee/Research_Project)
was **public** when checked on 2026-09-27: an unauthenticated request to the
[GitHub repository API](https://api.github.com/repos/huziibee/Research_Project)
returned HTTP 200 with `visibility=public` and `private=false`. This is a
dated observation, not a permanent visibility guarantee. The latest tree and
older Git commits contain source-derived text, as the project owner requested.

The authoritative [rights register](../configs/licences/dataset_licence_register.json)
records internal academic research use as `approved_with_conditions`, raw
data redistribution as `false`, and adapter release permission as `pending`.
Its exact-artifact `redistribution_permission` is `unresolved` for AmbiK,
IndirectRequests, VAGUE, CLARA, ClariQ, SafeAgentBench, and manual compound
cases. CoDraw-ICR-v2 is recorded as `permitted_noncommercial_with_attribution`.
Public availability, owner preference, internal-use approval, or a hash check
does not resolve those upstream rights. A licence review/permission decision
is still needed for the unresolved source-derived case text and archived
outputs already publicly reachable in the tree and history. No new licence
grant was found in this repository-only review.

## Scientific status

T0.7's two-judge package is complete with 120-case denominators and failed
cases retained. The judgments are exploratory under the current evaluator
policy: [no approved semantic-judge deviation was found](PAPER_REPRODUCIBILITY.md#semantic-judge-governance-finding).
T0.3 and a matched-depth-5 control were not included.
The four inherited T0.7 prediction streams in the case files are labelled
separately from new Raw and Fine-Tune inference. T39/T41 archives are frozen.
ABLE IX's five jobs were running/dependency-queued at the 2026-09-27 cluster
check; their final five-seed output has not yet been recovered into Git.

The `research/pilot120/README.md` file lists exact archive hashes. Preserve
older Git history: it contains original source/gold and historical decisions.
The new frozen manifest differs from the older historical version; both are
retained by Git history and the latest file's hash is recorded.
