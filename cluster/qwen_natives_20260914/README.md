# Qwen natives + official sidecar scoring

## Local (done)

```bash
PYTHONPATH=src python scripts/score_official_sidecar_followon.py
```

Writes `outputs/official_sidecar_followon_20260914.json`.

## Cluster

`biggpu` is one job at a time. Do **not** cancel 54259.

From a host that can SSH:

```bash
bash cluster/qwen_natives_20260914/sync_and_submit.sh
```

That rsyncs code/gold and submits:

1. `sidecar-score` on `bigbatch` (CPU; CPC F1 + risk + ask-label)
2. `qwen-natives` on `biggpu` with `--dependency=afterany:54259` if 54259 is still in queue
