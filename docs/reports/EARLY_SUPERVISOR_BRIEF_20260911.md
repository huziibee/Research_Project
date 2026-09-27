# Early supervisor brief — 11 September 2026

This is a discussion note, not the final honours report. T39/T41 stay frozen.

## What the project is

The May 2026 proposal asked: does a **risk-aware ambiguity manager** choose better next actions (do it / ask / quietly fill a slot / refuse) on **compound** messy robot commands than a raw LLM or a single dumb policy (always ask, always guess, degree-only)?

Scope is the **language layer only**. We do not claim a physical robot succeeded. That limit was already in the proposal.

## The live result (frozen Pilot-120, n=120)

The manager usually **understands the job** and still **asks**.

| What | Full manager | Plain meaning |
|---|---:|---|
| Observable goal trace right | 113/120 | A blind judge said the written trace captured the wanted action |
| Route right (proposal primary metric) | 33/120 | Next move matched gold |
| Predicted execute | 0/120 | It never took the “just do it” action |
| Gold wanted execute | 76 | Humans said these were licensed to act |
| Gold-execute sent to clarify | 75/76 | Over-asking |
| Indirect speech-act right | 1/29 | Polite form is still a mess |
| T39 GPU replicas | 5 | Already more repetition than the proposal required |

This is useful science. The proposal predicted that always-clarify would over-ask and that type-and-risk coordination should do better. Frozen T39 shows the conservative type-and-risk manager **behaves like always-clarify** on this compound set, while the degree router is the only frozen system that actually executes (29/76 gold-execute). Goal traces are still strong, so the failure is **acting**, not “the model has no idea.”

A separately versioned **goal-first v2** system (new prompt + new router, not a T39 rewrite) is on the cluster as job **53074**. A counterfactual reroute of frozen analyses (not a new model) already lifts route-correct 33→92/120 with **0** false executes on gold-refuse. That is discussion evidence, not official T39 evidence.

Frozen T39 compared five GPU systems. The proposal also asked for always-ask / always-guess bounds. Those need no model. On this gold (76 execute / 23 clarify / 21 refuse, **0 silent-resolve**):

| System | Route-correct | Note |
|---|---:|---|
| Direct base LLM | 88/120 | Best routing score; still not official |
| T28 adapter LLM | 87/120 | Adapter is `valid_for_official_use=false` |
| Always execute | 76/120 | Bound only; would act on refusals too |
| Degree router | 51/120 | Only frozen system that actually executes |
| Full type-and-risk manager | 33/120 | Over-asks |
| Always clarify | 23/120 | Context-blind manager matches this bound |
| Always refuse | 21/120 | Bound |
| Always silently resolve | 0/120 | Gold never uses this route |

The May hypothesis (“type-and-risk beats uniforms on routing”) is **not supported** on frozen T39. That is still good science: the manager is safer (execute recall 0) and worse at choosing when to act. Do not rewrite T39 to rescue the hypothesis.

## Good science / rigor we can defend

1. **Hashes and no gold in prompts.** We freeze bytes. We do not retune T39 after seeing scores.
2. **Repeated runs.** T39 has five GPU replicas and a reproducibility audit. After v2 job 53074 verifies, we should submit two more locked replicas and not change the prompt between them.
3. **We name missing measurements.** Physical task success and “pure router fault” (Layer 4) are `NOT_COMPUTED`, not guessed from route labels. A later contract forbids minting task success from route correctness.
4. **Do not mix lanes.** Pilot-120 is the frozen *early* routing study (`valid_for_official_use` is still false). AmbiK / CLARA / VAGUE / Indirect are weak-label diagnostics. The unused n=300 human programme (T13–T38) is a third lane and is not done. Never pool those accuracies.
5. **Baselines before cleverness.** Majority-class traps are written down (AmbiK: never predicting safety still yields 84.5%). Unique-input and modal baselines exist for the native scorers.
6. **Failures kept.** Over-asking, empty CPC, polite-form errors are the findings. We did not clean them away.
7. **Ethics.** Supervisor-only annotation does not need clearance (`ETHGOV-001`). External annotators would.
8. **No LLM as official judge.** Route scores use the deterministic evaluator. Semantic-goal judging used two blind models as an **addendum only**.

