# Figure 6 grounded-task flow: prospective text-only stress test

**Status:** Slurm job **61088** was submitted on 2026-09-27, PENDING with
`afterok:60976` behind the preserved ABLE IX queue. Its single allocation
runs a three-case technical smoke first, then the full 120-case emit and
score only if that smoke succeeds. No result is claimed until the new output,
score, Slurm exit, and hashes are verified. This experiment does not change
frozen Pilot-120, ABLE IX, or previously reported paper numbers.

## Question and prespecified flow

The paper's Figure 6 is a **future design recommendation**, not an evaluated
result. This experiment implements its binary branches in the stated order:

| Gate | True | False |
| --- | --- | --- |
| Grounded task? | Continue | Clarify |
| Exactly one atomic action specified? | Continue | Clarify |
| Robot capable of that action? | Continue | Refuse |
| Robot authorized for that action? | Continue | Refuse |
| Risk acceptable? | Execute | Refuse |

The figure does not specify unknown/missing judgments. The versioned
experimental extension sends **unknown at any gate to CLARIFY** and records
the first blocking gate. This abstention is reported separately from a
false gate. An unsupported quote for a positive gate makes that gate unknown;
an unresolved material CPC slot makes the grounding gate false. The code is
[`fig6_flow_v1.py`](../../src/ambiguity_manager/systems/fig6_flow_v1.py),
separate from all frozen routing policies. Exactly one atomic action is
literal here: a clear two-action sequence fails that gate. This may disagree
with Pilot-120's multi-step gold; the disagreement is an experiment finding,
not grounds to silently alter the flow.

## Fresh model output and evidence

[`run_fig6_flow_v1.py`](../../scripts/run_fig6_flow_v1.py) reads only the
frozen 120-row source JSONL for inference, checks its SHA-256
`f33b1e29f1e8aa256a475f07213aa07247def47d8e2148d54a472a40b71b05c9`,
and uses the pinned `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`
model. A constrained JSON schema requests a short interpreted task summary,
all 13 CPC task slots, unresolved slots, five **separate** gate judgments,
and a source quote/field for each gate. It also emits Pilot-17 ambiguity types,
the still-unresolved CPC slots, an alternative task interpretation if one
remains, and source quotes for every filled material CPC slot. Ambiguity
types describe ambiguity **present in the request**, even when context
resolves it; unresolved slots describe what remains after context. Clear
multi-step order is not `action_order` ambiguity. A positive grounding gate
cannot pass if a material filled slot lacks an exact source quote or a
material alternate interpretation remains. It never asks the model for a route;
the deterministic flow supplies that. Inference does not read gold, previous
predictions, or scores. The script records quote support, model/generation
identity, prompt and raw-output hashes, the gate trace, parser failures, and
one row per case. Completed rows are retained across interrupted jobs.

This is a new **text-only** condition. A quoted substring establishes only
that an output points to supplied text; it does not prove the model correctly
understood that text. The quote rule and CPC unresolved-slot rule make the
route conservative, but neither establishes physical grounding.

## Metrics and claim boundary

[`score_fig6_flow_v1.py`](../../scripts/score_fig6_flow_v1.py) checks exact
hashes of frozen source, route gold, official CPC gold, and official risk
sidecars before scoring. It requires the 120 frozen IDs and keeps failed
predictions in denominators. It also replays the five stored gates through
the exact router and rejects any row whose route or first blocking gate
differs. Prespecified outputs are:

- Exact terminal route and full route confusion, false executes among the 44
  gold non-execute cases, and false refusals among the 76 gold-execute cases.
- CPC eligible filled-cell value accuracy by slot, exact eligible CPC frame by
  case, and **joint route plus eligible CPC frame exactness**. CPC comparison
  is deterministic normalized text equality; it is stricter than some
  semantic paraphrases and does not score ineligible gold cells as truth.
- Predicted fills in CPC cells marked ineligible by gold, reported
  descriptively as possible unsupported specificity, not automatically false.
- Exact source-quote coverage for predicted filled material slots, reported
  descriptively; an exact quote does not establish correct semantic grounding.
- Per-gate true/false/unknown distributions and first-blocking-gate counts.
  **Gate correctness is NOT_COMPUTED:** Pilot-120 has no independent gold for
  grounding, atomicity, authorization, or acceptable-risk decisions. Its
  risk-level sidecar is not a safety-acceptability label.
- Pilot-17 ambiguity-type exact set and micro precision/recall/F1 against
  frozen pilot-adjudicated ambiguity types. Failed rows stay in the 120-case
  denominator. Unresolved-slot and alternative-interpretation counts are
  descriptive because independent post-context ambiguity gold is absent.

Even joint route+CPC agreement is a bounded text-layer proxy. It cannot show
that a physical robot knows the exact task, has perceived the scene, is
actually permitted to act, or will execute safely. To evaluate the five gates
as correctness claims, first commission independent blinded gate and full
task-frame annotations on a new held-out text set, freeze that protocol and
normalization, and evaluate this unchanged system there. Do not tune or
select this model on Pilot-120 and then present Pilot-120 as a clean held-out
test. The earlier 83/120 capability-patched CPU reroute is a distinct
intervention and is not a Figure 6 baseline.

## Run and verification

Local CPU preflight from repository root:

```sh
python3 scripts/run_fig6_flow_v1.py --out outputs/fig6_flow_v1_20260927
python3 -m pytest -q tests/test_fig6_flow_v1.py
```

The [Slurm launcher](../../cluster/pilot120_fig6_flow_v1/fig6_flow_v1.sbatch)
runs a GPU/schema preflight, a smoke on CA-0007/CA-0702/CA-0808, the fresh
120-case emit, CPU score, and output hashes in a separate versioned
directory. The staged code is
`/home-mscluster/mbangie/t12-hpc/code/pilot120_fig6_flow_v1-20260927`;
the output is
`/home-mscluster/mbangie/t12-hpc/results/pilot120_fig6_flow_v1-20260927`;
the log is `/home-mscluster/mbangie/t12-hpc/logs/p120-fig6-v1-61088.out`.
The staged runner, scorer, router, and launcher SHA-256 values are,
respectively, `c005205dd503d1b04532c69a7f7c51cca240b26d3f0a12388729e29ebb4c430a`,
`d85558157c7ada5e58c9a46c7288689691b99c2836b4f48fe0811d0b92364e73`,
`cc44642c2a506c9d86ce02b9a83b45092b43e7d8293c6b310d9d3f4255403a1b`,
and `1988367ca2457463615c8c3daa63de7146c30c43cb5d7a4b7799343014cae6ba`.
The four frozen input hashes matched the scorer's pinned values on the
cluster; the constrained schema compiled in the pinned container. The
original smoke-only job 61081 was cancelled before running because Slurm's
submitted-job quota prevented a separate full job; 61088 combines both phases.

The output contract is `smoke/predictions.jsonl` (three unique, non-failed
records), root `predictions.jsonl` (120 unique records), `score.json`, and
`SHA256_FINAL.txt`. A job is not complete merely because it is queued or has
a Slurm `COMPLETED` state. Verify all files and their hashes, the row
count/unique IDs, the parser-failure count, and the final log marker
`FIG6_FLOW_V1_JOB_DONE` before reporting numbers. If any ABLE IX dependency
fails, 61088 will remain blocked until that failure is investigated; do not
silently run it ahead of the study.
