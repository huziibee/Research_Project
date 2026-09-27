# Frozen T39/T41: historical result, not a new run

T39 used the same 120-case Pilot-120 evaluation-only data with five isolated
replicas. Its historical comparison reported direct base Qwen3-8B exact route
**88/120** and the then-unofficial early Pilot adapter **87/120** in each
replica. The result and per-class limits are described in the dated
[base-versus-adapter report](../reports/BASE_VS_ADAPTER_PERFORMANCE_20260911.md).
The T41 interpretation and adjudication evidence is preserved in
[`pilot120_t41_complete_closure.zip`](../../research/pilot120/artifacts/pilot120_t41_complete_closure.zip)
(SHA-256 `aea638cf05eab66610429e69f0d88f112eb09b4bd5582bb0d1b23d0a6dd3c21a`).

To inspect the evidence without changing it:

```powershell
py scripts/release/check_repository.py
New-Item -ItemType Directory -Force outputs/t41_readonly | Out-Null
py -m zipfile -e research/pilot120/artifacts/pilot120_t41_complete_closure.zip outputs/t41_readonly
Get-Content outputs/t41_readonly/pilot120_t41_complete_closure/final_t41/FINAL_GOLD_SHA256.json
```

The ZIP also contains five manager run manifests, complete row-score CSVs,
blind-adjudication decisions, and SHA-256 records. Consult those files for an
exact historical claim. The T39/T41 evidence is frozen; a new inference run
needs a new protocol and result identity. The older report is dated evidence,
not a live status page or proof that the adapter later used by T0.7 had the
same selection status.
