# Ticket completion report

## Ticket

- ID: T27F
- Title: Canonical constrained-schema compatibility and final T27 sealed recovery

## Preconditions and exclusions

- Verified T27E is BLOCKED and T28 remains prohibited.
- Base identity remains `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`.
- `selected_adapter=null`, `selected_model_strategy=null`, and `valid_for_official_use=false` remain unchanged.
- No protected, source_holdout, T13 calibration, supervisor, future manual-gold, or model-selection data was accessed.
- T27E diagnostic evidence and failed sealed evidence were read but not reused as T27F sealed evidence.
- Fresh T27F source_dev manifest contains 12 records and is disjoint by the committed exclusion manifest.

## Root cause

The T27C production registry mixed semantic nullable/optional representations with LMFE 0.10.12 generation constraints. T27E proved the ambiguity task itself worked under a minimal two-field schema, but ticket-local replacement left nullable enum schemas in other task entry points. The cluster wrapper also recorded nonzero Python status without making the sbatch process fail.

## Tests written first

`tests/test_t27f_canonical_schema_recovery.py` was written before the canonical implementation. The initial run failed because `ambiguity_manager.model.generation_schema` did not exist. The project environment initially lacked pytest; pytest 9.1.1, LMFE 0.10.12, and jsonschema were installed into `data/raw/.venv` and the tests then ran. Six canonical tests passed. The focused affected regression set passed 81/81.

## Implemented contract

- `predict_ambiguity_v1`: only `ambiguity_present` and `ambiguity_types`; 96-token bound preserved; primary and unresolved fields are not generated.
- `predict_intent_v1`: optional speech act is a non-null string enum and is omitted when unsupported.
- `predict_interpretations_v1`: optional nullable unions are represented as omittable non-null properties; selected interpretation remains optional and requires support.
- `predict_risk_capability_v1`: required non-null enums retain explicit `unknown`.
- `predict_cpc_v1`: schema and hash unchanged.
- Production null/missing semantics remain in deterministic assembly; missing ambiguity never becomes false, missing risk never becomes none/low, and missing capability never becomes capable.

## Schema authority and hashes

The authoritative layer is `src/ambiguity_manager/model/generation_schema.py`, configured by `configs/model/t27f_schema_compatibility_v1.json`. `load_task_registry` now resolves it for training and inference. All five effective task hashes are:

| Task | Hash |
|---|---|
| predict_intent_v1 | `40f7c5c2549ee6491264f5bdbfab5518cd545a4e1af9c30bb068e7d25d2da40b` |
| predict_cpc_v1 | `ca07907149b0c07bcac97c148d211e8b31543731ba6424bacf3f09583666428f` |
| predict_ambiguity_v1 | `a12d86f1276d6a7b740e6aa25e0562ca49c157045d8887120b6e3799ccb2091f` |
| predict_interpretations_v1 | `5dcaafe640c75107596f1c30cecc8a880e44e4186f6974f817aebcf89ac5b58a` |
| predict_risk_capability_v1 | `853577d378e88f40aa7ba7996ace3ff3478e0b7708743aa791d6e7d16d2f0ad9` |

## Preflight and cluster propagation

Local exact LMFE 0.10.12 preflight passed all five schemas and produced `configs/model/evidence/t27f_schema_preflight.json`. It records task/version/schema/prompt/bound, compile results, minimal instances, omission behavior, no nullable enums, and no fallback.

The first cluster preflight job 13843 failed with exit `2:0` because the script did not accept standard operator arguments. Its durable `runtime_failure.json` and failed heartbeat were pulled. After repair, job 13856 reached the exact container but failed with exit `1:0` because LMFE was absent; its preflight JSON and failure artifacts were pulled. A subsequent submission failed before job creation during SCP connection reset. No successful cluster preflight was obtained.

The operator regression test proves rendered non-strict sbatch includes nonzero exit propagation, failure marker, failed heartbeat, and `runtime_failure.json`; `COMPLETED` with nonzero exit is not success.

## Canary and sealed results

The all-task canary was not started because exact-container preflight could not be completed. `configs/model/evidence/t27f_canary_evidence.json` records `BLOCKED_NOT_RUN`; all runtime counts are `NOT_COMPUTED`.

The fresh T27F sealed set was frozen but the single sealed smoke was not run. `configs/model/evidence/t27f_sealed_evidence.json` records `BLOCKED_NOT_RUN`. No sealed model call, raw output, journal, assembly count, acceptance count, or route count is claimed.

## Commands and validation

- Required plan/evidence files inspected in the requested order.
- `python -m compileall -q src scripts tests` — passed.
- `python scripts/t27f_schema_preflight.py` — local five-task preflight passed.
- Focused pytest command over T27F/T27E/T27C/cluster tests — 81 passed.
- Full `pytest -q` — incomplete; timed out after 120 seconds with a Windows pytest output-handle error. Not claimed as pass.
- `python scripts/build_t27f_sealed_dataset.py` — produced fresh 12-record manifest.
- Cluster operator dry-run — rendered successfully.
- Cluster jobs 13843 and 13856 — failed durably as described above; no successful preflight.

## Hashes and identities

- T27F sealed manifest: `4961a41179e672af6e1e84e76d3d26610b0a0b857b7916d2a7e7599b9b31f6de`.
- Effective schema hashes: listed above.
- Constraint config hash in local preflight: `0077dd8165f25ae89b269d7700aded86fd259abfb6b3a0e7bdf3bbe5e50bcd7c`.
- Implementation commits: `a9643c2`, `a39cb15`, `4d4c6a3`.
- Adapter evidence identity remains technical-only: source commit `6419cfc479c7cf53d347c3343b6e2a859cad946b`, SHA-256 `9a206da3ac205a725bfbcdcc8958d16ec760d63db1d31e53e019a1281a734212`.
- Runtime/resource measurements: local preflight CPU-only; cluster preflight jobs allocated 1 node/8 CPUs/64 GB and failed before model load. GPU inference measurements are `NOT_COMPUTED`.

## Acceptance status

T27F: **BLOCKED**. The permanent schema and failure-propagation repairs are implemented and locally validated, but exact-container preflight, canary reconciliation, and the required one fresh sealed smoke lack successful evidence. All sealed acceptance counts are `NOT_COMPUTED`, never zeroed.

Parent T27: **BLOCKED**. T27F cannot establish the original sealed gate. T28 may not begin.

## Changed files

See commits `a9643c2`, `a39cb15`, and `4d4c6a3`; key files include the T27F ticket, ADR, generation-schema layer/config, preflight module/script, canary/sealed scripts/profiles, fresh manifest, cluster operator, task contract integration, tests, and evidence files.

## Stop condition

This report and the parent stage-gate addendum are the final T27F actions. No T28 work, adapter training, model replacement, protected-data access, adapter selection, or sealed rerun was performed.
