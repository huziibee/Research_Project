# T27 — Experiment protocol and hypothesis freeze

## Shared context

Project: Risk-Aware Ambiguity Manager. Follow the global contract and context refresh protocol. The approved datasets are AmbiK, IndirectRequests, conditional CLARA, conditional CoDraw-iCR, conditional VAGUE, auxiliary ClariQ, optional SafeAgentBench challenge, and the required manual compound extension. TEACh is not core unless a later written decision changes that.

## Goal

Freeze the experiment before protected-test execution so the study cannot drift in response to test results.

## Required tasks

1. Write `docs/protocols/EXPERIMENT_PROTOCOL.md` containing:
   - final research question and hypothesis;
   - primary and secondary outcomes;
   - exact systems/baselines;
   - datasets and split roles;
   - eligibility denominator for each metric;
   - threshold and prompt tuning rules;
   - repeated-run seed list;
   - statistical tests and alpha level;
   - multiple-comparison correction;
   - ablation set;
   - robustness transformations;
   - cost matrix ownership and freeze rule;
   - test-set access rule.
2. Create a machine-readable protocol manifest with hashes of split, schema, prompts, and configs.
3. Add a guard that blocks test execution if the manifest is absent or mismatched.
4. Record all deviations later in a versioned deviation log.

## Deliverables

- `docs/protocols/EXPERIMENT_PROTOCOL.md`
- protocol manifest
- test-set guard
- tests
- completion report

## Acceptance criteria

- Every promised comparison and metric is named before test execution.
- Test access is programmatically guarded.
- Protocol hashes are reproducible.

## Test-driven development requirements

Write failing tests for missing manifest, mismatched hashes, and allowed frozen execution before implementing the guard.

## Stop condition

Stop after the protocol is frozen. Do not run the protected test set.
