# T27 — Mandatory local LoRA/QLoRA smoke training

**Status:** READY

## Shared context

T00–T09 are completed. Follow `01_global_cursor_contract.md`, `02_context_refresh_protocol.md`, and the non-dataset proposal alignment. Work only on this ticket. Do not access protected test data before T29 passes.

## Required reference documents

- `04_hardware_model_strategy.md`
- `11_proposal_alignment_contract.md`

## Goal

Prove the complete supervised adaptation pipeline on the RTX 3070 before committing to full training.

## Preconditions

- T12 training environment exists.
- T15 train/dev splits exist.
- T23/T24 define output and metrics.

## Required tasks

1. Create schema-v2 supervised training examples from train only; keep dev strictly for evaluation.
2. Configure local LoRA/QLoRA with measured sequence length, batch, accumulation, checkpointing, and precision.
3. Train on a small representative subset and save adapter/checkpoint/logs.
4. Load the adapter on the exact base checkpoint through the final inference path.
5. Run dev smoke predictions and validate schema, loss movement, overfit signal, VRAM, runtime, and deterministic metrics.
6. Test restart/resume and artifact hashing.
7. Adjust only hardware/training mechanics, not protected-test-informed behaviour.
8. Issue PASS or BLOCKED; do not mark training optional.

## Deliverables

- Smoke-training config/code.
- Adapter/checkpoint.
- Resource/loss/dev report.
- Load/resume proof.
- T27 completion report.

## Acceptance criteria

- [ ] No protected data is accessed.
- [ ] Adapter loads on the exact base model.
- [ ] Training changes model outputs measurably without schema collapse.
- [ ] Peak resource use is recorded.
- [ ] The mandatory full-training path is demonstrably feasible or truthfully blocked.

## Test and evidence policy

Use Red–Green–Refactor for all deterministic behaviour. Record the initial failing test, final command, and results in the completion report.

## Stop condition

Stop after the training gate. Do not run full training if the smoke gate fails.
