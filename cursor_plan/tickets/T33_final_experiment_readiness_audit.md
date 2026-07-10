# T33 — Final experiment readiness and completeness audit

## Shared context

Project: Risk-Aware Ambiguity Manager. This is the final gate before report writing.

## Goal

Verify that the actual experiment, not merely the code, satisfies the project rubric and frozen protocol.

## Required audit areas

- research question and hypothesis answered;
- dataset inclusion register and licences complete;
- manual 50-example compound extension complete or revised target justified;
- annotation agreement and adjudication complete;
- split and leakage checks passed;
- required baselines including degree-based routing run;
- full manager and ablations run;
- all mandatory metrics run;
- cost-sensitive, statistical, robustness, and stability analyses complete;
- predictions, configs, logs, and hashes saved;
- failure analysis complete;
- limitations and negative results recorded;
- every table/figure traceable to outputs;
- AI-use declaration evidence updated for actual use.

## Required tasks

1. Build an automated checklist from manifests and output files.
2. Mark every item `PASS`, `FAIL`, `NOT_APPLICABLE`, or `BLOCKED` with evidence path.
3. Refuse a global PASS if any mandatory item is missing.
4. Write `docs/reports/final_experiment_readiness_audit.md`.

## Deliverables

- automated audit script and tests
- machine-readable audit output
- final audit report
- completion report

## Acceptance criteria

- No mandatory omission is hidden.
- Every PASS includes an evidence path.
- Report writing may begin only on global PASS or an explicit human-approved deviation.

## Test-driven development requirements

Create failing fixtures for missing outputs and passing fixtures for complete manifests before implementing the audit.

## Stop condition

Stop after issuing the final PASS/FAIL decision.
