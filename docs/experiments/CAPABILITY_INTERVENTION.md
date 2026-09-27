# Frozen-intent capability intervention (repaired T0.7)

## Exact inputs and method

This is a **CPU counterfactual reroute**, not a fresh model emit or robot-task
success test. The 120 repaired Goal-First T0.7 prediction rows, including
their `intent_summary` and other analysis fields, are held fixed. The emitted
route is the original condition. The gate-fix condition replays the same
analysis through the later `goal_first_v2` router. The LLM condition replaces
only the capability finding/status with a separate Qwen3-8B judgment before
rerouting. The oracle condition substitutes the frozen gold capability label;
it is a ceiling, not a deployable system. Gold routes stay unchanged.

| Evidence | Exact file and SHA-256 |
| --- | --- |
| Frozen source/gold | [`source_canonical.jsonl`](../../data/annotations/pilot_120_v1/source_canonical.jsonl) `f33b1e29f1e8aa256a475f07213aa07247def47d8e2148d54a472a40b71b05c9`; [`pilot_120_final_gold.jsonl`](../../data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl) `5e23ad1a92ff1873c8f039a8ce560a111dd6fb6b8ae8c11d6cf34dbfa1c360db` |
| Repaired predictions | Member `temperature_ablation_existing/T0.7/predictions/goal_first_manager_v2.predictions.jsonl` in the [full-analysis ZIP](../../research/pilot120/artifacts/p120_full_analysis_20260923.zip), member SHA-256 `e6cb2070aa56c566f955ce064775ffaac489a82962135ee69445b6e53182f258`; ZIP SHA-256 `0305b1e9ab062876ee6ee89778cc6028d2eaf01718b7dd0295944e7d9cb81a01` |
| Capability judgments | [Exact copied 120-row JSONL](../../research/pilot120/capability_intervention/capability_judgments_cluster.jsonl), SHA-256 `e4706a5e061b6f0da90801365fc58787db102027681e83de0209622a04f649b1` |
| Recorded aggregate and per-case correctness | [Repaired-run summary](../../research/pilot120/capability_intervention/sprint_rescue_summary.json), SHA-256 `af2acdb8fb87f2005159504d074ba94fb79b681f88d9f9c0aa7534112a7a8588` |
| Gold risk sidecar | [`pilot_120_gold_risk_official.jsonl`](../../data/annotations/pilot_120_v1/pilot_120_gold_risk_official.jsonl), SHA-256 `9273fd41aeb4fd336e441977c73b6b17d7b1e6e4f87da86ad974aea878fe1ac7` |

The original method is [`sprint_capability_ambiguity_rescue_20260918.py`](../../scripts/sprint_capability_ambiguity_rescue_20260918.py), with patch helpers in
[`lib_capability_debate_20260918.py`](../../scripts/lib_capability_debate_20260918.py)
and router code in [`routing.py`](../../src/ambiguity_manager/systems/routing.py).
The exact reconstructed [37-case residual ledger](../../research/pilot120/capability_intervention/residual_error_ledger.csv)
is generated and checked by
[`build_capability_residual_ledger.py`](../../scripts/release/build_capability_residual_ledger.py).
From a clean clone, run:

```sh
python scripts/release/check_repository.py
python scripts/release/build_capability_residual_ledger.py --check
```

Use `python3` on systems where that is the Python command, or `py` on Windows.
Omit `--check` only when intentionally rebuilding the derived CSV; inspect
the Git diff before committing. The builder refuses a changed ZIP, judgment,
summary, or frozen gold hash and checks all 120 IDs and reported counts.

## Recorded result

| Condition | Exact route /120 | False refusals among 76 gold-EXECUTE |
| --- | ---: | ---: |
| Original repaired T0.7 emit | 56 | 39 |
| Gate fix only | 57 | 26 |
| LLM capability patch | 83 | 4 |
| Oracle gold capability | 87 | 0 |

From original emit to LLM patch, **27 wrong cases became correct and zero
correct cases became wrong**. The LLM-patched residual is 37/120: 26
gold-EXECUTE predicted CLARIFY, 4 gold-EXECUTE predicted REFUSE, 5
gold-CLARIFY predicted EXECUTE, and 2 gold-CLARIFY predicted REFUSE. The
ledger includes predicted/gold capability and available risk fields. Its
diagnostic categories compare labels; they do not prove the cause of a route
error. [CA-0007](../../research/pilot120/cases/CA-0007.json) illustrates the
frozen source/gold and original T0.7 prediction; intervention routes are in
the residual ledger or can be recomputed with the builder.

**Claim limit:** these are paired reroutes of one 120-case set, with the
analysis held fixed. The oracle reads gold capability. The separate
capability-judge job produced complete 120-row judgments even though its
broader ambiguity-debate job had a partial failure. The older
`outputs/capability_debate_local_oracle_20260918/llm_capability_summary.json`
was computed on a different partial/local state and reports a different
false-refusal count; do not mix it with the repaired T0.7 table above. This
study cannot establish causal benefit for fresh inference, real users, or
physical robot safety. Pilot-120 remains evaluation-only.
