# Timeout contingency: prioritize temperatures if mega dies

**Why.** Mega 54259 may hit its 3-day wall before finishing T0.7 / T1.0. This chain runs **after** mega and emits missing Pilot-120 goal-first slices in priority order:

1. **0.5** (requested mid-temperature point)  
2. **0.7** (study default — needed for H3/H4 centred tables)  
3. **1.0** (higher-temperature claim)  
4. **0.3** (finish mid grid if still missing)

Then **fix-emit** (wording + CPC + ambiguity prompts) runs after that.

Skips any temperature that already has ≥120 goal-first prediction lines under mega sweep or this output dir.

```bash
# On cluster (after syncing this folder + ensuring PRIO_CODE_ROOT has evaluate script):
bash cluster/pilot120_timeout_contingency_20260915/submit_chain.sh
```

Default `MEGA_JOB=54259`. Cancels old fix-emit **54774** and re-chains it behind temp priority.
