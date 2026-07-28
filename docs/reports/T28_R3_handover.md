# T28-R3 handover

T28-R3 is **BLOCKED before training**.

The human internal-academic-use decision is recorded at `docs/governance/decisions/T28-R3_internal_use_decision.json`; unresolved dataset licence metadata and all public-release restrictions remain unchanged. The canonical/permitted hashes and split integrity passed, the CPU target canary produced `13,058` valid targets and skipped `632`, and the exact cluster LMFE preflight returned `VERIFY_PASSED`.

No training or evaluation was run because the checkout has no full-data T28 trainer/profile. T27 smoke profiles are not valid substitutes. `selected_adapter` and `selected_model_strategy` remain null, `valid_for_official_use` remains false, no protected data was accessed, and T29 did not begin.

Resume only after a bounded full-data trainer is implemented and its focused tests, preflight, immutable run matrix, and train/dev hash gates pass. Wait for human approval before resuming and before T29.
