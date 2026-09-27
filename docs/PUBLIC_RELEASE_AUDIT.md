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

The latest tree and older Git commits contain source-derived text. The
project owner explicitly chose to preserve it in this repository. Several
exact-artifact public redistribution permissions remain unresolved in
`configs/licences/dataset_licence_register.json`. This repository's
availability, hash verification, or internal academic-use approval is not a
licence grant. Review the source terms before setting visibility to public,
forking, or mirroring. No model weights or private credentials are included.

The GitHub `main` push was verified before this update. An unauthenticated
GitHub API request returned 404 while the same request succeeded for a known
public repository, so public visibility was not verified. GitHub CLI was not
authenticated here; an administrator must check visibility in GitHub settings.

## Scientific status

T0.7's official two-judge package is complete with 120-case denominators and
failed cases retained. T0.3 and a matched-depth-5 control were not included.
The four inherited T0.7 prediction streams in the case files are labelled
separately from new Raw and Fine-Tune inference. T39/T41 archives are frozen.
ABLE IX's five jobs were running/dependency-queued at the 2026-09-27 cluster
check; their final five-seed output has not yet been recovered into Git.

The `research/pilot120/README.md` file lists exact archive hashes. Preserve
older Git history: it contains original source/gold and historical decisions.
The new frozen manifest differs from the older historical version; both are
retained by Git history and the latest file's hash is recorded.
