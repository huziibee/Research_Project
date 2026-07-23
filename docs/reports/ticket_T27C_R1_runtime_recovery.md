# T27C-R1 Runtime Recovery and Sealed Smoke

## Decision

Runtime recovery **PASS**. The frozen T27C semantic/assembly evaluation is **BLOCKED - SEMANTIC/ASSEMBLY THRESHOLDS**. T27 remains blocked and T28 may not begin.

The implementation was committed and pushed before the live run. The sealed smoke used source commit `6419cfc479c7cf53d347c3343b6e2a859cad946b`; `0293c8461b01e6892f3927a17623c0725d6ce1f4` contains the post-run verification-allowlist correction only.

## Job 9479 diagnosis

Job 9479 was `CANCELLED by 328600030` on `mscluster109`, with Slurm exit `0:0`, after `00:27:52`. Stdout was empty. Stderr ended at `2026-07-23T17:49:10.390` with `JOB 9479 ... CANCELLED ... DUE to SIGNAL Terminated`. The last application output was model-weight loading during evaluation, before the first task-generation marker. No heartbeat, journal, prediction, or final result existed. The operator cancellation was propagated by Slurm; there was no time-limit indication and no evidence of a generation or constrained-schema deadlock.

The primary classification is **insufficient observability**. The run cannot be proven to have genuinely hung: it was cancelled while still in the pre-generation evaluation load path. The recovery therefore adds stage/progress evidence rather than changing T27C semantics.

The job-9479 adapter is **identity_mismatch**, not reusable: its checkpoint source commit was `unknown`, the pulled adapter identity lacked a safetensors hash, and its submitted config/source identity preceded the recovery freeze. It was not selected and was not used for the sealed run.

## Frozen workload and runtime design

The frozen workload remains 192 source training records, 470 task examples, 16 diagnostic records, and 12 sealed records. The sealed matrix is 5 tasks × 12 records × 2 modes = 120 calls: 60 base and 60 adapter.

The runner now loads the immutable base once per worker and the adapter once per worker, caches constraints by task-schema hash, journals every task attempt, updates an atomically replaced heartbeat, isolates per-task timeouts, and resumes only verified completed calls. Compatible calls are grouped by task; incompatible schemas never share a constraint. Base and adapter use the same prompt, tokenizer, generation settings, and `lm-format-enforcer==0.10.12` backend. No unconstrained fallback exists.

The Qwen contract uses `tokenizer.apply_chat_template(..., tokenize=False, add_generation_prompt=True, enable_thinking=False)`. Training and inference share the same rendered prefix through the assistant-generation boundary. Explicit EOS and PAD IDs are configured, and only the generated continuation is parsed; prompt echo is excluded.

The frozen policy is one attempt, 65,536 maximum output bytes, and task timeout `max(declared_minimum_seconds, diagnostic_p95_seconds × multiplier)` with a 300-second declared minimum and multiplier 3. No separate cluster diagnostic was run because job-9479 adapter reuse was rejected and only one fresh full smoke was permitted; this limitation is recorded rather than represented as diagnostic-derived timing. The sealed run did not tune timeouts from sealed outputs.

Heartbeat fields include run, phase, mode, task, record/batch IDs, attempt, elapsed phase/task time, completed/expected counts, latest success, GPU memory, PID, and timestamp. The journal records identity hashes, schema/constraint hashes, timestamps, status, raw-output hash/path, parsed-output hash, validation, and failure detail. Corrupt or duplicate entries block resume; a timeout is typed `prediction_timeout`, cannot become a successful semantic value, and leaves fail-safe unknowns. Evidence finalisation covers complete, failed, timed-out, and incomplete matrices.

## Live recovery result

The permitted fresh run was:

```text
python scripts/t12_cluster_job.py --run qlora_task_conditioned_smoke --poll --pull
```

Run `t12-qlora-task-conditioned-20260723T185137Z-6419cfc`, Slurm job `10065`, completed on `mscluster112` in 245.292 seconds with 28,080,521,216 peak VRAM bytes. The exact GPU model was not retained. The heartbeat reached `evaluation_complete` at 120/120. The journal contained 120 terminal entries: completed 120, timed out 0, failed 0, missing 0. Pull and verification passed: `VERIFY_PASSED`.

The training-plus-evaluation process used three base-model loads (initial training, resume verification, evaluation) and two adapter loads (resume verification, evaluation). Evaluation itself uses one base model with adapters disabled and one loaded adapter model. Five task constraints were compiled and cached once per task schema.

Task latencies from the sealed journal (mean / p95 / max seconds) were:

| Mode | Intent | CPC | Ambiguity | Interpretations | Risk/capability |
|---|---:|---:|---:|---:|---:|
| Base | 1.00 / 3 / 3 | 5.92 / 7 / 7 | 0.75 / 1 / 1 | 2.25 / 4 / 4 | 0.17 / 1 / 1 |
| Adapter | 0.92 / 1 / 1 | 4.33 / 5 / 5 | 0.58 / 1 / 1 | 2.83 / 12 / 12 | 0 / 0 / 0 |

The backend was retained: the pinned `lm-format-enforcer` 0.10.12 path was available and completed the bounded run. No replacement backend was justified, and no fallback was used. The pinned vLLM SIF was therefore not substituted.

## Semantic result

Base task parse/schema/semantic validity was 15/60 (25%). Adapter validity was 33/60 (55%). Both modes attempted 12 assemblies; both produced 0 production-schema-valid and 0 semantic/safety-accepted assemblies, with all 12 assembly statuses `unavailable`. Adapter-versus-base differences occurred in 44 task results. The compact audit recorded zero unsupported-commitment findings, zero fabricated-field findings, and no unsafe conversion of missing risk or capability into a positive value. The frozen semantic/assembly thresholds therefore fail honestly; this is not hidden by the successful runtime recovery.

The selected base remains `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`. `selected_adapter` and `selected_model_strategy` remain null. The adapter is technical smoke evidence only and is not official.

## Verification and tests

Focused T27C tests passed: 45 tests at the latest focused checkpoint, including runtime recovery, contract, forensic, heartbeat, journal, resume, timeout, failure-isolation, adapter-reuse, and backend-policy coverage. Cluster operator tests passed 27/27 after scoping heartbeat display to T27C profiles. Affected regression suites passed: T15 25, T16 85, T17 10, T18 6, T19 25, T20 14, T21 16, T22 5, T23 41, T24 53, T27 91, and T27B 33. Governance validation passed (84 tests / `governance validation OK`); T12 operator coverage passed 27/27 after the fix. Compile checks, clean import isolation, and `git diff --check` passed.

Implementation commits pushed:

- `6419cfc` — `fix(t27c): add bounded resumable task prediction`
- `aab7efe` — `fix(cluster): include recovery evidence files in verification`
- `0293c84` — `fix(cluster): scope recovery evidence allowlist to T27C`

Compact evidence is in `configs/model/evidence/t27c_runtime_recovery.json`. Runtime code is in `src/ambiguity_manager/model/t27c_runtime_recovery.py`; forensic evidence is in `docs/reports/ticket_T27C_R1_job9479_forensic_diagnosis.md`. The current local and remote branch SHA is `0293c8461b01e6892f3927a17623c0725d6ce1f4`. User-owned unrelated working-tree paths remain untouched and unstaged.
