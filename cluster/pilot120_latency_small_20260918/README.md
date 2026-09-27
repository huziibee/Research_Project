# Pilot-120 latency / small-model ablation (2026-09-18)

## Model choice

| Candidate | Why / why not |
|---|---|
| **Qwen3-0.6B** | Fastest dense Qwen3, but usually too weak for reliable structured JSON / compound analysis |
| **Qwen3-1.7B** | **Selected** — same family as 8B baseline; ~3× token throughput vs 4B in public speed benches; community floor for “still decent” small tasks |
| Qwen3-4B | Only a half-step from 8B; cancelled job **56437** |
| Qwen3-8B | Study baseline (~116 s/cmd mean `latency_ms` on repaired T0.7) |

## Active job

- **Job 56467** `p120-lat-1p7b` — `Qwen/Qwen3-1.7B`, **T=0.7 only**, full Pilot-120
- Protocol matched to 8B study path: **thinking on** (default chat template), **not** `--constrained-only`
- Code: `/home-mscluster/mbangie/t12-hpc/code/pilot120_latency_1p7b-20260918/`
- Out: `/home-mscluster/mbangie/t12-hpc/results/pilot120_latency_1p7b-20260918/T0.7/`
- Cancelled/failed prior: **56437** (4B), **56447** (missing annotations), **56463** (missing pyproject + wrong thinking-off path)

## Submit (from pack)

```bash
bash cluster/pilot120_latency_small_20260918/sync_and_submit_1p7b.sh
# or on cluster:
export LAT_CODE_ROOT=... LAT_OUTPUT=... LAT_MODEL=Qwen/Qwen3-1.7B LAT_TEMPERATURE=0.7 LAT_CONSTRAINED_ONLY=1
bash cluster/pilot120_latency_small_20260918/submit_1p7b.sh
```

## When done

1. Pull `T0.7/scores/latency_summary.json` + predictions.
2. Score intent auto + routing; optional CPU capability-patch on frozen 1.7B analysis.
3. Paper table: **8B baseline vs 1.7B @ T0.7** (latency_s_mean × intent × routing).
