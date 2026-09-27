# Experiment coverage and recovery audit

**Checked 2026-09-27 against the tracked repository, dated reports, seven
Pilot-120 ZIPs, and local output folders.** This is the map of work we found;
it is not a claim that every historical run can be reproduced from a clone.
The [four replay guides](README.md) cover selected saved studies. Many earlier
reports describe results whose raw model predictions, weights, or cluster
environment are outside Git. `outputs/` is ignored. A fresh clone therefore
recovers the tracked code, protocols, reports, Pilot-120 source/gold, cases,
and seven ZIPs, **not every local or remote experiment output**.

## Study-by-study map

“Report” means a dated claim-bearing record; “replay” means the tracked
repository has enough saved inputs to run its scorer. A green code test or a
Slurm `COMPLETED` state alone does not establish a scientific result.

| Work | Input / method | Result or status and where to read it | Fresh-clone recovery |
| --- | --- | --- | --- |
| T00–T11 data, contracts, and early foundation | Source datasets and ticket protocols | [T00–T11 reports](../reports/), starting at `ticket_T00_completion_report.md` | Reports/code; original upstream payloads must be obtained from [providers](../DATASETS.md) |
| T12 model/runtime stages | Pinned model and cluster canaries | [T12 completion](../reports/ticket_T12_completion_report.md) and stage reports; implementation/smoke evidence, not Pilot result | Code/reports; model weights, containers, and runtime logs external |
| T13–T15 annotation and protected split | Human guidance and governance | [T13 calibration](../reports/ticket_T13_foundation_and_calibration.md), [T14 tooling](../reports/ticket_T14A_tooling_readiness.md); do not infer a completed independent challenge set | Protocols/reports; verify any protected data separately |
| T16–T24 manager/evaluator foundation | Synthetic fixtures, deterministic seven-system adapters | [Foundation](../reports/ticket_T16_T24_model_independent_foundation.md), [correctness hardening](../reports/ticket_T16_T24_correctness_hardening.md); implementation checks, not official model scores | Code/tests/reports |
| T27–T28 model adaptation and selection | Source dev data, QLoRA, frozen selection policy | [T28 explanation](../reports/T28_OFFICIAL_STATUS_EXPLAINED_20260911.md); early Pilot adapter was provisional and global official selection remained incomplete | Code/reports/contracts; training payloads, weights, full run outputs external |
| T29–T38 early Pilot execution and audits | Pilot-120 plus versioned cluster contracts | Historical [T39/T40 protocol](../reports/T39_T40_Pilot120_science_protocol.md) and [execution log](../reports/T39_T40_EXECUTION_LOG_20260831.md); no single fresh-clone replay guide or complete raw-output archive established | Partial; trace each dated run before quoting it |
| Frozen T39/T40 | Pilot-120, five GPU replicas, availability audit | [Frozen guide](T39_T41_FROZEN.md), [science-closure queue](../reports/SCIENCE_CLOSURE_EXECUTION_QUEUE.md); bounded verified result | Reports and selected frozen evidence in [T41 ZIP](../../research/pilot120/artifacts/pilot120_t41_complete_closure.zip); full historical runtime roots external |
| T41 historical interpretation closure | Pilot sidecar, blind/adjudication evidence | [T41 ZIP](../../research/pilot120/artifacts/pilot120_t41_complete_closure.zip), [Pilot guide](../PILOT120.md) | Frozen package saved; this does **not** close the separately proposed independent human semantic study |
| T45 historical reconciliation | Saved T31 outputs, no new inference | [Closure queue](../reports/SCIENCE_CLOSURE_EXECUTION_QUEUE.md) says CPU reconciliation `VERIFY_PASSED` | Report/code; its local `outputs/t45_*` tree is ignored and not in the seven ZIPs |
| Goal-first v2 R1–R3 and router ablations | Pilot-120, new prompt/router, CPU salvage | [Ablation packet](../reports/GOAL_FIRST_V2_ABLATION_PACKET_20260912.md): goal-first 54/120, degree 59/120, rich 26/120, blind 21/120; 54 includes salvaged rows, harsh sensitivity 51/120 | Report/code; R1–R3 raw pulled outputs under ignored `outputs/cluster_pulls/`, not fully archived in Git |
| Dataset-native follow-on | VAGUE, AmbiK, Indirect Requests, CLARA; weak/mapped labels | [Follow-on status and score table](../reports/GOAL_FIRST_FOLLOWON_STATUS_20260912.md), [native protocol](../protocols/DATASET_NATIVE_EXPLORATORY_EVALUATION_V1.md); exploratory and unpooled | Scorers/reports; upstream data and ignored `outputs/followon_native_scores_20260912/` needed for exact replay |
| Semantic intent / historical blind judging | Pilot-120, two blind judge packets | [Audit](../reports/PILOT120_SEMANTIC_INTENT_PACKAGE_AUDIT_20260902.md) and [intent archive](../../research/pilot120/artifacts/pilot120_intent_evaluation_20260902.zip); original governance boundary remains | Intent and semantic archives saved; inspect archived manifests before citing a score |
| Pilot-120 gold-v2 and risk review | Pilot annotation source, adjudication worksheets | [Gold-v2 ZIP](../../research/pilot120/artifacts/gold_v2_officialization_20260914.zip) and tracked [annotation directory](../../data/annotations/pilot_120_v1/) | Package saved; different gold versions must not be silently mixed |
| T0.7 matched baseline | Pilot-120, six systems, two-judge intent | [Runnable replay](T07_MATCHED_BASELINE.md) and [final ZIP](../../research/pilot120/artifacts/t07_matched_baseline_completion_20260927_FINAL.zip) | Saved predictions and judgments rescore from clone; fresh GPU emit needs external model/adapter/container |
| One-turn recovery | Pilot-120 gold-EXECUTE clarification subset | [Runnable replay](ONE_TURN_RECOVERY.md) and [full-analysis ZIP](../../research/pilot120/artifacts/p120_full_analysis_20260923.zip) | Saved inference rescores from clone; original cluster stack external |
| Existing temperature streams | Pilot-120, five temperatures at seed 0 | [Runnable replay](TEMPERATURE_EXPLORATION.md); exploratory single-seed data in full-analysis ZIP | Saved streams rescore from clone |
| ABLE IX five-seed temperature study | Pilot-120, five planned temperatures/seeds | [Cluster launcher](../../cluster/pilot120_t03_gf_ablation_20260923/) and [Pilot guide](../PILOT120.md) have the **dated** 2026-09-27 running/dependency snapshot | No verified final five-seed archive in Git; live SSH status could not be refreshed in this audit |
| T42/T43/T44 proposed independent studies | New corpus, factorial context, family-disjoint confirmation | [Closure queue](../reports/SCIENCE_CLOSURE_EXECUTION_QUEUE.md) and [T43 protocol](../protocols/T43_FACTORIAL_CONTEXT_MANIFEST_PROTOCOL.md): study outcomes `NOT_COMPUTED` in the dated record | Readiness/protocol only; do not present as results |

