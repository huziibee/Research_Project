# A02-A04-R3 handover

## Current status

`INCOMPLETE — both primary servers now load; pilot completion remains in progress.`

The pilot is not yet eligible for `PASS_TO_HUMAN_REVIEW`. No full annotation job was submitted, no protected data was accessed, and no T15/T27/T28/T29 files were modified.

## Latest execution

Latest completed diagnostic job: `23155`, submitted to `mscluster110` in `biggpu` with exclusive 110G/no-GRES allocation. It confirmed GLM startup but stopped in validation. The repaired retry is pending submission.

Run directory:

`/home-mscluster/mbangie/dual-llm-a02-r1/data/dual_llm_benchmark_v1/runs/a02-a04-r3-pilot-23155-20260730`

Observed phase evidence:

- CPU/import preflight passed offline.
- Gemma 4 canary passed and the 40-record Gemma annotation phase completed without validator errors in the job log.
- Gemma cleanup evidence was written.
- GLM resolved to `Glm4MoeLiteForCausalLM` and began loading its 48 shards.
- GLM reached `SERVER_READY after 508.1s` after loading all 48 shards; canary requests returned HTTP 200 and cleanup completed in 21.5s. The server log records 55.94 GiB model memory.
- Both primary servers therefore load sequentially on Blackwell under the repaired 900-second readiness/120-second cleanup lifecycle.
- Job `23155` stopped in the validator because malformed GLM scalar outputs reached the envelope as `parsed_annotation: Infinity`/`0.0`; raw attempts are preserved. This was a validator crash, not a model-load failure.
- The authorised GLM runtime repair is staged: use `response_format: json_object` and apply the unchanged frozen schema locally. This changes only the structured-output backend.
- No accepted GLM annotation, agreement metrics, or review packet exists yet.

The GLM server log contains the preserved startup evidence. Job stdout/stderr are the authoritative phase logs in the run directory above.

## Frozen decisions and evidence

- Active pair: `annotator_a_gemma4` / `google/gemma-4-26B-A4B-it` revision `4d7ae4984b7db7de8f8457170b3f1a419ee76d52`; `annotator_b_glm` / `zai-org/GLM-4.7-Flash` revision `7dd20894a642a0aa287e9827cb1a1f7f91386b67`.
- Pilot: 40 records; hash `81d56440801c24a68032e3512dc7c6ca8c4fbd2317bdf56a78cf0d36172e6de1`.
- Gemma download job `23090` completed successfully. Its resolved manifest checksum and recorded key-file hashes matched.
- Mistral jobs `23083` and `23087` remain historical BLOCKED evidence and were not reused as annotation data.
- Earlier R3 allocation guards `23102` and `23111` correctly released unsafe busy-GPU allocations before model load.
- Jobs `23152` and `23155` establish that Gemma and GLM both load and clean up sequentially. Job `23155` is the strongest current GLM evidence.
- Schema-invalid Gemma attempts from `23113`, `23141`, `23143`, and `23144` remain preserved; no invalid output was accepted.

## Next steps

1. Submit and monitor the repaired retry with GLM `json_object`.
2. Confirm Gemma canary, Gemma 40-record outputs, cleanup, then GLM canary and cleanup.
3. Complete GLM’s 40 records with raw attempts, parsed outputs, and technical retry history.
4. Reconcile exactly 80 final statuses; calculate agreement/subgroup metrics; build the consolidated review packet and audit sample.
5. Prepare the full-run command/configuration but do not submit it. Human review remains the only approval gate.

## Important constraints

Do not redownload or change either active model revision. Do not use Mistral output, GPT, OpenAI, Codex, Qwen, protected data, or T15/T27/T28/T29 artifacts. Do not interpret this lifecycle timeout as a reason to invoke a model fallback; the permitted primary runtime repair has not yet been exhausted.

## Local commits

The R3 implementation and successive evidence-preserving repairs are committed through `ddc18ce`; the next retry must include the validator guard and GLM backend repair.
