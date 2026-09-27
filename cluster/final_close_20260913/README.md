# Final close-out 2026-09-13

One exclusive GPU job after the temperature sweep was stopped.

## Why this job, not another temperature sweep

The sweep (54150) was repeating Gemma/GLM natives we already have and failing every Qwen manager / fine-tune load (`selected_adapter: false`). It would not have produced official two-judge intent, gold CPC, or gold risk.

## What this job produces

1. Dedicated `intent_summary` boxes for **raw Qwen** and the **unofficial fine-tune**, with the 17 ambiguity names and 8 speech-act names in the prompt.
2. Two-judge intent (same Gemma/GLM protocol as the older 113) on:
   - existing new-manager `intent_summary` (packet already built)
   - the new raw / fine-tune boxes
3. Routing / ambiguity / speech-act eval JSON on those new boxes.

## What it will not invent

- Slot-binding / CPC F1: Pilot-120 gold has **no CPC frames**.
- Risk-sensitive decision accuracy: Pilot-120 gold has **no risk_level**.
- Qwen on VAGUE / AmbiK / Indirect / CLARA: not in this job (needs its own runner; CLARA will not finish in one exclusive window).
- Official status for the fine-tune (`valid_for_official_use` stays false).
- Overwrite of T39 / T41 / frozen goal-first trees.

## Local numbers already scored (no GPU)

See `outputs/local_proposal_gaps_20260913.json`.
