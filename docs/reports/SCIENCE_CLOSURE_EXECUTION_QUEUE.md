# Science-closure execution queue

**Purpose:** operational control record for closing every currently unavailable
science claim before any final supervisor dossier is assembled. This is not a
results document and does not convert a planned task into a completed result.

**Last verified state:** 2026-09-01, Pilot-120 v1 T39 attempt 6 is GPU-gated:
R1 and R2 have valid evidence atlases, R3 is active; T45 is complete locally.

## Non-negotiable rule

A row becomes complete only when its stated terminal artifact exists, is
auditable, and has a control status of `PASS`, `FAIL`, or `NOT_COMPUTED` with the actual
evidence gap. A queued Slurm job, an approved protocol, a green preflight, or a
draft document is never completion evidence. Artifact-specific statuses (for
example, `VERIFY_PASSED`) are diagnostic detail, not a substitute control state.

## Live gate

| Gate | State | Evidence | Consequence |
|---|---|---|---|
| T39 static execution contract | `PASS` for fresh GPU inference | `48620`; `/home-mscluster/mbangie/t28_r5_src/outputs/pilot_120/t39_20260901_6d71aff_gpu/t39_provenance_preflight.json` | The immutable GPU-gated archive binds frozen bytes; no CPU or <90-GiB runtime is eligible. |
| T40 availability audit | `PASS` | `48621`; `/home-mscluster/mbangie/t28_r5_src/outputs/pilot_120/t39_20260901_6d71aff_gpu/t40_interpretation_requirements_audit.json` | Existing Pilot gold cannot support intent/CPC/candidate/resolution/wording/silent-resolution claims. |
| T39 five-replay evidence and final audit | `RUNNING` | GPU preflight `48622`; R1 `48623`--`48626` and R2 `48627`, `48628`, `48630`, `48631` terminal with valid atlases; R3 `48693`--`48696` active | R4/R5 and the terminal audit remain required. Raw file hashes are integrity evidence; the replay-content audit normalises finite numeric latency telemetry only. |

## Closure queue

| Queue ID | Closes | Current state | Prerequisites before completion work | Terminal evidence required | Earliest execution lane |
|---|---|---|---|---|---|
| Q39-A | fresh terminal/cost/safety, ambiguity/capability, operations, slices, all-system disagreements, descriptive all-context ablation, deterministic taxonomy, greedy replay reproducibility | `RUNNING`: R1/R2 valid, R3 active; no pooled result or reproducibility claim | R3-R5 fresh outputs, per-component CUDA/VRAM/node attestation, and one evidence atlas per replica; no CPU/under-memory runtime is eligible | Five `t39_evidence_atlas.json` files plus latency-aware `t39_reproducibility_audit.json` | Serial GPU continuation, then CPU audit |
| Q45 / T45 | historical T31 direct-base cost reconciliation and evidence-only early-output slice/disagreement report | `PASS` (`VERIFY_PASSED`) CPU-only, non-official | Exact historical prediction/policy/source/gold bytes and all eight saved system outputs were recovered without inference | Byte/provenance reconciliation plus no-new-inference slice report; hashes recorded in T45 ticket | Complete; excluded from final scientific claims until the full dossier gate |
| Q41 | interpretation/CPC/candidate exactness; resolution; clarification/rejection target and wording; silent-resolution value; human semantic taxonomy coding | Protocol-approved, **not queued and not complete** | T39 final audit; frozen sidecar schema; two independent blinded annotators; adjudication plan; measurement-output contract | Sidecar source/annotation/decision manifests, agreement/adjudication artifact, field-score artifact, claim-to-gold crosswalk | Human-review and CPU validation after the gate |
| Q42 | single-ambiguity performance | Protocol-approved, **not queued and not complete** | A genuinely new source corpus; licence/source audit; immutable exclusion ledger; double annotation and adjudication; validator proving exactly one unresolved ambiguity instance of exactly one type and no secondary ambiguity | Frozen source/gold/protocol/exclusion manifests, validator result, fixed-system evaluation and support report | Corpus/annotation lane first; cluster inference only after freeze |
| Q43 | separate scene-only, dialogue-only and capability-only effects | Protocol-approved, **not queued and not complete** | T39 final audit; frozen eight-condition `2^3` manifest; byte/token input verifier; paired multiplicity/support analysis plan | Input-byte verifier, condition manifest, paired results artifact, support/multiplicity audit | Cluster after its preflight passes |
| Q44 | narrow family-disjoint held-out-corpus confirmation only | Protocol-approved, **not queued and not complete** | New licensable source; record/paraphrase/scenario-family exclusion audit against Pilot/T42/T41-new-source; double annotation/adjudication; held-out freeze | Licence/source/exclusion/frozen-gold manifests, annotation agreement, fixed-system confirmation artifact | Source and human-review lanes first; cluster only after the freeze |

## Explicit no-skip checklist

- `NOT_COMPUTED` interpretation and wording metrics remain owned by Q41; they
  cannot be inferred from terminal-route accuracy.
- `NOT_COMPUTED` single-ambiguity performance remains owned by Q42; Pilot-120
  has no eligible record and must not be relabelled into a single-ambiguity set.
- `NOT_COMPUTED` isolated scene/dialogue/capability effects remain owned by Q43;
  T39's all-context removal is descriptive only.
- `NOT_COMPUTED` generalisation remains owned by Q44; a broader claim is never
  substituted for the narrow predeclared confirmation analysis.
- T45 closes the historical direct-base cost-provenance question and its
  no-new-inference saved-output slice/disagreement report only; fresh Q39-A
  outputs still do not retroactively prove any other historical claim.
- Human double coding of semantic taxonomy categories remains Q41. T39's two
  deterministic rule implementations are a cross-check, not a human result.

## Transition policy

1. While Q39 is waiting or running, complete only non-claim-bearing
   preparation: schemas, source/licence audits, annotation packets, validators,
   exclusion-ledger tooling, manifest templates and precision calculations. T45
   was an explicit CPU-only no-new-inference reconciliation exception and cannot
   be used in the supervisor dossier outside the final gate.
2. Once Q39's final audit and T40 are terminal, launch Q41 annotation/sidecar
   validation and Q42 corpus construction in parallel.
3. Launch Q43 cluster inference only after its frozen condition/input verifier;
   launch Q44 inference only after family-disjoint source and gold freeze.
4. Assemble the final supervisor dossier only when Q39-Q45 each has a linked
   terminal artifact. Until then, this queue is the authoritative incomplete
   work list.
