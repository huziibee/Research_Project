# T12 — Local RTX 3070 text-model and training-stack setup

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `04_hardware_model_strategy.md`
- `11_proposal_alignment_contract.md`

## Goal

Select and prove a licensed local base model that supports both schema-constrained inference and mandatory local LoRA/QLoRA.

## Preconditions

- T10 passed.
- T11 governance infrastructure is implemented and committed; **T11 stage gate remains BLOCKED** on the pending supervisor/institutional ethics determination (`determination_status: "pending"`, `collection_permitted: false`). T11 must not be recorded as PASS.
- **Execution-order deviation `DEV-20260711-001`** authorises T12 while the T11 annotation-specific ethics gate remains pending. See `docs/decisions/DEV-20260711-001_pre_t12_execution_order_deviation.md` and `docs/governance/logs/deviation_log.jsonl`.
- T12 completion does **not** satisfy or erase the T11 ethics blocker. Before T13 human-review activities or T14 annotation collection, governance must be reassessed against the documented determination.
- The human can run commands on the RTX 3070 machine.

## Required tasks

1. Record `nvidia-smi`, exact GPU/VRAM, free memory, driver, CUDA visibility, OS, Python, and system RAM.
2. Install/configure a local inference runtime behind `ModelClient` and a separate local PEFT/TRL-compatible training environment.
3. Create a current model shortlist using verified model cards/licences; require exact checkpoint availability for training.
4. Test candidates from smaller to larger quantised variants on non-test schema-v2 fixtures.
5. Measure raw/parsed JSON validity, critical-field completion, latency, peak VRAM, repeatability, and restart/offline recovery.
6. Run a minimal adapter-load feasibility probe that does not yet train on research data.
7. Select one base model/revision for the direct baseline, proposed manager, and mandatory training path.
8. Record rejected candidates and reasons; update the model licence register.
9. Save raw outputs, environment lockfiles, model manifest, and operational runbook.

## Deliverables

- `ModelClient` local adapter.
- Inference and training environment manifests.
- Hardware report.
- Candidate bake-off report.
- Selected base-model decision.
- Model licence evidence.
- Smoke outputs and T12 completion report.

## Acceptance criteria

- [ ] Actual VRAM is measured before selection.
- [ ] Selected model runs schema-v2 inference locally.
- [ ] The exact base checkpoint is available to the training stack.
- [ ] Licence permits local academic use and adapter training.
- [ ] No protected examples are used.
- [ ] No LVLM dependencies are introduced.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after the base model and local stacks are proven. Do not author benchmark records or run fine-tuning.
