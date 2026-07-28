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

The T27C production registry mixed semantic nullable/optional representations with LMFE 0.10.12 generation constraints. T27E proved the ambiguity task itself worked under a minimal two-field schema, but ticket-local replacement left nullable enum schemas in other task entry points. Training-target rendering also retained optional nulls and production-owned ambiguity fields until the canonical layer was promoted. The cluster wrapper recorded nonzero Python status without making the sbatch process fail.

## Tests written first

`tests/test_t27f_canonical_schema_recovery.py` contains the canonical tests plus deterministic failure-marker tests. The pinned Windows environment `data/raw/.venv` supplied pytest 9.1.1 and LMFE 0.10.12. The deliberate red tests exposed missing Slurm exit propagation, failure-marker acceptance, and Linux sbatch portability on Windows (CRLF/WSL path handling). After repair, 43 focused schema/training/assembly tests, 28 cluster-operator tests, and 2 T27F failure-propagation tests passed. A governance subset passed 56 tests; four governance tests were blocked by the managed temporary-directory permission harness.

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

The first cluster preflight job 13843 failed with exit `2:0` because the script did not accept standard operator arguments. Its durable `runtime_failure.json` and failed heartbeat were pulled. After repair, job 13856 reached the exact container but failed with exit `1:0` because LMFE was absent; its preflight JSON and failure artifacts were pulled. In the current checkout, SSH reachability passed, but the submission was correctly refused by the clean-source invariant because the working tree contains the uncommitted T27F implementation, regenerated development examples, evidence, and report changes. No successful cluster preflight was obtained.

The operator regression tests execute a rendered non-strict sbatch with a deliberately failing dummy entry point and prove nonzero exit propagation, retrievable `runtime_failure.json`, failed heartbeat, and refusal to verify failure markers. `COMPLETED` with nonzero or missing exit code is not success.

## Canary and sealed results

The all-task canary was not started because exact-container preflight could not be completed. `configs/model/evidence/t27f_canary_evidence.json` records `BLOCKED_NOT_RUN`; all runtime counts are `NOT_COMPUTED`.

The fresh T27F sealed set was frozen but the single sealed smoke was not run. `configs/model/evidence/t27f_sealed_evidence.json` records `BLOCKED_NOT_RUN`. No sealed model call, raw output, journal, assembly count, acceptance count, or route count is claimed.

## Commands and validation

- Required plan/evidence files inspected in the requested order.
- `python3 -m compileall -q src scripts tests` — passed for the inspected implementation set.
- `python -m compileall -q src scripts tests` — passed.
- `data/raw/.venv/Scripts/python.exe scripts/t27f_schema_preflight.py --output configs/model/evidence/t27f_schema_preflight.json` — local five-task LMFE 0.10.12 preflight passed.
- `data/raw/.venv/Scripts/python.exe -m pytest -p no:cacheprovider ...` focused T27F/T27C/T27D/T27E tests — 43 passed, 2 Windows temp-fixture tests initially blocked; corrected cluster tests then passed 2/2.
- `data/raw/.venv/Scripts/python.exe -m pytest ... tests/test_t12_cluster_job_operator.py` — 28 passed; cluster failure-propagation tests passed 2/2.
- `data/raw/.venv/Scripts/python.exe -m pytest ...` governance subset — 56 passed, 4 blocked by managed temp-directory permissions.
- `ssh -o BatchMode=yes -o ConnectTimeout=5 wits-mscluster 'printf T27F_CLUSTER_REACHABLE'` — passed.
- Full `pytest -q` — incomplete; timed out after 120 seconds with a Windows pytest output-handle error. Not claimed as pass.
- `python scripts/build_t27f_sealed_dataset.py` — produced fresh 12-record manifest.
- `data/raw/.venv/Scripts/python.exe scripts/build_t27c_datasets.py` — regenerated 192 development source-train records and 470 task examples under the canonical generation registry; no protected data accessed.
- `data/raw/.venv/Scripts/python.exe scripts/t12_cluster_job.py --run t27f_schema_preflight --poll --pull --interval 5 --timeout 90` — refused before submission with `unexpected_tracked_modifications`; no cluster job and no sealed allowance consumed.
- Historical cluster jobs 13843 and 13856 — failed durably as described above; no successful preflight.
- No new cluster preflight, canary, or sealed submission was made after the clean-source refusal; no sealed one-run allowance was consumed.

## Hashes and identities

- T27F sealed manifest: `4961a41179e672af6e1e84e76d3d26610b0a0b857b7916d2a7e7599b9b31f6de`.
- Effective schema hashes: listed above.
- Constraint config hash in local preflight: `0077dd8165f25ae89b269d7700aded86fd259abfb6b3a0e7bdf3bbe5e50bcd7c`.
- Implementation commits: `a9643c2`, `a39cb15`, `4d4c6a3`.
- Adapter evidence identity remains technical-only: source commit `6419cfc479c7cf53d347c3343b6e2a859cad946b`, SHA-256 `9a206da3ac205a725bfbcdcc8958d16ec760d63db1d31e53e019a1281a734212`.
- Runtime/resource measurements: local preflight CPU-only; historical cluster preflight jobs allocated 1 node/8 CPUs/64 GB and failed before model load. Current cluster/canary/sealed GPU measurements are `NOT_COMPUTED`.

