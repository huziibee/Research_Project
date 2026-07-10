# 07 — Refinement Summary

This revision makes the execution pack cover the complete experiment rather than only implementation.

## Approved dataset decisions retained

- AmbiK retained.
- IndirectRequests retained.
- CLARA remains conditional on verified label meanings.
- CoDraw-iCR and VAGUE are approved conditional additions.
- ClariQ remains auxiliary.
- TEACh is not core unless a later decision changes this.
- SafeAgentBench remains an optional, separate safety/challenge integration.

## Major additions

- Selective TDD policy with Red–Green–Refactor requirements.
- Licence manifest and dataset inclusion register.
- Manual 50-example compound benchmark coverage matrix.
- Multi-label agreement, adjudication, and kappa requirements.
- Exact and near-duplicate/group-aware leakage prevention.
- Mandatory degree-based routing baseline.
- Expanded risk, capability, rejection, safety, and compound metrics.
- Protected-test protocol freeze and execution guard.
- Cost-sensitive evaluation.
- Confidence intervals, paired significance tests, and effect sizes.
- Ablation studies.
- Robustness/challenge-set testing.
- Repeated-run stability analysis.
- Immutable run manifests and stronger reproducibility metadata.
- Final automated experiment-readiness audit.

## New tickets

- T27 Experiment protocol and hypothesis freeze
- T28 Cost-sensitive evaluation
- T29 Statistical analysis
- T30 Ablation studies
- T31 Robustness challenge set
- T32 Repeated runs and stability
- T33 Final experiment readiness audit
