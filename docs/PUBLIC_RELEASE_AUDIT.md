# Repository release audit

Snapshot: 2026-09-27. The project owner chose to preserve the existing Git
history while cleaning the latest repository tree. This document describes the
latest tree; it does **not** claim that older Git objects are free of upstream
or Pilot-120 text.

## Latest tree

The release tree keeps project code, selected evaluation and Slurm scripts,
tests, evaluation contracts, rights records, dataset acquisition instructions,
and Pilot-120 hash-only metadata. Raw upstream files, the local Python virtual
environment, case-level annotations, derived data, and generated outputs have
been removed from Git tracking without deleting their local copies.

Run the conservative path audit from the repository root:

```sh
python scripts/check_public_release.py
```

It checks the current Git index for accidentally tracked raw, annotation,
derived, output, archive, and credential paths. The intended result is
`PUBLIC_RELEASE_PATH_AUDIT=PASS`. The test does not inspect older commits or
prove licence compliance. The 2026-09-27 pre-cleanup index had 3,090 paths;
2,189 data/output paths were removed from tracking. Reviewed research code and
documentation were then added.

## History and rights

Older commits still contain upstream datasets and derived Pilot-120 text.
Anyone who clones the full repository can retrieve those objects, even though
they are absent from the latest tree. The project owner explicitly accepted
retaining that history. This choice does not resolve upstream redistribution
permissions. `configs/licences/dataset_licence_register.json` records the
current rights evidence; internal academic-use approval is not a general
public redistribution grant.

The latest tree represents Pilot-120 through `docs/PILOT120.md`,
`docs/pilot120_public_manifest.json`, the evaluation contract, and aggregate
results. Full source and gold remain local for authorised verification.
Historical T39/T41 evidence and local ZIPs were not rewritten or deleted.

## What was checked

- Explicit Git staging rather than `git add .`.
- Current-index path audit and staged-file whitespace/JSON checks.
- Pattern scan of newly staged file contents for common credential formats.
- Focused code and schema tests; results are recorded in the commit handoff.

GitHub `main` was fast-forwarded to this reviewed tree on 2026-09-27, and
`git ls-remote` verified the remote commit. An unauthenticated GitHub API
request returned 404, so public visibility was **not** verified. GitHub CLI
was not authenticated in this environment. A repository administrator must
check and, if intended, set its visibility to public in GitHub settings.
