# T22 — Local open-source model setup for RTX 3070 laptop

## Shared context for this ticket

Project: Risk-Aware Ambiguity Manager. The system converts a command plus optional scene context, dialogue history, and capability context into either a non-ambiguous interpretation or a route: `execute`, `clarify`, `silently_resolve`, `face_preserving_rejection`, or `multi_step`.

Out of scope: robot planning, robot execution, navigation, grasping, and full safety classification.

Core ambiguity labels: `referential`, `spatial`, `pragmatic`, `temporal`, `quantitative`, `preference`, `commonsense`, `safety_precondition`, `capability`, `contextual`.

Cursor must follow `01_global_cursor_contract.md` and `02_context_refresh_protocol.md`.

## Goal

Set up local open-source model inference path for a laptop with RTX 3070 and 16GB system RAM.

## Hardware caution

Do not assume 16GB VRAM. Verify GPU memory with `nvidia-smi`.

## Required tasks

1. Run/ask human to run `nvidia-smi` and record:
   - GPU model,
   - VRAM total,
   - driver/CUDA compatibility if visible.
2. Create model setup notes in `docs/reports/local_model_setup.md`.
3. Implement local model adapter only if environment supports it.
4. Start with smallest viable quantized instruct text model.
5. Run JSON generation smoke test on 5 examples.
6. Log memory/runtime issues.
7. Do not fine-tune in this ticket.

## Deliverables

- Local model setup report.
- Optional local model adapter.
- Smoke test outputs.
- Completion report.

## Acceptance criteria

- VRAM is verified before model choice.
- Inference is behind `ModelClient`, not scattered in code.
- If local setup fails, fallback path is documented and ticket is not falsely marked successful.

## Test-driven development requirements

This ticket contains deterministic behavior and must use TDD where applicable. Before implementation, create focused failing tests for the acceptance behavior. Include happy-path, boundary, malformed-input, and regression cases relevant to this ticket. Implement the minimum change to pass, then refactor. Record the initial failure and final test command in the completion report.

## Stop condition

Stop after inference smoke test or documented hardware block. Do not fine-tune.