Other versioned cluster families—[AmbiK](../../cluster/ambik/),
[VAGUE](../../cluster/vague/), [native context](../../cluster/native_context/),
[Qwen natives](../../cluster/qwen_natives_20260914/),
[capability debate](../../cluster/pilot120_capability_debate_20260918/),
[latency](../../cluster/pilot120_latency_small_20260918/),
[goal-first](../../cluster/goal_first_v2/), and
[final close](../../cluster/final_close_20260913/)—have launchers or reports.
They are not individually certified as fresh-clone runnable or scientifically
complete by the four replay guides. Inspect their own manifests, logs, row
counts, and rights before using a result.

## What remains outside the repository

1. **Original upstream datasets:** follow [DATASETS.md](../DATASETS.md).
   Historical hashes and provider pins matter; a newer release is not an exact
   replacement. Redistribution rights remain unresolved for several sources.
2. **Model assets and cluster runtime:** Qwen/Gemma/GLM checkpoints, the T28
   adapter, container images, caches, SSH credentials, and Slurm account are
   not recovered by Git. Follow [setup](../SETUP_AND_RECOVERY.md).
3. **Unpromoted generated outputs:** ignored local `outputs/` held 3,325 files
   totalling 9,321,933,230 bytes at this audit; 8,557 MiB was under
   `outputs/t12_cluster_jobs/`. It contains native,
   goal-first, T28, T45, and other results that are not all inside the seven
   tracked ZIPs. The older local evidence-package and transfer archives are
   also outside the latest Git tree. Do not delete the old machine assuming
   those bytes have been backed up by the GitHub repo.
4. **ABLE IX final status:** a read-only SSH attempt on 2026-09-27 ended with
   the connection closed before a usable `squeue`/`sacct` response. Its final
   five-seed output and artifact integrity remain unverified here.

The next preservation task is a hash-and-contents inventory of the ignored
local/remote result roots, then a reviewed archive for each unique scientific
run that must survive deletion of this machine. This audit makes the gap
explicit; it does not mark that preservation complete.
