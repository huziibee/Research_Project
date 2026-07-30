# A02-A04-R3 handover

## Current status

`INCOMPLETE — waiting for one authorised lifecycle/runtime repair.`

The pilot is not yet eligible for `PASS_TO_HUMAN_REVIEW`. No full annotation job was submitted, no protected data was accessed, and no T15/T27/T28/T29 files were modified.

## Latest execution

Latest job: `23146`, submitted to `mscluster110` in `biggpu` with exclusive 110G/no-GRES allocation.

Run directory:

`/home-mscluster/mbangie/dual-llm-a02-r1/data/dual_llm_benchmark_v1/runs/a02-a04-r3-pilot-23146-20260730`

Observed phase evidence:

- CPU/import preflight passed offline.
- Gemma 4 canary passed and the 40-record Gemma annotation phase completed without validator errors in the job log.
- Gemma cleanup evidence was written.
- GLM resolved to `Glm4MoeLiteForCausalLM` and began loading its 48 shards.
- GLM reached shard `21/48`; the lifecycle readiness window expired before `/v1/models` became ready.
- Cleanup then failed at the current 30-second `proc.wait()` timeout. This is a lifecycle timeout, not evidence of GLM model incompatibility.
- No GLM annotation, agreement metrics, or review packet exists yet.

The GLM server log contains the preserved startup evidence. Job stdout/stderr are the authoritative phase logs in the run directory above.

## Frozen decisions and evidence

- Active pair: `annotator_a_gemma4` / `google/gemma-4-26B-A4B-it` revision `4d7ae4984b7db7de8f8457170b3f1a419ee76d52`; `annotator_b_glm` / `zai-org/GLM-4.7-Flash` revision `7dd20894a642a0aa287e9827cb1a1f7f91386b67`.
- Pilot: 40 records; hash `81d56440801c24a68032e3512dc7c6ca8c4fbd2317bdf56a78cf0d36172e6de1`.
- Gemma download job `23090` completed successfully. Its resolved manifest checksum and recorded key-file hashes matched.
- Mistral jobs `23083` and `23087` remain historical BLOCKED evidence and were not reused as annotation data.
- Earlier R3 allocation guards `23102` and `23111` correctly released unsafe busy-GPU allocations before model load.
- Schema-invalid Gemma attempts from `23113`, `23141`, `23143`, and `23144` remain preserved; no invalid output was accepted.

## Next steps

1. Repair `scripts/annotation/server_lifecycle.py` only within the authorised lifecycle/runtime boundary:
   - increase model readiness timeout from 360 seconds to at least 900 seconds for the 48-shard GLM load;
   - on readiness failure, send TERM, wait up to 120 seconds, then send KILL and verify process exit;
   - record readiness duration and cleanup duration in evidence.
2. Run the focused lifecycle/schema tests and commit the repair.
3. Resubmit the unchanged frozen pilot on verified `mscluster110` when the node is available.
4. Confirm Gemma canary, Gemma 40-record outputs, cleanup, then GLM canary and cleanup.
5. Complete GLM’s 40 records with raw attempts, parsed outputs, and technical retry history.
6. Reconcile exactly 80 final statuses; calculate agreement/subgroup metrics; build the consolidated review packet and audit sample.
7. Prepare the full-run command/configuration but do not submit it. Human review remains the only approval gate.

## Important constraints

Do not redownload or change either active model revision. Do not use Mistral output, GPT, OpenAI, Codex, Qwen, protected data, or T15/T27/T28/T29 artifacts. Do not interpret this lifecycle timeout as a reason to invoke a model fallback; the permitted primary runtime repair has not yet been exhausted.

## Local commits

The R3 implementation and successive evidence-preserving repairs are committed through `40c9b96`; the next lifecycle repair should be a new focused commit.
