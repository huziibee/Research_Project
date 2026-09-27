# Separate public code release: preparation gate

Status: **not published**. The full research repository is private and remains
the authoritative record, including frozen cases, predictions, archives, and
historical Git commits. Its current tree or history must not be copied to a
public repository.

## Proposed boundary

Create a **new repository with a new root commit** from individually reviewed
files. Candidate material is the project-authored Python implementation,
packaging metadata, dependency declarations, selected configuration contracts,
and a short reproduction guide that names upstream dataset acquisition points
and evidence hashes. The public guide should distinguish code execution from
reproduction of frozen results, which requires controlled data access.

Exclude `data/`, `research/`, `outputs/`, all ZIPs, model weights, copied figures,
case-level ledgers, historical Git objects, and all source-derived text by
default. Do not wholesale-copy `scripts/`, `tests/`, `cluster/`, `configs/`, or
`docs/`: these directories mix reusable code or metadata with fixed case IDs,
case-specific explanations, source-derived examples, outputs, and paths to
private evidence. For example,
`scripts/apply_gold_v2_risk_adjudication.py` embeds case explanations and
`src/ambiguity_manager/systems/response_generation.py` contains case-like
phrases. These need line-by-line rights review or a separately versioned,
scientifically labelled public implementation before inclusion.

## Release gate

1. Record an explicit allowlist of exact source commit and file hashes. Review
   every candidate file's **contents**, not just its pathname or extension.
2. Check text, generated assets, archives, test fixtures, and Git history for
   upstream-derived content, credentials, private paths, and accidental
   executable data. A regex scan alone is insufficient.
3. Verify that the selected code builds and that its documented tests pass
   *without* the controlled evidence. State any functionality withheld from
   the public package.
4. Create a new empty Git repository; copy only approved files. Verify its
   first commit's tree, history, and unauthenticated visibility before linking
   it from this private repository or the paper.
5. Do not assert that this resolves past public distribution. Prior clones or
   forks may still exist. Continue seeking exact-artifact permissions through
   [the rights register](../configs/licences/dataset_licence_register.json).

The publication decision needs a documented content review. This plan does not
grant redistribution rights or declare any current full-tree path safe for
public release.