## Issues with that rigor (say these out loud)

- **SGC is not official.** It is leftover-text judging because T39 never filled `intent_summary`.
- **Pilot-120 gold is dual-LLM, not supervisor gold.** Freeze policy: Grok × Claude/GLM + adjudication. Do not tell the meeting this was James/Rosman. T13–T15 still matter.
- **One v2 replica is not a freeze.** Treat 53074 as the first of three.
- **T39 never emitted CPC**, so we cannot yet blame the router in isolation. The v2 prompt asks for CPC; that is a new system.
- **T42 / T43 / T44 are not computed.** Readiness files exist. Launching them without a new frozen corpus would be fake closure.
- **TEACh/TEACh-DA** from the proposal is not a scored official set. CLARA covers the SaGC-style routing labels. VAGUE was added as a cleaner context ablation than the proposal listed.
- **Native full-model scores** must be hash-frozen before anyone inspects errors. Canaries are not those scores.

## Proposal checklist (May PDF vs now)

| Promised | Status |
|---|---|
| Ambiguity taxonomy + shared schema | Done |
| Hybrid benchmark + compound extension | Done as Pilot-120 (n=120, larger than the 50-example extension) plus native packets |
| Baselines: direct LLM, always clarify, always silent-resolve, degree, type-and-risk manager | Done |
| Routing correctness primary | Done (and currently unflattering for the frozen manager) |
| Intent / CPC / clarification / safe-reject metrics | Partial: route and speech-act yes; CPC empty on T39 |
| Failure analysis by type / risk / compound | Done as layered goal → speech-act → route |
| No embodied execution | Done, and we refuse to fake it |
| Double annotation / kappa | Pilot-120 gold is Grok × Claude/GLM plus adjudication, **not** James/Rosman. Terminal κ was high (~0.95). Supervisor gold is still the unused official lane |
| Silent-resolve used when fuzzy+low-risk | Frozen manager almost never silent-resolves; over-clarify instead. That is a finding |

## Ticket remainder (do not fake-close)

Official lane still needs supervisors to annotate (T13–T15). T42 needs a new source. T43/T44 are CPU-ready, not run. Q41 interpretation metrics stay `NOT_COMPUTED` until humans code them. After job 53074 verifies, submit two locked v2 replicas (`cluster/goal_first_v2/submit_replica.sh`). Do not change the prompt. Hash-freeze before reading errors.

July 2026 gaps: T11 ethics is already closed (`ETHGOV-001`). Compressed T12 is not official T29–T38. Those patches still hold.

Disk: stale worktrees/clones were removed (~6.8 GB). `outputs/` (~8.6 GB, mostly old T12 jobs) was left intact on purpose.

Talking page: open the canvas beside chat. Frozen T39 numbers are not rewritten by v2.

## Questions for the meeting (answered 11 Sep)

1. Over-asking with the goal already right is a real finding, but the product goal is: **if it already has the job, execute**, and only ask when necessary.
2. **Goal first.** Routing is secondary. Headline is whether it got the wanted job, then whether it nagged.
3. Native datasets **are in the report** as ablations and hole-plugging, not pooled into one accuracy with Pilot-120.
4. Extra v2 replicas = run the same locked v2 job two more times (R2, R3) with no prompt edits, to see if the result is stable.
5. James/Rosman **do not need to annotate T13–T15** for this report.

Queued follow-on: Slurm job behind **53074** (`gf-followon`, 3 days): v2 R2+R3, then Gemma/GLM VAGUE+AmbiK+Indirect, CLARA if time remains.

Full remainder: `docs/reports/REMAINING_TICKETS_AND_GAPS_20260911.md`.
