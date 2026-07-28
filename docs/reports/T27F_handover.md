# T27F handover

## Final state

T27F: **PASS**. Parent T27: **PASS**, pending human approval. T28 is prohibited until that approval is recorded.

The accepted evidence is committed in `configs/model/evidence/t27f_schema_preflight.json`, `configs/model/evidence/t27f_canary_evidence.json`, and `configs/model/evidence/t27f_sealed_evidence.json`, with pulled raw outputs, journals, manifests, verification records, and assembly results under `outputs/t12_cluster_jobs/` in the recovery worktree.

- Preflight job `22628`: LMFE `0.10.12`, five schemas, `VERIFY_PASSED`.
- Canary job `22632`: `160/160` terminal calls, zero fallbacks, `VERIFY_PASSED`.
- Sealed job `22660`: exactly one fresh smoke, exit `0:0`, `VERIFY_PASSED`.
- Sealed base and adapter modes: CPC-plus-ambiguity `12/12`, complete valid assemblies `12/12`, safe routes `12/12`, zero fallbacks.

`selected_adapter=null`, `selected_model_strategy=null`, and `valid_for_official_use=false`. No protected data was accessed, no training was rerun, and no new sealed run occurred during reconciliation. Stop here pending human approval; do not begin T28.
