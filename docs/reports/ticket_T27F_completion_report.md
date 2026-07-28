# T27F completion report

## Authoritative result

T27F: **PASS**. Parent T27: **PASS**, pending explicit human approval before any stage transition. T28 remains prohibited until that approval is recorded.

The accepted result is machine-verifiable from the committed evidence files and the pulled run artifacts. No adapter is selected, no model strategy is selected, and `valid_for_official_use=false` remains unchanged.

## Verified execution

- Exact-container LMFE preflight: job `22628`, run `t27f-schema-preflight-20260728T181235Z-0a41b35`, exit `0:0`, `VERIFY_PASSED`; LMFE `0.10.12`; all five effective schemas passed; no unconstrained fallback.
- Non-sealed canary: job `22632`, run `t27f-all-task-canary-20260728T181502Z-0a41b35`, `160/160` terminal calls, zero fallbacks, raw/journal reconciliation passed, `VERIFY_PASSED`.
- Sealed smoke: exactly one fresh run, job `22660`, run `t27f-sealed-20260728T190852Z-0a41b35`, exit `0:0`, `VERIFY_PASSED`.

Sealed acceptance, in both base and adapter modes: CPC-plus-ambiguity `12/12`; complete production-schema-valid assemblies `12/12`; safe routes `12/12`; zero fallbacks; zero unsafe execute decisions; zero unsafe silent resolutions; zero fabricated fields; zero unsupported commitments.

## Frozen identity and hashes

- Base model: `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`.
- `selected_adapter=null`; `selected_model_strategy=null`; `valid_for_official_use=false`.
- Source commit used by the runs: `0a41b3547c23da7d0afd7eff7104f93a4edafc1e`.
- Source archive SHA-256: `44d96ca7369505e1c573963402a46b391f912f4a130621f9d35d737b09cd9645`.
- Sealed manifest hash: `4961a41179e672af6e1e84e76d3d26610b0a0b857b7916d2a7e7599b9b31f6de`.
- Records-manifest hash recorded by the run: `3c04b298c363c0a65d3bef7cd5983a66eb007709b21d47b3256a99e248a023e9`.
- Task-matrix hash: `7789cacb2beb6fa8b69465b79c9d847d5f37f78531bae28ae1282291e3e6d131`.
- Constraint config hash: `0077dd8165f25ae89b269d7700aded86fd259abfb6b3a0e7bdf3bbe5e50bcd7c`.
- Effective schema hashes: intent `40f7c5c2549ee6491264f5bdbfab5518cd545a4e1af9c30bb068e7d25d2da40b`; CPC `ca07907149b0c07bcac97c148d211e8b31543731ba6424bacf3f09583666428f`; ambiguity `a12d86f1276d6a7b740e6aa25e0562ca49c157045d8887120b6e3799ccb2091f`; interpretations `5dcaafe640c75107596f1c30cecc8a880e44e4186f6974f817aebcf89ac5b58a`; risk/capability `853577d378e88f40aa7ba7996ace3ff3478e0b7708743aa791d6e7d16d2f0ad9`.

## Scope and stop condition

No protected data was accessed. No training was rerun. No new sealed run was submitted; job `22660` is the single accepted sealed smoke. This report is authoritative over earlier blocked-not-run notes and does not authorize T28.
