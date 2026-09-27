# Public release audit

Snapshot: 2026-09-27, branch `science/pilot120-t38`. This is an audit of the
current checkout and local Git index, not a claim that GitHub has received a
release. `git ls-remote` confirmed that the configured GitHub remote responds
and has `main` and research branches. GitHub CLI authentication is unavailable
in this environment; repository visibility and write access are unverified.

## Findings that block publishing this history

1. `data/raw/` tracks 1,939 paths, including 1,904 files from a local Python
   virtual environment and upstream dataset files/Git links. The existing
   `.gitignore` does not remove already tracked paths.
2. `data/annotations/pilot_120_v1/` tracks the 120-case full-text source,
   full-text gold, and per-record gold files. Pilot-120 must be represented in
   the public release by protocol, hashes, and aggregate results until
   redistribution rights for the derived text are resolved.
3. `data/development/` and `data/processed/` contain other derived records and
   need a record-level rights review before public inclusion.
4. The checkout has many untracked source files, reports, evidence bundles,
   archives, and cluster scripts. Some code is needed for the T0.7 and ABLE IX
   workflows, but bulk `git add .` would mix it with restricted data and local
   working files. Unrelated dirty changes were not reset or deleted.
5. Removing these paths in a later commit would leave their bytes in earlier
   public Git history. A public branch must be assembled from a clean history,
   with an explicit allowlist and a separate content/rights review before push.

Run the conservative index audit with:

```sh
python scripts/check_public_release.py
```

It reports path classes without printing file contents. It is expected to
fail on the historical working branch. Passing it alone would still not prove
that Git history is clean, that a document contains no secrets, or that a
third-party licence permits publication.

## Minimum public tree

- Root README, `pyproject.toml`, source package, reviewed tests, schema and
  evaluation contracts, and current rights/provenance registers.
- Reviewed scripts needed to build, evaluate, score, and validate each claimed
  experiment; the versioned Slurm launch scripts with machine paths explained.
- Dataset acquisition guide pointing to original providers and exact hashes.
- Pilot-120 public metadata in `docs/PILOT120.md`, frozen policy and result
  counts, with full-text access handled separately.
- Aggregate results and methods with a precise status label. Do not publish
  case-level predictions, source-derived prompts, model weights, or large
  evidence ZIPs by default.

Local evidence remains in its original location until a reviewed archive and
rollback route are established. No frozen T39/T41 bytes or Pilot-120 source/gold
files should be rewritten as a cleanup step.

## Release checks still required

1. Decide and record rights for every dataset-derived item on the public
   allowlist. The internal-use approval is not a public redistribution grant.
2. Build a clean history; verify `git ls-files`, Git object/history exposure,
   large files, and credentials before any push.
3. Run code-only tests in a fresh clone of that clean tree. Run restricted
   evaluation tests only in an authorised environment and report them
   separately.
4. Compare public aggregate tables to the frozen full-text archive hashes and
   label incomplete studies as incomplete.
5. Verify the actual remote branch, repository visibility, and published files
   after a push. A local commit or configured remote is not publication.
