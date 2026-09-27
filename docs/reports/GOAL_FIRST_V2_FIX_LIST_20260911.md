# Goal-first v2 fix list — 2026-09-11

T39 and T41 stay frozen. This is a separately versioned system.

## What was wrong

1. The conservative router only executes on zero ambiguity. Pilot-120 never gave it that case, so execute was 0/120. There is no second turn after clarify.
2. Goal understanding was already high (SGC 113/120; 74/76 gold-execute). Over-asking is the tunable failure, not “the model does not understand.”
3. The T39 prompt never asked for `intent_summary` or CPC values, so those fields were empty and the router only saw unresolved slots.

## Fixes (locked before any v2 score is read)

| ID | Fix | Where | GPU? | Status |
|---|---|---|---|---|
| F1 | Keep T39/T41 byte-frozen | do not edit T39 eval script or frozen outputs | no | kept |
| F2 | Goal-first v1 execute despite remaining ambiguity | `DeterministicRouter` policy `goal_first_v1` | no | done; counterfactual 33→80/120 |
| F3 | Goal-first v2: also execute conditional+low-risk; refuse unauthorised/unsafe instead of asking | `policy=goal_first_v2`, `GoalFirstManagerV2` | no for counterfactual; yes for new analyses | implemented |
| F4 | New analysis contract: `intent_summary` then CPC values, unresolved only if truly missing | `goal_first_analysis_v2.py` | yes to generate | implemented, not yet generated |
| F5 | Drop scene-licensed slots from unresolved (clock, PENDING tag, assigned destination, “shortly”) | `apply_scene_licence` | no | implemented |
| F6 | Same rich analysis, two routers: v2 vs conservative | `evaluate_goal_first_manager_v2.py` | yes | implemented |
| F7 | One isolated cluster job, required task cannot abort later tasks | `cluster/goal_first_v2/` | yes | replica 1 = Slurm **53074**; follow-on **53081** (`afterok:53074`) runs R2+R3 then natives |
| F8 | Native VAGUE/AmbiK/CLARA/Indirect full runs | `cluster/followon_53074/` | yes, Gemma then GLM after Qwen replicas | packed into **53081**; CLARA last / skip-if-low-time |
| F9 | New blind SGC judges for v2 `intent_summary` | later packet | yes | after v2 predictions exist |
| F10 | Schema-constrained decode only after two thinking attempts | same as T39, richer schema | yes | in v2 runner |

## Local evidence already in hand (no new model)

Re-routing frozen T39 analyses with v2 policy is `scripts/score_goal_first_v2_counterfactual.py`. That still uses empty CPC/`intent_summary`; it only tests the act/ask/refuse rule. Result on the frozen full-manager traces: route-correct **33 → 92/120**, gold-execute recall **0 → 69/76**, false execute on gold-refuse **0**, gold-refuse correctly refused **18/21**. The GPU job is what fills intent_summary and CPC.

## Cluster submit

On the cluster, with the same T39 container/model env:

```bash
export GFV2_OUTPUT=/home-mscluster/mbangie/t12-hpc/goal_first_v2_${USER}_$(date +%Y%m%d)
# T39_* env can stay set; submit.sh reuses them.
bash cluster/goal_first_v2/submit.sh
```

Output must be a new directory. Wall time 24h, one exclusive GPU. Expected runtime is similar to the T39 manager bundle (~8h) because it is still 120 full + 120 blind generations on Qwen3-8B.

## What “good” looks like after the job

- `intent_summary` non-null on 120/120 v2 records
- CPC has filled values on scene-licensed slots
- `goal_first_manager_v2` execute recall on gold-execute substantially above 0 (v1 counterfactual was 61/76)
- `rich_conservative_manager_v2` still over-asks if the router, not the prompt, is the bottleneck
- False execute on gold-refuse stays near 0