## Acceptance status

T27F: **BLOCKED**. The permanent schema and failure-propagation repairs are implemented and locally validated, but exact-container preflight, canary reconciliation, and the required one fresh sealed smoke lack successful evidence. All sealed acceptance counts are `NOT_COMPUTED`, never zeroed.

Parent T27: **BLOCKED**. T27F cannot establish the original sealed gate. T28 may not begin.

## Changed files

Changed files include `cursor_plan/tickets/T27F_canonical_schema_compatibility_and_sealed_recovery.md`, `configs/model/t27f_schema_compatibility_v1.json`, `configs/model/evidence/t27f_schema_preflight.json`, `configs/model/evidence/t27f_canary_evidence.json`, `configs/model/evidence/t27f_sealed_evidence.json`, `configs/cluster/t12_job_profiles.json`, `src/ambiguity_manager/model/generation_schema.py`, `src/ambiguity_manager/model/schema_preflight.py`, `src/ambiguity_manager/model/task_prediction_contract.py`, `src/ambiguity_manager/model/t27e_ambiguity_recovery.py`, `src/ambiguity_manager/model/qlora_task_conditioned_smoke.py`, `src/ambiguity_manager/model/cluster/job_operator.py`, `scripts/t27f_schema_preflight.py`, `scripts/t27f_all_task_canary.py`, `scripts/t27f_sealed.py`, `scripts/build_t27f_sealed_dataset.py`, `tests/test_t27f_canonical_schema_recovery.py`, `docs/decisions/ADR_T27F_generation_schema_authority.md`, this report, the parent addendum, and the fresh `data/development/t27f_final_smoke_v1` manifest/evidence files. Historical implementation commits are `a9643c2`, `a39cb15`, and `4d4c6a3`.

## Stop condition

This report and the parent stage-gate addendum are the final T27F actions. No T28 work, adapter training, model replacement, protected-data access, adapter selection, or sealed rerun was performed.

## Final execution update ? 2026-07-28

This section supersedes the earlier `BLOCKED_NOT_RUN` execution notes above. The clean isolated T27F worktree was used for the final runtime evidence; the dirty main checkout was not modified or cleaned.

### Verified preflight and canary

- Exact-container schema preflight job `22628`, run `t27f-schema-preflight-20260728T181235Z-0a41b35`: Slurm `COMPLETED`, exit `0:0`, operator `VERIFY_PASSED`.
- All five effective task schemas compiled under LMFE `0.10.12`; all schema hashes remained unchanged from the canonical registry.
- Canary job `22632`, run `t27f-all-task-canary-20260728T181502Z-0a41b35`: `160/160` terminal calls, zero unconstrained fallbacks, raw outputs and journal reconciled, operator `VERIFY_PASSED`.
- Canary assemblies: base `13` complete and `3` intentional partial fail-safe; adapter `16` complete. All `32/32` were production-schema-valid.

### Final sealed result

- Exactly one fresh T27F sealed smoke was executed: job `22660`, run `t27f-sealed-20260728T190852Z-0a41b35`.
- Slurm exit was `0:0`; all expected artifacts were pulled and operator verification returned `VERIFY_PASSED`.
- Base: `60` task calls, `52` parse/schema/semantic-valid, ambiguity `12/12`, CPC `12/12`, CPC-plus-ambiguity `12/12`, complete assemblies `12/12`, production-valid `12/12`, safe `12/12`, fallbacks `0`.
- Adapter: `60` task calls, `55` parse/schema/semantic-valid, ambiguity `12/12` (`100%`), CPC `12/12`, CPC-plus-ambiguity `12/12`, complete assemblies `12/12`, production-valid `12/12`, safe `12/12`, fallbacks `0`.
- Routes: base `9` clarify / `3` execute; adapter `12` clarify. Unsafe execute `0`, unsafe silent-resolve `0`, fabricated fields `0`, unsupported commitments `0`.
- Sealed evidence: `configs/model/evidence/t27f_sealed_evidence.json`; manifest hash `4961a41179e672af6e1e84e76d3d26610b0a0b857b7916d2a7e7599b9b31f6de`; records-manifest hash `3c04b298c363c0a65d3bef7cd5983a66eb007709b21d47b3256a99e248a023e9`; task-matrix hash `7789cacb2beb6fa8b69465b79c9d847d5f37f78531bae28ae1282291e3e6d131`.

### Final stage gate

T27F: **PASS**. The mandatory runtime, model/assembly, safety, and regression criteria are satisfied by committed evidence. Parent T27: **PASS**, subject to the explicitly required human stage-transition approval. `selected_adapter=null`, `selected_model_strategy=null`, and `valid_for_official_use=false` remain unchanged. T28 may not begin until human approval is recorded.
